"""Background collection-download worker.

Executes a queued collection-type ``download_jobs`` row: selects cached items
by the job's ``item_filter`` (medal→votes order), then per item

* KERNEL — ``kaggle kernels pull`` via subprocess (ref parsed + validated by
  :func:`kaggle_collections.parse_kernel_ref`),
* TOPIC — ``GetForumTopicById`` rendered to Markdown,
* DATASET — ``kaggle datasets download`` PLUS a drill-down into the dataset's own
  top notebooks (``ListKernels`` by ``datasetId``) and discussions
  (``GetDatasetBasics`` → forumId → ``GetTopicListByForumId``) (``all`` filter only),
* COMPETITION — capped vote-ordered drill-down into its top notebooks +
  discussions (``all`` filter only; cap = ``per_competition_cap``).

Notebook drill-downs honor the job's optional ``medal_filter`` (gold/silver/bronze).
Progress is committed after every item so the existing WS/status endpoints
work unchanged. Item-level failures increment ``failed_count`` and the job
continues; a Kaggle rate-limit (429) aborts the whole job cleanly rather than
hammering the API item after item.
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
from ..kaggle_service import get_api_session
from ..logging_config import get_logger
from ..models import Collection, CollectionItem, DownloadJob
from ..services.collection_service import select_items
from ..utils.file_utils import ensure_dir, make_zip, safe_output_path
from ..utils.sanitize import sanitize_error

_settings = get_settings()
_log = get_logger("backend.collection_worker")

_DEFAULT_CAP = 50
_SUBPROCESS_TIMEOUT = 180  # seconds per `kaggle` CLI call
_FETCH_DELAY = 1.0  # polite gap between Kaggle API calls

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


class _RateLimited(Exception):
    """Raised when a Kaggle call returns a rate-limit error mid-job (abort signal)."""


def _raise_if_rate_limited(error: str | None) -> None:
    """Turn a Kaggle rate-limit error string into the job-abort signal."""
    if error and ("rate-limit" in error.lower() or "429" in error):
        raise _RateLimited(error)


def _cap(job: DownloadJob) -> int:
    """Per-drill-down item cap (competition/dataset); ``None`` column → default."""
    return job.per_competition_cap if job.per_competition_cap is not None else _DEFAULT_CAP


def _medal_set(job: DownloadJob) -> set[str]:
    """Parse the job's ``medal_filter`` ("gold,silver") into a set (empty = all)."""
    raw = getattr(job, "medal_filter", None) or ""
    return {m.strip().lower() for m in raw.split(",") if m.strip()}


def _medal_ok(parsed: dict, medals: set[str]) -> bool:
    """True if a drill-down kernel passes the medal filter (empty filter = all)."""
    if not medals:
        return True
    return (parsed.get("medal") or "") in medals


class _Progress:
    """Sub-item progress tracker for a collection job.

    The unit of progress is the actual downloadable SUB-ITEM (one notebook, one
    discussion, one dataset's files), not the top-level collection item. This is
    what makes a single-COMPETITION download show a moving bar + ETA instead of
    sitting at ``0/1`` for an hour while its ~50 notebooks pull one by one.

    ``add_total`` is called the moment a drill-down's sub-item count is known
    (after enumeration); ``done`` is called as each sub-item finishes. Both
    commit so the existing WS/poll status endpoints reflect progress live.
    """

    def __init__(self, db, job: DownloadJob) -> None:
        self._db = db
        self._job = job
        self.total = 0
        self.completed = 0
        self.failed = 0

    async def reset(self) -> None:
        self._job.total = self._job.completed = self._job.failed_count = 0
        await self._db.commit()

    async def add_total(self, n: int) -> None:
        if n <= 0:
            return
        self.total += n
        self._job.total = self.total
        await self._db.commit()

    async def done(self, ok: bool, latest: str | None = None) -> None:
        if ok:
            self.completed += 1
        else:
            self.failed += 1
        self._job.completed = self.completed
        self._job.failed_count = self.failed
        if latest:
            self._job.latest_episode_id = str(latest)[:100]
        await self._db.commit()


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
    if job.collection_item_id is not None:
        # Single-item job: download just this one cached item (whatever its type).
        selected = [i for i in items if i.id == job.collection_item_id]
    else:
        selected = select_items(items, job.item_filter or "all")

    out_dir = ensure_dir(safe_output_path(_settings.downloads_base_path, job.user_id, job.job_uuid))
    cli = shutil.which("kaggle")

    # Shared, long-lived per-user page — never closed here.
    page, tokens = await get_api_session(job.user_id)
    # Progress is counted per downloadable SUB-ITEM (notebook/discussion/dataset
    # files), so a single competition's drill-down shows a moving bar, not 0/1.
    prog = _Progress(db, job)
    await prog.reset()
    rate_limited = False
    for item in selected:
        try:
            await _process_item(page, tokens, job, item, out_dir, cli, prog)
        except _RateLimited as exc:
            # Stop the whole job the moment Kaggle rate-limits us, rather than
            # failing every remaining item and hammering the API.
            _log.warning("collection_download.rate_limited", job=job.job_uuid, error=str(exc))
            rate_limited = True
            break
        except Exception as exc:  # noqa: BLE001 — one bad item must not kill the job
            _log.warning("collection_item.error", job=job.job_uuid, item=item.kaggle_doc_id, error=str(exc))
        await asyncio.sleep(_FETCH_DELAY)

    completed = prog.completed
    if rate_limited:
        await _fail(db, job, kc.RATE_LIMIT_MSG)
        return

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
    _log.info("collection_download.done", job=job.job_uuid, completed=prog.completed, failed=prog.failed)


async def _process_item(
    page, tokens, job: DownloadJob, item: CollectionItem, out_dir, cli, prog: _Progress
) -> None:
    """Download one collection item into ``out_dir``, reporting sub-item progress.

    KERNEL/TOPIC are a single unit each; DATASET/COMPETITION fan out and report
    their own enumerated sub-item counts via ``prog``.
    """
    doc_type = item.document_type
    if doc_type == "KERNEL":
        await prog.add_total(1)
        ok = await _pull_kernel(item.url, out_dir / "notebooks", cli)
        await prog.done(ok, item.kaggle_doc_id)
    elif doc_type == "TOPIC":
        await prog.add_total(1)
        ok = await _save_topic(page, tokens, item.url, item.kaggle_doc_id, out_dir / "discussions")
        await prog.done(ok, item.kaggle_doc_id)
    elif doc_type == "DATASET":
        await _drill_dataset(page, tokens, job, item, out_dir / "datasets", cli, prog)
    elif doc_type == "COMPETITION":
        await _drill_competition(page, tokens, job, item, out_dir / "competitions", prog)
    else:
        # COMMENT and unknown types carry nothing downloadable — count as one ok unit.
        await prog.add_total(1)
        await prog.done(True, item.kaggle_doc_id)


async def _pull_kernel(url: str | None, dest, cli) -> bool:
    """Download a kernel's source + output files + execution log into ``dest``.

    Each kernel lands in its own ``dest/<owner>_<slug>`` subfolder so that the
    generically-named output files (``__results__.html``, ``submission.csv``,
    ``<slug>.log``) from different kernels never collide. ``kernels pull`` (with
    ``-m`` for ``kernel-metadata.json``) decides success; the follow-up
    ``kernels output`` is best-effort — a kernel with no output, or a transient
    output error, must NOT flip the item to failed.
    """
    ref = kc.parse_kernel_ref(url)
    if ref is None or cli is None:
        return False
    owner, slug = ref
    kdir = ensure_dir(dest / _safe_name(f"{owner}_{slug}", slug))
    ok = await _run_cli(cli, "kernels", "pull", f"{owner}/{slug}", "-p", str(kdir), "-m")
    # Output files + the execution .log — best-effort; absence/failure is non-fatal.
    await _run_cli(cli, "kernels", "output", f"{owner}/{slug}", "-p", str(kdir), "-q", "-o")
    return ok


async def _save_topic(page, tokens, url: str | None, kaggle_doc_id: str, dest) -> bool:
    """Fetch one discussion thread (by URL/doc id) and write it as Markdown."""
    topic_id = kc.topic_id_from_doc(url, kaggle_doc_id)
    if topic_id is None:
        return False
    return await _save_topic_by_id(page, tokens, topic_id, dest)


async def _save_topic_by_id(page, tokens, topic_id: int, dest) -> bool:
    """Fetch one discussion thread by numeric forumTopicId and write Markdown."""
    topic, error = await kc.fetch_forum_topic(page, tokens, topic_id)
    _raise_if_rate_limited(error)
    if error is not None or topic is None:
        return False
    ensure_dir(dest)
    name = _safe_name(topic.get("name") or "", f"topic-{topic_id}")
    (dest / f"{topic_id}_{name}.md").write_text(kc.render_topic_markdown(topic), encoding="utf-8")
    return True


async def _drill_dataset(
    page, tokens, job: DownloadJob, item: CollectionItem, dest, cli, prog: _Progress
) -> None:
    """Download a DATASET: its files, then its top notebooks + discussions.

    Files via ``kaggle datasets download``; notebooks via ``ListKernels`` (by
    ``datasetId``, votes-desc, capped, medal-filtered); discussions via the
    dataset ``forumId`` (``GetDatasetBasics``) → ``GetTopicListByForumId``
    (HOT-ordered, capped). Each sub-item is reported through ``prog``; sub-item
    failures are logged, not fatal; a rate-limit propagates as
    :class:`_RateLimited` to abort the job.
    """
    base = ensure_dir(dest / _safe_name(item.title, item.kaggle_doc_id))
    ref = kc.parse_dataset_ref(item.url)
    cap = _cap(job)
    medals = _medal_set(job)

    # 1) The dataset files themselves (one progress unit).
    await prog.add_total(1)
    files_ok = False
    if ref and cli:
        files_ok = await _run_cli(
            cli, "datasets", "download", "-d", f"{ref[0]}/{ref[1]}",
            "-p", str(ensure_dir(base / "data")), "--unzip",
        )
    await prog.done(files_ok, item.kaggle_doc_id)

    # 2) The dataset's own notebooks (ListKernels by numeric datasetId).
    dataset_id = kc.trailing_int(item.kaggle_doc_id)
    if dataset_id is not None:
        kernels, error = await kc.enumerate_dataset_kernels(page, tokens, dataset_id, cap)
        _raise_if_rate_limited(error)
        kernels = [k for k in kernels if _medal_ok(k, medals)]
        await prog.add_total(len(kernels))
        for parsed in kernels:
            ok = await _pull_kernel(parsed["url"], base / "notebooks", cli)
            await prog.done(ok, parsed.get("kaggle_doc_id"))
            await asyncio.sleep(_FETCH_DELAY)

    # 3) The dataset's discussions (forumId → topic list → per-topic markdown).
    if ref:
        forum_id, error = await kc.fetch_dataset_forum_id(page, tokens, ref[0], ref[1])
        _raise_if_rate_limited(error)
        if forum_id:
            topics, error = await kc.fetch_dataset_topics(page, tokens, forum_id, cap)
            _raise_if_rate_limited(error)
            await prog.add_total(len(topics))
            for topic in topics:
                ok = await _save_topic_by_id(page, tokens, topic["topic_id"], base / "discussions")
                await prog.done(ok, str(topic["topic_id"]))
                await asyncio.sleep(_FETCH_DELAY)


async def _drill_competition(
    page, tokens, job: DownloadJob, item: CollectionItem, dest, prog: _Progress
) -> None:
    """Enumerate a competition's top notebooks + discussions (vote-ordered, capped).

    Each notebook/discussion is one progress unit reported through ``prog``, so a
    single-competition download shows a moving bar + ETA. Sub-item failures are
    logged, not fatal; a rate-limit propagates as :class:`_RateLimited`.
    """
    competition_id = kc.trailing_int(item.kaggle_doc_id)
    if competition_id is None:
        await prog.add_total(1)
        await prog.done(False, item.kaggle_doc_id)
        return
    cap = _cap(job)
    medals = _medal_set(job)
    contents = await kc.enumerate_competition_contents(page, tokens, competition_id, cap)
    _raise_if_rate_limited(contents["error"])
    kernels = [k for k in contents["kernels"] if _medal_ok(k, medals)]
    topics = contents["topics"]
    if contents["error"] is not None and not kernels and not topics:
        await prog.add_total(1)
        await prog.done(False, item.kaggle_doc_id)
        return
    if not kernels and not topics:
        # Genuinely empty competition — count one ok unit so the job isn't "failed".
        await prog.add_total(1)
        await prog.done(True, item.kaggle_doc_id)
        return

    await prog.add_total(len(kernels) + len(topics))
    comp_dir = ensure_dir(dest / _safe_name(item.title, item.kaggle_doc_id))
    cli = shutil.which("kaggle")
    failed = 0
    for parsed in kernels:
        ok = await _pull_kernel(parsed["url"], comp_dir / "notebooks", cli)
        failed += not ok
        await prog.done(ok, parsed.get("kaggle_doc_id") or item.kaggle_doc_id)
        await asyncio.sleep(_FETCH_DELAY)
    for parsed in topics:
        ok = await _save_topic(page, tokens, parsed["url"], parsed["kaggle_doc_id"], comp_dir / "discussions")
        failed += not ok
        await prog.done(ok, parsed.get("kaggle_doc_id"))
        await asyncio.sleep(_FETCH_DELAY)
    if failed:
        _log.warning(
            "collection_competition.partial",
            job=job.job_uuid, competition=item.kaggle_doc_id, failed=failed,
        )


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
