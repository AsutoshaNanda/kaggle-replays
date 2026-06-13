"""Leaderboard sync worker: fetch → store snapshot → resolve top-10% episodes.

Provides daily-sync and historical-backfill orchestration plus a midnight-UTC
scheduler loop (pure asyncio, no new dependencies). The top-10% cutoff for a
snapshot of ``N`` teams is ``ceil(N * 0.10)`` ranks.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..kaggle_service import fetch_leaderboard, get_api_session, list_episodes_checked
from ..logging_config import get_logger
from ..models import (
    Competition,
    LeaderboardEntry,
    LeaderboardSnapshot,
    Submission,
    TopPerformerEpisode,
)
from ..session_manager import get_session_manager

_log = get_logger("backend.leaderboard_worker")


def _top10_cutoff(total_teams: int) -> int:
    """Return the top-10% rank cutoff = ceil(total_teams * 0.10) (min 1)."""
    return max(1, math.ceil(total_teams * 0.10)) if total_teams else 0


async def fetch_leaderboard_entries(page, tokens, competition_kaggle_id) -> list[dict]:
    """Fetch and normalize leaderboard rows for a competition.

    Parses the confirmed ``GetLeaderboard`` response: a ``publicLeaderboard``
    list (rank/score/submission per team) joined to a ``teams`` list (team
    names) by ``teamId``.

    Args:
        page: Authenticated Playwright ``Page``.
        tokens: ``{"xsrf", "build_hash"}``.
        competition_kaggle_id: The numeric Kaggle competition ID.

    Returns:
        A list of ``{team_id, team_name, rank, score, best_submission_id}`` dicts
        ordered by rank ascending. Empty if the API call fails.
    """
    raw = await fetch_leaderboard(page, tokens, competition_kaggle_id)
    text = raw.get("text") if isinstance(raw, dict) else None
    if not text:
        return []
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []

    rows = data.get("publicLeaderboard") or []
    names = {str(t.get("teamId")): t.get("teamName") for t in data.get("teams", [])}
    normalized = []
    for i, row in enumerate(rows, start=1):
        team_id = str(row.get("teamId") or i)
        normalized.append(
            {
                "team_id": team_id,
                "team_name": names.get(team_id),
                "rank": int(row.get("rank") or i),
                "score": _to_float(row.get("displayScore")),
                "best_submission_id": _opt_str(row.get("submissionId")),
                "medal": _opt_str(row.get("medal")),
            }
        )
    normalized.sort(key=lambda r: r["rank"])
    return normalized


async def store_snapshot(
    db: AsyncSession, competition_id: int, snapshot_date: dt.date, entries: list[dict], raw_payload: dict | None = None
) -> LeaderboardSnapshot:
    """Persist a snapshot + entries idempotently for one competition/day.

    Re-running for the same ``(competition_id, snapshot_date)`` replaces the prior
    snapshot's entries rather than duplicating them.

    Returns:
        The stored :class:`LeaderboardSnapshot`.
    """
    total_teams = len(entries)
    cutoff = _top10_cutoff(total_teams)

    snapshot = (
        await db.execute(
            select(LeaderboardSnapshot).where(
                LeaderboardSnapshot.competition_id == competition_id,
                LeaderboardSnapshot.snapshot_date == snapshot_date,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = LeaderboardSnapshot(competition_id=competition_id, snapshot_date=snapshot_date)
        db.add(snapshot)
    snapshot.total_teams = total_teams
    snapshot.top10_cutoff_rank = cutoff
    snapshot.raw_payload = raw_payload
    snapshot.fetched_at = dt.datetime.now(dt.timezone.utc)
    await db.flush()

    # Replace existing entries for idempotency.
    for old in (
        await db.execute(select(LeaderboardEntry).where(LeaderboardEntry.snapshot_id == snapshot.id))
    ).scalars().all():
        await db.delete(old)
    await db.flush()

    for row in entries:
        db.add(
            LeaderboardEntry(
                snapshot_id=snapshot.id,
                team_id=row["team_id"],
                team_name=row.get("team_name"),
                rank=row["rank"],
                score=row.get("score"),
                is_top_10_percent=row["rank"] <= cutoff,
                best_submission_id=row.get("best_submission_id"),
            )
        )
    await db.commit()
    _log.info(
        "leaderboard.snapshot_stored",
        competition_id=competition_id,
        date=str(snapshot_date),
        total_teams=total_teams,
        cutoff=cutoff,
    )
    return snapshot


# How many top performers to resolve replay episode IDs for. The top 10% can be
# hundreds of teams; resolving all of them would fire hundreds of ListEpisodes
# calls and trip Kaggle's rate limit. We only need the best few, so this is
# bounded and the calls below are paced.
TOP_PERFORMER_EPISODE_LIMIT = 20
_EPISODE_DELAY = 0.4  # seconds between sequential ListEpisodes calls


async def resolve_top_episodes(page, tokens, db: AsyncSession, snapshot_id: int) -> int:
    """Resolve + store replay episode IDs for the TOP-N performers in a snapshot.

    This is what makes the "Top 10% Replays" page useful: each top performer gets
    their actual replay episode IDs (not just a name). Bounded to the best
    :data:`TOP_PERFORMER_EPISODE_LIMIT` ranks and PACED with a short delay between
    calls, stopping on the first error/429 (a later sync resumes) so it never
    storms Kaggle. Skips entries already resolved. Returns episode links added.
    """
    entries = (
        await db.execute(
            select(LeaderboardEntry)
            .where(
                LeaderboardEntry.snapshot_id == snapshot_id,
                LeaderboardEntry.is_top_10_percent.is_(True),
            )
            .order_by(LeaderboardEntry.rank.asc())
            .limit(TOP_PERFORMER_EPISODE_LIMIT)
        )
    ).scalars().all()

    added = 0
    for entry in entries:
        if not entry.best_submission_id:
            continue
        already = (
            await db.execute(
                select(TopPerformerEpisode).where(TopPerformerEpisode.entry_id == entry.id)
            )
        ).first()
        if already:
            continue
        episodes, error = await list_episodes_checked(page, tokens, entry.best_submission_id)
        if error is not None:
            _log.warning("leaderboard.episodes_stopped", snapshot_id=snapshot_id, reason=error)
            break  # likely 429 / expired session — stop; a later sync resumes
        for ep in episodes:
            db.add(TopPerformerEpisode(entry_id=entry.id, episode_id=str(ep["id"])))
            added += 1
        await db.commit()
        await asyncio.sleep(_EPISODE_DELAY)
    return added


async def run_daily_sync(competition_id: int, db_factory, session_manager) -> None:
    """Orchestrate fetch → store → resolve for ``competition_id`` for today (UTC)."""
    today = dt.datetime.now(dt.timezone.utc).date()
    async with db_factory() as db:
        comp = (await db.execute(select(Competition).where(Competition.id == competition_id))).scalar_one_or_none()
        if comp is None:
            return
        # Shared persistent page (session_manager param kept for signature
        # compatibility; get_api_session uses the same singleton internally).
        page, tokens = await get_api_session(comp.user_id)
        entries = await fetch_leaderboard_entries(page, tokens, comp.kaggle_id)
        if not entries:
            _log.warning("leaderboard.empty", competition_id=competition_id)
            return
        snapshot = await store_snapshot(db, competition_id, today, entries)
        await resolve_top_episodes(page, tokens, db, snapshot.id)


async def backfill(competition_id: int, start_date: dt.date, end_date: dt.date, db_factory, session_manager) -> None:
    """Reconstruct historical snapshots from cached submission timestamps.

    For each date in range, ranks teams by their best score among submissions
    whose ``fetched_at <= date`` and stores a synthetic snapshot. Uses only data
    already in the ``submissions`` table (no Kaggle calls).
    """
    async with db_factory() as db:
        comp = (await db.execute(select(Competition).where(Competition.id == competition_id))).scalar_one_or_none()
        if comp is None:
            return
        subs = (
            await db.execute(select(Submission).where(Submission.competition_id == competition_id))
        ).scalars().all()

        day = start_date
        while day <= end_date:
            cutoff_dt = dt.datetime.combine(day, dt.time.max, tzinfo=dt.timezone.utc)
            eligible = [s for s in subs if s.fetched_at and _aware(s.fetched_at) <= cutoff_dt and s.score is not None]
            best_by_team: dict[str, Submission] = {}
            for s in eligible:
                key = str(s.user_id)
                if key not in best_by_team or (s.score or 0) > (best_by_team[key].score or 0):
                    best_by_team[key] = s
            ranked = sorted(best_by_team.values(), key=lambda s: s.score or 0, reverse=True)
            entries = [
                {
                    "team_id": str(s.user_id),
                    "team_name": None,
                    "rank": i,
                    "score": s.score,
                    "best_submission_id": s.kaggle_id,
                }
                for i, s in enumerate(ranked, start=1)
            ]
            if entries:
                await store_snapshot(db, competition_id, day, entries)
            day += dt.timedelta(days=1)
    _log.info("leaderboard.backfill_done", competition_id=competition_id)


async def daily_scheduler_loop(db_factory, session_manager, stop_event: asyncio.Event) -> None:
    """Run :func:`run_daily_sync` for all active competitions at each midnight UTC.

    A pure-asyncio loop: sleeps until the next UTC midnight, then syncs every
    distinct active competition. Exits promptly when ``stop_event`` is set.
    """
    # Lazy import avoids any import-time cycle (kaggle_data_service is a service,
    # this is a task module imported by main at startup).
    from ..services import kaggle_data_service

    _log.info("leaderboard.scheduler_started")
    while not stop_event.is_set():
        delay = _seconds_until_midnight_utc()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            return  # stop_event was set during the wait
        except asyncio.TimeoutError:
            pass  # reached midnight
        async with db_factory() as db:
            comps = (await db.execute(select(Competition))).scalars().all()
        for comp in comps:
            # 1) Leaderboard snapshot (real standings → forward-looking history).
            try:
                await run_daily_sync(comp.id, db_factory, session_manager)
            except Exception as exc:  # noqa: BLE001
                _log.error("leaderboard.sync_error", competition_id=comp.id, error=str(exc))
            # 2) Submissions + episode IDs + skill-rating scores into the DB cache,
            #    so the UI serves everything from the DB and never hits Kaggle on a
            #    page view (rate-limit-safe; resolve_episode_data is paced).
            try:
                async with db_factory() as db:
                    await kaggle_data_service.sync_submissions(db, comp.user_id, comp, force=True)
                await kaggle_data_service.resolve_episode_data(comp.user_id, comp.id, force=True)
            except Exception as exc:  # noqa: BLE001
                _log.error("submissions.sync_error", competition_id=comp.id, error=str(exc))


def _seconds_until_midnight_utc() -> float:
    """Return seconds remaining until the next 00:00 UTC."""
    now = dt.datetime.now(dt.timezone.utc)
    tomorrow = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1.0, (tomorrow - now).total_seconds())


def _to_float(value) -> float | None:
    """Best-effort float parse, else ``None``."""
    try:
        return float(str(value).replace(",", "")) if value not in (None, "", "-") else None
    except (ValueError, TypeError):
        return None


def _opt_str(value) -> str | None:
    """Return ``str(value)`` or ``None``."""
    return str(value) if value not in (None, "") else None


def _aware(value: dt.datetime) -> dt.datetime:
    """Coerce a naive datetime to UTC-aware."""
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
