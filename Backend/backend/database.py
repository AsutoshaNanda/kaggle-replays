"""SQLAlchemy async engine, session factory, and declarative ``Base``.

Everything DB-related is async (``aiomysql`` driver). Routers and workers obtain
sessions through :func:`backend.dependencies.get_db` or the
:data:`AsyncSessionLocal` factory directly (background tasks).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

_settings = get_settings()

# pool_pre_ping avoids stale-connection errors after MySQL idle timeouts.
engine = create_async_engine(
    _settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""
