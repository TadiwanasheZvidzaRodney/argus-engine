"""Operational Admin Console, SRE Status Page, and Metering Router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.hardening.degraded import get_degraded_status, set_degraded_status
from argus_api.hardening.dr import simulate_dr_drill
from argus_api.hardening.metering import (
    get_tenant_metering_summary,
    record_tenant_metering,
)
from argus_api.hardening.slo import load_or_init_slos

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class DegradedModeRequest(BaseModel):
    read_only: bool = False
    live_paused: bool = False
    telemetry_paused: bool = False
    actions_disabled: bool = False
    maintenance_message: str | None = None
    scope: str = Field(default="tenant", description="'tenant' or 'global'")


class MeteringRecordRequest(BaseModel):
    resources_count: int = Field(ge=0)
    events_ingested: int = Field(default=0, ge=0)
    metric_requests: int = Field(default=0, ge=0)
    actions_planned: int = Field(default=0, ge=0)
    actions_executed: int = Field(default=0, ge=0)
    storage_bytes: int = Field(default=0, ge=0)


@router.get("/status", summary="Public / Operations Status and SLO report")
async def get_system_status(
    session: AsyncSession = Depends(get_tenant_db),
) -> dict[str, Any]:
    slos = await load_or_init_slos(session)
    degraded = await get_degraded_status(session, tenant_id=None)

    all_healthy = all(s["status"] == "healthy" for s in slos) and not degraded["is_degraded"]

    return {
        "overall_status": "OPERATIONAL" if all_healthy else "DEGRADED",
        "degraded_mode": degraded,
        "slos": slos,
        "dependencies": [
            {"name": "PostgreSQL Aurora", "status": "UP"},
            {"name": "Neo4j Graph Database", "status": "UP"},
            {"name": "Redis In-Memory State", "status": "UP"},
            {"name": "LocalStack / AWS STS", "status": "UP"},
        ],
    }


@router.get("/degraded", summary="Get degraded mode status")
async def get_degraded(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    return await get_degraded_status(session, tenant_id=auth.tenant_id)


@router.post("/degraded", summary="Update degraded mode status")
async def update_degraded(
    body: DegradedModeRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    target_tenant = auth.tenant_id if body.scope == "tenant" else None
    return await set_degraded_status(
        session,
        tenant_id=target_tenant,
        read_only=body.read_only,
        live_paused=body.live_paused,
        telemetry_paused=body.telemetry_paused,
        actions_disabled=body.actions_disabled,
        maintenance_message=body.maintenance_message,
        user_id=auth.user_id,
    )


@router.get("/metering", summary="Tenant consumption metering")
async def get_metering(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[dict[str, Any]]:
    return await get_tenant_metering_summary(session, auth.tenant_id)


@router.post("/metering/record", summary="Record tenant resource and event consumption")
async def record_metering(
    body: MeteringRecordRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    return await record_tenant_metering(
        session,
        tenant_id=auth.tenant_id,
        resources_count=body.resources_count,
        events_ingested=body.events_ingested,
        metric_requests=body.metric_requests,
        actions_planned=body.actions_planned,
        actions_executed=body.actions_executed,
        storage_bytes=body.storage_bytes,
    )


@router.post("/dr-drill", summary="Simulate multi-region disaster recovery drill")
async def run_dr_drill(
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    return simulate_dr_drill()
