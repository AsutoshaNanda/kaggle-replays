"""WebSocket endpoint streaming live download-job progress.

Auth is via a ``?token=`` query param (WebSockets can't send Authorization
headers). The socket validates the token + job ownership on connect, then pushes
a progress frame every 2 seconds until the job reaches a terminal state.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy import select

from ..database import AsyncSessionLocal
from ..logging_config import get_logger
from ..models import DownloadJob
from ..security import decode_access_token
from ..services.download_service import progress_view

router = APIRouter(tags=["ws"])
_log = get_logger("backend.ws")
_TERMINAL = {"done", "failed", "cancelled"}


@router.websocket("/ws/downloads/{job_uuid}")
async def ws_download_progress(websocket: WebSocket, job_uuid: str) -> None:
    """Stream progress frames for an owned job over a WebSocket."""
    token = websocket.query_params.get("token", "")
    try:
        user_id = int(decode_access_token(token)["sub"])
    except (JWTError, KeyError, ValueError):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    try:
        while True:
            async with AsyncSessionLocal() as db:
                job = (
                    await db.execute(select(DownloadJob).where(DownloadJob.job_uuid == job_uuid))
                ).scalar_one_or_none()
                if job is None or job.user_id != user_id:
                    await websocket.close(code=4403)
                    return
                view = progress_view(job)
                await websocket.send_json(
                    {
                        "status": view["status"],
                        "completed": view["completed"],
                        "total": view["total"],
                        "pct_complete": view["pct_complete"],
                        "latest_episode_id": job.latest_episode_id,
                        "failed_count": view["failed_count"],
                    }
                )
                if job.status in _TERMINAL:
                    await websocket.close(code=1000)
                    return
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        _log.info("ws.disconnect", job=job_uuid)
