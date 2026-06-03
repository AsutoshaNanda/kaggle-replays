"""Per-user Playwright browser-context pool (singleton).

Each user's Kaggle session lives in ``{SESSIONS_BASE_DIR}/{user_id}/auth.json``.
Contexts are cached by ``user_id`` and evicted LRU once
``MAX_CONCURRENT_CONTEXTS`` is exceeded. One shared Chromium browser backs all
contexts; a lock serializes create/evict so concurrent requests don't race.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, async_playwright

from .config import get_settings
from .logging_config import get_logger

_settings = get_settings()
_log = get_logger("backend.session_manager")


class PlaywrightSessionManager:
    """Singleton manager for per-user authenticated browser contexts."""

    _instance: "PlaywrightSessionManager | None" = None

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._contexts: "OrderedDict[int, BrowserContext]" = OrderedDict()
        self._lock = asyncio.Lock()
        self._max = _settings.MAX_CONCURRENT_CONTEXTS

    @classmethod
    def instance(cls) -> "PlaywrightSessionManager":
        """Return the process-wide singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def session_path(self, user_id: int) -> Path:
        """Return the validated ``auth.json`` path for ``user_id``.

        Raises:
            ValueError: If the resolved path escapes ``SESSIONS_BASE_DIR``.
        """
        base = _settings.sessions_base_path
        candidate = (base / str(user_id) / "auth.json").resolve()
        if not str(candidate).startswith(str(base)):
            raise ValueError("Path traversal attempt in session path")
        return candidate

    async def _ensure_browser(self) -> Browser:
        """Lazily launch the shared Chromium browser."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            _log.info("session.browser_launched")
        return self._browser

    async def get_context(self, user_id: int) -> BrowserContext:
        """Return a cached or freshly loaded context for ``user_id``.

        Validates that the user's ``auth.json`` exists and is readable before
        loading it. Marks the context most-recently-used and evicts the LRU
        entry if the cache exceeds ``MAX_CONCURRENT_CONTEXTS``.

        Raises:
            FileNotFoundError: If the user's ``auth.json`` is missing/unreadable.
        """
        async with self._lock:
            if user_id in self._contexts:
                self._contexts.move_to_end(user_id)
                return self._contexts[user_id]

            path = self.session_path(user_id)
            if not path.exists() or path.stat().st_size == 0:
                raise FileNotFoundError(f"No valid session for user {user_id}")

            browser = await self._ensure_browser()
            context = await browser.new_context(storage_state=str(path))
            self._contexts[user_id] = context
            self._contexts.move_to_end(user_id)
            _log.info("session.context_created", user_id=user_id)

            while len(self._contexts) > self._max:
                old_id, old_ctx = self._contexts.popitem(last=False)
                await old_ctx.close()
                _log.info("session.context_evicted", user_id=old_id)

            return context

    async def invalidate_context(self, user_id: int) -> None:
        """Close and remove a user's cached context, if present."""
        async with self._lock:
            ctx = self._contexts.pop(user_id, None)
            if ctx is not None:
                await ctx.close()
                _log.info("session.context_invalidated", user_id=user_id)

    async def close_all(self) -> None:
        """Close all contexts and the browser (call from app shutdown)."""
        async with self._lock:
            for ctx in self._contexts.values():
                await ctx.close()
            self._contexts.clear()
            if self._browser is not None:
                await self._browser.close()
                self._browser = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None
            _log.info("session.closed_all")


def get_session_manager() -> PlaywrightSessionManager:
    """Return the singleton :class:`PlaywrightSessionManager`."""
    return PlaywrightSessionManager.instance()
