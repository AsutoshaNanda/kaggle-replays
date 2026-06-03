"""Service: fetch Kaggle competitions/submissions/episodes and cache in MySQL.

Wraps the session manager + ``kaggle_service`` bridge and persists results to the
``competitions`` / ``submissions`` tables so ownership can be validated and
recent results served from cache.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..kaggle_service import (
    fetch_submission_episode_data,
    list_competitions,
    list_submissions,
    open_page,
)


class UpstreamRateLimited(Exception):
    """Raised when Kaggle's API rate-limits us (so routers can return 429)."""

    def __init__(self, message: str, retry_after: int = 60) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after
from ..models import Competition, Submission
from ..session_manager import get_session_manager

_CACHE_TTL = dt.timedelta(minutes=5)
# Submissions + episode lists are served from the DB cache for this long before a
# refresh is allowed (rate-limit-safe). Refreshes come from the daily scheduler or
# an explicit "Sync now"; normal page views never re-hit Kaggle within the window.
_DATA_TTL = dt.timedelta(hours=24)


async def sync_competitions(db: AsyncSession, user_id: int) -> list[Competition]:
    """Fetch the user's competitions from Kaggle and upsert them.

    Returns:
        The user's cached :class:`Competition` rows after upsert.
    """
    context = await get_session_manager().get_context(user_id)
    page, tokens = await open_page(context)
    try:
        data = await list_competitions(page, tokens)
    finally:
        await page.close()

    teams = {t["competitionId"]: t for t in data.get("userTeams", [])}
    for comp in data.get("competitions", []):
        kaggle_id = comp["id"]
        team = teams.get(kaggle_id)
        existing = (
            await db.execute(
                select(Competition).where(Competition.kaggle_id == kaggle_id, Competition.user_id == user_id)
            )
        ).scalar_one_or_none()
        deadline = _parse_dt(comp.get("deadline"))
        enabled = _parse_dt(comp.get("enabledDate"))
        category = comp.get("category") or comp.get("hostSegment")
        is_sim = bool(comp.get("requireSimulations") or comp.get("isSimulation"))
        if existing is None:
            db.add(
                Competition(
                    kaggle_id=kaggle_id,
                    user_id=user_id,
                    title=comp.get("title", ""),
                    slug=comp.get("competitionName", ""),
                    team_id=str(team["id"]) if team else None,
                    deadline=deadline,
                    enabled_date=enabled,
                    category=category,
                    is_simulation=is_sim,
                )
            )
        else:
            existing.title = comp.get("title", existing.title)
            existing.slug = comp.get("competitionName", existing.slug)
            existing.team_id = str(team["id"]) if team else existing.team_id
            if deadline is not None:
                existing.deadline = deadline
            if enabled is not None:
                existing.enabled_date = enabled
            if category is not None:
                existing.category = category
            existing.is_simulation = is_sim
            existing.fetched_at = dt.datetime.now(dt.timezone.utc)
    await db.commit()
    return (
        await db.execute(select(Competition).where(Competition.user_id == user_id))
    ).scalars().all()


def filter_competitions_by_tab(comps: list[Competition], tab: str) -> list[Competition]:
    """Filter competitions for the UI tab: ``completed`` (past deadline) vs the
    rest. ``entered``/``all`` return everything (the cached list is already the
    user's entered competitions). Unknown deadlines are treated as active."""
    if tab != "completed":
        return list(comps)
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for c in comps:
        if c.deadline is not None and _aware(c.deadline) < now:
            out.append(c)
    return out


def _parse_dt(value) -> dt.datetime | None:
    """Parse a Kaggle ISO-ish datetime string into a naive UTC datetime."""
    if not value or not isinstance(value, str):
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(cleaned)
        return parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


async def get_competitions_cached(db: AsyncSession, user_id: int) -> list[Competition]:
    """Return cached competitions if fresh (<5 min), else re-sync from Kaggle."""
    rows = (await db.execute(select(Competition).where(Competition.user_id == user_id))).scalars().all()
    if rows:
        newest = max((c.fetched_at for c in rows if c.fetched_at), default=None)
        if newest and dt.datetime.now(dt.timezone.utc) - _aware(newest) < _CACHE_TTL:
            return rows
    return await sync_competitions(db, user_id)


async def sync_submissions(
    db: AsyncSession, user_id: int, competition: Competition, force: bool = False
) -> list[Submission]:
    """Return a competition's submissions, served from the DB cache when fresh.

    Rate-limit-safe: Kaggle's ``ListSubmissions`` is only called when ``force`` is
    set (manual "Sync now") or the cached rows are older than :data:`_DATA_TTL`
    (default 24h). Otherwise the stored rows are returned untouched — normal page
    views never re-hit Kaggle. Episode counts/IDs/scores are filled separately by
    :func:`resolve_episode_data` (background / scheduler / manual sync).
    """
    rows = (
        await db.execute(select(Submission).where(Submission.competition_id == competition.id))
    ).scalars().all()
    if not force and rows:
        newest = max((s.fetched_at for s in rows if s.fetched_at), default=None)
        if newest and dt.datetime.now(dt.timezone.utc) - _aware(newest) < _DATA_TTL:
            return rows

    context = await get_session_manager().get_context(user_id)
    page, tokens = await open_page(context)
    try:
        subs = await list_submissions(page, tokens, competition.team_id)
    finally:
        await page.close()

    for sub in subs:
        kaggle_id = str(sub["id"])
        existing = (
            await db.execute(
                select(Submission).where(Submission.kaggle_id == kaggle_id, Submission.user_id == user_id)
            )
        ).scalar_one_or_none()
        score = _parse_score(sub.get("publicScoreFormatted"))
        if existing is None:
            db.add(
                Submission(
                    kaggle_id=kaggle_id,
                    user_id=user_id,
                    competition_id=competition.id,
                    title=sub.get("title", ""),
                    score=score,
                    episode_count=None,  # unknown until the resolver fills it in
                )
            )
        else:
            existing.title = sub.get("title", existing.title)
            existing.score = score if score is not None else existing.score
            existing.fetched_at = dt.datetime.now(dt.timezone.utc)
    await db.commit()
    return (
        await db.execute(select(Submission).where(Submission.competition_id == competition.id))
    ).scalars().all()


async def resolve_episode_data(user_id: int, competition_id: int, force: bool = False) -> None:
    """Background task: fetch each submission's episodes ONCE and cache the result.

    For each submission this stores (in the DB, the source of truth for the UI):
    ``episode_count``, ``episodes_json`` (``[{"id","outcome"}, ...]``),
    ``episodes_synced_at``, and the real ``score`` (the latest-episode skill
    rating — fixes the "score shows 0" bug for simulation submissions).

    Rate-limit-safe: one ``ListEpisodes`` call per submission, SEQUENTIAL with a
    small delay, and it STOPS on the first error/429 (a later run resumes). Only
    submissions never synced before (``episodes_synced_at IS NULL``) are processed
    unless ``force`` (manual "Sync now" / daily scheduler refresh). Never writes a
    misleading 0 — an inconclusive fetch leaves the prior value intact.
    """
    from ..database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        comp = (
            await db.execute(select(Competition).where(Competition.id == competition_id))
        ).scalar_one_or_none()
        if comp is None:
            return
        query = select(Submission).where(Submission.competition_id == competition_id)
        if not force:
            query = query.where(Submission.episodes_synced_at.is_(None))
        pending = (await db.execute(query)).scalars().all()
        if not pending:
            return

        context = await get_session_manager().get_context(user_id)
        page, tokens = await open_page(context)
        try:
            now = dt.datetime.now(dt.timezone.utc)
            for sub in pending:
                data = await fetch_submission_episode_data(page, tokens, sub.kaggle_id)
                if data["error"] is not None or data["count"] < 0:
                    break  # likely 429 / expired session — stop; resync later
                sub.episode_count = data["count"]
                sub.episodes_json = data["episodes"]
                sub.episodes_synced_at = now
                if data["score"] is not None:
                    sub.score = data["score"]
                await db.commit()
                await asyncio.sleep(0.25)
        finally:
            await page.close()


async def full_resync(user_id: int, competition_id: int) -> None:
    """Background orchestrator for the manual "Sync now".

    Force-refreshes a competition's submissions, then its episode IDs / counts /
    skill-rating scores. Deliberately robust: it logs and swallows Kaggle errors
    so a slow or rate-limited upstream never crashes the task (the HTTP endpoint
    returns immediately and the UI polls for the results).
    """
    from ..database import AsyncSessionLocal
    from ..logging_config import get_logger

    log = get_logger("backend.kaggle_data_service")
    try:
        async with AsyncSessionLocal() as db:
            comp = (
                await db.execute(select(Competition).where(Competition.id == competition_id))
            ).scalar_one_or_none()
            if comp is None:
                return
            await sync_submissions(db, user_id, comp, force=True)
    except Exception as exc:  # noqa: BLE001
        log.error("resync.submissions_error", competition_id=competition_id, error=str(exc))
    try:
        await resolve_episode_data(user_id, competition_id, force=True)
    except Exception as exc:  # noqa: BLE001
        log.error("resync.episodes_error", competition_id=competition_id, error=str(exc))


async def get_submission_episodes(db: AsyncSession, user_id: int, submission: Submission) -> list[dict]:
    """Return a submission's episodes as ``[{"id","outcome"}, ...]``, cache-first.

    Serves the persisted ``episodes_json`` (populated by the daily scheduler, a
    manual "Sync now", or the first-load resolver) so navigating the app never
    re-hits Kaggle. Only when no cached list exists yet does it fetch live ONCE,
    persist (count + episode IDs + the real skill-rating score), and return —
    every subsequent read is served from the DB. On a genuine Kaggle rate-limit
    (429) it raises :class:`UpstreamRateLimited` so the router returns 429 +
    Retry-After instead of silently showing an empty list.
    """
    if submission.episodes_json is not None:
        return submission.episodes_json

    context = await get_session_manager().get_context(user_id)
    page, tokens = await open_page(context)
    try:
        data = await fetch_submission_episode_data(page, tokens, submission.kaggle_id)
    finally:
        await page.close()

    if data["error"] is not None:
        # Don't persist errors; surface rate-limits so the user sees a countdown.
        if "rate-limit" in data["error"].lower() or "429" in data["error"]:
            raise UpstreamRateLimited(data["error"], retry_after=60)
        raise UpstreamRateLimited(data["error"], retry_after=30)

    submission.episode_count = data["count"]
    submission.episodes_json = data["episodes"]
    submission.episodes_synced_at = dt.datetime.now(dt.timezone.utc)
    if data["score"] is not None:
        submission.score = data["score"]
    await db.commit()
    return data["episodes"]


def _parse_score(formatted) -> float | None:
    """Parse ``publicScoreFormatted`` into a float, treating 0/empty as unknown.

    Simulation submissions report ``"0"``/empty here even though their real score
    (the agent skill rating, 800+) lives in the episodes. So a literal 0 is treated
    as "unknown" (None) and the rating is sourced from ``updatedScore`` instead (see
    :func:`resolve_episode_data`). Genuine metric scores in this app are non-zero.
    """
    if formatted in (None, "-", ""):
        return None
    try:
        val = float(str(formatted).replace(",", ""))
    except (ValueError, TypeError):
        return None
    return val if val != 0 else None


def _aware(value: dt.datetime) -> dt.datetime:
    """Coerce a naive datetime (MySQL) to UTC-aware for safe comparison."""
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
