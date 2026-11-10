"""Event sinks used by workers.

Phase 0 publishes to a Redis list so the local stack needs no AWS. Phase 3
swaps in an SQS/EventBridge sink behind the same protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from argus_core.events import EventEnvelope
from argus_core.logging import get_logger
from redis.asyncio import Redis

DEFAULT_QUEUE = "argus:events"


@runtime_checkable
class EventSink(Protocol):
    async def publish(self, envelope: EventEnvelope) -> None: ...


class RedisEventSink:
    def __init__(self, client: Redis, queue: str = DEFAULT_QUEUE) -> None:
        self._redis = client
        self._queue = queue

    async def publish(self, envelope: EventEnvelope) -> None:
        await self._redis.lpush(self._queue, envelope.model_dump_json())


class LoggingEventSink:
    """Development sink: validates and logs instead of publishing."""

    def __init__(self) -> None:
        self.published: list[EventEnvelope] = []

    async def publish(self, envelope: EventEnvelope) -> None:
        get_logger("argus_worker.sink").info(
            "event.published", event_type=envelope.type, event_id=envelope.id
        )
        self.published.append(envelope)
