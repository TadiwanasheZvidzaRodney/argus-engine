"""Telemetry subscription registry, quotas, cost accounting, and SSE helpers."""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from argus_core.errors import Forbidden, NotFound, RateLimited, UnprocessableEntity
from argus_core.events import new_uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.models import TelemetrySubscriptionModel, TelemetryUsageModel
from argus_api.telemetry.catalog import metric_names_for_type
from argus_api.telemetry.collector import MetricCollector

if TYPE_CHECKING:
    from argus_api.settings import ApiSettings

VALID_RESOLUTIONS = frozenset({60, 300, 3600})


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _today() -> date:
    return datetime.now(tz=UTC).date()


async def usage_for_today(session: AsyncSession, tenant_id: UUID) -> TelemetryUsageModel | None:
    result = await session.execute(
        select(TelemetryUsageModel).where(
            TelemetryUsageModel.tenant_id == tenant_id,
            TelemetryUsageModel.period_date == _today(),
        )
    )
    return result.scalar_one_or_none()


async def quota_status(
    session: AsyncSession, tenant_id: UUID, settings: ApiSettings
) -> dict[str, Any]:
    usage = await usage_for_today(session, tenant_id)
    used = usage.metric_requests if usage else 0
    budget = settings.telemetry_daily_metric_budget
    return {
        "period_date": _today().isoformat(),
        "metric_requests": used,
        "daily_budget": budget,
        "remaining": max(0, budget - used),
        "percent_used": round(used / budget * 100, 2) if budget else 100.0,
        "estimated_cost_usd": float(usage.estimated_cost_usd) if usage else 0.0,
        "degraded": used >= budget,
    }


async def record_usage(
    session: AsyncSession,
    tenant_id: UUID,
    metric_requests: int,
    settings: ApiSettings,
) -> dict[str, Any]:
    if metric_requests <= 0:
        return await quota_status(session, tenant_id, settings)
    usage = await usage_for_today(session, tenant_id)
    if usage is None:
        usage = TelemetryUsageModel(
            id=new_uuid7(),
            tenant_id=tenant_id,
            period_date=_today(),
            metric_requests=0,
            estimated_cost_usd=0.0,
        )
        session.add(usage)
        await session.flush()
    usage.metric_requests += metric_requests
    usage.estimated_cost_usd = float(usage.estimated_cost_usd) + (
        metric_requests * settings.telemetry_cost_per_metric_usd
    )
    await session.flush()
    return await quota_status(session, tenant_id, settings)


async def _expire_stale_subscriptions(session: AsyncSession, tenant_id: UUID) -> None:
    result = await session.execute(
        select(TelemetrySubscriptionModel).where(
            TelemetrySubscriptionModel.tenant_id == tenant_id,
            TelemetrySubscriptionModel.status == "active",
            TelemetrySubscriptionModel.expires_at <= _now(),
        )
    )
    for subscription in result.scalars().all():
        subscription.status = "expired"
    await session.flush()


async def create_subscription(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    settings: ApiSettings,
    resource_ids: list[str],
    metrics: list[str],
    resolution: int,
) -> TelemetrySubscriptionModel:
    if not resource_ids:
        raise UnprocessableEntity("At least one resource ID is required.")
    if len(resource_ids) > settings.telemetry_max_resources_per_subscription:
        raise UnprocessableEntity(
            f"At most {settings.telemetry_max_resources_per_subscription} resources "
            "may be subscribed at once."
        )
    if resolution not in VALID_RESOLUTIONS:
        raise UnprocessableEntity("Resolution must be 60, 300, or 3600 seconds.")
    if not metrics:
        raise UnprocessableEntity("At least one metric is required.")
    if len(metrics) > settings.telemetry_max_metrics_per_resource:
        raise UnprocessableEntity(
            f"At most {settings.telemetry_max_metrics_per_resource} metrics may be "
            "requested per resource."
        )

    await _expire_stale_subscriptions(session, tenant_id)
    active = (
        (
            await session.execute(
                select(TelemetrySubscriptionModel).where(
                    TelemetrySubscriptionModel.tenant_id == tenant_id,
                    TelemetrySubscriptionModel.user_id == user_id,
                    TelemetrySubscriptionModel.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    if len(active) >= settings.telemetry_max_subscriptions_per_user:
        raise RateLimited(retry_after_seconds=30)

    quota = await quota_status(session, tenant_id, settings)
    estimated_requests = len(resource_ids) * len(metrics)
    degraded = bool(quota["degraded"])
    effective_resolution = resolution
    if degraded:
        effective_resolution = max(resolution, settings.telemetry_degraded_resolution_seconds)
    if quota["metric_requests"] + estimated_requests > settings.telemetry_daily_metric_budget * 2:
        raise RateLimited(retry_after_seconds=60)

    subscription = TelemetrySubscriptionModel(
        id=new_uuid7(),
        tenant_id=tenant_id,
        user_id=user_id,
        resource_ids=resource_ids,
        metrics=metrics,
        resolution=effective_resolution,
        status="active",
        degraded=degraded or effective_resolution != resolution,
        expires_at=_now() + timedelta(seconds=settings.telemetry_subscription_ttl_seconds),
    )
    session.add(subscription)
    await session.flush()
    await record_usage(session, tenant_id, estimated_requests, settings)
    return subscription


async def load_subscription(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    subscription_id: UUID,
) -> TelemetrySubscriptionModel:
    subscription = (
        await session.execute(
            select(TelemetrySubscriptionModel).where(
                TelemetrySubscriptionModel.tenant_id == tenant_id,
                TelemetrySubscriptionModel.id == subscription_id,
            )
        )
    ).scalar_one_or_none()
    if subscription is None:
        raise NotFound("Telemetry subscription not found.")
    if subscription.user_id != user_id:
        raise Forbidden("This telemetry subscription belongs to another user.")
    if subscription.expires_at <= _now():
        subscription.status = "expired"
        await session.flush()
    return subscription


async def cancel_subscription(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    subscription_id: UUID,
) -> TelemetrySubscriptionModel:
    subscription = await load_subscription(session, tenant_id, user_id, subscription_id)
    subscription.status = "cancelled"
    await session.flush()
    return subscription


async def collect_snapshot(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    settings: ApiSettings,
    resources: list[dict[str, Any]],
    metrics: list[str],
    resolution: int,
    periods: int = 30,
    subscription_id: str | None = None,
    redis_client: Any | None = None,
) -> list[dict[str, Any]]:
    """Collect metric samples and account for their cost."""
    collector = MetricCollector(_cache_for(settings, redis_client))
    if resolution not in VALID_RESOLUTIONS:
        raise UnprocessableEntity("Resolution must be 60, 300, or 3600 seconds.")
    selected_metrics = metrics or ["CPUUtilization"]
    samples = await collector.collect(
        tenant=str(tenant_id),
        resources=resources,
        metrics=selected_metrics,
        resolution=resolution,
        periods=max(1, min(periods, 240)),
        subscription_id=subscription_id,
    )
    requests = 0
    for resource in resources:
        valid = set(metric_names_for_type(str(resource.get("type", ""))))
        requests += len([metric for metric in selected_metrics if metric in valid]) or 1
    await record_usage(session, tenant_id, requests, settings)
    return samples


_CACHES: dict[tuple[int, int], Any] = {}


def _cache_for(settings: ApiSettings, redis_client: Any | None = None) -> Any:
    from argus_api.telemetry.collector import TelemetryCache

    key = (id(settings), id(redis_client))
    cache = _CACHES.get(key)
    if cache is None:
        cache = TelemetryCache(redis=redis_client, ttl_seconds=settings.telemetry_cache_ttl_seconds)
        _CACHES[key] = cache
    return cache


async def sse_events(
    *,
    samples: list[dict[str, Any]],
    subscription_id: str,
    keepalive_seconds: int = 15,
    max_iterations: int = 1,
) -> Any:
    """Yield SSE frames for a subscription snapshot.

    ``max_iterations`` is bounded so a test or a short-lived request can drain the
    generator without waiting on an infinite stream.
    """
    sequence = int(time.time())
    for iteration in range(max(1, max_iterations)):
        for sample in samples:
            sequence += 1
            event_id = f"{sequence}:{sample['resource_id']}"
            yield (
                f"id: {event_id}\n"
                "event: telemetry.sample\n"
                f"data: {json.dumps({**sample, 'subscription_id': subscription_id})}\n\n"
            )
        if iteration < max_iterations - 1:
            yield f": keepalive {keepalive_seconds}\n\n"


__all__ = [
    "VALID_RESOLUTIONS",
    "cancel_subscription",
    "collect_snapshot",
    "create_subscription",
    "load_subscription",
    "quota_status",
    "record_usage",
    "sse_events",
]
