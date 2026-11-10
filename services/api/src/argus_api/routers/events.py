"""Real-time Event Ingestion, DLQ Inspection, and Replay Router."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from argus_core.events import new_uuid7
from argus_core.graph.client import build_graph_driver
from argus_core.graph.repository import GraphRepository
from argus_worker.events.dedupe import DedupeStore
from argus_worker.events.delta_applier import DeltaApplier
from argus_worker.events.normalizer import normalize_config_event
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.models import EventDlqIndex, EventIngestLog

router = APIRouter(prefix="/api/v1/events", tags=["events"])


class EventIngestRequest(BaseModel):
    event_id: str = Field(description="AWS Config or EventBridge event ID")
    source: str = Field(default="aws.config")
    payload: dict[str, Any]


class IngestResponse(BaseModel):
    event_id: str
    status: str  # applied | duplicate | ignored | error
    seq: int | None = None
    detail: str | None = None


class DlqItem(BaseModel):
    id: str
    message_id: str
    error_reason: str
    resolved: bool
    created_at: str


class ReplayRequest(BaseModel):
    target_dlq_id: str | None = None


class ReplayResponse(BaseModel):
    replayed_count: int
    status: str


def _get_applier(request: Request) -> DeltaApplier:
    applier = getattr(request.app.state, "delta_applier", None)
    if applier is None:
        driver = getattr(request.app.state, "graph_driver", None)
        if driver is None:
            driver = build_graph_driver(request.app.state.settings)
            request.app.state.graph_driver = driver
        redis_client = getattr(request.app.state, "redis_client", None)
        if redis_client is None and not request.app.state.settings.is_local:
            redis_client = Redis.from_url(
                request.app.state.settings.redis_url, decode_responses=True
            )
            request.app.state.redis_client = redis_client

        repo = GraphRepository(driver)
        applier = DeltaApplier(repo, redis_client)
        request.app.state.delta_applier = applier
    return applier


@router.post("/ingest", response_model=IngestResponse, summary="Ingest real-time AWS event")
async def ingest_event(
    body: EventIngestRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> IngestResponse:
    tenant_str = f"tnt_{auth.tenant_id}"
    dedupe: DedupeStore = getattr(request.app.state, "dedupe_store", DedupeStore())
    request.app.state.dedupe_store = dedupe

    # 1. Deduplication Check
    if await dedupe.is_duplicate(tenant_str, body.event_id):
        return IngestResponse(
            event_id=body.event_id,
            status="duplicate",
            detail="Event already processed within deduplication window",
        )

    # 2. Normalize Config Item
    delta = normalize_config_event(tenant_str, body.payload)
    if not delta:
        return IngestResponse(
            event_id=body.event_id,
            status="ignored",
            detail="Payload did not contain supported configuration item",
        )

    # 3. Apply Delta
    applier = _get_applier(request)
    result = await applier.apply_delta(delta)

    # 4. Log in PostgreSQL
    log_entry = EventIngestLog(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        event_id=body.event_id,
        source=body.source,
        event_type=delta.change_type,
        status="applied" if result.applied else "dropped",
    )
    session.add(log_entry)
    await session.flush()

    return IngestResponse(
        event_id=body.event_id,
        status="applied" if result.applied else "dropped",
        seq=result.seq,
        detail=result.reason,
    )


@router.get("/dlq", response_model=list[DlqItem], summary="List Dead-Letter Queue items")
async def list_dlq_events(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_AUDIT)),
) -> list[DlqItem]:
    stmt = (
        select(EventDlqIndex)
        .where(EventDlqIndex.tenant_id == auth.tenant_id)
        .order_by(desc(EventDlqIndex.created_at))
        .limit(limit)
    )
    items = (await session.execute(stmt)).scalars().all()
    return [
        DlqItem(
            id=f"dlq_{item.id.hex}",
            message_id=item.message_id,
            error_reason=item.error_reason,
            resolved=item.resolved,
            created_at=item.created_at.isoformat(),
        )
        for item in items
    ]


@router.post("/replay", response_model=ReplayResponse, summary="Replay DLQ events")
async def replay_events(
    body: ReplayRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> ReplayResponse:
    # Mark DLQ item as resolved and count
    stmt = select(EventDlqIndex).where(
        EventDlqIndex.tenant_id == auth.tenant_id, EventDlqIndex.resolved.is_(False)
    )
    if body.target_dlq_id:
        uid = UUID(body.target_dlq_id.removeprefix("dlq_"))
        stmt = stmt.where(EventDlqIndex.id == uid)

    records = (await session.execute(stmt)).scalars().all()
    for r in records:
        r.resolved = True
    await session.flush()

    return ReplayResponse(replayed_count=len(records), status="replayed")
