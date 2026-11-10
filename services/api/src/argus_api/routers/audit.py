"""Audit events query and chain verification router."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from argus_core.pagination import Page, decode_cursor
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.models import AuditEventModel

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit"])


class AuditItem(BaseModel):
    id: str
    actor_type: str
    actor_id: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    prev_hash: str | None = None
    hash: str
    created_at: datetime


class ChainVerificationResponse(BaseModel):
    total_records: int
    chain_valid: bool
    first_hash: str | None = None
    latest_hash: str | None = None
    message: str


@router.get("", response_model=Page[AuditItem], summary="Query audit trail")
async def list_audit_events(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_AUDIT)),
) -> Page[AuditItem]:
    secret = request.app.state.settings.cursor_secret.get_secret_value()

    query = (
        select(AuditEventModel)
        .where(AuditEventModel.tenant_id == auth.tenant_id)
        .order_by(desc(AuditEventModel.created_at), desc(AuditEventModel.id))
        .limit(limit + 1)
    )

    if action:
        query = query.where(AuditEventModel.action == action)
    if actor_id:
        query = query.where(AuditEventModel.actor_id == actor_id)

    if cursor:
        cursor_data = decode_cursor(cursor, secret=secret)
        last_time = datetime.fromisoformat(cursor_data["created_at"])
        last_id = UUID(cursor_data["id"])
        query = query.where(
            (AuditEventModel.created_at < last_time)
            | ((AuditEventModel.created_at == last_time) & (AuditEventModel.id < last_id))
        )

    result = await session.execute(query)
    records = result.scalars().all()

    has_more = len(records) > limit
    page_records = records[:limit]

    next_payload = None
    if has_more and page_records:
        last = page_records[-1]
        next_payload = {"created_at": last.created_at.isoformat(), "id": str(last.id)}

    items = [
        AuditItem(
            id=f"aud_{r.id.hex}",
            actor_type=r.actor_type,
            actor_id=r.actor_id,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            request_id=r.request_id,
            trace_id=r.trace_id,
            prev_hash=r.prev_hash,
            hash=r.hash,
            created_at=r.created_at,
        )
        for r in page_records
    ]

    return Page[AuditItem].build(
        items,
        limit=limit,
        next_payload=next_payload,
        secret=secret,
    )


@router.post("/verify", response_model=ChainVerificationResponse, summary="Verify audit hash chain")
async def verify_audit_chain(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_AUDIT)),
) -> ChainVerificationResponse:
    stmt = (
        select(AuditEventModel)
        .where(AuditEventModel.tenant_id == auth.tenant_id)
        .order_by(AuditEventModel.created_at.asc(), AuditEventModel.id.asc())
    )
    records = (await session.execute(stmt)).scalars().all()

    if not records:
        return ChainVerificationResponse(
            total_records=0,
            chain_valid=True,
            message="No audit records present for this tenant.",
        )

    prev_hash: str | None = None
    for r in records:
        if r.prev_hash != prev_hash:
            return ChainVerificationResponse(
                total_records=len(records),
                chain_valid=False,
                message=(
                    f"Broken hash chain at record {r.id}: "
                    f"expected prev_hash {prev_hash}, got {r.prev_hash}"
                ),
            )
        prev_hash = r.hash

    return ChainVerificationResponse(
        total_records=len(records),
        chain_valid=True,
        first_hash=records[0].hash,
        latest_hash=records[-1].hash,
        message="Cryptographic hash chain verified successfully.",
    )
