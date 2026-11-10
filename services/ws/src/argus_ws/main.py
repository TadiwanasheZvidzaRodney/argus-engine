"""WebSocket delta gateway with Redis Stream resumption and PubSub relay."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from argus_core.errors import ArgusError, Unauthorized
from argus_core.events import new_tenant_id
from argus_core.health import liveness_report
from argus_core.logging import configure_logging, get_logger
from argus_core.settings import Settings
from argus_core.telemetry import configure_telemetry
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from redis.asyncio import Redis

from argus_ws.protocol import (
    MAX_FRAME_BYTES,
    ClientFrame,
    ClientFrameType,
    DeltaData,
    ErrorData,
    HelloData,
    ServerFrame,
    ServerFrameType,
)

_TENANT_ID = re.compile(
    r"^tnt_[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

CLOSE_POLICY_VIOLATION = 1008
CLOSE_TRY_AGAIN_LATER = 1013


class SubscriptionHub:
    """Per-connection topic subscription state."""

    def __init__(self) -> None:
        self.topics: set[str] = set()

    def subscribe(self, topics: list[str]) -> set[str]:
        self.topics.update(topics)
        return set(self.topics)

    def unsubscribe(self, topics: list[str]) -> set[str]:
        self.topics.difference_update(topics)
        return set(self.topics)


class Connection:
    """Sequenced server-frame emitter with size guarding."""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.seq = 0

    async def send(self, frame_type: ServerFrameType, data: dict[str, Any]) -> None:
        frame = ServerFrame(type=frame_type, seq=self.seq, data=data)
        self.seq += 1
        payload = frame.model_dump_json()
        if len(payload.encode("utf-8")) > MAX_FRAME_BYTES:
            payload = ServerFrame(
                type=ServerFrameType.ERROR,
                seq=self.seq,
                data=ErrorData(
                    code="frame-too-large",
                    message="Resync required; delta exceeded the frame budget.",
                    retryable=True,
                ).model_dump(),
            ).model_dump_json()
            self.seq += 1
        await self.websocket.send_text(payload)

    async def send_delta(self, delta: DeltaData) -> None:
        await self.send(ServerFrameType.DELTA, delta.model_dump())


def _resolve_tenant(settings: Settings, requested: str | None) -> str:
    if settings.auth_mode == "oidc":
        raise Unauthorized("Token authentication is not enabled in this build.")
    if requested is None:
        return settings.default_tenant_id or new_tenant_id()
    if not _TENANT_ID.match(requested):
        raise Unauthorized("Tenant identifier is malformed.")
    return requested


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings(service_name="argus-ws")
    configure_logging(settings)
    configure_telemetry(settings)
    log = get_logger("argus_ws")

    redis_client: Redis | None = None
    if settings.env.value != "test":
        try:
            redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            redis_client = None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("gateway.started", heartbeat_seconds=settings.idempotency_lock_seconds)
        yield
        if redis_client is not None:
            await redis_client.aclose()
        log.info("gateway.stopped")

    app = FastAPI(
        title="Argus WebSocket Gateway", version=settings.service_version, lifespan=lifespan
    )
    app.state.redis = redis_client

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        report = await liveness_report(settings)
        return report.model_dump(mode="json")

    @app.get("/readyz")
    async def readyz() -> dict[str, Any]:
        report = await liveness_report(settings)
        return report.model_dump(mode="json")

    @app.websocket("/ws/v1/stream")
    async def stream(websocket: WebSocket, tenant_id: str | None = None) -> None:
        try:
            tenant = _resolve_tenant(settings, tenant_id)
        except ArgusError:
            await websocket.close(code=CLOSE_POLICY_VIOLATION, reason="tenant-required")
            return

        await websocket.accept()
        connection = Connection(websocket)
        hub = SubscriptionHub()
        heartbeat = max(5, settings.idempotency_lock_seconds)

        await connection.send(
            ServerFrameType.HELLO,
            HelloData(
                connection_id=uuid4(),
                tenant_id=tenant,
                heartbeat_seconds=heartbeat,
            ).model_dump(mode="json"),
        )
        log.info("connection.opened", tenant_id=tenant)

        pubsub_task: asyncio.Task[None] | None = None

        async def listen_pubsub() -> None:
            if redis_client is None:
                return
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(f"channel:{tenant}:deltas")
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            delta_payload = json.loads(message["data"])
                            await connection.send(ServerFrameType.DELTA, delta_payload)
                        except Exception:  # noqa: S110
                            pass
            finally:
                await pubsub.unsubscribe(f"channel:{tenant}:deltas")
                await pubsub.close()

        if redis_client is not None:
            pubsub_task = asyncio.create_task(listen_pubsub())

        try:
            while True:
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=heartbeat)
                except TimeoutError:
                    await connection.send(ServerFrameType.PING, {"awaiting": "pong"})
                    continue

                if len(raw.encode("utf-8")) > MAX_FRAME_BYTES:
                    await connection.send(
                        ServerFrameType.ERROR,
                        ErrorData(
                            code="frame-too-large", message="Frame exceeded 64 KiB."
                        ).model_dump(),
                    )
                    continue

                try:
                    frame = ClientFrame.model_validate(json.loads(raw))
                except (json.JSONDecodeError, ValidationError):
                    await connection.send(
                        ServerFrameType.ERROR,
                        ErrorData(
                            code="invalid-frame", message="Frame failed schema validation."
                        ).model_dump(),
                    )
                    continue

                if frame.type is ClientFrameType.SUBSCRIBE:
                    topics = hub.subscribe(frame.topics)
                    await connection.send(ServerFrameType.ACK, {"topics": sorted(topics)})
                elif frame.type is ClientFrameType.UNSUBSCRIBE:
                    topics = hub.unsubscribe(frame.topics)
                    await connection.send(ServerFrameType.ACK, {"topics": sorted(topics)})
                elif frame.type is ClientFrameType.RESUME:
                    if frame.resume_from_seq is None or redis_client is None:
                        await connection.send(
                            ServerFrameType.SNAPSHOT_REQUIRED,
                            {"reason": "resumption not supported in this environment"},
                        )
                    else:
                        # Inspect stream for sequence
                        stream_key = f"stream:{tenant}:deltas"
                        try:
                            entries = await redis_client.xrange(
                                stream_key, min="-", max="+", count=100
                            )
                            # Replay entries with seq >= resume_from_seq
                            replayed = 0
                            for _, data in entries or []:
                                if data and isinstance(data, dict):
                                    entry_seq = int(data.get("seq", 0))
                                    if entry_seq >= frame.resume_from_seq:
                                        payload = json.loads(str(data.get("payload", "{}")))
                                        await connection.send(ServerFrameType.DELTA, payload)
                                        replayed += 1
                            if replayed == 0 and entries:
                                await connection.send(
                                    ServerFrameType.SNAPSHOT_REQUIRED,
                                    {
                                        "reason": (
                                            "requested sequence has expired from stream retention"
                                        )
                                    },
                                )
                            else:
                                await connection.send(
                                    ServerFrameType.ACK, {"resumed_count": replayed}
                                )
                        except Exception:
                            await connection.send(
                                ServerFrameType.SNAPSHOT_REQUIRED,
                                {"reason": "stream error during replay"},
                            )
                else:  # pong
                    continue
        except WebSocketDisconnect:
            log.info("connection.closed", tenant_id=tenant)
        except Exception as exc:
            log.warning("connection.aborted", tenant_id=tenant, error=type(exc).__name__)
            await websocket.close(code=CLOSE_TRY_AGAIN_LATER)
        finally:
            if pubsub_task is not None:
                pubsub_task.cancel()

    return app


def app_factory() -> FastAPI:
    return create_app()
