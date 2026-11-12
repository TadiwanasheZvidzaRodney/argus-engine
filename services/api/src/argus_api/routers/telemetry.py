"""Telemetry subscription, snapshot, quota, and SSE streaming API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from argus_core.errors import NotFound, UnprocessableEntity
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.models import TelemetrySubscriptionModel
from argus_api.routers.sync import _get_graph_repo
from argus_api.telemetry.catalog import catalog_payload
from argus_api.telemetry.service import (
    VALID_RESOLUTIONS,
    cancel_subscription,
    collect_snapshot,
    create_subscription,
    load_subscription,
    quota_status,
    sse_events,
)

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


class SubscriptionRequest(BaseModel):
    resource_ids: list[str] = Field(min_length=1, max_length=500)
    metrics: list[str] = Field(min_length=1, max_length=6)
    resolution: int = Field(default=60)


class SubscriptionResponse(BaseModel):
    id: str
    status: str
    resource_ids: list[str]
    metrics: list[str]
    resolution: int
    degraded: bool
    expires_at: datetime
    created_at: datetime
    quota: dict[str, Any] | None = None


class SnapshotRequest(BaseModel):
    resource_ids: list[str] = Field(min_length=1, max_length=500)
    metrics: list[str] = Field(default_factory=list, max_length=6)
    resolution: int = Field(default=60)
    periods: int = Field(default=30, ge=1, le=240)


class SnapshotResponse(BaseModel):
    samples: list[dict[str, Any]]
    resolution: int
    quota: dict[str, Any]
    generated_at: datetime


def _response(subscription: TelemetrySubscriptionModel) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=str(subscription.id),
        status=subscription.status,
        resource_ids=list(subscription.resource_ids),
        metrics=list(subscription.metrics),
        resolution=subscription.resolution,
        degraded=subscription.degraded,
        expires_at=subscription.expires_at,
        created_at=subscription.created_at,
    )


def _parse_subscription_id(value: str) -> UUID:
    raw = value.removeprefix("sub_")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise NotFound(f"{value} is not a valid subscription identifier.") from exc


async def _load_resources(
    request: Request, auth: AuthContext, resource_ids: list[str]
) -> list[dict[str, Any]]:
    repo = _get_graph_repo(request)
    resources: list[dict[str, Any]] = []
    for resource_id in resource_ids:
        detail = await repo.get_resource_detail(f"tnt_{auth.tenant_id}", resource_id)
        if detail is not None:
            resources.append(detail)
    return resources


@router.get("/catalog", summary="Supported metrics per resource type")
async def telemetry_catalog(
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[dict[str, Any]]:
    return catalog_payload()


@router.get("/quota", summary="Per-tenant telemetry quota and cost")
async def telemetry_quota(
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    return await quota_status(session, auth.tenant_id, request.app.state.settings)


@router.post(
    "/subscriptions",
    response_model=SubscriptionResponse,
    status_code=201,
    summary="Create a scoped metric subscription",
)
async def subscribe(
    body: SubscriptionRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> SubscriptionResponse:
    subscription = await create_subscription(
        session,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        settings=request.app.state.settings,
        resource_ids=body.resource_ids,
        metrics=body.metrics,
        resolution=body.resolution,
    )
    response = _response(subscription)
    response.quota = await quota_status(session, auth.tenant_id, request.app.state.settings)
    return response


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionResponse,
    summary="Subscription status and quota usage",
)
async def get_subscription(
    subscription_id: str,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> SubscriptionResponse:
    subscription = await load_subscription(
        session, auth.tenant_id, auth.user_id, _parse_subscription_id(subscription_id)
    )
    response = _response(subscription)
    response.quota = await quota_status(session, auth.tenant_id, request.app.state.settings)
    return response


@router.delete(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionResponse,
    summary="Cancel a subscription",
)
async def unsubscribe(
    subscription_id: str,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> SubscriptionResponse:
    subscription = await cancel_subscription(
        session, auth.tenant_id, auth.user_id, _parse_subscription_id(subscription_id)
    )
    return _response(subscription)


@router.get("/stream", summary="SSE metric stream for a subscription")
async def stream(
    request: Request,
    subscription_id: str = Query(min_length=4),
    periods: int = Query(default=30, ge=1, le=240),
    iterations: int = Query(default=1, ge=1, le=10),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> StreamingResponse:
    subscription = await load_subscription(
        session, auth.tenant_id, auth.user_id, _parse_subscription_id(subscription_id)
    )
    resources = await _load_resources(request, auth, list(subscription.resource_ids))
    samples = await collect_snapshot(
        session,
        tenant_id=auth.tenant_id,
        settings=request.app.state.settings,
        resources=resources,
        metrics=list(subscription.metrics),
        resolution=subscription.resolution,
        periods=periods,
        subscription_id=str(subscription.id),
        redis_client=getattr(request.app.state, "redis_client", None),
    )
    frames = sse_events(
        samples=samples,
        subscription_id=str(subscription.id),
        keepalive_seconds=request.app.state.settings.telemetry_sse_keepalive_seconds,
        max_iterations=iterations,
    )
    return StreamingResponse(
        frames,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/snapshot", response_model=SnapshotResponse, summary="One-shot metric snapshot")
async def snapshot(
    body: SnapshotRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> SnapshotResponse:
    if body.resolution not in VALID_RESOLUTIONS:
        raise UnprocessableEntity("Resolution must be 60, 300, or 3600 seconds.")
    resources = await _load_resources(request, auth, body.resource_ids)
    samples = await collect_snapshot(
        session,
        tenant_id=auth.tenant_id,
        settings=request.app.state.settings,
        resources=resources,
        metrics=body.metrics or ["CPUUtilization"],
        resolution=body.resolution,
        periods=body.periods,
        redis_client=getattr(request.app.state, "redis_client", None),
    )
    return SnapshotResponse(
        samples=samples,
        resolution=body.resolution,
        quota=await quota_status(session, auth.tenant_id, request.app.state.settings),
        generated_at=datetime.now(tz=UTC),
    )


__all__ = ["router"]
