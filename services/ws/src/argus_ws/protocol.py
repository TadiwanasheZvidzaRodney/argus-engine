"""WebSocket wire protocol v1.

Frames are JSON objects with a monotonically increasing ``seq`` per connection.
Clients treat ``seq`` gaps as a signal to resync via the REST snapshot API
(Phase 4) rather than assuming they can patch the graph incrementally.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROTOCOL_VERSION: Literal[1] = 1
MAX_FRAME_BYTES = 64 * 1024


class ServerFrameType(StrEnum):
    HELLO = "hello"
    ACK = "ack"
    DELTA = "delta"
    PING = "ping"
    ERROR = "error"


class ClientFrameType(StrEnum):
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PONG = "pong"


class ServerFrame(BaseModel):
    model_config = ConfigDict(frozen=True)

    v: Literal[1] = PROTOCOL_VERSION
    type: ServerFrameType
    seq: int = Field(ge=0)
    ts: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ts")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class ClientFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    v: Literal[1] = PROTOCOL_VERSION
    type: ClientFrameType
    topics: list[str] = Field(default_factory=list, max_length=50)


class HelloData(BaseModel):
    connection_id: UUID
    tenant_id: str
    protocol_version: int = PROTOCOL_VERSION
    heartbeat_seconds: int
    supports: list[str] = Field(default_factory=lambda: ["delta", "resync-hint"])


class DeltaData(BaseModel):
    event_type: str
    subject: str | None = None
    resource_id: str | None = None
    revision: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ErrorData(BaseModel):
    code: str
    message: str
    retryable: bool = False
