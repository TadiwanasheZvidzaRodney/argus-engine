"""Discovery Sync Jobs, Coverage Reports, and Topology Summary Router."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from argus_core.errors import NotFound
from argus_core.events import new_uuid7
from argus_core.graph.client import build_graph_driver
from argus_core.graph.repository import GraphRepository
from argus_worker.discovery.orchestrator import SyncOrchestrator
from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.models import AwsAccount, ResourceCoverage, SyncJob

router = APIRouter(prefix="/api/v1", tags=["discovery"])


class StartSyncRequest(BaseModel):
    account_id: str = Field(description="12-digit AWS Account ID or account UUID")
    region: str | None = None
    type: str = Field(default="backfill", pattern=r"^(backfill|incremental|reconciliation)$")


class SyncJobShardResponse(BaseModel):
    id: str
    service: str
    region: str
    status: str
    items_discovered: int
    items_upserted: int


class SyncJobResponse(BaseModel):
    id: str
    account_id: str
    type: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    resource_count: int
    error_count: int
    shards: list[SyncJobShardResponse] = Field(default_factory=list)


class CoverageItem(BaseModel):
    resource_type: str
    supported: bool
    count: int
    last_seen_at: datetime


class TopologySummaryResponse(BaseModel):
    tenant_id: str
    nodes: int
    edges: int


def _get_graph_repo(request: Request) -> GraphRepository:
    driver = getattr(request.app.state, "graph_driver", None)
    if driver is None:
        driver = build_graph_driver(request.app.state.settings)
        request.app.state.graph_driver = driver
    return GraphRepository(driver)


@router.post(
    "/sync-jobs", response_model=SyncJobResponse, status_code=201, summary="Trigger discovery sync"
)
async def start_sync_job(
    body: StartSyncRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> SyncJobResponse:
    # Resolve account
    stmt = (
        select(AwsAccount)
        .where(
            AwsAccount.tenant_id == auth.tenant_id,
            (AwsAccount.account_id == body.account_id)
            | (
                AwsAccount.id == UUID(body.account_id.removeprefix("acc_"))
                if len(body.account_id) > 12
                else False
            ),
        )
        .options(selectinload(AwsAccount.regions))
    )
    account = (await session.execute(stmt)).scalar_one_or_none()
    if not account:
        raise NotFound(f"Account {body.account_id} not found.")

    job_id = new_uuid7()
    job = SyncJob(
        id=job_id,
        tenant_id=auth.tenant_id,
        account_id=account.id,
        region=body.region,
        type=body.type,
        status="running",
        started_at=datetime.now(tz=UTC),
    )
    session.add(job)
    await session.flush()

    # Run discovery orchestrator
    graph_repo = _get_graph_repo(request)
    orchestrator = SyncOrchestrator(graph_repo)
    active_regions = [r.region for r in account.regions if r.enabled] or ["us-east-1"]

    await orchestrator.run_sync_for_account(
        db_session=session,
        job_id=job_id,
        tenant_id=f"tnt_{auth.tenant_id}",
        account_uuid=account.id,
        account_id=account.account_id,
        regions=active_regions,
    )

    # Reload job with shards
    job_res = await session.execute(
        select(SyncJob).where(SyncJob.id == job_id).options(selectinload(SyncJob.shards))
    )
    loaded_job = job_res.scalar_one()

    return SyncJobResponse(
        id=f"job_{loaded_job.id.hex}",
        account_id=account.account_id,
        type=loaded_job.type,
        status=loaded_job.status,
        started_at=loaded_job.started_at,
        completed_at=loaded_job.completed_at,
        resource_count=loaded_job.resource_count,
        error_count=loaded_job.error_count,
        shards=[
            SyncJobShardResponse(
                id=f"shd_{s.id.hex}",
                service=s.service,
                region=s.region,
                status=s.status,
                items_discovered=s.items_discovered,
                items_upserted=s.items_upserted,
            )
            for s in loaded_job.shards
        ],
    )


@router.get("/sync-jobs", response_model=list[SyncJobResponse], summary="List sync jobs")
async def list_sync_jobs(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[SyncJobResponse]:
    stmt = (
        select(SyncJob, AwsAccount)
        .join(AwsAccount, SyncJob.account_id == AwsAccount.id)
        .where(SyncJob.tenant_id == auth.tenant_id)
        .order_by(desc(SyncJob.created_at))
        .limit(20)
        .options(selectinload(SyncJob.shards))
    )
    result = await session.execute(stmt)
    records = result.all()

    return [
        SyncJobResponse(
            id=f"job_{job.id.hex}",
            account_id=acc.account_id,
            type=job.type,
            status=job.status,
            started_at=job.started_at,
            completed_at=job.completed_at,
            resource_count=job.resource_count,
            error_count=job.error_count,
            shards=[
                SyncJobShardResponse(
                    id=f"shd_{s.id.hex}",
                    service=s.service,
                    region=s.region,
                    status=s.status,
                    items_discovered=s.items_discovered,
                    items_upserted=s.items_upserted,
                )
                for s in job.shards
            ],
        )
        for job, acc in records
    ]


@router.get(
    "/aws-accounts/{account_ref}/coverage",
    response_model=list[CoverageItem],
    summary="Get resource coverage",
)
async def get_resource_coverage(
    account_ref: str = Path(...),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[CoverageItem]:
    stmt = select(AwsAccount).where(
        AwsAccount.tenant_id == auth.tenant_id,
        (AwsAccount.account_id == account_ref)
        | (
            AwsAccount.id == UUID(account_ref.removeprefix("acc_"))
            if len(account_ref) > 12
            else False
        ),
    )
    account = (await session.execute(stmt)).scalar_one_or_none()
    if not account:
        raise NotFound(f"Account {account_ref} not found.")

    cov_stmt = (
        select(ResourceCoverage)
        .where(
            ResourceCoverage.tenant_id == auth.tenant_id,
            ResourceCoverage.account_id == account.id,
        )
        .order_by(desc(ResourceCoverage.count))
    )
    items = (await session.execute(cov_stmt)).scalars().all()

    return [
        CoverageItem(
            resource_type=i.resource_type,
            supported=i.supported,
            count=i.count,
            last_seen_at=i.last_seen_at,
        )
        for i in items
    ]


@router.get(
    "/topology/summary", response_model=TopologySummaryResponse, summary="Graph summary count"
)
async def get_topology_summary(
    request: Request,
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> TopologySummaryResponse:
    repo = _get_graph_repo(request)
    summary = await repo.count_summary(f"tnt_{auth.tenant_id}")
    return TopologySummaryResponse(
        tenant_id=f"tnt_{auth.tenant_id}",
        nodes=summary["nodes"],
        edges=summary["edges"],
    )


@router.get("/topology/neighborhood", summary="Neighborhood graph traversal")
async def get_neighborhood(
    request: Request,
    root_id: str = Query(..., description="Root ARN or URN"),
    depth: int = Query(default=1, ge=1, le=3),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    repo = _get_graph_repo(request)
    return await repo.query_neighborhood(f"tnt_{auth.tenant_id}", root_id=root_id, depth=depth)
