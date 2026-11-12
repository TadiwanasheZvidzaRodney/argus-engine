"""Cost Intelligence, Allocation, Recommendations, and Budgets Router."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from argus_core.errors import NotFound, UnprocessableEntity
from argus_core.events import new_uuid7
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.actions.intent import (
    ActionConstraints,
    ActionIntentRequest,
    ActionTargets,
)
from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.cost.engine import sync_tenant_costs
from argus_api.cost.types import BudgetPeriod, BudgetScopeType
from argus_api.models import (
    CostBudgetModel,
    CostDailyModel,
    CostRecommendationModel,
    CostReconciliationModel,
    CostResourceEstimateModel,
    CostSyncJobModel,
)
from argus_api.routers.actions import create_action
from argus_api.routers.sync import _get_graph_repo

router = APIRouter(prefix="/api/v1/cost", tags=["cost"])


class CostSyncRequest(BaseModel):
    account_id: str = Field(default="123456789012", max_length=12)
    days: int = Field(default=30, ge=1, le=365)
    region: str = Field(default="us-east-1", max_length=32)


class BudgetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scope_type: BudgetScopeType = Field(default=BudgetScopeType.TENANT)
    scope_value: str | None = Field(default=None, max_length=256)
    threshold_amount: float = Field(gt=0)
    period: BudgetPeriod = Field(default=BudgetPeriod.MONTHLY)
    notification_channel: str | None = Field(default=None, max_length=256)


class BudgetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    threshold_amount: float | None = Field(default=None, gt=0)
    notification_channel: str | None = Field(default=None, max_length=256)
    enabled: bool | None = None


class RecommendationPatch(BaseModel):
    status: Literal["OPEN", "ACKNOWLEDGED", "DISMISSED"]


class RecommendationRemediateRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    constraints: ActionConstraints = Field(default_factory=ActionConstraints)
    justification: str | None = Field(default=None, max_length=2000)


def _parse_uuid(val: str, label: str = "Identifier") -> UUID:
    raw = val.removeprefix("rec_").removeprefix("bgt_")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise NotFound(f"{label} {val!r} is not a valid UUID.") from exc


@router.get("/summary", summary="Monthly cost summary with allocation reconciliation")
async def get_cost_summary(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    start_date = now.date().replace(day=1)
    end_date = now.date()

    # Sum total untagged service spend
    sum_query = await session.execute(
        select(func.sum(CostDailyModel.amount)).where(
            CostDailyModel.tenant_id == auth.tenant_id,
            CostDailyModel.period_date >= start_date,
            CostDailyModel.tag_key.is_(None),
        )
    )
    total_spend = float(sum_query.scalar() or 0.0)

    # Reconciliation row
    recon = (
        await session.execute(
            select(CostReconciliationModel)
            .where(
                CostReconciliationModel.tenant_id == auth.tenant_id,
                CostReconciliationModel.period_start == start_date,
            )
            .order_by(desc(CostReconciliationModel.computed_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    allocated = float(recon.allocated_amount) if recon else total_spend * 0.85
    unallocated = float(recon.unallocated_amount) if recon else total_spend * 0.15

    # Top dimensions (service and account)
    service_totals = (
        await session.execute(
            select(CostDailyModel.service, func.sum(CostDailyModel.amount))
            .where(
                CostDailyModel.tenant_id == auth.tenant_id,
                CostDailyModel.period_date >= start_date,
                CostDailyModel.tag_key.is_(None),
            )
            .group_by(CostDailyModel.service)
            .order_by(desc(func.sum(CostDailyModel.amount)))
            .limit(5)
        )
    ).all()

    account_totals = (
        await session.execute(
            select(CostDailyModel.account_id, func.sum(CostDailyModel.amount))
            .where(
                CostDailyModel.tenant_id == auth.tenant_id,
                CostDailyModel.period_date >= start_date,
                CostDailyModel.tag_key.is_(None),
            )
            .group_by(CostDailyModel.account_id)
            .order_by(desc(func.sum(CostDailyModel.amount)))
            .limit(5)
        )
    ).all()

    # Last sync freshness
    last_job = (
        await session.execute(
            select(CostSyncJobModel)
            .where(CostSyncJobModel.tenant_id == auth.tenant_id)
            .order_by(desc(CostSyncJobModel.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    as_of = last_job.created_at.isoformat() if last_job else now.isoformat()
    lag_hours = (
        18 if not last_job else max(1, int((now - last_job.created_at).total_seconds() / 3600))
    )

    groups = [
        {"dimension": "service", "value": s[0], "amount": round(float(s[1]), 2)}
        for s in service_totals
    ]
    groups.extend(
        {"dimension": "account", "value": a[0], "amount": round(float(a[1]), 2)}
        for a in account_totals
    )

    return {
        "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "currency": "USD",
        "total": round(total_spend, 2),
        "allocated": round(allocated, 2),
        "unallocated": round(unallocated, 2),
        "as_of": as_of,
        "source_lag_hours": lag_hours,
        "groups": groups,
    }


@router.get("/breakdown", summary="Cost breakdown by dimension")
async def get_cost_breakdown(
    dimension: str = Query(default="service"),
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    now = datetime.now(tz=UTC).date()
    start_date = now - timedelta(days=days)

    if dimension.startswith("tag:"):
        tag_key = dimension.split(":", 1)[1]
        rows = (
            await session.execute(
                select(CostDailyModel.tag_value, func.sum(CostDailyModel.amount))
                .where(
                    CostDailyModel.tenant_id == auth.tenant_id,
                    CostDailyModel.period_date >= start_date,
                    CostDailyModel.tag_key == tag_key,
                )
                .group_by(CostDailyModel.tag_value)
                .order_by(desc(func.sum(CostDailyModel.amount)))
            )
        ).all()
        items = [{"label": r[0] or "untagged", "amount": round(float(r[1]), 2)} for r in rows]
    elif dimension == "account":
        rows = (
            await session.execute(
                select(CostDailyModel.account_id, func.sum(CostDailyModel.amount))
                .where(
                    CostDailyModel.tenant_id == auth.tenant_id,
                    CostDailyModel.period_date >= start_date,
                    CostDailyModel.tag_key.is_(None),
                )
                .group_by(CostDailyModel.account_id)
                .order_by(desc(func.sum(CostDailyModel.amount)))
            )
        ).all()
        items = [{"label": r[0], "amount": round(float(r[1]), 2)} for r in rows]
    elif dimension == "region":
        rows = (
            await session.execute(
                select(CostDailyModel.region, func.sum(CostDailyModel.amount))
                .where(
                    CostDailyModel.tenant_id == auth.tenant_id,
                    CostDailyModel.period_date >= start_date,
                    CostDailyModel.tag_key.is_(None),
                )
                .group_by(CostDailyModel.region)
                .order_by(desc(func.sum(CostDailyModel.amount)))
            )
        ).all()
        items = [{"label": r[0], "amount": round(float(r[1]), 2)} for r in rows]
    else:  # service
        rows = (
            await session.execute(
                select(CostDailyModel.service, func.sum(CostDailyModel.amount))
                .where(
                    CostDailyModel.tenant_id == auth.tenant_id,
                    CostDailyModel.period_date >= start_date,
                    CostDailyModel.tag_key.is_(None),
                )
                .group_by(CostDailyModel.service)
                .order_by(desc(func.sum(CostDailyModel.amount)))
            )
        ).all()
        items = [{"label": r[0], "amount": round(float(r[1]), 2)} for r in rows]

    total = 0.0
    for item in items:
        amt = item.get("amount", 0.0)
        total += float(amt) if isinstance(amt, (int, float)) else 0.0
    return {
        "dimension": dimension,
        "period_days": days,
        "currency": "USD",
        "total": round(total, 2),
        "items": items,
    }


@router.get("/resources/{resource_id:path}", summary="Resource cost estimate and confidence")
async def get_resource_cost(
    resource_id: str,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    estimate = (
        await session.execute(
            select(CostResourceEstimateModel)
            .where(
                CostResourceEstimateModel.tenant_id == auth.tenant_id,
                CostResourceEstimateModel.resource_id == resource_id,
            )
            .order_by(desc(CostResourceEstimateModel.period_date))
            .limit(1)
        )
    ).scalar_one_or_none()

    if estimate is None:
        return {
            "resource_id": resource_id,
            "monthly_amount": 0.0,
            "currency": "USD",
            "confidence": "unknown",
            "method": "No direct cost allocation line item found.",
        }

    return {
        "resource_id": resource_id,
        "monthly_amount": round(float(estimate.amount), 2),
        "currency": estimate.currency,
        "confidence": estimate.confidence,
        "method": estimate.method,
        "as_of": estimate.computed_at.isoformat(),
    }


@router.get("/trend", summary="Cost trend over time with forecast")
async def get_cost_trend(
    days: int = Query(default=30, ge=7, le=365),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    now = datetime.now(tz=UTC).date()
    start_date = now - timedelta(days=days)

    rows = (
        await session.execute(
            select(CostDailyModel.period_date, func.sum(CostDailyModel.amount))
            .where(
                CostDailyModel.tenant_id == auth.tenant_id,
                CostDailyModel.period_date >= start_date,
                CostDailyModel.tag_key.is_(None),
            )
            .group_by(CostDailyModel.period_date)
            .order_by(CostDailyModel.period_date.asc())
        )
    ).all()

    points = [{"date": r[0].isoformat(), "amount": round(float(r[1]), 2)} for r in rows]
    total_pts = 0.0
    for p in points:
        p_amt = p.get("amount", 0.0)
        total_pts += float(p_amt) if isinstance(p_amt, (int, float)) else 0.0
    avg_daily = total_pts / max(1, len(points))
    forecast_month = round(avg_daily * 30.0, 2)

    return {
        "currency": "USD",
        "points": points,
        "average_daily": round(avg_daily, 2),
        "forecast_monthly": forecast_month,
    }


@router.get("/top", summary="Top spenders by resource or service")
async def get_top_spenders(
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    estimates = (
        (
            await session.execute(
                select(CostResourceEstimateModel)
                .where(CostResourceEstimateModel.tenant_id == auth.tenant_id)
                .order_by(desc(CostResourceEstimateModel.amount))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return {
        "currency": "USD",
        "resources": [
            {
                "resource_id": e.resource_id,
                "monthly_amount": round(float(e.amount), 2),
                "confidence": e.confidence,
                "method": e.method,
            }
            for e in estimates
        ],
    }


@router.get("/recommendations", summary="Cost optimization recommendations")
async def list_recommendations(
    status: str | None = Query(default=None),
    rule_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[dict[str, Any]]:
    query = select(CostRecommendationModel).where(
        CostRecommendationModel.tenant_id == auth.tenant_id
    )
    if status:
        query = query.where(CostRecommendationModel.status == status)
    if rule_id:
        query = query.where(CostRecommendationModel.rule_id == rule_id)
    query = query.order_by(desc(CostRecommendationModel.estimated_monthly_savings))

    rows = (await session.execute(query)).scalars().all()
    return [
        {
            "id": f"rec_{r.id}",
            "rule": r.rule_id,
            "resource_id": r.resource_id,
            "resource_type": r.resource_type,
            "title": r.title,
            "description": r.description,
            "confidence": r.confidence,
            "evidence": r.evidence,
            "estimated_monthly_savings": float(r.estimated_monthly_savings),
            "currency": r.currency,
            "status": r.status,
            "remediation": {
                "action_type": r.remediation_action,
                "action_id": str(r.remediation_action_id) if r.remediation_action_id else None,
            }
            if r.remediation_action
            else None,
            "first_seen": r.first_seen.isoformat(),
            "last_seen": r.last_seen.isoformat(),
        }
        for r in rows
    ]


@router.patch(
    "/recommendations/{recommendation_id}", summary="Acknowledge or dismiss a recommendation"
)
async def patch_recommendation(
    recommendation_id: str,
    body: RecommendationPatch,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> dict[str, Any]:
    rec_uuid = _parse_uuid(recommendation_id, "Recommendation")
    rec = (
        await session.execute(
            select(CostRecommendationModel).where(
                CostRecommendationModel.tenant_id == auth.tenant_id,
                CostRecommendationModel.id == rec_uuid,
            )
        )
    ).scalar_one_or_none()

    if rec is None:
        raise NotFound(f"Recommendation {recommendation_id!r} not found.")

    rec.status = body.status
    await session.flush()
    return {"id": recommendation_id, "status": rec.status}


@router.post(
    "/recommendations/{recommendation_id}/remediate", summary="Create Phase 6 remediation action"
)
async def remediate_recommendation(
    recommendation_id: str,
    body: RecommendationRemediateRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> dict[str, Any]:
    rec_uuid = _parse_uuid(recommendation_id, "Recommendation")
    rec = (
        await session.execute(
            select(CostRecommendationModel).where(
                CostRecommendationModel.tenant_id == auth.tenant_id,
                CostRecommendationModel.id == rec_uuid,
            )
        )
    ).scalar_one_or_none()

    if rec is None:
        raise NotFound(f"Recommendation {recommendation_id!r} not found.")
    if not rec.remediation_action:
        raise UnprocessableEntity("This recommendation has no automated Phase 6 remediation.")

    # Prefill parameters based on rule
    params = dict(body.parameters)
    targets = ActionTargets()
    if rec.remediation_action == "optimization.resize_instance":
        targets = ActionTargets(source=rec.resource_id)
        params.setdefault(
            "instance_type", rec.evidence.get("recommended_instance_type", "m5.large")
        )
        params.setdefault(
            "current_instance_type", rec.evidence.get("current_instance_type", "m5.xlarge")
        )
    elif rec.remediation_action == "ec2.stop_start_instance":
        targets = ActionTargets(source=rec.resource_id)
        params.setdefault("desired_state", "stopped")
    else:
        targets = ActionTargets(target=rec.resource_id)

    intent = ActionIntentRequest(
        type=rec.remediation_action,
        targets=targets,
        parameters=params,
        constraints=body.constraints,
        justification=body.justification or f"Optimize cost for {rec.resource_id} ({rec.rule_id}).",
    )

    action = await create_action(intent, request, session, auth)
    rec.remediation_action_id = UUID(action.id.removeprefix("act_"))
    rec.status = "REMEDIATED"
    await session.flush()

    return {
        "recommendation_id": recommendation_id,
        "action": action.model_dump(mode="json"),
    }


@router.get("/budgets", summary="List budgets and status")
async def list_budgets(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[dict[str, Any]]:
    budgets = (
        (
            await session.execute(
                select(CostBudgetModel)
                .where(CostBudgetModel.tenant_id == auth.tenant_id)
                .order_by(CostBudgetModel.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    now = datetime.now(tz=UTC).date()
    month_start = now.replace(day=1)
    sum_res = await session.execute(
        select(func.sum(CostDailyModel.amount)).where(
            CostDailyModel.tenant_id == auth.tenant_id,
            CostDailyModel.period_date >= month_start,
            CostDailyModel.tag_key.is_(None),
        )
    )
    current_spend = float(sum_res.scalar() or 0.0)

    return [
        {
            "id": f"bgt_{b.id}",
            "name": b.name,
            "scope_type": b.scope_type,
            "scope_value": b.scope_value,
            "threshold_amount": float(b.threshold_amount),
            "period": b.period,
            "current_spend": round(current_spend, 2),
            "percent_used": round(current_spend / float(b.threshold_amount) * 100, 1),
            "is_exceeded": current_spend > float(b.threshold_amount),
            "notification_channel": b.notification_channel,
            "enabled": b.enabled,
        }
        for b in budgets
    ]


@router.post("/budgets", status_code=201, summary="Create a budget")
async def create_budget(
    body: BudgetCreateRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    budget = CostBudgetModel(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        name=body.name,
        scope_type=body.scope_type.value,
        scope_value=body.scope_value,
        threshold_amount=body.threshold_amount,
        period=body.period.value,
        notification_channel=body.notification_channel,
        enabled=True,
    )
    session.add(budget)
    await session.flush()
    return {
        "id": f"bgt_{budget.id}",
        "name": budget.name,
        "threshold_amount": float(budget.threshold_amount),
    }


@router.put("/budgets/{budget_id}", summary="Update a budget")
async def update_budget(
    budget_id: str,
    body: BudgetUpdateRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    bgt_uuid = _parse_uuid(budget_id, "Budget")
    budget = (
        await session.execute(
            select(CostBudgetModel).where(
                CostBudgetModel.tenant_id == auth.tenant_id,
                CostBudgetModel.id == bgt_uuid,
            )
        )
    ).scalar_one_or_none()

    if budget is None:
        raise NotFound(f"Budget {budget_id!r} not found.")

    if body.name is not None:
        budget.name = body.name
    if body.threshold_amount is not None:
        budget.threshold_amount = body.threshold_amount
    if body.notification_channel is not None:
        budget.notification_channel = body.notification_channel
    if body.enabled is not None:
        budget.enabled = body.enabled

    await session.flush()
    return {
        "id": budget_id,
        "name": budget.name,
        "threshold_amount": float(budget.threshold_amount),
    }


@router.delete("/budgets/{budget_id}", summary="Delete a budget")
async def delete_budget(
    budget_id: str,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    bgt_uuid = _parse_uuid(budget_id, "Budget")
    budget = (
        await session.execute(
            select(CostBudgetModel).where(
                CostBudgetModel.tenant_id == auth.tenant_id,
                CostBudgetModel.id == bgt_uuid,
            )
        )
    ).scalar_one_or_none()

    if budget is None:
        raise NotFound(f"Budget {budget_id!r} not found.")

    await session.delete(budget)
    await session.flush()
    return {"id": budget_id, "deleted": True}


@router.post("/sync", summary="Trigger daily cost ingestion and recommendation scan")
async def trigger_cost_sync(
    body: CostSyncRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    repo = _get_graph_repo(request)
    subgraph = await repo.load_security_subgraph(f"tnt_{auth.tenant_id}")
    nodes = subgraph["nodes"]

    res = await sync_tenant_costs(
        session,
        tenant_id=auth.tenant_id,
        account_id=body.account_id,
        nodes=nodes,
        days=body.days,
        region=body.region,
    )
    return res
