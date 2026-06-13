"""Kaggle internal-API client for the Collections feature.

All endpoints below were proven by live probes (2026-06-11) against the
authenticated session, using the same fetch-inside-Playwright mechanism as
``kaggle_service.py``:

* ``users.CollectionsService/ListCollections`` — body ``{}`` →
  ``{"collections": [{collectionId, name, itemCount, ...}]}``.
* ``search.SearchContentService/ListSearchContent`` — collection contents
  (``listType: LIST_TYPE_COLLECTIONS`` + ``collectionId``) AND competition
  drill-down (``listType: LIST_TYPE_UNSPECIFIED`` + ``competitionIds`` +
  ``documentTypes``; the collections listType returns 0 rows for competition
  filters). Documents carry ``id``, ``title``, ``documentType``
  (KERNEL/TOPIC/COMPETITION/DATASET/COMMENT), ``votes``, ``totalComments``,
  ``ownerUser{userName, tier}``, ``enrichedInfo{url}`` and a top-level
  ``medal`` ("GOLD"/"SILVER"/"BRONZE", omitted when none). Responses paginate
  via ``nextPageToken`` (verified: a second page returns disjoint documents),
  and ``canonicalOrderBy: LIST_SEARCH_CONTENT_ORDER_BY_VOTES`` is a valid
  server-side sort (verified: votes descending) — used for drill-down so only
  the top pages need fetching.
* ``discussions.DiscussionsService/GetForumTopicById`` — body
  ``{forumTopicId, includeComments: true}`` → full thread with
  ``firstMessage.rawMarkdown``, ``comments[].rawMarkdown`` and nested
  ``replies``. A TOPIC document's ``id`` IS the ``forumTopicId``.

Every fetcher returns ``(data, error)`` following the
``kaggle_service.list_episodes_checked`` convention (429 → rate-limit
message, 401/403 → session-expired message), so callers can abort on
rate limits without parsing exceptions.
"""

from __future__ import annotations

import asyncio
import json
import re

from .utils.throttle import kaggle_throttle

LIST_COLLECTIONS = "/api/i/users.CollectionsService/ListCollections"
LIST_SEARCH_CONTENT = "/api/i/search.SearchContentService/ListSearchContent"
GET_FORUM_TOPIC = "/api/i/discussions.DiscussionsService/GetForumTopicById"
# Dataset drill-down (probe-verified 2026-06-13): a DATASET item's own notebooks
# come from ``ListKernels`` filtered by ``datasetId``; its discussions need the
# dataset's ``forumId`` (from ``GetDatasetBasics`` — NOT the non-existent
# ``GetDatasetView`` the CLI prototype guessed) fed into ``GetTopicListByForumId``.
LIST_KERNELS = "/api/i/kernels.KernelsService/ListKernels"
GET_DATASET_BASICS = "/api/i/datasets.DatasetDetailService/GetDatasetBasics"
GET_TOPIC_LIST = "/api/i/discussions.DiscussionsService/GetTopicListByForumId"

ORDER_BY_DATE_UPDATED = "LIST_SEARCH_CONTENT_ORDER_BY_DATE_UPDATED"
ORDER_BY_VOTES = "LIST_SEARCH_CONTENT_ORDER_BY_VOTES"

RATE_LIMIT_MSG = "Kaggle is rate-limiting requests (429). Please wait a minute and retry."
SESSION_EXPIRED_MSG = "Kaggle session expired. Re-run `python login.py` to reconnect."

# Kernel/owner path segments accepted for `kaggle kernels pull` (never let an
# arbitrary URL fragment reach a subprocess argument).
_REF_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

_MEDAL_NAMES = {"gold", "silver", "bronze"}
_MEDAL_INTS = {1: "gold", 2: "silver", 3: "bronze"}


async def _post_internal(page, tokens, path: str, payload: dict) -> dict:
    """POST to a Kaggle internal API from inside the authenticated page.

    Args:
        page: Authenticated Playwright ``Page``.
        tokens: ``{"xsrf", "build_hash"}`` from ``downloader.get_auth_tokens``.
        path: Endpoint path (one of the module constants).
        payload: JSON body.

    Returns:
        ``{"status": int, "text": str}``; ``{"status": 0}`` on evaluate failure.

    Every call is paced through the shared :data:`kaggle_throttle` so collection
    and dataset drill-downs never burst Kaggle's private API.
    """
    await kaggle_throttle.acquire()
    try:
        resp = await page.evaluate(
            """
        async ({xsrf, buildHash, path, payload}) => {
            const r = await fetch(path, {
                method: "POST",
                headers: {
                    "content-type": "application/json",
                    "x-xsrf-token": xsrf,
                    "x-kaggle-build-version": buildHash
                },
                body: JSON.stringify(payload)
            });
            return { status: r.status, text: await r.text() };
        }
        """,
            {
                "xsrf": tokens["xsrf"],
                "buildHash": tokens["build_hash"],
                "path": path,
                "payload": payload,
            },
        )
    except Exception:  # noqa: BLE001
        return {"status": 0, "text": ""}
    kaggle_throttle.record(resp.get("status") if isinstance(resp, dict) else None)
    return resp


def _check(resp: dict, what: str) -> tuple[dict | None, str | None]:
    """Map a raw ``{"status","text"}`` response to ``(parsed_json, error)``."""
    status = resp.get("status") if isinstance(resp, dict) else 0
    if status != 200:
        if status == 429:
            return None, RATE_LIMIT_MSG
        if status in (401, 403):
            return None, SESSION_EXPIRED_MSG
        return None, f"Kaggle returned HTTP {status or 'error'} while {what}."
    try:
        return json.loads(resp.get("text") or "{}"), None
    except (ValueError, TypeError):
        return None, f"Could not parse the Kaggle response while {what}."


def _search_payload(filters: dict, order_by: str, page_token: str, page_size: int, skip: int) -> dict:
    """Build a ``ListSearchContent`` body (base shape proven by the prototype)."""
    return {
        "pageToken": page_token,
        "pageSize": page_size,
        "skip": skip,
        "canonicalOrderBy": order_by,
        "filters": {
            "query": "",
            "documentTypes": [],
            "listType": "LIST_TYPE_COLLECTIONS",
            "privacy": "ALL",
            "ownerType": "OWNER_TYPE_UNSPECIFIED",
            "tagIds": [],
            "competitionIds": [],
            "sharedViaGroups": [],
            "discussionFilters": {
                "onlyNewComments": False,
                "sourceType": "SEARCH_DISCUSSIONS_SOURCE_TYPE_UNSPECIFIED",
                "writeUpInclusionType": "WRITE_UP_INCLUSION_TYPE_INCLUDE",
                "writeUpTypes": [],
                "hackathonTrackIds": [],
            },
            **filters,
        },
    }


async def fetch_collections(page, tokens) -> tuple[list[dict], str | None]:
    """Return ``(collections, error)`` from ``ListCollections``."""
    resp = await _post_internal(page, tokens, LIST_COLLECTIONS, {})
    data, error = _check(resp, "listing collections")
    if error is not None:
        return [], error
    return data.get("collections", []), None


async def _fetch_search_documents(
    page,
    tokens,
    filters: dict,
    order_by: str,
    page_size: int,
    max_pages: int,
    delay_seconds: float,
    limit: int = 0,
) -> tuple[list[dict], str | None]:
    """Run the paginated ``ListSearchContent`` loop and return ``(docs, error)``.

    Advances by ``nextPageToken`` when the API supplies one, else by ``skip``;
    de-duplicates across pages so either behavior is safe. Stops on: an empty
    page, all ``totalDocuments`` collected, a short page without a continuation
    token, ``limit`` reached (when non-zero), or the ``max_pages`` safety cap.
    A non-200 mid-loop returns the documents collected so far plus the error.
    """
    docs: list[dict] = []
    seen: set[str] = set()
    page_token, skip = "", 0
    for page_no in range(max_pages):
        payload = _search_payload(filters, order_by, page_token, page_size, skip)
        resp = await _post_internal(page, tokens, LIST_SEARCH_CONTENT, payload)
        data, error = _check(resp, "listing collection contents")
        if error is not None:
            return docs, error
        batch = data.get("documents", [])
        for doc in batch:
            key = str(doc.get("documentId") or doc.get("id"))
            if key not in seen:
                seen.add(key)
                docs.append(doc)
        total = int(data.get("totalDocuments") or 0)
        next_token = data.get("nextPageToken") or ""
        if not batch:
            break
        if limit and len(docs) >= limit:
            break
        if total and len(docs) >= total:
            break
        if not next_token and len(batch) < page_size:
            break
        if next_token:
            page_token, skip = next_token, 0
        else:
            skip += len(batch)
        await asyncio.sleep(delay_seconds)
    return docs, None


async def fetch_collection_items(
    page,
    tokens,
    collection_id: int,
    page_size: int = 100,
    max_pages: int = 50,
    delay_seconds: float = 1.0,
) -> tuple[list[dict], str | None]:
    """Return ``(documents, error)`` for everything saved in a collection."""
    return await _fetch_search_documents(
        page,
        tokens,
        {"collectionId": int(collection_id)},
        ORDER_BY_DATE_UPDATED,
        page_size,
        max_pages,
        delay_seconds,
    )


async def enumerate_competition_contents(
    page,
    tokens,
    competition_kaggle_id: int,
    cap: int,
    page_size: int = 100,
    max_pages: int = 50,
    delay_seconds: float = 1.0,
) -> dict:
    """Enumerate a competition's notebooks + discussions (the drill-down).

    The single interface behind which the discovery result lives: vote-ordered
    ``ListSearchContent`` queries with ``listType: LIST_TYPE_UNSPECIFIED`` and a
    ``competitionIds`` filter (probe-verified — see module docstring). Server-side
    vote ordering means a cap of N needs only ``ceil(N / page_size)`` pages.

    Args:
        page: Authenticated Playwright ``Page``.
        tokens: ``{"xsrf", "build_hash"}``.
        competition_kaggle_id: Numeric competition ID (a COMPETITION document's ``id``).
        cap: Top-N per type to enumerate (0 = everything, bounded by ``max_pages``).
        page_size / max_pages / delay_seconds: Pagination tuning.

    Returns:
        ``{"kernels": [parsed], "topics": [parsed], "error": str | None}`` —
        items normalized by :func:`parse_item`. ``error`` is set on the first
        upstream failure (partial results are still returned).
    """
    out: dict = {"kernels": [], "topics": [], "error": None}
    for key, doc_type in (("kernels", "KERNEL"), ("topics", "TOPIC")):
        docs, error = await _fetch_search_documents(
            page,
            tokens,
            {
                "competitionIds": [int(competition_kaggle_id)],
                "documentTypes": [doc_type],
                "listType": "LIST_TYPE_UNSPECIFIED",
            },
            ORDER_BY_VOTES,
            page_size,
            max_pages,
            delay_seconds,
            limit=cap,
        )
        out[key] = [parse_item(d) for d in docs]
        if error is not None:
            out["error"] = error
            break
        await asyncio.sleep(delay_seconds)
    return out


def _parse_kernel(kernel: dict) -> dict:
    """Normalize one ``ListKernels`` row to the same shape :func:`parse_item` yields.

    ``ListKernels`` returns ``author.userName`` + ``currentUrlSlug`` (not a URL),
    ``totalVotes`` and a top-level ``medal`` ("GOLD"/"SILVER"/"BRONZE") — probe
    confirmed. A synthetic ``/code/owner/slug`` URL lets the worker reuse
    :func:`parse_kernel_ref` / ``_pull_kernel`` unchanged.
    """
    owner = (kernel.get("author") or {}).get("userName") or ""
    slug = kernel.get("currentUrlSlug") or ""
    return {
        "kaggle_doc_id": str(kernel.get("id") or ""),
        "document_type": "KERNEL",
        "title": str(kernel.get("title") or "")[:500],
        "votes": int(kernel.get("totalVotes") or 0),
        "medal": normalize_medal(kernel.get("medal")),
        "url": f"/code/{owner}/{slug}" if owner and slug else None,
    }


async def enumerate_dataset_kernels(
    page,
    tokens,
    dataset_id: int,
    cap: int,
    page_size: int = 20,
    max_pages: int = 50,
    delay_seconds: float = 1.0,
) -> tuple[list[dict], str | None]:
    """Return ``(kernels, error)`` for a DATASET's notebooks, votes-desc, capped.

    ``ListKernels`` exposes only a HOTNESS sort for a ``datasetId`` filter (no
    server-side vote order), but each row carries ``totalVotes``, so we page
    under HOTNESS until ``cap`` candidates are gathered, then sort by votes
    descending and trim — a true "top-N by votes" without over-fetching.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for page_no in range(1, max_pages + 1):
        payload = {
            "kernelFilterCriteria": {
                "search": "",
                "listRequest": {
                    "sortBy": "HOTNESS",
                    "pageSize": page_size,
                    "group": "EVERYONE",
                    "page": page_no,
                    "datasetId": int(dataset_id),
                    "modelIds": [],
                    "modelInstanceIds": [],
                    "excludeKernelIds": [],
                    "tagIds": "",
                    "excludeResultsFilesOutputs": False,
                    "wantOutputFiles": False,
                },
            },
            "detailFilterCriteria": {
                "deletedAccessBehavior": "RETURN_NOTHING",
                "unauthorizedAccessBehavior": "RETURN_NOTHING",
                "excludeResultsFilesOutputs": False,
                "wantOutputFiles": False,
                "kernelIds": [],
                "outputFileTypes": [],
                "includeInvalidDataSources": False,
            },
            "readMask": "pinnedKernels",
        }
        resp = await _post_internal(page, tokens, LIST_KERNELS, payload)
        data, error = _check(resp, "listing dataset notebooks")
        if error is not None:
            return _sorted_capped(out, cap), error
        batch = data.get("kernels", [])
        if not batch:
            break
        for kernel in batch:
            parsed = _parse_kernel(kernel)
            if not parsed["url"] or parsed["kaggle_doc_id"] in seen:
                continue
            seen.add(parsed["kaggle_doc_id"])
            out.append(parsed)
        # Enough candidates gathered to satisfy the cap after the votes sort.
        if cap and len(out) >= cap:
            break
        if len(batch) < page_size:
            break
        await asyncio.sleep(delay_seconds)
    return _sorted_capped(out, cap), None


def _sorted_capped(items: list[dict], cap: int) -> list[dict]:
    """Sort parsed kernels by votes descending and apply ``cap`` (0 = no cap)."""
    items.sort(key=lambda d: -int(d.get("votes") or 0))
    return items[:cap] if cap else items


async def fetch_dataset_forum_id(page, tokens, owner: str, slug: str) -> tuple[int | None, str | None]:
    """Return ``(forum_id, error)`` for a dataset via ``GetDatasetBasics``.

    ``forumId`` is a top-level field of the basics payload (probe-verified) and is
    distinct from the dataset's own ``datasetId``.
    """
    resp = await _post_internal(page, tokens, GET_DATASET_BASICS, {"ownerSlug": owner, "datasetSlug": slug})
    data, error = _check(resp, "fetching dataset basics")
    if error is not None:
        return None, error
    forum_id = data.get("forumId")
    if not forum_id:
        return None, None
    try:
        return int(forum_id), None
    except (TypeError, ValueError):
        return None, None


async def fetch_dataset_topics(
    page,
    tokens,
    forum_id: int,
    cap: int,
    max_pages: int = 50,
    delay_seconds: float = 1.0,
) -> tuple[list[dict], str | None]:
    """Return ``(topics, error)`` for a dataset forum via ``GetTopicListByForumId``.

    The list endpoint only accepts ``TOPIC_LIST_SORT_BY_HOT`` (other sorts 400)
    and carries no per-topic vote count, so topics are taken in HOT order and
    capped. Each ``id`` is the ``forumTopicId`` for :func:`fetch_forum_topic`.
    """
    out: list[dict] = []
    seen: set[int] = set()
    for page_no in range(1, max_pages + 1):
        payload = {
            "category": "TOPIC_LIST_CATEGORY_ALL",
            "group": "TOPIC_LIST_GROUP_ALL",
            "customGroupingIds": [],
            "author": "TOPIC_LIST_AUTHOR_UNSPECIFIED",
            "myActivity": "TOPIC_LIST_MY_ACTIVITY_UNSPECIFIED",
            "recency": "TOPIC_LIST_RECENCY_UNSPECIFIED",
            "filterCategoryIds": [],
            "searchQuery": "",
            "sortBy": "TOPIC_LIST_SORT_BY_HOT",
            "page": page_no,
            "forumId": int(forum_id),
        }
        resp = await _post_internal(page, tokens, GET_TOPIC_LIST, payload)
        data, error = _check(resp, "listing dataset discussions")
        if error is not None:
            return out, error
        batch = data.get("topics", [])
        if not batch:
            break
        for topic in batch:
            tid = topic.get("id")
            if tid is None or tid in seen:
                continue
            seen.add(tid)
            out.append({"topic_id": int(tid), "title": str(topic.get("title") or "")})
            if cap and len(out) >= cap:
                return out, None
        await asyncio.sleep(delay_seconds)
    return out, None


async def fetch_forum_topic(page, tokens, forum_topic_id: int) -> tuple[dict | None, str | None]:
    """Return ``(forumTopic, error)`` for one discussion thread (with comments)."""
    resp = await _post_internal(
        page, tokens, GET_FORUM_TOPIC, {"forumTopicId": int(forum_topic_id), "includeComments": True}
    )
    data, error = _check(resp, "fetching a discussion topic")
    if error is not None:
        return None, error
    topic = data.get("forumTopic")
    if not isinstance(topic, dict):
        return None, "Kaggle returned no forumTopic payload."
    return topic, None


def normalize_medal(value) -> str | None:
    """Normalize Kaggle's medal representations to ``gold|silver|bronze|None``.

    Observed live as top-level ``"GOLD"``/``"BRONZE"`` strings (field omitted
    when no medal); also accepts ``MEDAL_GOLD``-style enums and 1/2/3 ints
    defensively.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return _MEDAL_INTS.get(value)
    name = str(value).strip().lower()
    if name.startswith("medal_"):
        name = name[len("medal_"):]
    return name if name in _MEDAL_NAMES else None


def parse_item(doc: dict) -> dict:
    """Normalize one ``ListSearchContent`` document to ``collection_items`` values.

    ``create_time``/``update_time`` stay as raw ISO strings; the service layer
    parses them into datetimes. The full document is preserved under ``raw_json``
    so later-discovered fields can be backfilled by a re-sync.
    """
    owner = doc.get("ownerUser") or {}
    enriched = doc.get("enrichedInfo") or {}
    return {
        "kaggle_doc_id": str(doc.get("documentId") or doc.get("id") or ""),
        "document_type": str(doc.get("documentType") or "UNKNOWN")[:30],
        "title": str(doc.get("title") or "")[:500],
        "votes": int(doc.get("votes") or 0),
        "total_comments": int(doc.get("totalComments") or 0),
        "author_username": owner.get("userName"),
        "author_tier": owner.get("tier"),
        "medal": normalize_medal(doc.get("medal")),
        "url": (enriched.get("url") or None),
        "create_time": doc.get("createTime"),
        "update_time": doc.get("updateTime"),
        "raw_json": doc,
    }


def parse_kernel_ref(url: str | None) -> tuple[str, str] | None:
    """Parse ``/code/owner/slug`` (or legacy ``/c/owner/slug``) into ``(owner, slug)``.

    Returns ``None`` for anything unparseable or containing characters unsafe
    to pass to the ``kaggle`` CLI subprocess.
    """
    parts = (url or "").strip("/").split("/")
    if len(parts) < 3 or parts[0] not in ("code", "c"):
        return None
    owner, slug = parts[1], parts[2]
    if not (_REF_SEGMENT_RE.match(owner) and _REF_SEGMENT_RE.match(slug)):
        return None
    return owner, slug


def topic_id_from_doc(item_url: str | None, kaggle_doc_id: str) -> int | None:
    """Extract the numeric forumTopicId for a TOPIC item.

    A TOPIC document's numeric ``id`` is the forumTopicId; cached rows store it
    as ``topic-<id>`` (``documentId``), and the URL ends with the same number
    (``.../discussion/<id>``) as a fallback.
    """
    match = re.search(r"(\d+)$", kaggle_doc_id or "")
    if match:
        return int(match.group(1))
    match = re.search(r"/discussion/(\d+)", item_url or "")
    return int(match.group(1)) if match else None


def render_topic_markdown(topic: dict) -> str:
    """Render a ``GetForumTopicById`` payload to Markdown (prototype format).

    Title / Author / Votes / URL header, the original post, then each comment
    as ``###`` with its replies as ``#### Reply by``. A footer records how many
    comments were rendered versus the topic's reported total (huge threads may
    be truncated by the API).
    """
    lines: list[str] = []
    lines.append(f"# {topic.get('name', 'Untitled')}\n")
    lines.append(f"Author: {topic.get('authorUserDisplayName', 'Unknown')}\n")
    lines.append(f"Votes: {topic.get('totalVotes', 0)}\n")
    if topic.get("url"):
        lines.append(f"URL: https://www.kaggle.com{topic['url']}\n")
    lines.append("## Original Post\n")
    first = topic.get("firstMessage") or {}
    lines.append((first.get("rawMarkdown") or "").rstrip() + "\n")

    comments = topic.get("comments") or []
    rendered = 0
    if comments:
        lines.append("## Comments\n")
    for comment in comments:
        author = (comment.get("author") or {}).get("displayName", "Unknown")
        lines.append(f"### {author}\n")
        lines.append((comment.get("rawMarkdown") or "").rstrip() + "\n")
        rendered += 1
        for reply in comment.get("replies") or []:
            reply_author = (reply.get("author") or {}).get("displayName", "Unknown")
            lines.append(f"#### Reply by {reply_author}\n")
            lines.append((reply.get("rawMarkdown") or "").rstrip() + "\n")
            rendered += 1

    total = topic.get("totalComments")
    if isinstance(total, int) and total > 0:
        lines.append(f"---\n\n_{rendered} of {total} comments/replies exported._\n")
    return "\n".join(lines)
