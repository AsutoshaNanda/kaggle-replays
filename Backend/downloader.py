"""Kaggle Replay Downloader — async, concurrent, resumable replay fetcher.

A modular refactor of ``submission_2.py`` built on ``playwright.async_api``.
It preserves the *exact* Kaggle internal API calls, request headers,
auth-token extraction, request payloads, and on-disk layout of the original
script, while adding:

* concurrent batch downloads (``Promise.all`` inside one browser context),
* retry-with-exponential-backoff on HTTP failures,
* skip-already-downloaded resume behaviour,
* episode-outcome filtering (all / win / lose / draw),
* ZIP packaging (json / zip / both),
* a bulk "download every submission" mode,
* a proper ``argparse`` CLI with an ``--inspect`` discovery mode.

Authentication is reused from ``auth.json`` (a Playwright storage state created
by ``login.py``) exactly as the original did. No credentials, tokens, or
competition IDs are stored in this file — the XSRF and build-hash tokens are
read from the live browser cookies at runtime.

Usage::

    python downloader.py --help
    python downloader.py --headless --inspect
    python downloader.py --headless --filter win --format zip
    python downloader.py --headless --bulk
"""

# ---------------------------------------------------------------------------
# 1. IMPORTS — stdlib first, then playwright, then optional tqdm
# ---------------------------------------------------------------------------
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import shutil
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

try:  # Optional dependency — degrade gracefully to a manual progress bar.
    from tqdm import tqdm

    _HAS_TQDM = True
except ImportError:  # pragma: no cover - exercised only when tqdm is absent
    _HAS_TQDM = False


# ---------------------------------------------------------------------------
# 2. CONSTANTS
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(message)s"
DEFAULT_BATCH_SIZE = 10          # replays fetched concurrently per evaluate() call
MAX_RETRIES = 3                  # retry attempts per failed episode
RETRY_DELAY_BASE = 2             # seconds; backoff = RETRY_DELAY_BASE * 2 ** attempt
MAX_WORKERS = 5                  # reserved for the multi-context pool (see improvements.md)

# Exact Kaggle endpoints / navigation target preserved from submission_2.py.
KAGGLE_COMPETITIONS_URL = "https://www.kaggle.com/competitions"
API_LIST_COMPETITIONS = "/api/i/competitions.CompetitionService/ListCompetitions"
API_LIST_SUBMISSIONS = "/api/i/competitions.SubmissionService/ListSubmissions"
API_LIST_EPISODES = "/api/i/competitions.EpisodeService/ListEpisodes"
REPLAY_PATH_TEMPLATE = "/competitions/episodes/{id}/replay.json"  # documentation only

log = logging.getLogger("downloader")


# ---------------------------------------------------------------------------
# 3. setup_logging
# ---------------------------------------------------------------------------
def setup_logging(level: str) -> logging.Logger:
    """Configure and return the module logger.

    Diagnostic output goes to ``stderr`` so that ``stdout`` stays clean for the
    interactive menus, progress bar, and summaries.

    Args:
        level: A logging level name such as ``"INFO"`` or ``"DEBUG"``.

    Returns:
        The configured :class:`logging.Logger` named ``"downloader"``.
    """
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric, format=LOG_FORMAT, stream=sys.stderr)
    return logging.getLogger("downloader")


# ---------------------------------------------------------------------------
# 4. parse_args
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        The populated :class:`argparse.Namespace`.

    Notes:
        ``--competition`` and ``--submission`` take the **1-based index** shown
        in the interactive menus (not the Kaggle numeric ID), so a fully
        non-interactive run can be scripted, e.g. ``--competition 1
        --submission 3``.
    """
    parser = argparse.ArgumentParser(
        prog="downloader.py",
        description="Download Kaggle competition episode replays concurrently.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--competition", type=int, default=None,
        help="1-based index of the competition to use (skips the menu).",
    )
    parser.add_argument(
        "--submission", type=int, default=None,
        help="1-based index of the submission to use (skips the menu).",
    )
    parser.add_argument(
        "--filter", choices=["all", "win", "lose", "draw"], default="all",
        help="Only download episodes with this outcome.",
    )
    parser.add_argument(
        "--format", dest="format", choices=["json", "zip", "both"], default="json",
        help="Save individual JSONs, a single ZIP, or both.",
    )
    parser.add_argument(
        "--bulk", action="store_true",
        help="Download replays for EVERY submission in the competition.",
    )
    parser.add_argument(
        "--headless", action="store_true", default=True,
        help="Run Chromium headless (default).",
    )
    parser.add_argument(
        "--inspect", action="store_true",
        help="Print the first episode + replay JSON structure, then exit.",
    )
    parser.add_argument(
        "--output-dir", dest="output_dir", default="downloads",
        help="Base directory for downloaded replays.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# 5. get_auth_tokens
# ---------------------------------------------------------------------------
async def get_auth_tokens(page) -> dict:
    """Read the XSRF and build-hash tokens from the page cookies.

    Uses the *exact* JavaScript cookie-matching expressions from the original
    scripts so the values are identical to a real browser session.

    Args:
        page: An authenticated Playwright ``Page`` on kaggle.com.

    Returns:
        ``{"xsrf": <str|None>, "build_hash": <str|None>}``.
    """
    xsrf = await page.evaluate(
        """
    () => document.cookie.match(/XSRF-TOKEN=([^;]+)/)?.[1]
    """
    )
    build_hash = await page.evaluate(
        """
    () => document.cookie.match(/build-hash=([^;]+)/)?.[1]
    """
    )
    return {"xsrf": xsrf, "build_hash": build_hash}


# ---------------------------------------------------------------------------
# 6. fetch_competitions
# ---------------------------------------------------------------------------
async def fetch_competitions(page, tokens: dict) -> dict:
    """Fetch the user's entered competitions via the Kaggle internal API.

    Payload, endpoint, and headers are byte-for-byte identical to
    ``submission_2.py`` (``LIST_OPTION_USER_ENTERED`` / readMask
    ``competitions,userTeams``).

    Args:
        page: Authenticated Playwright ``Page``.
        tokens: Mapping with ``xsrf`` and ``build_hash`` keys.

    Returns:
        The raw decoded API response (``{"competitions": [...],
        "userTeams": [...]}``) or ``{}`` on error.
    """
    try:
        return await page.evaluate(
            """
        async ({xsrf, buildHash}) => {
            const r = await fetch(
                "/api/i/competitions.CompetitionService/ListCompetitions",
                {
                    method: "POST",
                    headers: {
                        "content-type": "application/json",
                        "x-xsrf-token": xsrf,
                        "x-kaggle-build-version": buildHash
                    },
                    body: JSON.stringify({
                        selector: {
                            competitionIds: [],
                            listOption: "LIST_OPTION_USER_ENTERED",
                            sortOption: "SORT_OPTION_NUM_TEAMS",
                            hostSegmentIdFilter: 0,
                            searchQuery: "",
                            prestigeFilter: "PRESTIGE_FILTER_UNSPECIFIED",
                            visibilityFilter: "VISIBILITY_FILTER_UNSPECIFIED",
                            participationFilter: "PARTICIPATION_FILTER_UNSPECIFIED",
                            tagIds: [],
                            excludeTagIds: [],
                            requireSimulations: false,
                            requireKernels: false,
                            requireHackathons: false
                        },
                        pageToken: "",
                        pageSize: 50,
                        readMask: "competitions,userTeams"
                    })
                }
            );

            return await r.json();
        }
        """,
            {"xsrf": tokens["xsrf"], "buildHash": tokens["build_hash"]},
        )
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        log.error("ListCompetitions request failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# 7. fetch_submissions
# ---------------------------------------------------------------------------
async def fetch_submissions(page, tokens: dict, team_id: str) -> list[dict]:
    """Fetch all submissions for a team via the Kaggle internal API.

    Args:
        page: Authenticated Playwright ``Page``.
        tokens: Mapping with ``xsrf`` and ``build_hash`` keys.
        team_id: The Kaggle team ID for the chosen competition.

    Returns:
        A list of submission dicts (possibly empty).
    """
    try:
        resp = await page.evaluate(
            """
        async ({xsrf, buildHash, teamId}) => {
            const r = await fetch(
                "/api/i/competitions.SubmissionService/ListSubmissions",
                {
                    method: "POST",
                    headers: {
                        "content-type": "application/json",
                        "x-xsrf-token": xsrf,
                        "x-kaggle-build-version": buildHash
                    },
                    body: JSON.stringify({
                        teamId: teamId,
                        pageSize: 50,
                        pageToken: "",
                        selector: {
                            listOption: "LIST_OPTION_DEFAULT",
                            sortOption: "SORT_OPTION_DEFAULT",
                            submissionIds: []
                        }
                    })
                }
            );

            return await r.json();
        }
        """,
            {"xsrf": tokens["xsrf"], "buildHash": tokens["build_hash"], "teamId": team_id},
        )
    except Exception as exc:  # noqa: BLE001
        log.error("ListSubmissions request failed: %s", exc)
        return []
    return resp.get("submissions", []) if isinstance(resp, dict) else []


# ---------------------------------------------------------------------------
# 8. fetch_episodes
# ---------------------------------------------------------------------------
async def fetch_episodes(page, tokens: dict, submission_id: str) -> list[dict]:
    """Fetch all episodes for a submission via the Kaggle internal API.

    Args:
        page: Authenticated Playwright ``Page``.
        tokens: Mapping with ``xsrf`` and ``build_hash`` keys.
        submission_id: The Kaggle submission ID.

    Returns:
        A list of episode dicts (possibly empty).
    """
    try:
        resp = await page.evaluate(
            """
        async ({xsrf, buildHash, submissionId}) => {
            const r = await fetch(
                "/api/i/competitions.EpisodeService/ListEpisodes",
                {
                    method: "POST",
                    headers: {
                        "content-type": "application/json",
                        "x-xsrf-token": xsrf,
                        "x-kaggle-build-version": buildHash
                    },
                    body: JSON.stringify({
                        submissionId: submissionId
                    })
                }
            );

            return await r.json();
        }
        """,
            {"xsrf": tokens["xsrf"], "buildHash": tokens["build_hash"], "submissionId": submission_id},
        )
    except Exception as exc:  # noqa: BLE001
        log.error("ListEpisodes request failed: %s", exc)
        return []
    return resp.get("episodes", []) if isinstance(resp, dict) else []


# ---------------------------------------------------------------------------
# 9. fetch_replay_batch
# ---------------------------------------------------------------------------
async def fetch_replay_batch(page, episode_ids: list[str]) -> list[dict]:
    """Fetch a batch of replay JSON documents concurrently in one round-trip.

    Runs ``Promise.all`` inside a single ``page.evaluate`` so all requests in
    the batch share the one authenticated browser context. The replay endpoint
    (``/competitions/episodes/{id}/replay.json``) is identical to the original.

    Args:
        page: Authenticated Playwright ``Page``.
        episode_ids: Up to :data:`DEFAULT_BATCH_SIZE` episode IDs.

    Returns:
        A list of ``{"id", "status", "text"}`` dicts (``text`` is ``None`` on
        non-200 responses; ``status`` is ``0`` if the fetch itself threw).
    """
    try:
        return await page.evaluate(
            """
        async (episodeIds) => {
            const results = await Promise.all(
                episodeIds.map(async (id) => {
                    try {
                        const r = await fetch(`/competitions/episodes/${id}/replay.json`);
                        const text = r.status === 200 ? await r.text() : null;
                        return { id, status: r.status, text };
                    } catch (e) {
                        return { id, status: 0, text: null, error: e.message };
                    }
                })
            );
            return results;
        }
        """,
            episode_ids,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Replay batch request failed: %s", exc)
        return [{"id": eid, "status": 0, "text": None} for eid in episode_ids]


# ---------------------------------------------------------------------------
# 10. determine_outcome
# ---------------------------------------------------------------------------
def determine_outcome(episode: dict, replay_text, submission_id=None) -> str:
    """Classify an episode as ``'win'``, ``'lose'``, ``'draw'`` or ``'unknown'``.

    CONFIRMED FIELD MAPPING (verified via ``--inspect`` on Orbit Wars)
    -----------------------------------------------------------------
    Each episode dict carries an ``agents`` list, one entry per competing agent,
    of the shape::

        {"id", "submissionId", "reward", "index"?, "initialScore",
         "updatedScore", "teamId"}

    The *submitting* agent is the one whose ``submissionId`` equals the
    submission being downloaded. Its terminal ``reward`` (e.g. ``+1`` / ``-1``),
    compared against the best ``reward`` among the other agents, decides the
    outcome:

    * my reward  >  best other  → ``'win'``
    * my reward  <  best other  → ``'lose'``
    * my reward  == best other  → ``'draw'`` (tied at the top)

    Because the rewards live in the episode dict itself, outcome is determined
    with **zero extra replay fetches** — ``replay_text`` is only used as a
    fallback (the replay's top-level ``rewards`` array, indexed by agent order)
    when ``agents`` is unavailable.

    Args:
        episode: The episode dict from :func:`fetch_episodes`.
        replay_text: The raw replay JSON string, or ``None`` for the (preferred)
            dict-only zero-fetch check.
        submission_id: The submitting submission's ID. Required to identify
            which agent is "ours"; without it this returns ``'unknown'``.

    Returns:
        One of ``'win'``, ``'lose'``, ``'draw'``, ``'unknown'``.

    Note:
        ``submission_id`` extends the original two-argument signature: the
        submitting agent cannot be identified from the episode dict alone.
    """
    agents = episode.get("agents")

    # 1) Self-describing string field on the episode (defensive; not seen in the
    #    Orbit Wars schema but cheap and harmless to support).
    for key in ("outcome", "result"):
        val = episode.get(key)
        if isinstance(val, str):
            low = val.strip().lower()
            if low in ("win", "won"):
                return "win"
            if low in ("lose", "loss", "lost"):
                return "lose"
            if low in ("draw", "tie", "tied"):
                return "draw"

    # 2) PRIMARY (confirmed): terminal rewards on episode["agents"]. No fetch.
    if isinstance(agents, list) and agents and submission_id is not None:
        mine = next(
            (a for a in agents if str(a.get("submissionId")) == str(submission_id)),
            None,
        )
        if mine is not None and mine.get("reward") is not None:
            verdict = _verdict_from_rewards(
                mine["reward"],
                [a.get("reward") for a in agents if a is not mine],
            )
            if verdict is not None:
                return verdict

    # 3) FALLBACK: replay JSON top-level rewards, indexed by agent order.
    if replay_text and isinstance(agents, list) and submission_id is not None:
        idx = next(
            (i for i, a in enumerate(agents)
             if str(a.get("submissionId")) == str(submission_id)),
            None,
        )
        if idx is not None:
            try:
                rewards = json.loads(replay_text).get("rewards")
            except (ValueError, TypeError, AttributeError):
                rewards = None
            if isinstance(rewards, list) and 0 <= idx < len(rewards):
                verdict = _verdict_from_rewards(
                    rewards[idx], [r for i, r in enumerate(rewards) if i != idx]
                )
                if verdict is not None:
                    return verdict

    return "unknown"


def _verdict_from_rewards(my_reward, other_rewards):
    """Return ``'win'`` / ``'lose'`` / ``'draw'`` from rewards, or ``None``.

    A tie with the best opponent counts as a ``'draw'`` (per project decision).
    Returns ``None`` (→ caller reports ``'unknown'``) if rewards are missing.
    """
    others = [r for r in other_rewards if r is not None]
    if my_reward is None or not others:
        return None
    best_other = max(others)
    if my_reward > best_other:
        return "win"
    if my_reward < best_other:
        return "lose"
    return "draw"


# ---------------------------------------------------------------------------
# 11. make_output_dir
# ---------------------------------------------------------------------------
def make_output_dir(base: str, competition_slug: str, submission_name: str) -> Path:
    """Build (and create) the output directory, guarding against path traversal.

    Layout matches the original: ``{base}/{slug}/{name}_replays/``.

    Args:
        base: Base downloads directory (e.g. ``"downloads"``).
        competition_slug: The competition ``competitionName`` slug.
        submission_name: The (already human-readable) submission title.

    Returns:
        The resolved, created :class:`pathlib.Path`.

    Raises:
        ValueError: If the resolved path escapes ``base`` (traversal attempt).
    """
    base_path = Path(base).resolve()
    slug = sanitize_filename(competition_slug)
    name = sanitize_filename(submission_name)
    candidate = (base_path / slug / f"{name}_replays").resolve()
    if not candidate.is_relative_to(base_path):
        raise ValueError(f"Refusing path outside base downloads dir: {candidate}")
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


# ---------------------------------------------------------------------------
# 12. sanitize_filename
# ---------------------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a path component.

    Strips ``.py`` / ``.zip`` / ``.tar.gz`` extensions, replaces spaces with
    underscores, and keeps only ``[A-Za-z0-9_-]``.

    Args:
        name: The raw name (e.g. a submission title).

    Returns:
        A sanitized component, never empty (falls back to ``"unnamed"``).
    """
    name = name or ""
    for ext in (".tar.gz", ".zip", ".py"):
        if name.endswith(ext):
            name = name[: -len(ext)]
            break
    name = name.replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_-]", "", name)
    return name or "unnamed"


# --- private I/O + progress helpers (used by download_submission_replays) ---
def _save_replay(output_dir: Path, episode_id: str, text: str) -> None:
    """Write one replay JSON to ``{output_dir}/{episode_id}.json``."""
    (output_dir / f"{episode_id}.json").write_text(text, encoding="utf-8")


def _write_failed(output_dir: Path, failures: list[tuple]) -> None:
    """Append ``id<TAB>status`` lines for permanently failed episodes."""
    path = output_dir / "failed_episodes.txt"
    with path.open("a", encoding="utf-8") as handle:
        for episode_id, status in failures:
            handle.write(f"{episode_id}\t{status}\n")


def _make_progress(total: int):
    """Return a tqdm bar if available, else a tiny dict-based manual tracker."""
    if _HAS_TQDM:
        return tqdm(total=total, unit="replay")
    return {"done": 0, "total": total}


def _progress_update(progress, episode_id: str, status: str) -> None:
    """Advance the progress display by one item."""
    if _HAS_TQDM:
        progress.update(1)
        progress.set_postfix_str(f"{episode_id} {status}")
        return
    progress["done"] += 1
    done, total = progress["done"], progress["total"]
    pct = int(done / total * 100) if total else 100
    bar_len = 24
    filled = int(bar_len * done / total) if total else bar_len
    bar = "#" * filled + "-" * (bar_len - filled)
    sys.stdout.write(f"\r[{done}/{total}] {bar} {pct}% | {episode_id} {status}   ")
    sys.stdout.flush()


def _progress_close(progress) -> None:
    """Finish the progress display cleanly."""
    if _HAS_TQDM:
        progress.close()
    else:
        sys.stdout.write("\n")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# 13. download_submission_replays
# ---------------------------------------------------------------------------
async def download_submission_replays(
    page, tokens: dict, competition: dict, submission: dict, args, base_dir: str
) -> dict:
    """Download (and optionally ZIP) every matching replay for one submission.

    Pipeline: fetch episodes → apply outcome filter → skip already-downloaded →
    batch-fetch replays with retry/backoff → save to disk → package.

    Args:
        page: Authenticated Playwright ``Page``.
        tokens: Mapping with ``xsrf`` and ``build_hash`` keys.
        competition: The selected competition dict.
        submission: The selected submission dict.
        args: Parsed CLI namespace (``filter``, ``format`` are read here).
        base_dir: Base downloads directory.

    Returns:
        ``{"downloaded": int, "skipped": int, "failed": int}``.
    """
    start = time.time()
    slug = competition.get("competitionName", "competition")
    submission_id = submission["id"]
    submission_name = sanitize_filename(submission.get("title", str(submission_id)))
    output_dir = make_output_dir(base_dir, slug, submission_name)
    filter_mode = args.filter

    episodes = await fetch_episodes(page, tokens, submission_id)
    id_to_ep = {ep["id"]: ep for ep in episodes}

    # Skip episodes already on disk (resume behaviour).
    skipped = 0
    to_fetch: list[str] = []
    for episode_id in id_to_ep:
        if (output_dir / f"{episode_id}.json").exists():
            skipped += 1
        else:
            to_fetch.append(episode_id)
    if skipped:
        log.info("Skipping %d already-downloaded episode(s).", skipped)

    # Outcome filtering is EXACT and FREE here: the episode dict already carries
    # each agent's terminal reward, so we partition before any replay fetch.
    stats = {"unknown": 0, "filtered": 0}
    if filter_mode != "all":
        kept = []
        for episode_id in to_fetch:
            verdict = determine_outcome(id_to_ep[episode_id], None, submission_id)
            if verdict == filter_mode:
                kept.append(episode_id)
            elif verdict == "unknown":
                stats["unknown"] += 1
            else:
                stats["filtered"] += 1
        to_fetch = kept

    downloaded = 0
    failures: list[tuple] = []
    progress = _make_progress(len(to_fetch))

    def handle(result: dict, track: bool) -> None:
        # Episodes are already outcome-filtered, so every 200-OK is saved.
        # ``track`` advances the progress bar on the initial pass only; retries
        # report via log lines so the bar never runs past 100%.
        nonlocal downloaded
        episode_id = result["id"]
        status = result.get("status")
        text = result.get("text")
        if status == 200 and text is not None:
            _save_replay(output_dir, episode_id, text)
            downloaded += 1
            if track:
                _progress_update(progress, episode_id, "ok")
        else:
            failures.append((episode_id, status))
            if track:
                _progress_update(progress, episode_id, f"err{status}")

    for batch in _chunks(to_fetch, DEFAULT_BATCH_SIZE):
        for result in await fetch_replay_batch(page, batch):
            handle(result, track=True)
    _progress_close(progress)

    # Retry only the genuine HTTP failures with exponential backoff.
    for attempt in range(1, MAX_RETRIES + 1):
        if not failures:
            break
        delay = RETRY_DELAY_BASE * (2 ** attempt)
        retry_ids = [eid for eid, _ in failures]
        failures = []
        log.warning(
            "Retry %d/%d for %d episode(s) after %ds backoff.",
            attempt, MAX_RETRIES, len(retry_ids), delay,
        )
        await asyncio.sleep(delay)
        for batch in _chunks(retry_ids, DEFAULT_BATCH_SIZE):
            for result in await fetch_replay_batch(page, batch):
                handle(result, track=False)
        recovered = len(retry_ids) - len(failures)
        if recovered:
            log.info("Recovered %d episode(s) on retry %d.", recovered, attempt)

    failed = len(failures)
    if failures:
        _write_failed(output_dir, failures)
        log.error("%d episode(s) failed permanently — see failed_episodes.txt", failed)

    zip_path = _package(output_dir, args.format)

    elapsed = time.time() - start
    _print_submission_summary(
        competition, submission_name, output_dir, zip_path,
        downloaded, skipped, failed, stats, filter_mode, elapsed,
    )
    return {"downloaded": downloaded, "skipped": skipped, "failed": failed}


def _chunks(items: list, size: int):
    """Yield successive ``size``-length slices of ``items``."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _package(output_dir: Path, fmt: str):
    """Create a ZIP archive per ``--format``; return the ZIP path or ``None``.

    For ``zip`` the individual JSON files are removed afterwards; for ``both``
    they are kept alongside the archive.
    """
    if fmt not in ("zip", "both"):
        return None
    archive = shutil.make_archive(str(output_dir), "zip", root_dir=str(output_dir))
    zip_path = Path(archive)
    if fmt == "zip":
        for json_file in output_dir.glob("*.json"):
            json_file.unlink()
    return zip_path


def _print_submission_summary(
    competition, submission_name, output_dir, zip_path,
    downloaded, skipped, failed, stats, filter_mode, elapsed,
) -> None:
    """Print the per-submission ✅ summary block."""
    print(f"\n✅ {competition.get('title', '?')} / {submission_name}")
    print(f"   Downloaded : {downloaded}")
    print(f"   Skipped    : {skipped} (already existed)")
    print(f"   Failed     : {failed}")
    if filter_mode != "all":
        print(f"   Filtered   : {stats['filtered']} (outcome != {filter_mode})")
        print(f"   Unknown    : {stats['unknown']} (outcome undetermined)")
    print(f"   Output     : {output_dir}/")
    if zip_path is not None:
        print(f"   ZIP        : {zip_path}")
    print(f"   Time       : {elapsed:.1f}s")
    if filter_mode != "all" and downloaded == 0 and stats["unknown"] > 0:
        print(
            f"   ⚠ No episodes matched '{filter_mode}'. {stats['unknown']} "
            f"episode(s) had no determinable outcome (missing agent rewards — "
            f"e.g. still-running or errored episodes)."
        )


# ---------------------------------------------------------------------------
# 14. download_all_submissions
# ---------------------------------------------------------------------------
async def download_all_submissions(page, tokens: dict, competition: dict, args) -> None:
    """Bulk mode: download replays for every submission in a competition.

    Shows a summary table with per-submission episode counts, asks for explicit
    confirmation, then iterates :func:`download_submission_replays` and prints an
    aggregate summary.

    Args:
        page: Authenticated Playwright ``Page``.
        tokens: Mapping with ``xsrf`` and ``build_hash`` keys.
        competition: Selected competition dict; must carry ``_team_id`` (set by
            :func:`main` from the matching user team).
        args: Parsed CLI namespace.
    """
    team_id = competition.get("_team_id")
    submissions = await fetch_submissions(page, tokens, team_id)
    if not submissions:
        print("No submissions found for this competition.")
        return

    # Pre-fetch episode counts (cheap list calls) for the summary table.
    counts = [len(await fetch_episodes(page, tokens, s["id"])) for s in submissions]

    print(f"\nCompetition: {competition.get('title', '?')}")
    print("─" * 47)
    print("  # │ Score    │ Submission Name     │ Episodes")
    for i, (sub, count) in enumerate(zip(submissions, counts), start=1):
        score = str(sub.get("publicScoreFormatted", "-"))
        name = sanitize_filename(sub.get("title", ""))[:19]
        print(f"  {i} │ {score:<8} │ {name:<19} │ {count}")
    print("─" * 47)
    total = sum(counts)
    print(f"TOTAL: {total} episodes across {len(submissions)} submissions")

    confirm = input(
        f"WARNING: This will download ~{total} replay files. Continue? [y/N]: "
    ).strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        return

    aggregate = {"downloaded": 0, "skipped": 0, "failed": 0}
    for sub in submissions:
        result = await download_submission_replays(
            page, tokens, competition, sub, args, args.output_dir
        )
        for key in aggregate:
            aggregate[key] += result[key]

    print("\n=== Bulk Summary ===")
    print(f"Submissions : {len(submissions)}")
    print(f"Downloaded  : {aggregate['downloaded']}")
    print(f"Skipped     : {aggregate['skipped']}")
    print(f"Failed      : {aggregate['failed']}")


# ---------------------------------------------------------------------------
# 15. interactive_select_competition
# ---------------------------------------------------------------------------
def interactive_select_competition(competitions_data: dict, preselect: int = None):
    """Choose a competition (and its user team) from the API response.

    Args:
        competitions_data: Raw :func:`fetch_competitions` response.
        preselect: Optional 1-based index (from ``--competition``) that skips the
            interactive prompt.

    Returns:
        ``(competition_dict, team_dict_or_None)``.

    Raises:
        SystemExit: If no competitions are available.
    """
    competitions = competitions_data.get("competitions", [])
    teams = competitions_data.get("userTeams", [])
    if not competitions:
        raise SystemExit(
            "No competitions returned — auth.json is likely empty or expired. "
            "Run `python login.py` to refresh the session."
        )

    if preselect is not None:
        index = preselect
    else:
        print("\nCompetitions:\n")
        for i, comp in enumerate(competitions, start=1):
            print(f"{i}. {comp['title']} ({comp['competitionName']})")
        index = int(input("\nSelect competition: "))

    competition = competitions[index - 1]
    team = next((t for t in teams if t["competitionId"] == competition["id"]), None)
    return competition, team


# ---------------------------------------------------------------------------
# 16. interactive_select_submission
# ---------------------------------------------------------------------------
def interactive_select_submission(submission_list: list[dict], preselect: int = None) -> dict:
    """Choose a submission from the list.

    Args:
        submission_list: Submissions from :func:`fetch_submissions`.
        preselect: Optional 1-based index (from ``--submission``) that skips the
            interactive prompt.

    Returns:
        The selected submission dict.

    Raises:
        SystemExit: If the list is empty.
    """
    if not submission_list:
        raise SystemExit("No submissions found for this competition.")

    if preselect is not None:
        index = preselect
    else:
        print("\nSubmissions:\n")
        for i, sub in enumerate(submission_list, start=1):
            score = sub.get("publicScoreFormatted", "-")
            print(f"{i}. {score} | {sub['title']}")
        index = int(input("\nSelect submission: "))

    selected = submission_list[index - 1]
    print("\nSelected Submission")
    print("ID   :", selected["id"])
    print("Score:", selected.get("publicScoreFormatted", "-"))
    print("Name :", selected["title"])
    return selected


async def _run_inspect(page, tokens: dict, competitions_data: dict, args) -> None:
    """Implement ``--inspect``: dump episode + replay structure, then return.

    Prints ``episode_list[0]`` and the first 3000 characters of the first
    episode's replay JSON so the real outcome field names can be confirmed
    before :func:`determine_outcome` is finalised.
    """
    competition, team = interactive_select_competition(competitions_data, args.competition)
    if team is None:
        print("No user team found for this competition — cannot list submissions.")
        return
    submissions = await fetch_submissions(page, tokens, team["id"])
    submission = interactive_select_submission(submissions, args.submission)

    episodes = await fetch_episodes(page, tokens, submission["id"])
    if not episodes:
        print("No episodes found for this submission.")
        return

    print("\n=== EPISODE[0] STRUCTURE ===")
    print(json.dumps(episodes[0], indent=2))

    first_id = episodes[0]["id"]
    results = await fetch_replay_batch(page, [first_id])
    replay_text = results[0].get("text") if results else None
    print("\n=== REPLAY JSON (first 3000 chars) ===")
    print((replay_text or "<no replay text returned>")[:3000])

    print(
        "\nINSPECT COMPLETE — check field names above, then re-run without "
        "--inspect and with --filter win/lose"
    )


# ---------------------------------------------------------------------------
# 17. main
# ---------------------------------------------------------------------------
async def main() -> None:
    """CLI entry point: set up Playwright, authenticate, and dispatch the flow."""
    args = parse_args()
    setup_logging("INFO")

    auth_path = Path("auth.json")
    if not auth_path.exists() or auth_path.stat().st_size == 0:
        log.error(
            "auth.json is missing or empty. Run `python login.py` first to "
            "create a Kaggle browser session, then re-run this script."
        )
        sys.exit(1)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=args.headless)
        try:
            context = await browser.new_context(storage_state="auth.json")
        except Exception as exc:  # noqa: BLE001
            log.error("Could not load auth.json (%s). Re-run `python login.py`.", exc)
            await browser.close()
            sys.exit(1)

        page = await context.new_page()
        await page.goto(KAGGLE_COMPETITIONS_URL)
        await page.wait_for_timeout(3000)

        tokens = await get_auth_tokens(page)
        if not tokens.get("xsrf") or not tokens.get("build_hash"):
            log.error(
                "Could not read XSRF / build-hash cookies — the session has "
                "likely expired. Re-run `python login.py`."
            )
            await browser.close()
            sys.exit(1)

        competitions_data = await fetch_competitions(page, tokens)

        if args.inspect:
            await _run_inspect(page, tokens, competitions_data, args)
            await browser.close()
            sys.exit(0)

        competition, team = interactive_select_competition(competitions_data, args.competition)
        if team is None:
            log.error(
                "No user team found for '%s' — cannot list submissions.",
                competition.get("competitionName"),
            )
            await browser.close()
            sys.exit(1)
        competition["_team_id"] = team["id"]

        if args.bulk:
            await download_all_submissions(page, tokens, competition, args)
        else:
            submissions = await fetch_submissions(page, tokens, team["id"])
            submission = interactive_select_submission(submissions, args.submission)
            await download_submission_replays(
                page, tokens, competition, submission, args, args.output_dir
            )

        await browser.close()


# ---------------------------------------------------------------------------
# 18. entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(main())
