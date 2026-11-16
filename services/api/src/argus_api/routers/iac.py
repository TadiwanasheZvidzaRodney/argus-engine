"""GitOps Bridge, IaC Drift Detection, and Pull Request Synthesis Router."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from argus_core.events import new_uuid7
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.iac.drift import detect_iac_drift
from argus_api.iac.synthesizer import synthesize_hcl_diff
from argus_api.iac.vcs import create_or_simulate_pull_request
from argus_api.models import (
    GitRepositoryModel,
    IacDriftRecordModel,
    IacPullRequestModel,
)
from argus_api.routers.sync import _get_graph_repo

router = APIRouter(prefix="/api/v1/iac", tags=["iac"])


class RepositoryCreateRequest(BaseModel):
    provider: str = Field(default="github", max_length=32)
    repo_url: str = Field(min_length=8, max_length=512)
    default_branch: str = Field(default="main", max_length=128)
    iac_path: str = Field(default="terraform/", max_length=256)


class SynthesizePrRequest(BaseModel):
    action_type: str = Field(max_length=128)
    target_resource_id: str = Field(max_length=2048)
    parameters: dict[str, Any] = Field(default_factory=dict)
    repo_id: UUID | None = None
    action_id: UUID | None = None


@router.get("/repositories", summary="List connected IaC Git repositories")
async def list_repositories(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(GitRepositoryModel)
                .where(GitRepositoryModel.tenant_id == auth.tenant_id)
                .order_by(desc(GitRepositoryModel.created_at))
            )
        )
        .scalars()
        .all()
    )

    return [
        {
            "id": str(r.id),
            "provider": r.provider,
            "repo_url": r.repo_url,
            "default_branch": r.default_branch,
            "iac_path": r.iac_path,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/repositories", status_code=201, summary="Connect an IaC Git repository")
async def create_repository(
    body: RepositoryCreateRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    repo = GitRepositoryModel(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        provider=body.provider,
        repo_url=body.repo_url,
        default_branch=body.default_branch,
        iac_path=body.iac_path,
        status="active",
    )
    session.add(repo)
    await session.flush()

    return {
        "id": str(repo.id),
        "repo_url": repo.repo_url,
        "default_branch": repo.default_branch,
        "status": repo.status,
    }


@router.get("/drift", summary="List detected IaC drift records")
async def list_drift(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(IacDriftRecordModel)
                .where(IacDriftRecordModel.tenant_id == auth.tenant_id)
                .order_by(desc(IacDriftRecordModel.detected_at))
            )
        )
        .scalars()
        .all()
    )

    return [
        {
            "id": str(r.id),
            "resource_id": r.resource_id,
            "resource_type": r.resource_type,
            "iac_file_path": r.iac_file_path,
            "iac_block_type": r.iac_block_type,
            "iac_block_name": r.iac_block_name,
            "drift_details": r.drift_details,
            "status": r.status,
            "detected_at": r.detected_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/drift/scan", summary="Scan live graph for IaC ClickOps drift")
async def trigger_drift_scan(
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    repo = _get_graph_repo(request)
    subgraph = await repo.load_security_subgraph(f"tnt_{auth.tenant_id}")
    nodes = subgraph["nodes"]

    drifted_items = detect_iac_drift(nodes)
    now = datetime.now(tz=UTC)
    created_count = 0

    for d in drifted_items:
        existing = (
            await session.execute(
                select(IacDriftRecordModel).where(
                    IacDriftRecordModel.tenant_id == auth.tenant_id,
                    IacDriftRecordModel.resource_id == d["resource_id"],
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                IacDriftRecordModel(
                    id=new_uuid7(),
                    tenant_id=auth.tenant_id,
                    resource_id=d["resource_id"],
                    resource_type=d["resource_type"],
                    iac_file_path=d["iac_file_path"],
                    iac_block_type=d["iac_block_type"],
                    iac_block_name=d["iac_block_name"],
                    drift_details=d["drift_details"],
                    status="DRIFTED",
                    detected_at=now,
                )
            )
            created_count += 1
        else:
            existing.drift_details = d["drift_details"]
            existing.detected_at = now

    await session.flush()
    return {
        "drift_count": len(drifted_items),
        "created": created_count,
        "scanned_at": now.isoformat(),
    }


@router.get("/prs", summary="List synthesized GitOps Pull Requests")
async def list_pull_requests(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(IacPullRequestModel)
                .where(IacPullRequestModel.tenant_id == auth.tenant_id)
                .order_by(desc(IacPullRequestModel.created_at))
            )
        )
        .scalars()
        .all()
    )

    return [
        {
            "id": str(r.id),
            "action_id": str(r.action_id) if r.action_id else None,
            "repo_id": str(r.repo_id),
            "pr_url": r.pr_url,
            "pr_number": r.pr_number,
            "title": r.title,
            "branch_name": r.branch_name,
            "hcl_diff": r.hcl_diff,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/prs", status_code=201, summary="Synthesize and open a GitOps Pull Request")
async def synthesize_pr(
    body: SynthesizePrRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> dict[str, Any]:
    # Resolve repository
    repo = None
    if body.repo_id:
        repo = (
            await session.execute(
                select(GitRepositoryModel).where(
                    GitRepositoryModel.tenant_id == auth.tenant_id,
                    GitRepositoryModel.id == body.repo_id,
                )
            )
        ).scalar_one_or_none()

    if repo is None:
        repo = (
            await session.execute(
                select(GitRepositoryModel)
                .where(GitRepositoryModel.tenant_id == auth.tenant_id)
                .order_by(desc(GitRepositoryModel.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()

    repo_url = repo.repo_url if repo else "https://github.com/argus-customer/terraform-live"
    repo_id = repo.id if repo else new_uuid7()

    # Synthesize HCL diff
    diff_data = synthesize_hcl_diff(
        action_type=body.action_type,
        target_resource_id=body.target_resource_id,
        parameters=body.parameters,
    )

    # Create / simulate Pull Request
    vcs_pr = create_or_simulate_pull_request(
        repo_url=repo_url,
        action_type=body.action_type,
        title=diff_data["summary"],
        hcl_diff=diff_data["hcl_diff"],
    )

    pr_model = IacPullRequestModel(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        action_id=body.action_id,
        repo_id=repo_id,
        pr_url=vcs_pr["pr_url"],
        pr_number=vcs_pr["pr_number"],
        title=vcs_pr["title"],
        branch_name=vcs_pr["branch_name"],
        hcl_diff=vcs_pr["hcl_diff"],
        status="OPEN",
    )
    session.add(pr_model)
    await session.flush()

    return {
        "id": str(pr_model.id),
        "pr_url": pr_model.pr_url,
        "pr_number": pr_model.pr_number,
        "branch_name": pr_model.branch_name,
        "title": pr_model.title,
        "hcl_diff": pr_model.hcl_diff,
        "status": pr_model.status,
    }
