"""Tiny asyncio-safe in-memory TTL cache.

Used to avoid re-hitting Kaggle's internal API (which rate-limits aggressively)
for data that changes slowly within a short window — primarily a submission's
episode list. No external service (Redis) is required; this is process-local and
sufficient for the single-worker dev/deploy footprint.

Usage::

    cache = TTLCache(default_ttl=120)
    hit = await cache.get(key)
    if hit is None:
        value = await expensive_fetch()
        await cache.set(key, value)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any


class TTLCache:
    """A minimal async-safe key→value cache with per-entry expiry."""

    def __init__(self, default_ttl: float = 120.0) -> None:
        """Initialize the cache.

        Args:
            default_ttl: Default time-to-live in seconds for ``set`` calls.
        """
        self._default_ttl = default_ttl
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Return the cached value for ``key`` if present and unexpired, else None."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Store ``value`` under ``key`` with an optional per-entry ``ttl``."""
        async with self._lock:
            self._store[key] = (time.monotonic() + (ttl or self._default_ttl), value)

    async def invalidate(self, key: str) -> None:
        """Remove a single key (no error if absent)."""
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        """Drop all cached entries."""
        async with self._lock:
            self._store.clear()


# Process-wide cache for Kaggle episode lists (keyed by user_id + submission).
episode_cache = TTLCache(default_ttl=120.0)
