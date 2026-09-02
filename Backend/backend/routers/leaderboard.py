"""Leaderboard endpoints: daily history, per-day top-100 replays, sync trigger.

All endpoints are JWT-protected and validate that the competition belongs to the
requesting user. ``history`` returns an empty ``days`` list (never 500) when no
snapshots exist yet.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit
from ..database import AsyncSessionLocal
from ..dependencies import get_current_user, get_db, limiter
from ..models import (
    Competition,
    ExportJob,
    LeaderboardEntry,
    LeaderboardSnapshot,
    TopPerformerEpisode,
    User,
)
from ..kaggle_service import open_page
from ..schemas import (
    LeaderboardCurrentResponse,
    LeaderboardDay,
    LeaderboardHistoryResponse,
    LeaderboardReplaysResponse,
    LeaderboardRow,
    LeaderboardSyncRequest,
    LeaderboardSyncResponse,
    Top100ExportCapabilities,
    Top100ExportJob,
    Top100ExportLatestResponse,
    Top100ExportRequest,
    TopPerformer,
)
from ..session_manager import get_session_manager
from ..tasks import export_worker, leaderboard_worker
from ..utils.cache import episode_cache

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


async def _owned_competition(db: AsyncSession, user_id: int, competition_id: int) -> Competition:
    """Return the competition (resolved by its KAGGLE id) if owned by ``user_id``.

    The frontend routes always carry the Kaggle numeric competition id (the same
    value the ``/competitions/{kaggle_id}/submissions`` endpoint uses), so we
    resolve by ``kaggle_id`` + ``user_id`` here — NOT the internal PK. All
    snapshot/worker calls below then use the returned ``comp.id`` (the FK target).
    """
    comp = (
        await db.execute(
            select(Competition).where(
                Competition.kaggle_id == competition_id, Competition.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if comp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competition not found")
    return comp


async def _recently_synced(db: AsyncSession, competition: Competition) -> bool:
    """True if today's snapshot for this competition was captured very recently.

    Used to debounce rapid "Sync now" clicks so we don't stack background jobs.
    """
    today = dt.datetime.now(dt.timezone.utc).date()
    snapshot_date = min(today, _deadline_date(competition)) if competition.deadline else today
    snap = (
        await db.execute(
            select(LeaderboardSnapshot).where(
                LeaderboardSnapshot.competition_id == competition.id,
                LeaderboardSnapshot.snapshot_date == snapshot_date,
            )
        )
    ).scalar_one_or_none()
    if snap is None or snap.fetched_at is None:
        return False
    fetched = snap.fetched_at if snap.fetched_at.tzinfo else snap.fetched_at.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - fetched).total_seconds() < _SYNC_DEBOUNCE_SECONDS


async def _has_unresolved_top100(db: AsyncSession, competition: Competition) -> bool:
    deadline = _deadline_date(competition) if competition.deadline else dt.datetime.now(dt.timezone.utc).date()
    unresolved = (
        await db.execute(
            select(LeaderboardEntry.id)
            .join(LeaderboardSnapshot, LeaderboardEntry.snapshot_id == LeaderboardSnapshot.id)
            .where(
                LeaderboardSnapshot.competition_id == competition.id,
                LeaderboardSnapshot.snapshot_date <= deadline,
                LeaderboardEntry.rank <= 100,
                LeaderboardEntry.episodes_resolved_at.is_(None),
            )
            .limit(1)
        )
    ).first()
    return unresolved is not None


async def _top_performers(db: AsyncSession, snapshot_id: int) -> list[TopPerformer]:
    """Build the top-100 performer DTOs with episode counts for a snapshot."""
    entries = (
        await db.execute(
            select(LeaderboardEntry)
            .where(LeaderboardEntry.snapshot_id == snapshot_id, LeaderboardEntry.rank <= 100)
            .order_by(LeaderboardEntry.rank.asc())
            .limit(100)
        )
    ).scalars().all()
    ids_by_entry: dict[int, list[str]] = {entry.id: [] for entry in entries}
    if ids_by_entry:
        episode_rows = (
            await db.execute(
                select(TopPerformerEpisode.entry_id, TopPerformerEpisode.episode_id).where(
                    TopPerformerEpisode.entry_id.in_(ids_by_entry)
                )
            )
        ).all()
        for entry_id, episode_id in episode_rows:
            ids_by_entry[entry_id].append(episode_id)

    performers = []
    for entry in entries:
        episode_ids = ids_by_entry[entry.id]
        performers.append(
            TopPerformer(
                team_id=entry.team_id,
                team_name=entry.team_name,
                rank=entry.rank,
                score=entry.score,
                best_submission_id=entry.best_submission_id,
                episode_ids=episode_ids,
                episode_count=len(episode_ids),
                episodes_resolved=entry.episodes_resolved_at is not None or bool(episode_ids),
            )
        )
    return performers


@router.get("/{competition_id}/history", response_model=LeaderboardHistoryResponse)
@limiter.limit("30/minute")
async def history(
    request: Request,
    competition_id: int,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardHistoryResponse:
    """Return daily snapshots (optionally date-bounded); empty list if none."""
    comp = await _owned_competition(db, current_user.id, competition_id)
    deadline = _deadline_date(comp) if comp.deadline else None
    if deadline and (to_date is None or to_date > deadline):
        to_date = deadline
    query = select(LeaderboardSnapshot).where(LeaderboardSnapshot.competition_id == comp.id)
    if from_date:
        query = query.where(LeaderboardSnapshot.snapshot_date >= from_date)
    if to_date:
        query = query.where(LeaderboardSnapshot.snapshot_date <= to_date)
    snapshots = (await db.execute(query.order_by(LeaderboardSnapshot.snapshot_date.asc()))).scalars().all()

    days = [
        LeaderboardDay(
            date=snap.snapshot_date,
            total_teams=snap.total_teams,
            top10_cutoff_rank=snap.top10_cutoff_rank,
            top_performers=await _top_performers(db, snap.id),
        )
        for snap in snapshots
    ]
    last_synced = max((s.fetched_at for s in snapshots if s.fetched_at), default=None)
    return LeaderboardHistoryResponse(days=days, last_synced_at=last_synced)


@router.get("/{competition_id}/current", response_model=LeaderboardCurrentResponse)
@limiter.limit("20/minute")
async def current(
    request: Request,
    competition_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardCurrentResponse:
    """Return the competition's CURRENT public leaderboard (cached ~3 min)."""
    import math

    comp = await _owned_competition(db, current_user.id, competition_id)
    cache_key = f"lb_current:{comp.kaggle_id}"
    rows = await episode_cache.get(cache_key)
    if rows is None:
        context = await get_session_manager().get_context(current_user.id)
        page, tokens = await open_page(context)
        try:
            rows = await leaderboard_worker.fetch_leaderboard_entries(page, tokens, comp.kaggle_id)
        finally:
            await page.close()
        if rows:
            await episode_cache.set(cache_key, rows, ttl=180)
    total = len(rows)
    cutoff = max(1, math.ceil(total * 0.10)) if total else 0
    entries = [LeaderboardRow(**r) for r in rows]
    return LeaderboardCurrentResponse(
        total_teams=total,
        top10_cutoff_rank=cutoff,
        entries=entries,
        last_synced_at=dt.datetime.now(dt.timezone.utc),
    )


@router.get("/{competition_id}/date/{date}/replays", response_model=LeaderboardReplaysResponse)
@limiter.limit("30/minute")
async def date_replays(
    request: Request,
    competition_id: int,
    date: dt.date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardReplaysResponse:
    """Return the top-100 teams and their episode IDs for a specific date."""
    comp = await _owned_competition(db, current_user.id, competition_id)
    if comp.deadline and date > _deadline_date(comp):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Date is after competition end")
    snapshot = (
        await db.execute(
            select(LeaderboardSnapshot).where(
                LeaderboardSnapshot.competition_id == comp.id,
                LeaderboardSnapshot.snapshot_date == date,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No snapshot for that date")
    return LeaderboardReplaysResponse(
        date=snapshot.snapshot_date,
        total_teams=snapshot.total_teams,
        top10_cutoff_rank=snapshot.top10_cutoff_rank,
        top_performers=await _top_performers(db, snapshot.id),
    )


# A non-backfill sync is heavy (leaderboard fetch + paced episode resolution that
# aborts on Kaggle's own 429), so this app-level cap is generous — it exists only
# to stop a stuck loop, not to ration legitimate re-syncs (the prior 4/hour blocked
# real use after a few clicks). Rapid re-clicks are additionally absorbed by the
# debounce below.
_SYNC_DEBOUNCE_SECONDS = 90


@router.post("/{competition_id}/sync", response_model=LeaderboardSyncResponse)
@limiter.limit("30/minute")
async def sync(
    request: Request,
    competition_id: int,
    body: LeaderboardSyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardSyncResponse:
    """Trigger a daily sync or a historical backfill as a background task."""
    comp = await _owned_competition(db, current_user.id, competition_id)
    manager = get_session_manager()

    if body.backfill:
        start = body.from_date or (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=7))
        end = body.to_date or dt.datetime.now(dt.timezone.utc).date()
        if comp.deadline:
            end = min(end, _deadline_date(comp))
        asyncio.create_task(
            leaderboard_worker.backfill(comp.id, start, end, AsyncSessionLocal, manager)
        )
        mode, message = "backfill", f"Backfill scheduled from {start} to {end}"
    else:
        if leaderboard_worker.sync_is_running(comp.id):
            return LeaderboardSyncResponse(
                status="skipped",
                mode="sync",
                message="Top 100 sync is already running. Refresh to see progress.",
            )
        # Debounce: if today's snapshot was captured moments ago, skip spawning a
        # duplicate background job (prevents accidental rapid re-clicks from
        # stacking work or burning the rate limit).
        recent = await _recently_synced(db, comp)
        if recent and not await _has_unresolved_top100(db, comp):
            return LeaderboardSyncResponse(
                status="skipped", mode="sync", message="Already synced moments ago — refresh to see results."
            )
        asyncio.create_task(
            leaderboard_worker.run_daily_sync(comp.id, AsyncSessionLocal, manager)
        )
        mode, message = "sync", "Daily sync scheduled"

    await write_audit(
        db, action="leaderboard.sync", ip_address=request.state.client_ip,
        status="success", user_id=current_user.id, resource_type="competition", resource_id=str(comp.id),
        detail={"mode": mode},
    )
    return LeaderboardSyncResponse(status="scheduled", mode=mode, message=message)


def _deadline_date(comp: Competition) -> dt.date:
    deadline = comp.deadline
    if deadline is None:
        return dt.datetime.now(dt.timezone.utc).date()
    aware = deadline if deadline.tzinfo else deadline.replace(tzinfo=dt.timezone.utc)
    return aware.date()


@router.get("/{competition_id}/export-capabilities", response_model=Top100ExportCapabilities)
async def export_capabilities(
    competition_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Top100ExportCapabilities:
    await _owned_competition(db, current_user.id, competition_id)
    drive_ready = export_worker.drive_ready()
    return Top100ExportCapabilities(
        kaggle_dataset_ready=export_worker.kaggle_ready(),
        google_drive_ready=drive_ready,
        google_drive_message=(
            "Google Drive is ready"
            if drive_ready
            else "Install rclone, run rclone config, and set GOOGLE_DRIVE_DESTINATION"
        ),
    )


@router.post("/{competition_id}/exports", response_model=Top100ExportJob)
@limiter.limit("5/hour")
async def start_export(
    request: Request,
    competition_id: int,
    body: Top100ExportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Top100ExportJob:
    comp = await _owned_competition(db, current_user.id, competition_id)
    if body.target == "google_drive" and not export_worker.drive_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Drive needs rclone, rclone config, and GOOGLE_DRIVE_DESTINATION",
        )
    if body.target == "kaggle_dataset" and not export_worker.kaggle_ready():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Kaggle CLI is not installed")
    job = await export_worker.create_export_job(current_user.id, comp.id, body.target, body.public)
    await write_audit(
        db,
        action="leaderboard.export",
        ip_address=request.state.client_ip,
        status="success",
        user_id=current_user.id,
        resource_type="export_job",
        resource_id=job.job_uuid,
        detail={"target": body.target, "public": body.public},
    )
    return Top100ExportJob(**export_worker.export_view(job))


@router.get("/{competition_id}/exports/latest", response_model=Top100ExportLatestResponse)
async def latest_export(
    competition_id: int,
    target: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Top100ExportLatestResponse:
    if target not in ("kaggle_dataset", "google_drive"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid export target")
    comp = await _owned_competition(db, current_user.id, competition_id)
    job = (
        await db.execute(
            select(ExportJob)
            .where(
                ExportJob.user_id == current_user.id,
                ExportJob.competition_id == comp.id,
                ExportJob.target == target,
            )
            .order_by(ExportJob.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return Top100ExportLatestResponse(
        job=Top100ExportJob(**export_worker.export_view(job)) if job else None
    )
