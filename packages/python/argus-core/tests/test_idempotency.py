from __future__ import annotations

import pytest
from argus_core.idempotency import (
    BeginOutcome,
    InMemoryIdempotencyStore,
    StoredResponse,
    fingerprint_request,
)


def test_fingerprint_changes_with_body_method_and_path() -> None:
    base = fingerprint_request("POST", "/api/v1/actions", b"{}")
    assert base != fingerprint_request("POST", "/api/v1/actions", b'{"a":1}')
    assert base != fingerprint_request("PUT", "/api/v1/actions", b"{}")
    assert base != fingerprint_request("POST", "/api/v1/other", b"{}")
    assert base == fingerprint_request("post", "/api/v1/actions", b"{}")


async def test_replay_returns_original_response() -> None:
    store = InMemoryIdempotencyStore()
    fingerprint = fingerprint_request("POST", "/api/v1/actions", b"{}")

    assert (await store.begin("k1", fingerprint, ttl_seconds=60, lock_seconds=5)).outcome is (
        BeginOutcome.ACQUIRED
    )
    await store.complete(
        "k1",
        StoredResponse(status_code=201, body={"id": "act_1"}, fingerprint=fingerprint),
        ttl_seconds=60,
    )

    replay = await store.begin("k1", fingerprint, ttl_seconds=60, lock_seconds=5)
    assert replay.outcome is BeginOutcome.REPLAY
    assert replay.stored is not None
    assert replay.stored.status_code == 201
    assert replay.stored.body == {"id": "act_1"}


async def test_concurrent_duplicate_is_in_flight() -> None:
    store = InMemoryIdempotencyStore()
    fingerprint = fingerprint_request("POST", "/api/v1/actions", b"{}")

    await store.begin("k2", fingerprint, ttl_seconds=60, lock_seconds=5)
    second = await store.begin("k2", fingerprint, ttl_seconds=60, lock_seconds=5)
    assert second.outcome is BeginOutcome.IN_FLIGHT


async def test_key_reuse_with_different_payload_is_rejected() -> None:
    store = InMemoryIdempotencyStore()
    original = fingerprint_request("POST", "/api/v1/actions", b'{"a":1}')
    mutated = fingerprint_request("POST", "/api/v1/actions", b'{"a":2}')

    await store.begin("k3", original, ttl_seconds=60, lock_seconds=5)
    await store.complete(
        "k3",
        StoredResponse(status_code=202, body={}, fingerprint=original),
        ttl_seconds=60,
    )

    result = await store.begin("k3", mutated, ttl_seconds=60, lock_seconds=5)
    assert result.outcome is BeginOutcome.FINGERPRINT_MISMATCH


async def test_release_clears_lock_after_failure() -> None:
    store = InMemoryIdempotencyStore()
    fingerprint = fingerprint_request("POST", "/api/v1/actions", b"{}")

    await store.begin("k4", fingerprint, ttl_seconds=60, lock_seconds=5)
    await store.release("k4")
    retry = await store.begin("k4", fingerprint, ttl_seconds=60, lock_seconds=5)
    assert retry.outcome is BeginOutcome.ACQUIRED


async def test_expired_entries_are_purged() -> None:
    store = InMemoryIdempotencyStore()
    fingerprint = fingerprint_request("POST", "/api/v1/actions", b"{}")

    await store.begin("k5", fingerprint, ttl_seconds=60, lock_seconds=0)
    # A zero lock TTL must not wedge the key forever.
    result = await store.begin("k5", fingerprint, ttl_seconds=60, lock_seconds=0)
    assert result.outcome is BeginOutcome.ACQUIRED


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_are_still_fingerprintable(method: str) -> None:
    assert fingerprint_request(method, "/health", b"") != fingerprint_request(
        "POST", "/health", b""
    )
