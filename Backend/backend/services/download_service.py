"""Service helpers for the downloads router: job creation, progress math, files."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Competition, DownloadJob, Submission


async def create_job(
    db: AsyncSession, user_id: int, submission_id: int, filter_mode: str, format_mode: str, is_bulk: bool = False
) -> DownloadJob:
    """Insert a queued ``download_jobs`` row and return it."""
    job = DownloadJob(
        job_uuid=str(uuid.uuid4()),
        user_id=user_id,
        submission_id=submission_id,
        filter_mode=filter_mode,
        format_mode=format_mode,
        is_bulk=is_bulk,
        status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_owned_job(db: AsyncSession, user_id: int, job_uuid: str) -> DownloadJob | None:
    """Return a job by UUID only if it belongs to ``user_id``."""
    return (
        await db.execute(select(DownloadJob).where(DownloadJob.job_uuid == job_uuid))
    ).scalar_one_or_none()


async def get_owned_submission(db: AsyncSession, user_id: int, submission_id: int) -> Submission | None:
    """Return a submission by ID only if owned by ``user_id``."""
    return (
        await db.execute(
            select(Submission).where(Submission.id == submission_id, Submission.user_id == user_id)
        )
    ).scalar_one_or_none()


async def get_owned_competition(db: AsyncSession, user_id: int, competition_id: int) -> Competition | None:
    """Return a competition by ID only if owned by ``user_id``."""
    return (
        await db.execute(
            select(Competition).where(Competition.id == competition_id, Competition.user_id == user_id)
        )
    ).scalar_one_or_none()


def progress_view(job: DownloadJob) -> dict:
    """Compute progress metrics for a job's status response."""
    pct = (job.completed / job.total * 100.0) if job.total else 0.0
    now = dt.datetime.now(dt.timezone.utc)
    started = _aware(job.started_at) if job.started_at else None
    end = _aware(job.completed_at) if job.completed_at else now
    elapsed = (end - started).total_seconds() if started else 0.0
    remaining = None
    if job.status == "running" and job.completed and job.total:
        per = elapsed / job.completed
        remaining = max(0.0, per * (job.total - job.completed))
    return {
        "job_id": job.job_uuid,
        "status": job.status,
        "total": job.total,
        "completed": job.completed,
        "failed_count": job.failed_count,
        "skipped": job.skipped,
        "pct_complete": round(pct, 1),
        "elapsed_seconds": round(elapsed, 1),
        "estimated_remaining_seconds": round(remaining, 1) if remaining is not None else None,
    }


def history_view(job: DownloadJob) -> dict:
    """Build a history-row dict for ``JobHistoryItem``.

    The ORM column is ``job_uuid`` but the API field is ``job_id``; mapping here
    (rather than ``model_validate`` on the ORM object) avoids a validation error.
    """
    submission = getattr(job, "submission", None)
    return {
        "job_id": job.job_uuid,
        "status": job.status,
        "filter_mode": job.filter_mode,
        "format_mode": job.format_mode,
        "is_bulk": job.is_bulk,
        "total": job.total,
        "completed": job.completed,
        "failed_count": job.failed_count,
        "skipped": job.skipped,
        "submission_title": submission.title if submission else None,
        "submission_score": submission.score if submission else None,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


def _aware(value: dt.datetime) -> dt.datetime:
    """Coerce a naive datetime to UTC-aware."""
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
