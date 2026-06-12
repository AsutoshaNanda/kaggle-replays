"""Background collection-download worker.

Executes a queued collection-type ``download_jobs`` row: selects cached items
by the job's ``item_filter`` (medal→votes order), then per item

* KERNEL — ``kaggle kernels pull`` via subprocess (ref parsed + validated by
  :func:`kaggle_collections.parse_kernel_ref`),
* TOPIC — ``GetForumTopicById`` rendered to Markdown,
* DATASET — ``kaggle datasets download`` (``all`` filter only),
* COMPETITION — capped vote-ordered drill-down into its top notebooks +
  discussions (``all`` filter only; cap = ``per_competition_cap``).

Progress is committed after every item so the existing WS/status endpoints
work unchanged. Item-level failures increment ``failed_count`` and the job
continues; only infrastructure errors fail the whole job.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import shutil

from sqlalchemy import select

from .. import kaggle_collections as kc
from ..config import get_settings
from ..database import AsyncSessionLocal
from ..kaggle_service import open_page
from ..logging_config import get_logger
from ..models import Collection, CollectionItem, DownloadJob
from ..services.collection_service import select_items
from ..session_manager import get_session_manager
from ..utils.file_utils import ensure_dir, make_zip, safe_output_path
from ..utils.sanitize import sanitize_error

_settings = get_settings()
_log = get_logger("backend.collection_worker")

_DEFAULT_CAP = 50
_SUBPROCESS_TIMEOUT = 180  # seconds per `kaggle` CLI call
_FETCH_DELAY = 1.0  # polite gap between Kaggle API calls

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


async def run_collection_job(job_uuid: str) -> None:
    """Execute one collection job by UUID, updating its DB row throughout."""
    async with AsyncSessionLocal() as db:
        job = (
            await db.execute(select(DownloadJob).where(DownloadJob.job_uuid == job_uuid))
        ).scalar_one_or_none()
        if job is None or job.job_type != "collection":
            return
        collection = (
            await db.execute(select(Collection).where(Collection.id == job.collection_id))
        ).scalar_one_or_none()
        if collection is None:
            await _fail(db, job, "Collection not found")
            return

        job.status = "running"
        job.started_at = dt.datetime.now(dt.timezone.utc)
        await db.commit()
        _log.info("collection_download.started", job=job_uuid, collection=collection.name)

        try:
            await _execute(db, job, collection)
        except Exception as exc:  # noqa: BLE001
            _log.error("collection_download.failed", job=job_uuid, error=str(exc))
            await _fail(db, job, sanitize_error(str(exc)))


async def _execute(db, job: DownloadJob, collection: Collection) -> None:
    """Run the select→download→package pipeline for ``job``."""
    items = list(
        (
            await db.execute(
                select(CollectionItem).where(CollectionItem.collection_id == collection.id)
            )
        ).scalars()
    )
    selected = select_items(items, job.item_filter or "all")
    job.total = len(selected)
    await db.commit()

    out_dir = ensure_dir(safe_output_path(_settings.downloads_base_path, job.user_id, job.job_uuid))
    cli = shutil.which("kaggle")

    manager = get_session_manager()
    context = await manager.get_context(job.user_id)
    page, tokens = await open_page(context)
    completed = failed = 0
    try:
        for item in selected:
            try:
                ok = await _process_item(page, tokens, job, item, out_dir, cli)
            except Exception as exc:  # noqa: BLE001 — one bad item must not kill the job
                _log.warning("collection_item.error", job=job.job_uuid, item=item.kaggle_doc_id, error=str(exc))
                ok = False
            if ok:
                completed += 1
            else:
                failed += 1
            job.completed, job.failed_count = completed, failed
            job.latest_episode_id = item.kaggle_doc_id[:100]
            await db.commit()
            await asyncio.sleep(_FETCH_DELAY)
    finally:
        await page.close()

    if completed == 0:
        # Nothing produced (empty selection or every item failed): finish without
        # an output file so the UI doesn't offer an empty ZIP.
        job.status = "done" if job.total == 0 else "failed"
        if job.status == "failed":
            job.error_msg = "All items failed to download — check the Kaggle session and `kaggle` CLI."
        job.output_path = None
        job.completed_at = dt.datetime.now(dt.timezone.utc)
        await db.commit()
        _log.info("collection_download.done_empty", job=job.job_uuid, total=job.total)
        return

    output_path = str(out_dir)
    if job.format_mode in ("zip", "both"):
        zip_path = make_zip(out_dir, out_dir)
        output_path = str(zip_path)
        if job.format_mode == "zip":
            for child in out_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                elif child.suffix != ".zip":
                    child.unlink(missing_ok=True)

    job.status = "done"
    job.output_path = output_path
    job.completed_at = dt.datetime.now(dt.timezone.utc)
    job.expires_at = job.completed_at + dt.timedelta(hours=_settings.JOB_OUTPUT_TTL_HOURS)
    await db.commit()
    _log.info("collection_download.done", job=job.job_uuid, completed=completed, failed=failed)


async def _process_item(page, tokens, job: DownloadJob, item: CollectionItem, out_dir, cli) -> bool:
    """Download one collection item into ``out_dir``; return success."""
    doc_type = item.document_type
    if doc_type == "KERNEL":
        return await _pull_kernel(item.url, out_dir / "notebooks", cli)
    if doc_type == "TOPIC":
        return await _save_topic(page, tokens, item.url, item.kaggle_doc_id, out_dir / "discussions")
    if doc_type == "DATASET":
        return await _pull_dataset(item.url, out_dir / "datasets", cli)
    if doc_type == "COMPETITION":
        return await _drill_competition(page, tokens, job, item, out_dir / "competitions")
    # COMMENT and unknown types carry nothing downloadable — count as skipped-ok.
    return True


async def _pull_kernel(url: str | None, dest, cli) -> bool:
    """``kaggle kernels pull owner/slug`` into ``dest``."""
    ref = kc.parse_kernel_ref(url)
    if ref is None or cli is None:
        return False
    ensure_dir(dest)
    return await _run_cli(cli, "kernels", "pull", f"{ref[0]}/{ref[1]}", "-p", str(dest))


async def _pull_dataset(url: str | None, dest, cli) -> bool:
    """``kaggle datasets download owner/slug`` into ``dest``."""
    ref = _parse_dataset_ref(url)
    if ref is None or cli is None:
        return False
    ensure_dir(dest)
    return await _run_cli(cli, "datasets", "download", "-d", f"{ref[0]}/{ref[1]}", "-p", str(dest))


async def _save_topic(page, tokens, url: str | None, kaggle_doc_id: str, dest) -> bool:
    """Fetch one discussion thread and write it as Markdown."""
    topic_id = kc.topic_id_from_doc(url, kaggle_doc_id)
    if topic_id is None:
        return False
    topic, error = await kc.fetch_forum_topic(page, tokens, topic_id)
    if error is not None or topic is None:
        return False
    ensure_dir(dest)
    name = _safe_name(topic.get("name") or "", f"topic-{topic_id}")
    (dest / f"{topic_id}_{name}.md").write_text(kc.render_topic_markdown(topic), encoding="utf-8")
    return True


async def _drill_competition(page, tokens, job: DownloadJob, item: CollectionItem, dest) -> bool:
    """Enumerate a competition's top notebooks + discussions (vote-ordered, capped).

    Success means the enumeration worked and at least one sub-item saved (or the
    competition genuinely has none); sub-item failures are logged, not fatal.
    """
    try:
        competition_id = int(re.search(r"(\d+)$", item.kaggle_doc_id).group(1))  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        return False
    cap = job.per_competition_cap if job.per_competition_cap is not None else _DEFAULT_CAP
    contents = await kc.enumerate_competition_contents(page, tokens, competition_id, cap)
    if contents["error"] is not None and not contents["kernels"] and not contents["topics"]:
        return False

    comp_dir = ensure_dir(dest / _safe_name(item.title, item.kaggle_doc_id))
    cli = shutil.which("kaggle")
    saved = failed = 0
    for parsed in contents["kernels"]:
        ok = await _pull_kernel(parsed["url"], comp_dir / "notebooks", cli)
        saved, failed = saved + ok, failed + (not ok)
        await asyncio.sleep(_FETCH_DELAY)
    for parsed in contents["topics"]:
        ok = await _save_topic(page, tokens, parsed["url"], parsed["kaggle_doc_id"], comp_dir / "discussions")
        saved, failed = saved + ok, failed + (not ok)
        await asyncio.sleep(_FETCH_DELAY)
    if failed:
        _log.warning(
            "collection_competition.partial",
            job=job.job_uuid, competition=item.kaggle_doc_id, saved=saved, failed=failed,
        )
    return saved > 0 or (not contents["kernels"] and not contents["topics"])


async def _run_cli(*argv: str) -> bool:
    """Run a `kaggle` CLI command; True on exit code 0."""
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_SUBPROCESS_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        return False
    if proc.returncode != 0:
        _log.warning("kaggle_cli.failed", argv=argv[1:3], stderr=(stderr or b"")[:300].decode(errors="replace"))
    return proc.returncode == 0


def _parse_dataset_ref(url: str | None) -> tuple[str, str] | None:
    """Parse ``/datasets/owner/slug`` into a CLI-safe ``(owner, slug)``."""
    parts = (url or "").strip("/").split("/")
    if len(parts) < 3 or parts[0] != "datasets":
        return None
    owner, slug = parts[1], parts[2]
    if not (kc._REF_SEGMENT_RE.match(owner) and kc._REF_SEGMENT_RE.match(slug)):  # noqa: SLF001
        return None
    return owner, slug


def _safe_name(text: str, fallback: str) -> str:
    """Reduce a title to a filesystem-safe name (never empty)."""
    cleaned = _SAFE_NAME_RE.sub("", text).strip().replace(" ", "_")[:80]
    return cleaned or fallback


async def _fail(db, job: DownloadJob, message: str) -> None:
    """Mark a job failed with a sanitized error message."""
    job.status = "failed"
    job.error_msg = message
    job.completed_at = dt.datetime.now(dt.timezone.utc)
    await db.commit()
