"""Canonical event and audit contracts (v1).

These models are the single source of truth for the wire contracts. JSON
Schemas in ``packages/contracts/schemas`` are generated from them, so the
Python producers, the TypeScript consumers, and the documentation cannot drift.

See docs/contracts/event-conventions.md for the envelope rules.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_TENANT_ID_PATTERN = r"^tnt_[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
_ULID_PATTERN = r"^evt_[0-9A-HJKMNP-TV-Z]{26}$"
_EVENT_TYPE_PATTERN = r"^argus\.[a-z0-9]+(\.[a-z0-9]+)+\.v[0-9]+$"
_REGION_PATTERN = r"^[a-z]{2}(-[a-z]+)+-[0-9]$"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"

_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_LOCK = threading.Lock()
_ULID_LAST: tuple[int, int] = (0, 0)


def new_ulid(*, timestamp_ms: int | None = None) -> str:
    """Generate a monotonic ULID (48-bit ms + 80-bit sequence).

    Within one millisecond the random component is incremented rather than
    re-drawn, so identifiers created by a single process sort in creation
    order. Ordering across processes is still only millisecond-accurate.
    """
    global _ULID_LAST
    millis = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    millis &= (1 << 48) - 1
    with _ULID_LOCK:
        last_ms, last_rand = _ULID_LAST
        if millis <= last_ms:
            millis = last_ms
            rand = (last_rand + 1) & ((1 << 80) - 1)
        else:
            rand = int.from_bytes(os.urandom(10), "big")
        _ULID_LAST = (millis, rand)
    value = (millis << 80) | rand
    return "".join(_CROCKFORD32[(value >> (5 * shift)) & 0x1F] for shift in range(25, -1, -1))


def new_event_id() -> str:
    return f"evt_{new_ulid()}"


def new_uuid7() -> UUID:
    """RFC 9562 UUIDv7: time-ordered, index-friendly primary keys."""
    millis = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    value = (millis << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


def new_tenant_id() -> str:
    return f"tnt_{new_uuid7()}"


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class EventType(StrEnum):
    """Event types published on the internal bus (subject may narrow scope)."""

    RESOURCE_DISCOVERED = "argus.resource.discovered.v1"
    RESOURCE_CHANGED = "argus.resource.changed.v1"
    RESOURCE_DELETED = "argus.resource.deleted.v1"
    SYNC_COMPLETED = "argus.sync.completed.v1"
    FINDING_DETECTED = "argus.finding.detected.v1"
    ACTION_REQUESTED = "argus.action.requested.v1"
    ACTION_APPROVED = "argus.action.approved.v1"
    ACTION_EXECUTED = "argus.action.executed.v1"
    ACTION_FAILED = "argus.action.failed.v1"
    COST_UPDATED = "argus.cost.updated.v1"
    AUDIT_APPENDED = "argus.audit.appended.v1"
    WORKER_HEARTBEAT = "argus.worker.heartbeat.v1"


class EventEnvelope(BaseModel):
    """CloudEvents-compatible envelope carried by every internal event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(default_factory=new_event_id, pattern=_ULID_PATTERN)
    type: str = Field(
        pattern=_EVENT_TYPE_PATTERN,
        # Surface the closed vocabulary in the JSON Schema so non-Python
        # consumers reject unknown types at the edge, not in a worker.
        json_schema_extra={"enum": [member.value for member in EventType]},
    )
    source: str = Field(pattern=r"^argus\.[a-z0-9]+(-[a-z0-9]+)*$")
    tenant_id: str = Field(pattern=_TENANT_ID_PATTERN)
    account_id: str | None = Field(default=None, pattern=r"^[0-9]{12}$")
    region: str | None = Field(default=None, pattern=_REGION_PATTERN)
    subject: str | None = Field(default=None, max_length=2048)
    time: datetime = Field(default_factory=utcnow)
    idempotency_key: str = Field(min_length=1, max_length=256)
    trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    schema_version: Literal["1.0"] = "1.0"
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("time")
    @classmethod
    def _normalise_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("event time must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        known = {member.value for member in EventType}
        if value not in known:
            raise ValueError(f"unknown event type: {value}")
        return value


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    SERVICE = "service"


class AuditEvent(BaseModel):
    """Hash-chained audit record. Append-only; enforced by DB privileges."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID = Field(default_factory=new_uuid7)
    tenant_id: str = Field(pattern=_TENANT_ID_PATTERN)
    actor_type: ActorType
    actor_id: str | None = Field(default=None, max_length=256)
    action: str = Field(min_length=3, max_length=128, pattern=r"^[a-z][a-z0-9_.:-]*$")
    resource_type: str | None = Field(default=None, max_length=128)
    resource_id: str | None = Field(default=None, max_length=512)
    request_id: str | None = Field(default=None, max_length=128)
    trace_id: str | None = Field(default=None, max_length=64)
    source_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=512)
    before_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    after_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    metadata: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    hash: str = Field(pattern=_SHA256_PATTERN)
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("created_at")
    @classmethod
    def _normalise_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    @classmethod
    def create(cls, *, prev_hash: str | None = None, **fields: Any) -> AuditEvent:
        """Build a sealed audit record whose ``hash`` chains to ``prev_hash``."""
        # Validate through the model so coercions (e.g. enum members) happen
        # before hashing; a placeholder hash satisfies the required field.
        draft = cls.model_validate({**fields, "prev_hash": prev_hash, "hash": "0" * 64})
        payload = draft.model_dump(mode="json", exclude={"hash"})
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        chained = hashlib.sha256(f"{prev_hash or ''}{digest}".encode()).hexdigest()
        return draft.model_copy(update={"hash": chained})


def build_envelope(
    *,
    event_type: EventType | str,
    source: str,
    tenant_id: str,
    idempotency_key: str,
    data: dict[str, Any] | None = None,
    account_id: str | None = None,
    region: str | None = None,
    subject: str | None = None,
    trace_id: str | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        type=str(event_type),
        source=source,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        data=data or {},
        account_id=account_id,
        region=region,
        subject=subject,
        trace_id=trace_id,
    )
