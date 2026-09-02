"""Resumable top-100 ZIP export and publishing worker."""

from __future__ import annotations

import asyncio
import csv
import datetime as dt
import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path

from sqlalchemy import select

from ..config import get_settings
from ..database import AsyncSessionLocal
from ..logging_config import get_logger
from ..models import (
    Competition,
    DownloadJob,
    ExportJob,
    LeaderboardEntry,
    LeaderboardSnapshot,
    TopPerformerEpisode,
    User,
)
from ..services.download_service import create_replay_job
from ..session_manager import get_session_manager
from ..utils.sanitize import safe_component, sanitize_error
from .download_worker import run_download_job
from .leaderboard_worker import run_daily_sync

_settings = get_settings()
_log = get_logger("backend.export_worker")
_ACTIVE_STATUSES = ("queued", "waiting_for_replays", "downloading", "uploading")


async def create_export_job(
    user_id: int,
    competition_id: int,
    target: str,
    is_public: bool,
) -> ExportJob:
    async with AsyncSessionLocal() as db:
        active = (
            await db.execute(
                select(ExportJob)
                .where(
                    ExportJob.user_id == user_id,
                    ExportJob.competition_id == competition_id,
                    ExportJob.target == target,
                    ExportJob.status.in_(_ACTIVE_STATUSES),
                )
                .order_by(ExportJob.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if active is not None:
            return active
        job = ExportJob(
            job_uuid=str(uuid.uuid4()),
            user_id=user_id,
            competition_id=competition_id,
            target=target,
            status="queued",
            is_public=is_public,
            total_players=100,
            download_job_ids={},
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
    asyncio.create_task(run_export_job(job.job_uuid))
    return job


async def resume_export_jobs() -> int:
    async with AsyncSessionLocal() as db:
        jobs = (
            await db.execute(select(ExportJob).where(ExportJob.status.in_(_ACTIVE_STATUSES)))
        ).scalars().all()
        for job in jobs:
            job.status = "queued"
        await db.commit()
    for job in jobs:
        asyncio.create_task(run_export_job(job.job_uuid))
    return len(jobs)


async def run_export_job(job_uuid: str) -> None:
    async with AsyncSessionLocal() as db:
        job = (
            await db.execute(select(ExportJob).where(ExportJob.job_uuid == job_uuid))
        ).scalar_one_or_none()
        if job is None or job.status == "done":
            return
        job.started_at = job.started_at or dt.datetime.now(dt.timezone.utc)
        job.error_msg = None
        await db.commit()
        try:
            competition = (
                await db.execute(select(Competition).where(Competition.id == job.competition_id))
            ).scalar_one()
            user = (await db.execute(select(User).where(User.id == job.user_id))).scalar_one()
            snapshot, players = await _wait_for_players(db, job, competition)
            stage = _stage_path(job.user_id, competition, snapshot.snapshot_date)
            stage.mkdir(parents=True, exist_ok=True)
            await _prepare_archives(db, job, snapshot, players, stage)
            job.status = "uploading"
            await db.commit()
            if job.target == "kaggle_dataset":
                await _publish_kaggle(job, user, competition, snapshot, stage)
            else:
                await _publish_drive(job, competition, snapshot, stage)
            job.status = "done"
            job.completed_at = dt.datetime.now(dt.timezone.utc)
            await db.commit()
        except Exception as exc:
            _log.error("export.failed", job=job_uuid, error=str(exc))
            job.status = "failed"
            job.error_msg = sanitize_error(str(exc), 1000)
            job.completed_at = dt.datetime.now(dt.timezone.utc)
            await db.commit()


async def _wait_for_players(db, job: ExportJob, competition: Competition):
    while True:
        snapshot, players = await _final_players(db, competition)
        resolved = sum(1 for player in players if player["resolved"])
        job.snapshot_id = snapshot.id if snapshot else None
        job.total_players = len(players) or 100
        job.resolved_players = resolved
        job.status = "waiting_for_replays"
        await db.commit()
        if snapshot is not None and players and resolved == len(players):
            return snapshot, players
        await run_daily_sync(
            competition.id,
            AsyncSessionLocal,
            get_session_manager(),
            final_only=True,
        )
        await asyncio.sleep(15)


async def _final_players(db, competition: Competition):
    deadline = _deadline_date(competition)
    snapshot = (
        await db.execute(
            select(LeaderboardSnapshot)
            .where(
                LeaderboardSnapshot.competition_id == competition.id,
                LeaderboardSnapshot.snapshot_date <= deadline,
            )
            .order_by(LeaderboardSnapshot.snapshot_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        return None, []
    entries = (
        await db.execute(
            select(LeaderboardEntry)
            .where(LeaderboardEntry.snapshot_id == snapshot.id, LeaderboardEntry.rank <= 100)
            .order_by(LeaderboardEntry.rank.asc())
            .limit(100)
        )
    ).scalars().all()
    episode_ids = {entry.id: [] for entry in entries}
    if episode_ids:
        rows = (
            await db.execute(
                select(TopPerformerEpisode.entry_id, TopPerformerEpisode.episode_id).where(
                    TopPerformerEpisode.entry_id.in_(episode_ids)
                )
            )
        ).all()
        for entry_id, episode_id in rows:
            episode_ids[entry_id].append(str(episode_id))
    players = [
        {
            "entry_id": entry.id,
            "team_id": entry.team_id,
            "team_name": entry.team_name or entry.team_id,
            "rank": entry.rank,
            "score": entry.score,
            "episode_ids": episode_ids[entry.id],
            "resolved": entry.episodes_resolved_at is not None or bool(episode_ids[entry.id]),
        }
        for entry in entries
    ]
    return snapshot, players


async def _prepare_archives(db, job: ExportJob, snapshot, players: list[dict], stage: Path) -> None:
    job.status = "downloading"
    job.total_episodes = sum(len(player["episode_ids"]) for player in players)
    await db.commit()
    mappings = dict(job.download_job_ids or {})
    manifest: list[dict] = []
    completed_players = 0
    completed_episodes = 0
    for player in players:
        job.current_rank = player["rank"]
        name = _archive_name(snapshot.snapshot_date, player)
        archive = stage / f"{name}.zip"
        included = _zip_json_count(archive)
        failed = 0
        if included is None:
            if not player["episode_ids"]:
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED):
                    pass
                included = 0
            else:
                download = await _run_player_download(db, job, mappings, player, name)
                source = Path(download.output_path or "")
                if download.status != "done" or not source.is_file():
                    raise RuntimeError(download.error_msg or f"Rank {player['rank']} ZIP failed")
                shutil.copy2(source, archive)
                included = _zip_json_count(archive)
                if included is None:
                    raise RuntimeError(f"Rank {player['rank']} ZIP validation failed")
                failed = download.failed_count
        completed_players += 1
        completed_episodes += included
        manifest.append(
            {
                "date": snapshot.snapshot_date.isoformat(),
                "rank": player["rank"],
                "player": player["team_name"],
                "team_id": player["team_id"],
                "score": player["score"],
                "expected_episodes": len(player["episode_ids"]),
                "included_episodes": included,
                "failed_episodes": failed,
                "zip_file": archive.name,
            }
        )
        job.completed_players = completed_players
        job.completed_episodes = completed_episodes
        job.download_job_ids = mappings
        await db.commit()
        _write_manifest(stage / "manifest.csv", manifest)
    job.current_rank = None
    await db.commit()


async def _run_player_download(db, export: ExportJob, mappings: dict, player: dict, name: str) -> DownloadJob:
    key = str(player["entry_id"])
    download = None
    if key in mappings:
        download = (
            await db.execute(select(DownloadJob).where(DownloadJob.job_uuid == mappings[key]))
        ).scalar_one_or_none()
        if download is not None and download.status in ("running", "queued"):
            download.status = "queued"
            await db.commit()
    if (
        download is None
        or download.status in ("failed", "cancelled")
        or (download.status == "done" and not download.output_path)
    ):
        download = await create_replay_job(
            db,
            export.user_id,
            player["episode_ids"],
            "zip",
            name,
            export.id,
        )
        mappings[key] = download.job_uuid
        export.download_job_ids = mappings
        await db.commit()
    if download.status != "done":
        await run_download_job(download.job_uuid)
        await db.refresh(download)
    return download


async def _publish_kaggle(job, user, competition, snapshot, stage: Path) -> None:
    kaggle = shutil.which("kaggle") or "/opt/anaconda3/bin/kaggle"
    if not Path(kaggle).is_file():
        raise RuntimeError("Kaggle CLI is not installed")
    slug = _dataset_slug(competition.slug, snapshot.snapshot_date)
    dataset_ref = f"{user.kaggle_user}/{slug}"
    metadata = {
        "title": _dataset_title(competition.title),
        "id": dataset_ref,
        "licenses": [{"name": "unknown"}],
        "description": (
            f"Top 100 final-day replay ZIPs for {competition.title}. "
            "Each ZIP contains one player's replay JSON files. See manifest.csv for counts. "
            "Source: Kaggle competition replays; use is subject to the competition rules."
        ),
        "keywords": ["games", "json"],
    }
    (stage / "dataset-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    status_code, _ = await _process(kaggle, "datasets", "status", dataset_ref, "--format", "json")
    if status_code != 0:
        command = [kaggle, "datasets", "create", "-p", str(stage), "-t", "-r", "skip"]
        if job.is_public:
            command.append("--public")
        code, output = await _process(*command)
        if code != 0:
            raise RuntimeError(f"Kaggle dataset creation failed: {output}")
        for _ in range(12):
            await asyncio.sleep(5)
            status_code, _ = await _process(
                kaggle, "datasets", "status", dataset_ref, "--format", "json"
            )
            if status_code == 0:
                break
        if status_code != 0:
            raise RuntimeError("Kaggle accepted the upload but status verification failed")
    job.dataset_ref = dataset_ref
    job.result_url = f"https://www.kaggle.com/datasets/{dataset_ref}"


async def _publish_drive(job, competition, snapshot, stage: Path) -> None:
    rclone = shutil.which("rclone")
    destination = _settings.GOOGLE_DRIVE_DESTINATION
    if not rclone or not destination:
        raise RuntimeError("Google Drive needs rclone and GOOGLE_DRIVE_DESTINATION configuration")
    target = "/".join(
        [destination.rstrip("/"), safe_component(competition.slug), snapshot.snapshot_date.isoformat()]
    )
    code, output = await _process(
        rclone,
        "copy",
        str(stage),
        target,
        "--retries",
        "8",
        "--retries-sleep",
        "30s",
        "--low-level-retries",
        "20",
    )
    if code != 0:
        raise RuntimeError(f"Google Drive upload failed: {output}")
    job.destination = target


async def _process(*args: str) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await process.communicate()
    return process.returncode or 0, output.decode("utf-8", errors="replace")[-2000:]


def export_view(job: ExportJob) -> dict:
    return {
        "job_id": job.job_uuid,
        "target": job.target,
        "status": job.status,
        "public": job.is_public,
        "total_players": job.total_players,
        "resolved_players": job.resolved_players,
        "completed_players": job.completed_players,
        "total_episodes": job.total_episodes,
        "completed_episodes": job.completed_episodes,
        "current_rank": job.current_rank,
        "result_url": job.result_url,
        "destination": job.destination,
        "error": job.error_msg,
    }


def drive_ready() -> bool:
    return bool(shutil.which("rclone") and _settings.GOOGLE_DRIVE_DESTINATION)


def kaggle_ready() -> bool:
    path = shutil.which("kaggle") or "/opt/anaconda3/bin/kaggle"
    return Path(path).is_file()


def _stage_path(user_id: int, competition: Competition, day: dt.date) -> Path:
    base = _settings.downloads_base_path.resolve()
    path = (base / str(user_id) / "exports" / safe_component(competition.slug) / day.isoformat()).resolve()
    if not str(path).startswith(str(base)):
        raise RuntimeError("Invalid export path")
    return path


def _archive_name(day: dt.date, player: dict) -> str:
    player_name = safe_component(player["team_name"])[:70]
    return safe_component(
        f"{day.isoformat()}_rank-{player['rank']:03d}_{player_name}_{len(player['episode_ids'])}-episodes"
    )[:200]


def _zip_json_count(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                return None
            return sum(1 for name in archive.namelist() if name.endswith(".json"))
    except (OSError, zipfile.BadZipFile):
        return None


def _write_manifest(path: Path, rows: list[dict]) -> None:
    fields = [
        "date",
        "rank",
        "player",
        "team_id",
        "score",
        "expected_episodes",
        "included_episodes",
        "failed_episodes",
        "zip_file",
    ]
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _dataset_slug(competition_slug: str, day: dt.date) -> str:
    suffix = f"-top-100-replays-{day.strftime('%Y%m%d')}"
    base = re.sub(r"[^a-z0-9-]+", "-", competition_slug.lower()).strip("-")
    return f"{base[: 50 - len(suffix)].rstrip('-')}{suffix}"


def _dataset_title(title: str) -> str:
    suffix = " Top 100 Replays"
    return f"{title[: 50 - len(suffix)].rstrip()}{suffix}"


def _deadline_date(competition: Competition) -> dt.date:
    if competition.deadline is None:
        return dt.datetime.now(dt.timezone.utc).date()
    value = competition.deadline
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return min(dt.datetime.now(dt.timezone.utc).date(), value.date())
