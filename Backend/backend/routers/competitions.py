"""Competition endpoints: list the user's competitions and their submissions."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..dependencies import get_current_user, get_db, limiter
from ..models import Competition, User
from ..schemas import (
    CompetitionItem,
    CompetitionListResponse,
    SubmissionItem,
    SubmissionListResponse,
)
from ..services import kaggle_data_service
from ..session_manager import get_session_manager
from ..tasks import leaderboard_worker

router = APIRouter(prefix="/competitions", tags=["competitions"])


@router.get("", response_model=CompetitionListResponse)
@limiter.limit("30/minute")
async def get_competitions(
    request: Request,
    tab: str = "all",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompetitionListResponse:
    """Return the user's competitions for the given tab (entered/completed/all)."""
    comps = await kaggle_data_service.get_competitions_cached(db, current_user.id)
    comps = kaggle_data_service.filter_competitions_by_tab(comps, tab)
    items = [CompetitionItem.model_validate(c) for c in comps]
    return CompetitionListResponse(competitions=items)


@router.get("/{kaggle_competition_id}/submissions", response_model=SubmissionListResponse)
@limiter.limit("30/minute")
async def get_submissions(
    request: Request,
    kaggle_competition_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubmissionListResponse:
    """Return submissions for a competition the user owns (else 403/404)."""
    comp = (
        await db.execute(
            select(Competition).where(
                Competition.kaggle_id == kaggle_competition_id, Competition.user_id == current_user.id
            )
        )
    ).scalar_one_or_none()
    if comp is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Competition not owned by user")
    # Cache-first (force=False): serves stored rows unless older than 24h. Live
    # ListSubmissions is only called on the first load / when the cache is stale.
    subs = await kaggle_data_service.sync_submissions(db, current_user.id, comp)
    # First-time only: if any submission's episodes were never synced, kick off ONE
    # paced background resolve (episode count + IDs + real skill-rating score). After
    # that, episode data is served from the DB cache — no live calls on navigation.
    if any(s.episodes_synced_at is None for s in subs):
        asyncio.create_task(
            kaggle_data_service.resolve_episode_data(current_user.id, comp.id)
        )
    last = max((s.fetched_at for s in subs if s.fetched_at), default=None)
    return SubmissionListResponse(
        submissions=[SubmissionItem.model_validate(s) for s in subs],
        last_synced_at=last,
    )


@router.post("/{kaggle_competition_id}/sync", response_model=SubmissionListResponse)
@limiter.limit("6/hour")
async def sync_submissions_now(
    request: Request,
    kaggle_competition_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubmissionListResponse:
    """Owner-only manual "Sync now": force a fresh pull for a competition.

    Re-pulls submissions immediately (so the list updates at once), then resolves
    episode counts/IDs/scores AND the leaderboard snapshot in the background. This
    is the only user-triggered Kaggle fetch; all page views read the DB cache.
    """
    comp = (
        await db.execute(
            select(Competition).where(
                Competition.kaggle_id == kaggle_competition_id, Competition.user_id == current_user.id
            )
        )
    ).scalar_one_or_none()
    if comp is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Competition not owned by user")
    subs = await kaggle_data_service.sync_submissions(db, current_user.id, comp, force=True)
    asyncio.create_task(
        kaggle_data_service.resolve_episode_data(current_user.id, comp.id, force=True)
    )
    asyncio.create_task(
        leaderboard_worker.run_daily_sync(comp.id, AsyncSessionLocal, get_session_manager())
    )
    last = max((s.fetched_at for s in subs if s.fetched_at), default=None)
    return SubmissionListResponse(
        submissions=[SubmissionItem.model_validate(s) for s in subs],
        last_synced_at=last,
    )
