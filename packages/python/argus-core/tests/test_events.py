from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from argus_core.events import (
    AuditEvent,
    EventEnvelope,
    EventType,
    build_envelope,
    new_event_id,
    new_tenant_id,
    new_uuid7,
)
from argus_core.schema_export import audit_event_schema, check_schemas, event_envelope_schema
from pydantic import ValidationError


def test_tenant_id_is_prefixed_uuid7() -> None:
    tenant_id = new_tenant_id()
    assert tenant_id.startswith("tnt_")
    assert UUID(tenant_id.removeprefix("tnt_")).version == 7


def test_uuid7_is_time_prefixed() -> None:
    first = new_uuid7()
    second = new_uuid7()
    assert first.version == 7
    assert second.version == 7
    # The 48-bit timestamp prefix never moves backwards within a process.
    assert (first.int >> 80) <= (second.int >> 80)


def test_ulid_ids_are_sortable_and_prefixed() -> None:
    ids = [new_event_id() for _ in range(50)]
    assert all(i.startswith("evt_") and len(i) == 30 for i in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_event_envelope_accepts_documented_example() -> None:
    envelope = build_envelope(
        event_type=EventType.RESOURCE_CHANGED,
        source="argus.discovery",
        tenant_id=new_tenant_id(),
        idempotency_key="aws-config:123456789012:us-east-1:v3",
        account_id="123456789012",
        region="us-east-1",
        subject="arn:aws:ec2:us-east-1:123456789012:instance/i-0abc",
        data={"change": "MODIFIED"},
    )
    payload = envelope.model_dump(mode="json")
    assert payload["type"] == "argus.resource.changed.v1"
    assert payload["schema_version"] == "1.0"
    assert payload["time"].endswith("Z") or "+00:00" in payload["time"]
    # Round-trip: the serialized form must validate back to the same object.
    assert EventEnvelope.model_validate(payload) == envelope


def test_event_envelope_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError, match="unknown event type"):
        EventEnvelope(
            type="argus.resource.exploded.v1",
            source="argus.discovery",
            tenant_id=new_tenant_id(),
            idempotency_key="k",
        )


def test_event_envelope_rejects_naive_time() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        EventEnvelope(
            type="argus.resource.changed.v1",
            source="argus.discovery",
            tenant_id=new_tenant_id(),
            idempotency_key="k",
            time=datetime(2026, 1, 1),
        )


def test_event_envelope_rejects_raw_uuid_tenant() -> None:
    with pytest.raises(ValidationError):
        EventEnvelope(
            type="argus.resource.changed.v1",
            source="argus.discovery",
            tenant_id="8c1d0b0e-0000-7000-8000-000000000000",
            idempotency_key="k",
        )


def test_audit_hash_chains_to_previous_record() -> None:
    tenant_id = new_tenant_id()
    first = AuditEvent.create(
        tenant_id=tenant_id,
        actor_type="user",
        actor_id="user_123",
        action="tenant.connected",
        resource_type="aws_account",
        resource_id="123456789012",
    )
    second = AuditEvent.create(
        tenant_id=tenant_id,
        actor_type="user",
        actor_id="user_123",
        action="tenant.connected",
        resource_type="aws_account",
        resource_id="123456789012",
        prev_hash=first.hash,
    )
    assert first.prev_hash is None
    assert second.prev_hash == first.hash
    assert first.hash != second.hash


def test_audit_hash_is_deterministic_for_fixed_input() -> None:
    tenant_id = "tnt_0190c3a1-0000-7000-8000-000000000000"
    kwargs = {
        "id": UUID("0190c3a1-0000-7000-8000-000000000001"),
        "tenant_id": tenant_id,
        "actor_type": "system",
        "action": "sync.completed",
        "created_at": datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
    }
    assert AuditEvent.create(**kwargs).hash == AuditEvent.create(**kwargs).hash


def test_audit_event_rejects_unknown_actor_type() -> None:
    with pytest.raises(ValidationError):
        AuditEvent.create(
            tenant_id=new_tenant_id(),
            actor_type="robot",
            action="sync.completed",
        )


def test_contract_schemas_are_json_serialisable() -> None:
    for schema in (event_envelope_schema(), audit_event_schema()):
        assert schema["$id"].startswith("https://schemas.argus.example.com/")
        json.dumps(schema)


def test_checked_in_schemas_match_models(tmp_path) -> None:
    stale = check_schemas(tmp_path)
    assert sorted(stale) == ["audit-event.v1.json", "event-envelope.v1.json"]
