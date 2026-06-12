"""Collections endpoints: list, sync, items, download.

All endpoints are JWT-protected and operate only on the requesting user's
collections. Sync endpoints open the user's authenticated Playwright page and
hit Kaggle's internal Collections/Search APIs; list endpoints serve the cache.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit
from ..dependencies import get_current_user, get_db, limiter
from ..kaggle_service import open_page
from ..models import User
from ..schemas import (
    CollectionDownloadRequest,
    CollectionDownloadResponse,
    CollectionItemSchema,
    CollectionItemsResponse,
    CollectionListItem,
    CollectionListResponse,
)
from ..services import collection_service
from ..session_manager import get_session_manager
from ..tasks.collection_worker import run_collection_job

router = APIRouter(prefix="/collections", tags=["collections"])

_ITEM_FILTERS = ("all", "notebooks", "discussions")


@router.get("", response_model=CollectionListResponse)
async def get_collections(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> CollectionListResponse:
    """Return the user's cached collections (empty until the first sync)."""
    rows = await collection_service.list_collections(db, current_user.id)
    return CollectionListResponse(
        collections=[CollectionListItem.model_validate(r) for r in rows],
        last_synced_at=max((r.fetched_at for r in rows), default=None),
    )


@router.post("/sync", response_model=CollectionListResponse)
@limiter.limit("10/hour")
async def sync_collections(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionListResponse:
    """Refresh the collection list from Kaggle."""
    manager = get_session_manager()
    context = await manager.get_context(current_user.id)
    page, tokens = await open_page(context)
    try:
        rows, error = await collection_service.sync_collections(db, current_user.id, page, tokens)
    finally:
        await page.close()
    if error is not None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error)
    await write_audit(
        db, action="collections.sync", ip_address=request.state.client_ip,
        status="success", user_id=current_user.id, resource_type="collection",
    )
    return CollectionListResponse(
        collections=[CollectionListItem.model_validate(r) for r in rows],
        last_synced_at=max((r.fetched_at for r in rows), default=None),
    )


@router.get("/{collection_id}/items", response_model=CollectionItemsResponse)
async def get_collection_items(
    collection_id: int,
    item_filter: str = Query("all", pattern="^(all|notebooks|discussions)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionItemsResponse:
    """Return a collection's cached items, medal→votes sorted, optionally filtered."""
    collection = await collection_service.get_owned_collection(db, current_user.id, collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    items = await collection_service.list_items(db, collection.id)
    selected = collection_service.select_items(items, item_filter)
    return CollectionItemsResponse(
        items=[CollectionItemSchema.model_validate(collection_service.item_view(i)) for i in selected],
        total=len(selected),
        last_synced_at=collection.items_synced_at,
    )


@router.post("/{collection_id}/sync", response_model=CollectionItemsResponse)
@limiter.limit("10/hour")
async def sync_collection_items(
    request: Request,
    collection_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionItemsResponse:
    """Refresh one collection's items from Kaggle (full pagination)."""
    collection = await collection_service.get_owned_collection(db, current_user.id, collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    manager = get_session_manager()
    context = await manager.get_context(current_user.id)
    page, tokens = await open_page(context)
    try:
        items, error = await collection_service.sync_collection_items(db, collection, page, tokens)
    finally:
        await page.close()
    if error is not None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error)
    await write_audit(
        db, action="collections.items_sync", ip_address=request.state.client_ip,
        status="success", user_id=current_user.id, resource_type="collection", resource_id=str(collection_id),
    )
    selected = collection_service.select_items(items, "all")
    return CollectionItemsResponse(
        items=[CollectionItemSchema.model_validate(collection_service.item_view(i)) for i in selected],
        total=len(selected),
        last_synced_at=collection.items_synced_at,
    )


@router.post("/{collection_id}/download", response_model=CollectionDownloadResponse)
@limiter.limit("5/hour")
async def download_collection(
    request: Request,
    collection_id: int,
    body: CollectionDownloadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionDownloadResponse:
    """Create a collection download job and launch the worker."""
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Collection download requires confirm=true"
        )
    collection = await collection_service.get_owned_collection(db, current_user.id, collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    items = await collection_service.list_items(db, collection.id)
    selected = collection_service.select_items(items, body.item_filter)
    if not selected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No matching items — sync the collection first or change the filter",
        )
    job = await collection_service.create_collection_job(
        db, current_user.id, collection.id, body.item_filter, body.format_mode, body.per_competition_cap
    )
    asyncio.create_task(run_collection_job(job.job_uuid))
    await write_audit(
        db, action="collections.download", ip_address=request.state.client_ip,
        status="success", user_id=current_user.id, resource_type="download_job", resource_id=job.job_uuid,
    )
    return CollectionDownloadResponse(job_id=job.job_uuid, total_items=len(selected), status="queued")
