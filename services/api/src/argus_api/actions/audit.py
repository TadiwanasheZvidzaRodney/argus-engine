"""Hash-chained audit and immutable evidence helpers for actions."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from argus_core.events import AuditEvent, new_uuid7
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.actions.planner import stable_hash
from argus_api.auth import AuthContext
from argus_api.models import ActionEvidenceModel, AuditEventModel


async def append_audit(
    session: AsyncSession,
    *,
    auth: AuthContext,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEventModel:
    previous = (
        await session.execute(
            select(AuditEventModel)
            .where(AuditEventModel.tenant_id == auth.tenant_id)
            .order_by(desc(AuditEventModel.created_at), desc(AuditEventModel.id))
            .limit(1)
        )
    ).scalar_one_or_none()

    event = AuditEvent.create(
        prev_hash=previous.hash if previous else None,
        tenant_id=f"tnt_{auth.tenant_id}",
        actor_type="user",
        actor_id=str(auth.user_id),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata or {},
    )
    row = AuditEventModel(
        id=event.id,
        tenant_id=auth.tenant_id,
        actor_type=event.actor_type.value,
        actor_id=event.actor_id,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        request_id=event.request_id,
        trace_id=event.trace_id,
        source_ip=event.source_ip,
        user_agent=event.user_agent,
        before_hash=event.before_hash,
        after_hash=event.after_hash,
        metadata_=event.metadata,
        prev_hash=event.prev_hash,
        hash=event.hash,
    )
    session.add(row)
    await session.flush()
    return row


async def append_evidence(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    action_id: UUID,
    kind: str,
    payload: dict[str, Any],
    suffix: str,
) -> ActionEvidenceModel:
    checksum = stable_hash(payload)
    uri = f"s3://argus-action-evidence/tenant=tnt_{tenant_id}/action=act_{action_id.hex}/{suffix}"
    row = ActionEvidenceModel(
        id=new_uuid7(),
        tenant_id=tenant_id,
        action_id=action_id,
        kind=kind,
        uri=uri,
        checksum=checksum,
        payload=payload,
    )
    session.add(row)
    await session.flush()
    return row


def evidence_payload_size(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, default=str))
