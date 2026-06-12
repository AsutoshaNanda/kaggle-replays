"""Download endpoints: start, bulk, status, file stream, cancel, history."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..audit import write_audit
from ..config import get_settings
from ..dependencies import get_current_user, get_db, limiter
from ..models import DownloadJob, Submission, User
from ..schemas import (
    BulkDownloadRequest,
    BulkDownloadResponse,
    DownloadStartRequest,
    DownloadStartResponse,
    JobHistoryItem,
    JobHistoryResponse,
    JobStatusResponse,
    MessageResponse,
)
from ..services import download_service
from ..tasks.download_worker import run_download_job
from ..utils.file_utils import delete_path, safe_output_path, stream_file

router = APIRouter(prefix="/downloads", tags=["downloads"])
_settings = get_settings()


@router.post("/start", response_model=DownloadStartResponse)
@limiter.limit("10/hour")
async def start_download(
    request: Request,
    body: DownloadStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DownloadStartResponse:
    """Create a download job for an owned submission and launch the worker."""
    sub = await download_service.get_owned_submission(db, current_user.id, body.submission_id)
    if sub is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Submission not owned by user")
    job = await download_service.create_job(
        db, current_user.id, sub.id, body.filter_mode, body.format_mode, is_bulk=False
    )
    asyncio.create_task(run_download_job(job.job_uuid))
    await write_audit(
        db, action="download.start", ip_address=request.state.client_ip,
        status="success", user_id=current_user.id, resource_type="download_job", resource_id=job.job_uuid,
    )
    return DownloadStartResponse(job_id=job.job_uuid, status="queued")


@router.post("/bulk", response_model=BulkDownloadResponse)
@limiter.limit("3/hour")
async def bulk_download(
    request: Request,
    body: BulkDownloadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkDownloadResponse:
    """Create a bulk download job across all submissions of an owned competition."""
    if not body.confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bulk download requires confirm=true")
    comp = await download_service.get_owned_competition(db, current_user.id, body.competition_id)
    if comp is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Competition not owned by user")
    subs = (await db.execute(select(Submission).where(Submission.competition_id == comp.id))).scalars().all()
    if not subs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No submissions to download")
    estimated = sum(s.episode_count or 0 for s in subs)
    job = await download_service.create_job(
        db, current_user.id, subs[0].id, body.filter_mode, body.format_mode, is_bulk=True
    )
    asyncio.create_task(run_download_job(job.job_uuid))
    await write_audit(
        db, action="download.bulk", ip_address=request.state.client_ip,
        status="success", user_id=current_user.id, resource_type="download_job", resource_id=job.job_uuid,
    )
    return BulkDownloadResponse(job_id=job.job_uuid, total_submissions=len(subs), total_episodes_estimated=estimated)


@router.get("/{job_uuid}/status", response_model=JobStatusResponse)
async def job_status(
    job_uuid: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> JobStatusResponse:
    """Return progress for an owned job."""
    job = await download_service.get_owned_job(db, current_user.id, job_uuid)
    _ensure_owner(job, current_user.id)
    return JobStatusResponse(**download_service.progress_view(job))


@router.get("/{job_uuid}/file")
async def download_file(
    job_uuid: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """Stream a completed job's ZIP, validating ownership and path safety."""
    job = await download_service.get_owned_job(db, current_user.id, job_uuid)
    _ensure_owner(job, current_user.id)
    if job.status != "done" or not job.output_path:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job output not ready")
    base = _settings.downloads_base_path
    expected = safe_output_path(base, current_user.id, job_uuid)
    path = Path(job.output_path)
    if not str(path.resolve()).startswith(str(expected.parent.resolve())) or not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Output file missing")
    filename = f"{job_uuid}.zip"
    return StreamingResponse(
        stream_file(path),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{job_uuid}", response_model=MessageResponse)
async def cancel_job(
    request: Request, job_uuid: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Cancel an owned job and delete its output."""
    job = await download_service.get_owned_job(db, current_user.id, job_uuid)
    _ensure_owner(job, current_user.id)
    job.status = "cancelled"
    if job.output_path:
        delete_path(Path(job.output_path))
    delete_path(safe_output_path(_settings.downloads_base_path, current_user.id, job_uuid))
    await db.commit()
    await write_audit(
        db, action="download.cancel", ip_address=request.state.client_ip,
        status="success", user_id=current_user.id, resource_type="download_job", resource_id=job_uuid,
    )
    return MessageResponse(message="cancelled")


@router.get("", response_model=JobHistoryResponse)
async def list_jobs(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> JobHistoryResponse:
    """Return the user's 50 most recent jobs, newest first."""
    rows = (
        await db.execute(
            select(DownloadJob)
            .where(DownloadJob.user_id == current_user.id)
            .options(selectinload(DownloadJob.submission), selectinload(DownloadJob.collection))
            .order_by(DownloadJob.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    return JobHistoryResponse(
        jobs=[JobHistoryItem(**download_service.history_view(j)) for j in rows]
    )


def _ensure_owner(job: DownloadJob | None, user_id: int) -> None:
    """Raise 404 if the job is missing, 403 if it belongs to another user."""
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your job")
