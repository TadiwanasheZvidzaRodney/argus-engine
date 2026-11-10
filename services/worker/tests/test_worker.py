from __future__ import annotations

from datetime import UTC, datetime

import pytest
from argus_core.events import EventType
from argus_core.settings import Settings
from argus_worker.main import emit_heartbeat, heartbeat_idempotency_key, run_forever
from argus_worker.queue import LoggingEventSink

TENANT = "tnt_0190c3a1-0000-7000-8000-000000000000"


@pytest.fixture
def settings() -> Settings:
    return Settings(service_name="argus-worker", env="test", _env_file=None)


async def test_heartbeat_is_a_valid_envelope(settings: Settings) -> None:
    sink = LoggingEventSink()
    envelope = await emit_heartbeat(sink, settings, tenant_id=TENANT)
    assert envelope.type == EventType.WORKER_HEARTBEAT.value
    assert envelope.source == "argus.worker"
    assert envelope.tenant_id == TENANT
    assert sink.published == [envelope]


async def test_heartbeat_is_idempotent_within_a_minute(settings: Settings) -> None:
    sink = LoggingEventSink()
    first = await emit_heartbeat(sink, settings, tenant_id=TENANT)
    second = await emit_heartbeat(sink, settings, tenant_id=TENANT)
    assert first.idempotency_key == second.idempotency_key
    assert first.id != second.id


def test_idempotency_key_is_minute_bucketed() -> None:
    later = datetime(2026, 11, 10, 12, 1, tzinfo=UTC)
    earlier = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    assert heartbeat_idempotency_key(TENANT, earlier) != heartbeat_idempotency_key(TENANT, later)


async def test_run_forever_stops_after_max_iterations(settings: Settings) -> None:
    sink = LoggingEventSink()
    code = await run_forever(sink, settings, interval_seconds=0.01, max_iterations=2)
    assert code == 0
    assert len(sink.published) == 2
