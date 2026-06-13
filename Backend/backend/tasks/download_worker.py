"""Background download-job worker.

Executes a queued ``download_jobs`` row end-to-end: fetches episodes, applies the
outcome filter (zero-fetch), batch-downloads replays into a path validated by
:func:`safe_output_path`, updates progress every batch, optionally ZIPs, and
finalizes status. Full tracebacks go to the log; only a sanitized one-line error
reaches the DB.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from ..config import get_settings
from ..database import AsyncSessionLocal
from ..kaggle_service import episode_outcome, list_episodes_checked, open_page
from ..logging_config import get_logger
from ..models import DownloadJob, Submission
from ..session_manager import get_session_manager
from ..utils.file_utils import ensure_dir, make_zip, safe_output_path
from ..utils.sanitize import sanitize_error

_settings = get_settings()
_log = get_logger("backend.download_worker")
_BATCH = 10


async def run_download_job(job_uuid: str) -> None:
    """Execute one download job by UUID, updating its DB row throughout.

    Args:
        job_uuid: The job's public UUID.
    """
    async with AsyncSessionLocal() as db:
        job = (await db.execute(select(DownloadJob).where(DownloadJob.job_uuid == job_uuid))).scalar_one_or_none()
        if job is None:
            return

        # Replay-by-id jobs carry an explicit episode list and no submission;
        # everything else is the submission-scoped path.
        is_replay = job.submission_id is None and bool(job.episode_ids)
        submission = None
        if not is_replay:
            submission = (
                await db.execute(select(Submission).where(Submission.id == job.submission_id))
            ).scalar_one_or_none()
            if submission is None:
                await _fail(db, job, "Submission not found")
                return

        job.status = "running"
        job.started_at = dt.datetime.now(dt.timezone.utc)
        await db.commit()
        _log.info("download.started", job=job_uuid, user_id=job.user_id)

        try:
            if is_replay:
                await _execute_replays(db, job)
            else:
                await _execute(db, job, submission)
        except Exception as exc:  # noqa: BLE001
            _log.error("download.failed", job=job_uuid, error=str(exc))
            await _fail(db, job, sanitize_error(str(exc)))


async def _execute(db, job: DownloadJob, submission: Submission) -> None:
    """Run the fetch→filter→download→package pipeline for ``job``."""
    manager = get_session_manager()
    context = await manager.get_context(job.user_id)
    page, tokens = await open_page(context)
    try:
        episodes, ep_error = await list_episodes_checked(page, tokens, submission.kaggle_id)
        if ep_error is not None:
            # Transient/auth failure — fail loudly rather than "done" with 0.
            raise RuntimeError(ep_error)
        id_to_ep = {str(ep["id"]): ep for ep in episodes}
        wanted = _apply_filter(id_to_ep, submission.kaggle_id, job.filter_mode)

        out_dir = ensure_dir(safe_output_path(_settings.downloads_base_path, job.user_id, job.job_uuid))
        job.total = len(wanted)
        await db.commit()

        import downloader  # project-root module (already on sys.path)

        completed = failed = 0
        for batch in _chunks(wanted, _BATCH):
            results = await downloader.fetch_replay_batch(page, batch)
            for res in results:
                eid = str(res["id"])
                if res.get("status") == 200 and res.get("text") is not None:
                    (out_dir / f"{eid}.json").write_text(res["text"], encoding="utf-8")
                    completed += 1
                else:
                    failed += 1
                job.latest_episode_id = eid
            job.completed, job.failed_count = completed, failed
            await db.commit()
    finally:
        await page.close()

    # Nothing matched (0-episode submission or an outcome filter with no hits):
    # finish cleanly with no output file so the UI doesn't offer an empty ZIP.
    if completed == 0:
        job.status = "done"
        job.output_path = None
        job.completed_at = dt.datetime.now(dt.timezone.utc)
        await db.commit()
        _log.info("download.done_empty", job=job.job_uuid, total=job.total)
        return

    output_path = str(out_dir)
    if job.format_mode in ("zip", "both"):
        zip_path = make_zip(out_dir, out_dir)
        output_path = str(zip_path)
        if job.format_mode == "zip":
            for jf in out_dir.glob("*.json"):
                jf.unlink()

    job.status = "done"
    job.output_path = output_path
    job.completed_at = dt.datetime.now(dt.timezone.utc)
    job.expires_at = job.completed_at + dt.timedelta(hours=_settings.JOB_OUTPUT_TTL_HOURS)
    await db.commit()
    _log.info("download.done", job=job.job_uuid, completed=job.completed, failed=job.failed_count)


async def _execute_replays(db, job: DownloadJob) -> None:
    """Download an explicit list of replay episode IDs (no submission lookup).

    Identical packaging to :func:`_execute`, but the episode set comes straight
    from ``job.episode_ids`` and there's no outcome filter to apply.
    """
    manager = get_session_manager()
    context = await manager.get_context(job.user_id)
    page, tokens = await open_page(context)
    wanted = [str(e) for e in (job.episode_ids or [])]
    try:
        out_dir = ensure_dir(safe_output_path(_settings.downloads_base_path, job.user_id, job.job_uuid))
        job.total = len(wanted)
        await db.commit()

        import downloader  # project-root module (already on sys.path)

        completed = failed = 0
        for batch in _chunks(wanted, _BATCH):
            results = await downloader.fetch_replay_batch(page, batch)
            for res in results:
                eid = str(res["id"])
                if res.get("status") == 200 and res.get("text") is not None:
                    (out_dir / f"{eid}.json").write_text(res["text"], encoding="utf-8")
                    completed += 1
                else:
                    failed += 1
                job.latest_episode_id = eid
            job.completed, job.failed_count = completed, failed
            await db.commit()
    finally:
        await page.close()

    if completed == 0:
        job.status = "done"
        job.output_path = None
        job.completed_at = dt.datetime.now(dt.timezone.utc)
        await db.commit()
        _log.info("download.done_empty", job=job.job_uuid, total=job.total)
        return

    output_path = str(out_dir)
    if job.format_mode in ("zip", "both"):
        zip_path = make_zip(out_dir, out_dir)
        output_path = str(zip_path)
        if job.format_mode == "zip":
            for jf in out_dir.glob("*.json"):
                jf.unlink()

    job.status = "done"
    job.output_path = output_path
    job.completed_at = dt.datetime.now(dt.timezone.utc)
    job.expires_at = job.completed_at + dt.timedelta(hours=_settings.JOB_OUTPUT_TTL_HOURS)
    await db.commit()
    _log.info("download.done", job=job.job_uuid, completed=job.completed, failed=job.failed_count)


def _apply_filter(id_to_ep: dict, submission_kaggle_id: str, filter_mode: str) -> list[str]:
    """Return the episode IDs to download under the active outcome filter."""
    if filter_mode == "all":
        return list(id_to_ep.keys())
    return [eid for eid, ep in id_to_ep.items() if episode_outcome(ep, submission_kaggle_id) == filter_mode]


def _chunks(items: list, size: int):
    """Yield ``size``-length slices of ``items``."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def _fail(db, job: DownloadJob, message: str) -> None:
    """Mark a job failed with a sanitized error message."""
    job.status = "failed"
    job.error_msg = message
    job.completed_at = dt.datetime.now(dt.timezone.utc)
    await db.commit()
