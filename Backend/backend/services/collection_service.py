"""Service helpers for the Collections feature: sync, sorting, job creation.

Sync upserts keep cached rows stable (PKs never churn): collections are matched
by ``kaggle_id`` per user, items by ``kaggle_doc_id`` per collection. Items
removed from a collection on Kaggle are deleted locally; collections are never
auto-deleted because ``download_jobs.collection_id`` cascades and job history
must survive a re-sync.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import kaggle_collections
from ..models import Collection, CollectionItem, DownloadJob

# Display/download priority: medal first (gold > silver > bronze > none),
# then votes descending — the order chosen for the feature spec.
_MEDAL_RANK = {"gold": 0, "silver": 1, "bronze": 2}

# Which document types each item_filter selects at the top level. COMPETITION
# items are only processed under "all" (they fan out into capped notebooks +
# discussions inside the worker), mirroring the proven CLI behavior.
FILTER_DOC_TYPES = {
    "all": None,  # everything
    "notebooks": {"KERNEL"},
    "discussions": {"TOPIC"},
}


def item_sort_key(item: CollectionItem) -> tuple[int, int]:
    """Sort key: medal rank ascending, votes descending."""
    return (_MEDAL_RANK.get(item.medal or "", 3), -(item.votes or 0))


def select_items(
    items: list[CollectionItem], item_filter: str, medals: set[str] | None = None
) -> list[CollectionItem]:
    """Return the items a job/list view includes, filtered + sorted.

    ``item_filter`` keeps only the matching document types; ``medals`` (a subset
    of gold/silver/bronze, empty/None = all) further restricts NOTEBOOK items to
    those medals — discussions/competitions/datasets are never medal-filtered.
    Result is medal→votes sorted.
    """
    allowed = FILTER_DOC_TYPES.get(item_filter)
    medals = medals or set()
    picked = []
    for i in items:
        if allowed is not None and i.document_type not in allowed:
            continue
        if medals and i.document_type == "KERNEL" and (i.medal or "") not in medals:
            continue
        picked.append(i)
    return sorted(picked, key=item_sort_key)


async def get_owned_collection(db: AsyncSession, user_id: int, collection_id: int) -> Collection | None:
    """Return a collection by PK only if owned by ``user_id``."""
    return (
        await db.execute(
            select(Collection).where(Collection.id == collection_id, Collection.user_id == user_id)
        )
    ).scalar_one_or_none()


async def list_collections(db: AsyncSession, user_id: int) -> list[Collection]:
    """Return the user's cached collections, alphabetical."""
    return list(
        (
            await db.execute(
                select(Collection).where(Collection.user_id == user_id).order_by(Collection.name.asc())
            )
        ).scalars()
    )


async def list_items(db: AsyncSession, collection_id: int) -> list[CollectionItem]:
    """Return all cached items of a collection (unsorted)."""
    return list(
        (
            await db.execute(
                select(CollectionItem).where(CollectionItem.collection_id == collection_id)
            )
        ).scalars()
    )


async def sync_collections(
    db: AsyncSession, user_id: int, page, tokens
) -> tuple[list[Collection], str | None]:
    """Fetch the user's collections from Kaggle and upsert the cache.

    Returns ``(collections, error)``; on error the cached rows are returned
    unchanged so the UI can still render.
    """
    raw, error = await kaggle_collections.fetch_collections(page, tokens)
    if error is not None:
        return await list_collections(db, user_id), error

    existing = {c.kaggle_id: c for c in await list_collections(db, user_id)}
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    for entry in raw:
        kaggle_id = int(entry.get("collectionId") or 0)
        if not kaggle_id:
            continue
        row = existing.get(kaggle_id)
        if row is None:
            row = Collection(kaggle_id=kaggle_id, user_id=user_id, name="", item_count=0)
            db.add(row)
        row.name = str(entry.get("name") or f"Collection {kaggle_id}")[:500]
        row.item_count = int(entry.get("itemCount") or 0)
        row.fetched_at = now
    await db.commit()
    return await list_collections(db, user_id), None


async def sync_collection_items(
    db: AsyncSession, collection: Collection, page, tokens
) -> tuple[list[CollectionItem], str | None]:
    """Fetch a collection's documents from Kaggle and upsert the item cache.

    Stale items (no longer in the collection) are deleted. On fetch error the
    cache is left untouched and returned with the error message.
    """
    docs, error = await kaggle_collections.fetch_collection_items(page, tokens, collection.kaggle_id)
    if error is not None:
        return await list_items(db, collection.id), error

    existing = {i.kaggle_doc_id: i for i in await list_items(db, collection.id)}
    seen: set[str] = set()
    for doc in docs:
        parsed = kaggle_collections.parse_item(doc)
        doc_id = parsed["kaggle_doc_id"]
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        row = existing.get(doc_id)
        if row is None:
            row = CollectionItem(collection_id=collection.id, kaggle_doc_id=doc_id)
            db.add(row)
        row.document_type = parsed["document_type"]
        row.title = parsed["title"]
        row.votes = parsed["votes"]
        row.total_comments = parsed["total_comments"]
        row.author_username = parsed["author_username"]
        row.author_tier = parsed["author_tier"]
        row.medal = parsed["medal"]
        row.url = parsed["url"]
        row.create_time = _parse_dt(parsed["create_time"])
        row.update_time = _parse_dt(parsed["update_time"])
        row.raw_json = parsed["raw_json"]

    stale = [doc_id for doc_id in existing if doc_id not in seen]
    if stale:
        await db.execute(
            delete(CollectionItem).where(
                CollectionItem.collection_id == collection.id,
                CollectionItem.kaggle_doc_id.in_(stale),
            )
        )

    collection.items_synced_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    collection.item_count = len(seen)
    await db.commit()
    return await list_items(db, collection.id), None


async def create_collection_job(
    db: AsyncSession,
    user_id: int,
    collection_id: int,
    item_filter: str,
    format_mode: str,
    per_competition_cap: int,
    medals: set[str] | None = None,
) -> DownloadJob:
    """Insert a queued collection-type ``download_jobs`` row and return it."""
    job = DownloadJob(
        job_uuid=str(uuid.uuid4()),
        user_id=user_id,
        submission_id=None,
        job_type="collection",
        collection_id=collection_id,
        item_filter=item_filter,
        per_competition_cap=per_competition_cap,
        medal_filter=",".join(sorted(medals)) if medals else None,
        filter_mode="all",  # episode-only column; collection jobs store the default
        format_mode=format_mode,
        is_bulk=False,
        status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


def item_view(item: CollectionItem) -> dict:
    """Build the ``CollectionItemSchema`` dict for one cached item."""
    return {
        "id": item.id,
        "kaggle_doc_id": item.kaggle_doc_id,
        "document_type": item.document_type,
        "title": item.title,
        "votes": item.votes,
        "total_comments": item.total_comments,
        "author_username": item.author_username,
        "author_tier": item.author_tier,
        "medal": item.medal,
        "url": item.url,
        "create_time": item.create_time,
        "update_time": item.update_time,
    }


def _parse_dt(value) -> dt.datetime | None:
    """Parse a Kaggle ISO timestamp to a naive-UTC datetime (MySQL DATETIME)."""
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return parsed
