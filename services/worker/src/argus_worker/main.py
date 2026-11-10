"""Worker entry point.

Phase 0 exercises the operational spine: structured startup, a typed event
emitted on a schedule, idempotency keys that survive restarts, and graceful
SIGTERM handling so ECS can drain tasks without losing a tick.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import sys
from datetime import UTC, datetime
from typing import Any

from argus_core.events import EventEnvelope, EventType, build_envelope, new_tenant_id
from argus_core.logging import configure_logging, get_logger
from argus_core.settings import Environment, Settings
from redis.asyncio import Redis

from argus_worker.queue import EventSink, LoggingEventSink, RedisEventSink

HEARTBEAT_SOURCE = "argus.worker"


def heartbeat_idempotency_key(tenant_id: str, now: datetime) -> str:
    """One heartbeat per tenant per minute, stable across retries."""
    return f"{HEARTBEAT_SOURCE}:{tenant_id}:{now:%Y%m%dT%H%M}"


async def emit_heartbeat(
    sink: EventSink, settings: Settings, *, tenant_id: str | None = None
) -> EventEnvelope:
    now = datetime.now(tz=UTC)
    tenant = tenant_id or settings.default_tenant_id or new_tenant_id()
    envelope = build_envelope(
        event_type=EventType.WORKER_HEARTBEAT,
        source=HEARTBEAT_SOURCE,
        tenant_id=tenant,
        idempotency_key=heartbeat_idempotency_key(tenant, now),
        data={"pid": os.getpid(), "phase": "phase-0"},
    )
    await sink.publish(envelope)
    return envelope


async def run_forever(
    sink: EventSink,
    settings: Settings,
    *,
    interval_seconds: float = 30.0,
    max_iterations: int | None = None,
) -> int:
    log = get_logger("argus_worker")
    stop = asyncio.Event()

    def request_stop(*_: Any) -> None:
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        # Not on the main thread (e.g. embedded in tests) -> no signal handling.
        with contextlib.suppress(ValueError):
            signal.signal(sig, request_stop)

    log.info("worker.started", interval_seconds=interval_seconds)
    iterations = 0
    while not stop.is_set():
        envelope = await emit_heartbeat(sink, settings)
        iterations += 1
        log.info("worker.tick", event_id=envelope.id, iterations=iterations)
        if max_iterations is not None and iterations >= max_iterations:
            break
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
    log.info("worker.stopped", iterations=iterations)
    return 0


async def check_health(settings: Settings) -> bool:
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.ping()
        return True
    except Exception:
        return False
    finally:
        await client.aclose()


def _build_sink(settings: Settings) -> EventSink:
    if settings.env is Environment.LOCAL:
        client = Redis.from_url(settings.queue_url, decode_responses=True)
        return RedisEventSink(client)
    return LoggingEventSink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="argus-worker", description="Argus worker runtime")
    parser.add_argument("command", choices=["run", "once", "health", "version"])
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--tenant-id", default=None)
    return parser


async def _async_main(args: argparse.Namespace, settings: Settings) -> int:
    if args.command == "once":
        sink = _build_sink(settings)
        envelope = await emit_heartbeat(sink, settings, tenant_id=args.tenant_id)
        print(envelope.model_dump_json())  # noqa: T201
        return 0
    if args.command == "run":
        sink = _build_sink(settings)
        return await run_forever(sink, settings, interval_seconds=args.interval)
    if args.command == "health":
        return 0 if await check_health(settings) else 1
    print(settings.service_version)  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings(service_name="argus-worker")
    configure_logging(settings)
    return asyncio.run(_async_main(args, settings))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
