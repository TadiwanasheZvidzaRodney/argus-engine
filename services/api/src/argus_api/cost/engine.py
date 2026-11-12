"""Cost sync coordinator, daily ingestion, and optimization evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from argus_core.events import new_uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.cost.adapter import generate_daily_costs
from argus_api.cost.allocation import estimate_resource_cost, reconcile_period_totals
from argus_api.cost.rules import evaluate_optimization_rules
from argus_api.models import (
    CostDailyModel,
    CostRecommendationModel,
    CostReconciliationModel,
    CostResourceEstimateModel,
    CostSyncJobModel,
)


async def sync_tenant_costs(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    account_id: str,
    nodes: list[dict[str, Any]],
    days: int = 30,
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Ingest cost records, compute resource estimates, reconcile, and run optimization rules."""
    now = datetime.now(tz=UTC)
    records = generate_daily_costs(
        account_id=account_id, region=region, days=days, end_date=now.date()
    )

    # 1. Upsert daily records
    ingested_count = 0
    for rec in records:
        existing = (
            await session.execute(
                select(CostDailyModel).where(
                    CostDailyModel.tenant_id == tenant_id,
                    CostDailyModel.account_id == rec.account_id,
                    CostDailyModel.region == rec.region,
                    CostDailyModel.service == rec.service,
                    CostDailyModel.usage_type == rec.usage_type,
                    CostDailyModel.tag_key == rec.tag_key,
                    CostDailyModel.tag_value == rec.tag_value,
                    CostDailyModel.period_date == rec.period_date,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                CostDailyModel(
                    id=new_uuid7(),
                    tenant_id=tenant_id,
                    account_id=rec.account_id,
                    region=rec.region,
                    service=rec.service,
                    usage_type=rec.usage_type,
                    tag_key=rec.tag_key,
                    tag_value=rec.tag_value,
                    amount=rec.amount,
                    currency=rec.currency,
                    period_date=rec.period_date,
                )
            )
            ingested_count += 1
        else:
            existing.amount = rec.amount

    await session.flush()

    # 2. Resource cost estimates for nodes in topology
    total_estimated_daily = 0.0
    for node in nodes:
        estimate = estimate_resource_cost(node)
        total_estimated_daily += estimate.daily_amount

        existing_est = (
            await session.execute(
                select(CostResourceEstimateModel).where(
                    CostResourceEstimateModel.tenant_id == tenant_id,
                    CostResourceEstimateModel.resource_id == estimate.resource_id,
                    CostResourceEstimateModel.period_date == now.date(),
                )
            )
        ).scalar_one_or_none()

        if existing_est is None:
            session.add(
                CostResourceEstimateModel(
                    id=new_uuid7(),
                    tenant_id=tenant_id,
                    resource_id=estimate.resource_id,
                    period_date=now.date(),
                    amount=estimate.monthly_amount,
                    confidence=estimate.confidence.value,
                    method=estimate.method,
                    currency=estimate.currency,
                )
            )
        else:
            existing_est.amount = estimate.monthly_amount
            existing_est.confidence = estimate.confidence.value
            existing_est.method = estimate.method

    await session.flush()

    # 3. Monthly reconciliation calculation
    month_start = now.date().replace(day=1)
    month_end = now.date()
    sum_res = await session.execute(
        select(func.sum(CostDailyModel.amount)).where(
            CostDailyModel.tenant_id == tenant_id,
            CostDailyModel.period_date >= month_start,
            CostDailyModel.tag_key.is_(None),  # base untagged records
        )
    )
    total_service_spend = float(sum_res.scalar() or 0.0)
    monthly_resource_spend = total_estimated_daily * 30.0
    allocated, unallocated, variance_pct = reconcile_period_totals(
        total_service_spend, monthly_resource_spend
    )

    reconcile_row = (
        await session.execute(
            select(CostReconciliationModel).where(
                CostReconciliationModel.tenant_id == tenant_id,
                CostReconciliationModel.period_start == month_start,
                CostReconciliationModel.period_end == month_end,
            )
        )
    ).scalar_one_or_none()

    if reconcile_row is None:
        session.add(
            CostReconciliationModel(
                id=new_uuid7(),
                tenant_id=tenant_id,
                period_start=month_start,
                period_end=month_end,
                total_amount=total_service_spend,
                allocated_amount=allocated,
                unallocated_amount=unallocated,
                variance_pct=variance_pct,
                status="reconciled" if variance_pct < 2.0 else "variance_alert",
            )
        )
    else:
        reconcile_row.total_amount = total_service_spend
        reconcile_row.allocated_amount = allocated
        reconcile_row.unallocated_amount = unallocated
        reconcile_row.variance_pct = variance_pct
        reconcile_row.status = "reconciled" if variance_pct < 2.0 else "variance_alert"

    await session.flush()

    # 4. Evaluate optimization rules
    hits = evaluate_optimization_rules(nodes)
    recs_created = 0
    for hit in hits:
        existing_rec = (
            await session.execute(
                select(CostRecommendationModel).where(
                    CostRecommendationModel.tenant_id == tenant_id,
                    CostRecommendationModel.rule_id == hit.rule_id,
                    CostRecommendationModel.resource_id == hit.resource_id,
                )
            )
        ).scalar_one_or_none()

        if existing_rec is None:
            session.add(
                CostRecommendationModel(
                    id=new_uuid7(),
                    tenant_id=tenant_id,
                    rule_id=hit.rule_id,
                    resource_id=hit.resource_id,
                    resource_type=hit.resource_type,
                    title=hit.title,
                    description=hit.description,
                    evidence=hit.evidence,
                    confidence=hit.confidence,
                    estimated_monthly_savings=hit.estimated_monthly_savings,
                    currency=hit.currency,
                    status="OPEN",
                    remediation_action=hit.remediation_action,
                    first_seen=now,
                    last_seen=now,
                )
            )
            recs_created += 1
        else:
            existing_rec.last_seen = now
            existing_rec.evidence = hit.evidence
            existing_rec.estimated_monthly_savings = hit.estimated_monthly_savings

    # 5. Log sync job
    session.add(
        CostSyncJobModel(
            id=new_uuid7(),
            tenant_id=tenant_id,
            account_id=account_id,
            period_date=now.date(),
            status="SUCCEEDED",
            records_ingested=ingested_count,
        )
    )
    await session.flush()

    return {
        "account_id": account_id,
        "records_ingested": ingested_count,
        "total_spend": total_service_spend,
        "allocated_spend": allocated,
        "unallocated_spend": unallocated,
        "recommendations_created": recs_created,
        "as_of": now.isoformat(),
    }
