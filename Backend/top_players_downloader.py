"""Daily top-player Kaggle replay downloader with resumable player/day ZIPs."""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import email.utils
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

import downloader


LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(message)s"
LIST_COMPETITIONS = "/api/i/competitions.CompetitionService/ListCompetitions"
GET_LEADERBOARD = "/api/i/competitions.LeaderboardService/GetLeaderboard"
LIST_EPISODES = "/api/i/competitions.EpisodeService/ListEpisodes"
RETRYABLE_STATUSES = {0, 408, 425, 500, 502, 503, 504}
log = logging.getLogger("top_players_downloader")


class KaggleRequestError(RuntimeError):
    pass


class KaggleAuthenticationError(KaggleRequestError):
    pass


@dataclass(frozen=True)
class RequestSettings:
    delay: float
    max_retries: int
    retry_base: float
    retry_cap: float


class KaggleClient:
    def __init__(self, page, tokens: dict[str, str], settings: RequestSettings) -> None:
        self.page = page
        self.tokens = tokens
        self.settings = settings
        self._last_request = 0.0
        self._rate_limit_count = 0

    async def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        text = await self._request("POST", path, body)
        try:
            value = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise KaggleRequestError(f"Kaggle returned invalid JSON for {path}") from exc
        if not isinstance(value, dict):
            raise KaggleRequestError(f"Kaggle returned an unexpected response for {path}")
        return value

    async def get_text(self, path: str) -> str:
        return await self._request("GET", path, None)

    async def _request(self, method: str, path: str, body: dict[str, Any] | None) -> str:
        retry = 0
        while True:
            await self._pace()
            try:
                response = await self.page.evaluate(
                    """
                    async ({method, path, body, xsrf, buildHash}) => {
                        try {
                            const r = await fetch(path, {
                                method,
                                headers: {
                                    "content-type": "application/json",
                                    "x-xsrf-token": xsrf,
                                    "x-kaggle-build-version": buildHash
                                },
                                body: body === null ? undefined : JSON.stringify(body)
                            });
                            return {
                                status: r.status,
                                text: await r.text(),
                                retryAfter: r.headers.get("retry-after")
                            };
                        } catch (error) {
                            return {status: 0, text: "", error: String(error), retryAfter: null};
                        }
                    }
                    """,
                    {
                        "method": method,
                        "path": path,
                        "body": body,
                        "xsrf": self.tokens["xsrf"],
                        "buildHash": self.tokens["build_hash"],
                    },
                )
            except Exception as exc:
                response = {"status": 0, "text": "", "error": str(exc), "retryAfter": None}

            status = int(response.get("status") or 0)
            if status == 200:
                self._rate_limit_count = 0
                return str(response.get("text") or "")
            if status == 429:
                self._rate_limit_count += 1
                wait = self._rate_limit_wait(response.get("retryAfter"))
                log.warning("Kaggle rate limit reached. Pausing %.1f seconds, then continuing.", wait)
                await asyncio.sleep(wait)
                continue
            if status in (401, 403):
                raise KaggleAuthenticationError(
                    "Kaggle login expired. Run `python login.py`, then rerun this command to resume."
                )
            if status in RETRYABLE_STATUSES and retry < self.settings.max_retries:
                wait = self._retry_wait(retry)
                retry += 1
                log.warning("Kaggle request failed with HTTP %s. Retry %d in %.1f seconds.", status, retry, wait)
                await asyncio.sleep(wait)
                continue
            detail = str(response.get("text") or response.get("error") or "unknown error")[:300]
            raise KaggleRequestError(f"Kaggle returned HTTP {status} for {path}: {detail}")

    async def _pace(self) -> None:
        now = time.monotonic()
        wait = self.settings.delay - (now - self._last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    def _retry_wait(self, retry: int) -> float:
        base = min(self.settings.retry_cap, self.settings.retry_base * (2**retry))
        return base + random.uniform(0, min(1.0, base * 0.1))

    def _rate_limit_wait(self, retry_after: Any) -> float:
        parsed = parse_retry_after(retry_after)
        if parsed is not None:
            return max(parsed, self.settings.delay)
        base = min(self.settings.retry_cap, self.settings.retry_base * (2 ** min(self._rate_limit_count, 10)))
        return base + random.uniform(0, min(5.0, base * 0.1))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture the daily top 100 and create one resumable replay ZIP per player/day.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--competition", help="Competition slug or numeric Kaggle competition ID.")
    parser.add_argument("--top", type=top_count, default=100, metavar="1-100")
    parser.add_argument("--output-dir", default="downloads/top-players")
    parser.add_argument("--auth-state", default="auth.json")
    parser.add_argument("--end-date", help="YYYY-MM-DD fallback only when Kaggle omits the deadline.")
    parser.add_argument("--request-delay", type=float, default=1.0)
    parser.add_argument("--max-retries", type=int, default=8)
    parser.add_argument("--retry-base", type=float, default=3.0)
    parser.add_argument("--retry-cap", type=float, default=300.0)
    parser.add_argument("--drive-destination", help="Optional rclone path, for example gdrive:Kaggle-Replays.")
    parser.add_argument("--headful", action="store_true")
    return parser.parse_args()


def top_count(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer from 1 to 100") from exc
    if not 1 <= parsed <= 100:
        raise argparse.ArgumentTypeError("must be from 1 to 100")
    return parsed


def parse_retry_after(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        pass
    try:
        target = email.utils.parsedate_to_datetime(str(value))
    except (TypeError, ValueError, OverflowError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=dt.timezone.utc)
    return max(0.0, (target - dt.datetime.now(dt.timezone.utc)).total_seconds())


def parse_datetime(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            day = dt.date.fromisoformat(cleaned)
        except ValueError:
            return None
        return dt.datetime.combine(day, dt.time.max, tzinfo=dt.timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def competition_deadline(competition: dict[str, Any], fallback: str | None) -> dt.datetime:
    deadline = parse_datetime(competition.get("deadline"))
    if deadline is not None:
        return deadline
    deadline = parse_datetime(fallback)
    if deadline is not None:
        return deadline
    raise SystemExit(
        "Kaggle did not return a competition deadline. Pass --end-date YYYY-MM-DD so no later day is processed."
    )


def snapshot_date(now: dt.datetime, deadline: dt.datetime) -> dt.date:
    return min(now.astimezone(dt.timezone.utc).date(), deadline.astimezone(dt.timezone.utc).date())


def safe_name(value: Any, fallback: str) -> str:
    cleaned = downloader.sanitize_filename(str(value or fallback)).strip("._-")
    return cleaned[:120] or fallback


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


async def fetch_competitions(client: KaggleClient) -> list[dict[str, Any]]:
    data = await client.post_json(
        LIST_COMPETITIONS,
        {
            "selector": {
                "competitionIds": [],
                "listOption": "LIST_OPTION_USER_ENTERED",
                "sortOption": "SORT_OPTION_NUM_TEAMS",
                "hostSegmentIdFilter": 0,
                "searchQuery": "",
                "prestigeFilter": "PRESTIGE_FILTER_UNSPECIFIED",
                "visibilityFilter": "VISIBILITY_FILTER_UNSPECIFIED",
                "participationFilter": "PARTICIPATION_FILTER_UNSPECIFIED",
                "tagIds": [],
                "excludeTagIds": [],
                "requireSimulations": False,
                "requireKernels": False,
                "requireHackathons": False,
            },
            "pageToken": "",
            "pageSize": 50,
            "readMask": "competitions,userTeams",
        },
    )
    return list(data.get("competitions") or [])


def select_competition(competitions: list[dict[str, Any]], selector: str | None) -> dict[str, Any]:
    if not competitions:
        raise SystemExit("No entered competitions were returned. Refresh auth.json with `python login.py`.")
    if selector:
        lowered = selector.casefold()
        match = next(
            (
                comp
                for comp in competitions
                if str(comp.get("id")) == selector
                or str(comp.get("competitionName") or "").casefold() == lowered
            ),
            None,
        )
        if match is None:
            raise SystemExit(f"Competition not found: {selector}")
        return match
    print("\nCompetitions:\n")
    for index, comp in enumerate(competitions, start=1):
        print(f"{index}. {comp.get('title')} ({comp.get('competitionName')})")
    try:
        chosen = int(input("\nSelect competition: "))
        return competitions[chosen - 1]
    except (ValueError, IndexError):
        raise SystemExit("Invalid competition selection.") from None


async def fetch_leaderboard(client: KaggleClient, competition_id: Any, top_n: int) -> list[dict[str, Any]]:
    data = await client.post_json(
        GET_LEADERBOARD,
        {"competitionId": int(competition_id), "leaderboardMode": "LEADERBOARD_MODE_DEFAULT"},
    )
    names = {str(team.get("teamId")): team.get("teamName") for team in data.get("teams") or []}
    players = []
    for position, row in enumerate(data.get("publicLeaderboard") or [], start=1):
        rank = int(row.get("rank") or position)
        if rank > top_n:
            continue
        team_id = str(row.get("teamId") or position)
        submission_id = row.get("submissionId")
        if submission_id in (None, ""):
            log.warning("Skipping rank %d because Kaggle returned no submission ID.", rank)
            continue
        players.append(
            {
                "rank": rank,
                "team_id": team_id,
                "player_name": str(names.get(team_id) or team_id),
                "submission_id": str(submission_id),
                "score": row.get("displayScore"),
            }
        )
    players.sort(key=lambda item: item["rank"])
    return players[:top_n]


async def fetch_episode_ids(client: KaggleClient, submission_id: str) -> list[str]:
    data = await client.post_json(LIST_EPISODES, {"submissionId": submission_id})
    ids = {str(item["id"]) for item in data.get("episodes") or [] if item.get("id") not in (None, "")}
    return sorted(ids, key=lambda value: (int(value) if value.isdigit() else sys.maxsize, value))


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def archive_episode_count(path: Path, expected_ids: list[str] | None = None) -> int | None:
    if not path.exists():
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".json")]
            if archive.testzip() is not None:
                return None
    except (OSError, zipfile.BadZipFile):
        return None
    if expected_ids is not None and set(names) != {f"{episode_id}.json" for episode_id in expected_ids}:
        return None
    return len(names)


def create_archive(archive_path: Path, stage_dir: Path, episode_ids: list[str]) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_name(f".{archive_path.name}.tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for episode_id in episode_ids:
                archive.write(stage_dir / f"{episode_id}.json", arcname=f"{episode_id}.json")
        os.replace(temporary, archive_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def valid_replay_file(path: Path) -> bool:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(value, (dict, list))


async def download_replay(client: KaggleClient, episode_id: str, destination: Path, retries: int) -> None:
    for attempt in range(retries + 1):
        text = await client.get_text(f"/competitions/episodes/{episode_id}/replay.json")
        try:
            value = json.loads(text)
        except ValueError:
            value = None
        if isinstance(value, (dict, list)):
            destination.write_text(text, encoding="utf-8")
            return
        if attempt < retries:
            wait = min(30.0, 2.0 * (2**attempt))
            log.warning("Replay %s was invalid JSON. Retrying in %.1f seconds.", episode_id, wait)
            await asyncio.sleep(wait)
    raise KaggleRequestError(f"Replay {episode_id} repeatedly returned invalid JSON.")


def remote_path(base: str, *parts: str) -> str:
    return "/".join([base.rstrip("/"), *(part.strip("/") for part in parts)])


def upload_archive(path: Path, destination: str, slug: str, player_dir: str) -> bool:
    target = remote_path(destination, slug, player_dir, path.name)
    try:
        subprocess.run(
            [
                "rclone",
                "copyto",
                str(path),
                target,
                "--retries",
                "8",
                "--retries-sleep",
                "30s",
                "--low-level-retries",
                "20",
            ],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        log.error("Drive upload failed for %s with exit code %d. Rerun to retry.", path, exc.returncode)
        return False
    return True


def update_summary(root: Path, record: dict[str, Any]) -> None:
    summary_path = root / "summary.json"
    summary = load_json(summary_path) or {"archives": {}}
    archives = summary.setdefault("archives", {})
    archives[f"{record['date']}:{record['team_id']}"] = record
    atomic_json(summary_path, summary)
    rows = sorted(archives.values(), key=lambda item: (item["date"], int(item["rank"]), item["team_id"]))
    csv_path = root / "summary.csv"
    temporary = csv_path.with_name(f".{csv_path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "rank",
                "player_name",
                "team_id",
                "submission_id",
                "episodes",
                "expected_episodes",
                "failed_episodes",
                "zip_path",
                "drive_uploaded",
            ],
        )
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in writer.fieldnames} for row in rows)
    os.replace(temporary, csv_path)


def previous_summary_record(root: Path, day: str, team_id: str) -> dict[str, Any] | None:
    summary = load_json(root / "summary.json") or {}
    record = (summary.get("archives") or {}).get(f"{day}:{team_id}")
    return record if isinstance(record, dict) else None


async def process_player(
    client: KaggleClient,
    competition_root: Path,
    day: str,
    player: dict[str, Any],
    replay_retries: int,
) -> dict[str, Any]:
    team_id = safe_name(player["team_id"], "team")
    player_name = safe_name(player["player_name"], team_id)
    player_dir_name = f"{player_name}--{team_id}"
    player_dir = competition_root / player_dir_name
    archive_path = player_dir / f"{day}.zip"
    state_path = competition_root / ".state" / team_id / f"{day}.json"
    state = load_json(state_path)
    if state and state.get("submission_id") == player["submission_id"]:
        episode_ids = [str(value) for value in state.get("episode_ids") or []]
    else:
        episode_ids = await fetch_episode_ids(client, player["submission_id"])
        state = {
            "date": day,
            "team_id": player["team_id"],
            "submission_id": player["submission_id"],
            "episode_ids": episode_ids,
        }
        atomic_json(state_path, state)

    existing_count = archive_episode_count(archive_path, episode_ids)
    archive_rebuilt = existing_count is None
    failed_ids: list[str] = []
    if existing_count is None:
        stage_dir = competition_root / ".partial" / day / team_id
        stage_dir.mkdir(parents=True, exist_ok=True)
        total = len(episode_ids)
        for index, episode_id in enumerate(episode_ids, start=1):
            replay_path = stage_dir / f"{episode_id}.json"
            if not valid_replay_file(replay_path):
                try:
                    await download_replay(client, episode_id, replay_path, replay_retries)
                except KaggleAuthenticationError:
                    raise
                except KaggleRequestError as exc:
                    failed_ids.append(episode_id)
                    log.error("Skipping replay %s for now: %s", episode_id, exc)
            if index == total or index % 25 == 0:
                log.info("%s | rank %d | %s | %d/%d", day, player["rank"], player["player_name"], index, total)
        included_ids = [
            episode_id
            for episode_id in episode_ids
            if valid_replay_file(stage_dir / f"{episode_id}.json")
        ]
        create_archive(archive_path, stage_dir, included_ids)
        existing_count = archive_episode_count(archive_path, included_ids)
        if existing_count != len(included_ids):
            raise KaggleRequestError(f"Archive validation failed: {archive_path}")
        if not failed_ids:
            for episode_id in episode_ids:
                replay_path = stage_dir / f"{episode_id}.json"
                if replay_path.exists():
                    replay_path.unlink()

    previous = previous_summary_record(competition_root, day, player["team_id"])
    previously_uploaded = bool(previous and previous.get("drive_uploaded")) and not archive_rebuilt
    record = {
        "date": day,
        "rank": player["rank"],
        "player_name": player["player_name"],
        "team_id": player["team_id"],
        "submission_id": player["submission_id"],
        "episodes": existing_count,
        "expected_episodes": len(episode_ids),
        "failed_episodes": len(failed_ids),
        "zip_path": str(archive_path),
        "drive_uploaded": previously_uploaded,
    }
    update_summary(competition_root, record)
    print(
        f"{day} | #{player['rank']:03d} | {player['player_name']} | "
        f"{existing_count}/{len(episode_ids)} episodes included | {archive_path}"
    )
    return record


def existing_snapshot_paths(snapshot_dir: Path, final_day: dt.date) -> list[Path]:
    paths = []
    for path in snapshot_dir.glob("*.json"):
        try:
            day = dt.date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day <= final_day:
            paths.append(path)
    return sorted(paths)


async def run(args: argparse.Namespace) -> None:
    auth_path = Path(args.auth_state).expanduser().resolve()
    if not auth_path.is_file() or auth_path.stat().st_size == 0:
        raise SystemExit(f"Missing auth state: {auth_path}. Run `python login.py` first.")
    settings = RequestSettings(
        delay=max(0.1, args.request_delay),
        max_retries=max(0, args.max_retries),
        retry_base=max(0.1, args.retry_base),
        retry_cap=max(1.0, args.retry_cap),
    )
    if args.drive_destination and shutil.which("rclone") is None:
        raise SystemExit("--drive-destination requires rclone. Install it, then run `rclone config` once.")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not args.headful)
        try:
            context = await browser.new_context(storage_state=str(auth_path))
            page = await context.new_page()
            await page.goto(downloader.KAGGLE_COMPETITIONS_URL)
            tokens = {"xsrf": None, "build_hash": None}
            for _ in range(30):
                tokens = await downloader.get_auth_tokens(page)
                if tokens.get("xsrf") and tokens.get("build_hash"):
                    break
                await asyncio.sleep(0.1)
            if not tokens.get("xsrf") or not tokens.get("build_hash"):
                raise SystemExit("Could not read Kaggle session tokens. Run `python login.py` again.")
            client = KaggleClient(page, tokens, settings)
            competitions = await fetch_competitions(client)
            competition = select_competition(competitions, args.competition)
            deadline = competition_deadline(competition, args.end_date)
            now = dt.datetime.now(dt.timezone.utc)
            final_day = deadline.date()
            day = snapshot_date(now, deadline)
            start = parse_datetime(competition.get("enabledDate"))
            if start is not None and now < start:
                raise SystemExit(f"Competition starts on {start.date()}; nothing was downloaded.")
            slug = safe_name(competition.get("competitionName"), str(competition.get("id")))
            competition_root = Path(args.output_dir).expanduser().resolve() / slug
            snapshots = competition_root / ".snapshots"
            snapshot_path = snapshots / f"{day.isoformat()}.json"
            if not snapshot_path.exists():
                players = await fetch_leaderboard(client, competition["id"], args.top)
                atomic_json(
                    snapshot_path,
                    {
                        "competition_id": competition["id"],
                        "competition_slug": slug,
                        "competition_title": competition.get("title"),
                        "deadline": deadline.isoformat(),
                        "snapshot_date": day.isoformat(),
                        "captured_at": now.isoformat(),
                        "top_n": args.top,
                        "players": players,
                    },
                )
                log.info("Captured %d leaderboard players for %s.", len(players), day)
            else:
                log.info("Using saved leaderboard snapshot for %s.", day)

            paths = existing_snapshot_paths(snapshots, final_day)
            if not paths:
                raise SystemExit("No leaderboard snapshots are available to process.")
            records = []
            for path in paths:
                snapshot = load_json(path)
                if snapshot is None:
                    log.error("Skipping unreadable snapshot: %s", path)
                    continue
                snapshot_day = dt.date.fromisoformat(str(snapshot["snapshot_date"]))
                if snapshot_day > final_day:
                    continue
                players = list(snapshot.get("players") or [])[: args.top]
                log.info("Processing %s: %d players.", snapshot_day, len(players))
                for player in players:
                    records.append(
                        await process_player(
                            client,
                            competition_root,
                            snapshot_day.isoformat(),
                            player,
                            settings.max_retries,
                        )
                    )

            if args.drive_destination:
                log.info("All local ZIPs are complete. Starting optional Google Drive upload.")
                for record in records:
                    if record["failed_episodes"]:
                        log.warning("Not uploading incomplete ZIP: %s", record["zip_path"])
                        continue
                    archive_path = Path(record["zip_path"])
                    record["drive_uploaded"] = upload_archive(
                        archive_path,
                        args.drive_destination,
                        slug,
                        archive_path.parent.name,
                    )
                    update_summary(competition_root, record)

            if start is not None:
                captured = {dt.date.fromisoformat(path.stem) for path in paths}
                expected_end = min(now.date(), final_day)
                expected = (expected_end - start.date()).days + 1
                missing = max(0, expected - len(captured))
                if missing:
                    log.warning(
                        "%d competition day(s) have no saved leaderboard snapshot. "
                        "Kaggle does not expose exact past daily standings.",
                        missing,
                    )
            log.info("Done. No snapshot after competition end date %s was processed.", final_day)
        finally:
            await browser.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stderr)
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        log.warning("Stopped. Rerun the same command to resume from saved progress.")
        raise SystemExit(130) from None
    except KaggleRequestError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
