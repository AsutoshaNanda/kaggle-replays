"""Process-wide async throttle for Kaggle internal-API calls.

Kaggle rate-limits its private endpoints aggressively. Rather than scatter
per-call ``asyncio.sleep`` guesses across every fetcher, every Kaggle call goes
through one shared :data:`kaggle_throttle`:

* a global minimum interval between call *starts* (a ~1 req/s token bucket of
  size 1), so no burst — regardless of which feature fires the calls, and
* additive-increase / on-success-reset backoff: each observed 429 lengthens the
  spacing (up to a ceiling); a clean response relaxes it again.

This is the single ceiling that takes the project's Kaggle API pressure from
"hammering" to "polite". It is intentionally simple (no Redis) — correct for the
single-worker deploy footprint.
"""

from __future__ import annotations

import asyncio


class KaggleThrottle:
    """A global pacer: spaces call starts and backs off on 429s."""

    def __init__(self, min_interval: float = 1.0, penalty_step: float = 1.5, penalty_max: float = 30.0) -> None:
        self._min = min_interval
        self._penalty_step = penalty_step
        self._penalty_max = penalty_max
        self._penalty = 0.0
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until enough time has passed since the previous call start."""
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            target = self._last + self._min + self._penalty
            if target > now:
                await asyncio.sleep(target - now)
            self._last = loop.time()

    def record(self, status: int | None) -> None:
        """Feed back a response status: grow spacing on 429, relax otherwise."""
        if status == 429:
            self._penalty = min(self._penalty_max, (self._penalty + self._penalty_step) or self._penalty_step)
        elif status and status < 500:
            self._penalty = 0.0


# Single shared instance used by kaggle_service + kaggle_collections.
kaggle_throttle = KaggleThrottle()
