"""Leaderboard endpoints: daily history, per-day top-10% replays, sync trigger.

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
    TopPerformer,
)
from ..session_manager import get_session_manager
from ..tasks import leaderboard_worker
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


async def _recently_synced(db: AsyncSession, competition_id: int) -> bool:
    """True if today's snapshot for this competition was captured very recently.

    Used to debounce rapid "Sync now" clicks so we don't stack background jobs.
    """
    today = dt.datetime.now(dt.timezone.utc).date()
    snap = (
        await db.execute(
            select(LeaderboardSnapshot).where(
                LeaderboardSnapshot.competition_id == competition_id,
                LeaderboardSnapshot.snapshot_date == today,
            )
        )
    ).scalar_one_or_none()
    if snap is None or snap.fetched_at is None:
        return False
    fetched = snap.fetched_at if snap.fetched_at.tzinfo else snap.fetched_at.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - fetched).total_seconds() < _SYNC_DEBOUNCE_SECONDS


async def _top_performers(db: AsyncSession, snapshot_id: int) -> list[TopPerformer]:
    """Build the top-10% performer DTOs (with episode IDs) for a snapshot."""
    entries = (
        await db.execute(
            select(LeaderboardEntry)
            .where(LeaderboardEntry.snapshot_id == snapshot_id, LeaderboardEntry.is_top_10_percent.is_(True))
            .order_by(LeaderboardEntry.rank.asc())
            .limit(50)  # the page shows the best performers; keep the payload small
        )
    ).scalars().all()
    performers = []
    for entry in entries:
        episode_ids = (
            await db.execute(
                select(TopPerformerEpisode.episode_id).where(TopPerformerEpisode.entry_id == entry.id)
            )
        ).scalars().all()
        performers.append(
            TopPerformer(
                team_id=entry.team_id,
                team_name=entry.team_name,
                rank=entry.rank,
                score=entry.score,
                best_submission_id=entry.best_submission_id,
                episode_ids=list(episode_ids),
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
    """Return the top-10% teams + their episode IDs for a specific date."""
    comp = await _owned_competition(db, current_user.id, competition_id)
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
@limiter.limit("1/minute")
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
        asyncio.create_task(
            leaderboard_worker.backfill(comp.id, start, end, AsyncSessionLocal, manager)
        )
        mode, message = "backfill", f"Backfill scheduled from {start} to {end}"
    else:
        # Debounce: if today's snapshot was captured moments ago, skip spawning a
        # duplicate background job (prevents accidental rapid re-clicks from
        # stacking work or burning the rate limit).
        recent = await _recently_synced(db, comp.id)
        if recent:
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
