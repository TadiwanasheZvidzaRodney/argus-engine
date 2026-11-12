"""Tenant usage metering, commercial consumption tracking, and unit economics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from argus_core.events import new_uuid7
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.models import UsageMeteringModel


async def record_tenant_metering(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    resources_count: int,
    events_ingested: int = 0,
    metric_requests: int = 0,
    actions_planned: int = 0,
    actions_executed: int = 0,
    storage_bytes: int = 0,
) -> dict[str, Any]:
    """Upsert daily consumption record and estimate marginal cost."""
    today = datetime.now(tz=UTC).date()
    existing = (
        await session.execute(
            select(UsageMeteringModel).where(
                UsageMeteringModel.tenant_id == tenant_id,
                UsageMeteringModel.period_date == today,
            )
        )
    ).scalar_one_or_none()

    # Unit economics estimate: $0.001/resource + $0.00001/event + $0.00001/metric + $0.05/action
    cost = (
        (resources_count * 0.001)
        + (events_ingested * 0.00001)
        + (metric_requests * 0.00001)
        + (actions_executed * 0.05)
    )

    if existing is None:
        rec = UsageMeteringModel(
            id=new_uuid7(),
            tenant_id=tenant_id,
            period_date=today,
            resources_count=resources_count,
            events_ingested=events_ingested,
            metric_requests=metric_requests,
            actions_planned=actions_planned,
            actions_executed=actions_executed,
            storage_bytes=storage_bytes,
            estimated_cost_usd=round(cost, 4),
        )
        session.add(rec)
    else:
        existing.resources_count = max(existing.resources_count, resources_count)
        existing.events_ingested += events_ingested
        existing.metric_requests += metric_requests
        existing.actions_planned += actions_planned
        existing.actions_executed += actions_executed
        existing.storage_bytes = max(existing.storage_bytes, storage_bytes)
        existing.estimated_cost_usd = round(cost, 4)
        rec = existing

    await session.flush()
    return {
        "tenant_id": str(tenant_id),
        "period_date": today.isoformat(),
        "resources_count": rec.resources_count,
        "events_ingested": rec.events_ingested,
        "metric_requests": rec.metric_requests,
        "actions_executed": rec.actions_executed,
        "estimated_cost_usd": float(rec.estimated_cost_usd),
    }


async def get_tenant_metering_summary(
    session: AsyncSession,
    tenant_id: UUID,
) -> list[dict[str, Any]]:
    """Return historical 30-day metering consumption for a tenant."""
    rows = (
        (
            await session.execute(
                select(UsageMeteringModel)
                .where(UsageMeteringModel.tenant_id == tenant_id)
                .order_by(desc(UsageMeteringModel.period_date))
                .limit(30)
            )
        )
        .scalars()
        .all()
    )

    return [
        {
            "period_date": r.period_date.isoformat(),
            "resources_count": r.resources_count,
            "events_ingested": r.events_ingested,
            "metric_requests": r.metric_requests,
            "actions_planned": r.actions_planned,
            "actions_executed": r.actions_executed,
            "storage_bytes": r.storage_bytes,
            "estimated_cost_usd": float(r.estimated_cost_usd),
        }
        for r in rows
    ]
