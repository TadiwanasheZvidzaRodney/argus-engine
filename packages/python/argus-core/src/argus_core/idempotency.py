"""Idempotency primitives for mutating HTTP requests.

Contract (see docs/contracts/api-conventions.md):

* every non-GET request must carry ``Idempotency-Key``;
* a key is bound to the request fingerprint (method + path + body hash);
* replays within the TTL return the original response untouched;
* a concurrent duplicate returns ``409 idempotency-request-in-flight``;
* a key reused with a different payload returns ``409 idempotency-key-reuse``.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from redis.asyncio import Redis


class BeginOutcome(StrEnum):
    ACQUIRED = "acquired"
    REPLAY = "replay"
    IN_FLIGHT = "in-flight"
    FINGERPRINT_MISMATCH = "fingerprint-mismatch"


@dataclass(frozen=True)
class StoredResponse:
    status_code: int
    body: dict[str, Any]
    fingerprint: str


@dataclass(frozen=True)
class BeginResult:
    outcome: BeginOutcome
    stored: StoredResponse | None = None


def fingerprint_request(method: str, path: str, body: bytes) -> str:
    """Stable fingerprint binding an idempotency key to one exact request."""
    digest = hashlib.sha256()
    digest.update(method.upper().encode("utf-8"))
    digest.update(b"\x00")
    digest.update(path.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(body)
    return digest.hexdigest()


@runtime_checkable
class IdempotencyStore(Protocol):
    async def begin(
        self, key: str, fingerprint: str, *, ttl_seconds: int, lock_seconds: int
    ) -> BeginResult: ...

    async def complete(self, key: str, response: StoredResponse, *, ttl_seconds: int) -> None: ...

    async def release(self, key: str) -> None: ...


class InMemoryIdempotencyStore:
    """Single-process store for tests and local smoke runs."""

    def __init__(self) -> None:
        self._responses: dict[str, tuple[float, StoredResponse]] = {}
        self._locks: dict[str, tuple[float, str]] = {}

    async def begin(
        self, key: str, fingerprint: str, *, ttl_seconds: int, lock_seconds: int
    ) -> BeginResult:
        now = time.monotonic()
        self._purge(now)
        stored_entry = self._responses.get(key)
        if stored_entry is not None:
            stored = stored_entry[1]
            if stored.fingerprint != fingerprint:
                return BeginResult(BeginOutcome.FINGERPRINT_MISMATCH)
            return BeginResult(BeginOutcome.REPLAY, stored)

        lock = self._locks.get(key)
        if lock is not None and lock[0] > now:
            return BeginResult(BeginOutcome.IN_FLIGHT)

        self._locks[key] = (now + lock_seconds, fingerprint)
        return BeginResult(BeginOutcome.ACQUIRED)

    async def complete(self, key: str, response: StoredResponse, *, ttl_seconds: int) -> None:
        self._locks.pop(key, None)
        self._responses[key] = (time.monotonic() + ttl_seconds, response)

    async def release(self, key: str) -> None:
        self._locks.pop(key, None)

    def _purge(self, now: float) -> None:
        for store in (self._responses, self._locks):
            expired = [key for key, value in store.items() if value[0] <= now]
            for key in expired:
                del store[key]


class RedisIdempotencyStore:
    """Redis-backed store safe across API replicas.

    Responses live under ``idem:resp:{key}`` and in-flight locks under
    ``idem:lock:{key}``; both expire, so a crashed request self-heals.
    """

    def __init__(self, client: Redis) -> None:
        self._redis = client

    @staticmethod
    def _response_key(key: str) -> str:
        return f"idem:resp:{key}"

    @staticmethod
    def _lock_key(key: str) -> str:
        return f"idem:lock:{key}"

    async def begin(
        self, key: str, fingerprint: str, *, ttl_seconds: int, lock_seconds: int
    ) -> BeginResult:
        cached = await self._redis.get(self._response_key(key))
        if cached is not None:
            payload = json.loads(cached)
            stored = StoredResponse(
                status_code=int(payload["status_code"]),
                body=payload["body"],
                fingerprint=str(payload["fingerprint"]),
            )
            if stored.fingerprint != fingerprint:
                return BeginResult(BeginOutcome.FINGERPRINT_MISMATCH)
            return BeginResult(BeginOutcome.REPLAY, stored)

        acquired = await self._redis.set(self._lock_key(key), fingerprint, nx=True, ex=lock_seconds)
        if not acquired:
            return BeginResult(BeginOutcome.IN_FLIGHT)
        return BeginResult(BeginOutcome.ACQUIRED)

    async def complete(self, key: str, response: StoredResponse, *, ttl_seconds: int) -> None:
        payload = json.dumps(
            {
                "status_code": response.status_code,
                "body": response.body,
                "fingerprint": response.fingerprint,
            }
        )
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(self._response_key(key), payload, ex=ttl_seconds)
            pipe.delete(self._lock_key(key))
            await pipe.execute()

    async def release(self, key: str) -> None:
        await self._redis.delete(self._lock_key(key))
