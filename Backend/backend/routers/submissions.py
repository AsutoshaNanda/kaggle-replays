"""Submission endpoints: list a submission's episodes with computed outcomes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_current_user, get_db, limiter
from ..models import Submission, User
from ..schemas import EpisodeItem, EpisodeListResponse, FilterMode
from ..services import kaggle_data_service
from ..services.kaggle_data_service import UpstreamRateLimited

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get("/{submission_id}/episodes", response_model=EpisodeListResponse)
@limiter.limit("30/minute")
async def get_episodes(
    request: Request,
    submission_id: int,
    filter: FilterMode = "all",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EpisodeListResponse:
    """Return episodes for a user-owned submission, filtered by outcome.

    Outcomes are computed from each episode's agent rewards (zero extra fetches).
    """
    sub = (
        await db.execute(
            select(Submission).where(Submission.id == submission_id, Submission.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Submission not owned by user")

    try:
        episodes = await kaggle_data_service.get_submission_episodes(db, current_user.id, sub)
    except UpstreamRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=exc.message,
            headers={"Retry-After": str(exc.retry_after)},
        )
    items: list[EpisodeItem] = []
    for ep in episodes:
        # Episodes arrive pre-classified ({"id","outcome"}) from the DB cache.
        outcome = ep.get("outcome", "unknown")
        if filter != "all" and outcome != filter:
            continue
        items.append(EpisodeItem(id=str(ep.get("id")), outcome=outcome))

    note = None if filter == "all" else "Outcome data is derived from agent rewards and may be approximate."
    return EpisodeListResponse(episodes=items, total=len(items), filter_applied=filter, note=note)
