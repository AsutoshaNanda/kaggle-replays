"""FastAPI application factory: middleware, CORS, routers, lifespan, scheduler.

Boot sequence (lifespan startup):
1. configure structlog + rotating file logging,
2. ensure sessions/downloads base dirs exist,
3. launch the midnight-UTC leaderboard scheduler (pure asyncio).

Shutdown: signal the scheduler to stop and close all Playwright contexts.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from .config import get_settings
from .database import AsyncSessionLocal
from .dependencies import limiter, rate_limit_exceeded_handler
from .logging_config import configure_logging, get_logger
from .middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from .routers import auth, collections, competitions, downloads, leaderboard, submissions, ws
from .session_manager import get_session_manager
from .tasks.leaderboard_worker import daily_scheduler_loop

_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start logging + scheduler, clean up on shutdown."""
    configure_logging(_settings.LOG_LEVEL, _settings.LOG_FILE)
    log = get_logger("backend.main")
    _settings.sessions_base_path.mkdir(parents=True, exist_ok=True)
    _settings.downloads_base_path.mkdir(parents=True, exist_ok=True)

    stop_event = asyncio.Event()
    manager = get_session_manager()
    scheduler_task = asyncio.create_task(
        daily_scheduler_loop(AsyncSessionLocal, manager, stop_event)
    )
    log.info("app.startup", origins=_settings.allowed_origins_list)

    try:
        yield
    finally:
        stop_event.set()
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        await manager.close_all()
        log.info("app.shutdown")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(title="Kaggle Replay Analytics API", version="0.1.0", lifespan=lifespan)

    # Rate limiting (slowapi).
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Security headers + request-context logging.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # CORS — explicit allow-list only, never wildcard.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    # Routers.
    for module in (auth, competitions, submissions, downloads, ws, leaderboard, collections):
        app.include_router(module.router)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        """Liveness probe."""
        return {"status": "ok"}

    return app


app = create_app()
