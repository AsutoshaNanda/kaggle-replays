"""Bridge between the FastAPI backend and the Phase 1 ``downloader.py`` module.

``downloader.py`` lives at the project root (one level above ``backend/``) and
exposes the async Kaggle API helpers. This module imports it once and provides
thin, context-aware wrappers plus a couple of backend-only helpers (token
decoding, leaderboard fetch) that reuse the exact same auth conventions.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path

# Make the project-root downloader.py importable without copying its code.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import downloader  # noqa: E402  (intentional post-path-insert import)

from .utils.cache import episode_cache  # noqa: E402


async def open_page(context):
    """Open an authenticated Kaggle page and return ``(page, tokens)``.

    Navigates to the competitions URL (as the original scripts do) and reads the
    XSRF / build-hash cookies via :func:`downloader.get_auth_tokens`.

    Args:
        context: A Playwright ``BrowserContext`` from the session manager.

    Returns:
        ``(page, tokens)`` where ``tokens`` is ``{"xsrf", "build_hash"}``.
    """
    page = await context.new_page()
    await page.goto(downloader.KAGGLE_COMPETITIONS_URL)
    await page.wait_for_timeout(3000)
    tokens = await downloader.get_auth_tokens(page)
    return page, tokens


async def list_competitions(page, tokens) -> dict:
    """Return the raw ListCompetitions response (competitions + userTeams)."""
    return await downloader.fetch_competitions(page, tokens)


async def list_submissions(page, tokens, team_id: str) -> list[dict]:
    """Return submissions for a team."""
    return await downloader.fetch_submissions(page, tokens, team_id)


async def list_episodes(page, tokens, submission_id: str) -> list[dict]:
    """Return episodes for a submission."""
    return await downloader.fetch_episodes(page, tokens, submission_id)


async def list_episodes_checked(page, tokens, submission_id: str) -> tuple[list[dict], str | None]:
    """Return ``(episodes, error)`` for a submission, surfacing API errors.

    Unlike :func:`list_episodes` (which swallows non-200s as an empty list),
    this distinguishes a transient/auth error from a genuinely empty submission
    so the download worker can fail loudly instead of producing nothing.

    Returns:
        ``(episodes, None)`` on success (list may be empty for a real 0-episode
        submission), or ``([], message)`` when the API returned a non-200 such as
        ``429 RESOURCE_EXHAUSTED`` or the session looks expired.
    """
    try:
        resp = await page.evaluate(
            """
        async ({xsrf, buildHash, sid}) => {
            const r = await fetch(
                "/api/i/competitions.EpisodeService/ListEpisodes",
                {
                    method: "POST",
                    headers: {
                        "content-type": "application/json",
                        "x-xsrf-token": xsrf,
                        "x-kaggle-build-version": buildHash
                    },
                    body: JSON.stringify({ submissionId: sid })
                }
            );
            return { status: r.status, text: await r.text() };
        }
        """,
            {"xsrf": tokens["xsrf"], "buildHash": tokens["build_hash"], "sid": str(submission_id)},
        )
    except Exception as exc:  # noqa: BLE001
        return [], f"Episode lookup failed: {exc}"

    status = resp.get("status") if isinstance(resp, dict) else 0
    if status != 200:
        if status == 429:
            return [], "Kaggle is rate-limiting requests (429). Please wait a minute and retry."
        if status in (401, 403):
            return [], "Kaggle session expired. Re-run `python login.py` to reconnect."
        return [], f"Kaggle returned HTTP {status} while listing episodes."
    try:
        import json as _json

        data = _json.loads(resp.get("text") or "{}")
    except (ValueError, TypeError):
        return [], "Could not parse the episode list from Kaggle."
    return data.get("episodes", []), None


_EPISODE_COUNT_DELAY = 0.2  # seconds between sequential ListEpisodes calls


async def _fetch_one_episode_count(page, tokens, submission_id: str) -> int:
    """Return one submission's episode count, or ``-1`` on error/non-200.

    A single ``ListEpisodes`` call. ``-1`` is the "unknown" sentinel (distinct
    from a genuine ``0``), notably for Kaggle ``429 RESOURCE_EXHAUSTED``.
    """
    try:
        resp = await page.evaluate(
            """
        async ({xsrf, buildHash, sid}) => {
            const r = await fetch(
                "/api/i/competitions.EpisodeService/ListEpisodes",
                {
                    method: "POST",
                    headers: {
                        "content-type": "application/json",
                        "x-xsrf-token": xsrf,
                        "x-kaggle-build-version": buildHash
                    },
                    body: JSON.stringify({ submissionId: sid })
                }
            );
            const text = r.status === 200 ? await r.text() : null;
            return { status: r.status, text };
        }
        """,
            {"xsrf": tokens["xsrf"], "buildHash": tokens["build_hash"], "sid": str(submission_id)},
        )
    except Exception:  # noqa: BLE001
        return -1
    if not isinstance(resp, dict) or resp.get("status") != 200 or not resp.get("text"):
        return -1
    try:
        return len(json.loads(resp["text"]).get("episodes", []))
    except (ValueError, TypeError, AttributeError):
        return -1


async def fetch_episode_counts(page, tokens, submission_ids: list[str]) -> dict:
    """Return ``{submission_id: episode_count}`` fetched SEQUENTIALLY + cached.

    Kaggle rate-limits ``ListEpisodes`` aggressively, so this deliberately does
    NOT fire all calls at once (the old ``Promise.all`` burst caused
    ``429 RESOURCE_EXHAUSTED``). Instead it:

    * serves any submission already in :data:`episode_cache` (key
      ``epcount:{id}``) without a network call,
    * fetches the remaining misses ONE AT A TIME with a small delay between
      calls,
    * **stops early on the first 429** and marks every not-yet-fetched
      submission as unknown (``-1``) rather than hammering Kaggle further.

    ``-1`` is the "unknown" sentinel (distinct from a genuine ``0``) so callers
    can avoid clobbering a known count and can render a dash instead of 0.

    Args:
        page: Authenticated Playwright ``Page``.
        tokens: ``{"xsrf", "build_hash"}``.
        submission_ids: Kaggle submission IDs (strings).

    Returns:
        Mapping of submission id -> episode count (``-1`` = unknown/error).
    """
    out: dict[str, int] = {}
    rate_limited = False
    for raw_id in submission_ids:
        sid = str(raw_id)
        cache_key = f"epcount:{sid}"
        cached = await episode_cache.get(cache_key)
        if cached is not None:
            out[sid] = cached
            continue
        if rate_limited:
            out[sid] = -1  # don't keep hitting Kaggle after a 429
            continue
        count = await _fetch_one_episode_count(page, tokens, sid)
        if count < 0:
            # Treat the first failure as a likely rate-limit and back off for
            # the rest of the batch; only cache real successes.
            rate_limited = True
            out[sid] = -1
        else:
            out[sid] = count
            await episode_cache.set(cache_key, count)
            await asyncio.sleep(_EPISODE_COUNT_DELAY)
    return out


def episode_outcome(episode: dict, submission_id) -> str:
    """Classify an episode's outcome using the Phase 1 logic (zero fetch)."""
    return downloader.determine_outcome(episode, None, submission_id)


def _to_int(value) -> int:
    """Best-effort int parse (used to order episodes by recency); else 0."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float_score(raw) -> float | None:
    """Parse a Kaggle score value (number or ``{"value": ...}``) into a float."""
    if isinstance(raw, dict):
        raw = raw.get("value")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def latest_skill_rating(episodes: list[dict], submission_id) -> float | None:
    """Return the submitting agent's skill rating from the MOST RECENT episode.

    For simulation competitions the per-submission score shown on Kaggle is the
    agent's rating (``updatedScore``), NOT ``publicScoreFormatted`` (which is
    ``"0"``/empty there). Episodes are ordered by ``id`` (Kaggle episode IDs
    increase over time), and we take the newest episode whose ``agents[]`` entry
    matches this ``submission_id``. Falls back to ``initialScore``; ``None`` if
    no rating is present.
    """
    sid = str(submission_id)
    for ep in sorted(episodes, key=lambda e: _to_int(e.get("id")), reverse=True):
        agent = next(
            (a for a in (ep.get("agents") or []) if str(a.get("submissionId")) == sid),
            None,
        )
        if agent is None:
            continue
        val = _to_float_score(agent.get("updatedScore"))
        if val is None:
            val = _to_float_score(agent.get("initialScore"))
        if val is not None:
            return val
    return None


async def fetch_submission_episode_data(page, tokens, submission_id: str) -> dict:
    """Fetch a submission's episodes ONCE and derive everything the UI caches.

    Returns ``{"episodes": [{"id","outcome"}, ...], "count": int,
    "score": float|None, "error": str|None}``. ``count`` is ``-1`` (unknown) on
    error/429 — distinct from a genuine ``0``. ``score`` is the latest-episode
    skill rating (see :func:`latest_skill_rating`). One ``ListEpisodes`` call.
    """
    episodes, error = await list_episodes_checked(page, tokens, submission_id)
    if error is not None:
        return {"episodes": [], "count": -1, "score": None, "error": error}
    items = [
        {"id": str(ep.get("id")), "outcome": episode_outcome(ep, submission_id)}
        for ep in episodes
    ]
    return {
        "episodes": items,
        "count": len(items),
        "score": latest_skill_rating(episodes, submission_id),
        "error": None,
    }


def decode_client_token(storage_state_path: Path) -> dict:
    """Extract Kaggle identity claims from the ``CLIENT-TOKEN`` cookie JWT.

    The Kaggle ``CLIENT-TOKEN`` cookie is a JWT whose payload includes ``sub``
    (the username handle), ``displayName``, ``thumbnailUrl``, ``profileUrl`` and
    ``tier``. Reading it avoids an extra API round-trip to learn who just logged
    in and to populate their profile.

    Args:
        storage_state_path: Path to a Playwright ``auth.json``.

    Returns:
        ``{"kaggle_user", "display_name", "thumbnail_url", "profile_url",
        "tier"}`` (values may be ``None``).
    """
    empty = {
        "kaggle_user": None,
        "display_name": None,
        "thumbnail_url": None,
        "profile_url": None,
        "tier": None,
    }
    try:
        state = json.loads(Path(storage_state_path).read_text())
    except (OSError, ValueError):
        return dict(empty)

    token = next(
        (c.get("value", "") for c in state.get("cookies", []) if c.get("name") == "CLIENT-TOKEN"),
        "",
    )
    parts = token.split(".")
    if len(parts) < 2:
        return dict(empty)
    try:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(pad))
    except (ValueError, json.JSONDecodeError):
        return dict(empty)
    return {
        "kaggle_user": claims.get("sub"),
        "display_name": claims.get("displayName"),
        "thumbnail_url": claims.get("thumbnailUrl"),
        "profile_url": claims.get("profileUrl"),
        "tier": claims.get("tier"),
    }


async def fetch_leaderboard(page, tokens, competition_id) -> dict:
    """Fetch a competition's public leaderboard via the Kaggle internal API.

    Endpoint, payload, and response shape were confirmed by live request
    interception (the leaderboard page issues exactly this call)::

        POST /api/i/competitions.LeaderboardService/GetLeaderboard
        body: {"competitionId": <int>, "leaderboardMode": "LEADERBOARD_MODE_DEFAULT"}
        resp: {"publicLeaderboard": [{teamId, submissionId, rank, displayScore,
                                      medal, inTheMoney}, ...],
               "teams": [{teamId, teamName, ...}, ...]}

    Args:
        page: Authenticated Playwright ``Page``.
        tokens: ``{"xsrf", "build_hash"}``.
        competition_id: The **numeric** Kaggle competition ID (not the slug).

    Returns:
        ``{"status": int, "text": str}`` (raw), or ``{}`` on error.
    """
    try:
        return await page.evaluate(
            """
        async ({xsrf, buildHash, competitionId}) => {
            const r = await fetch(
                "/api/i/competitions.LeaderboardService/GetLeaderboard",
                {
                    method: "POST",
                    headers: {
                        "content-type": "application/json",
                        "x-xsrf-token": xsrf,
                        "x-kaggle-build-version": buildHash
                    },
                    body: JSON.stringify({
                        competitionId: competitionId,
                        leaderboardMode: "LEADERBOARD_MODE_DEFAULT"
                    })
                }
            );
            return { status: r.status, text: await r.text() };
        }
        """,
            {"xsrf": tokens["xsrf"], "buildHash": tokens["build_hash"], "competitionId": int(competition_id)},
        )
    except Exception:  # noqa: BLE001
        return {}
