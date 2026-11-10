"""Idempotency deduplication store for incoming AWS events."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

DEFAULT_DEDUPE_TTL_SECONDS = 7 * 86400  # 7 days


class DedupeStore:
    """Redis-backed event deduplication store with in-memory fallback for unit tests."""

    def __init__(
        self, client: Redis | None = None, ttl_seconds: int = DEFAULT_DEDUPE_TTL_SECONDS
    ) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds
        self._memory_cache: dict[str, float] = {}

    def _cache_key(self, tenant_id: str, idempotency_key: str) -> str:
        return f"dedupe:{tenant_id}:{idempotency_key}"

    async def is_duplicate(self, tenant_id: str, idempotency_key: str) -> bool:
        """Check if an event was already processed. If not, mark it as seen."""
        key = self._cache_key(tenant_id, idempotency_key)
        if self.client is not None:
            # SET NX EX atomically sets if not exists
            acquired = await self.client.set(key, "1", nx=True, ex=self.ttl_seconds)
            return acquired is None

        now = time.monotonic()
        # Clean expired memory entries
        expired = [k for k, exp in self._memory_cache.items() if exp <= now]
        for k in expired:
            del self._memory_cache[k]

        if key in self._memory_cache:
            return True

        self._memory_cache[key] = now + self.ttl_seconds
        return False
