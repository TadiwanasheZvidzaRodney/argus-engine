"""GitOps Bridge, IaC Drift Detection, and Pull Request Synthesis Router."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from argus_core.errors import Conflict, Forbidden, NotFound, UnprocessableEntity
from argus_core.events import new_uuid7
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.actions.audit import append_audit
from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.iac.drift import detect_iac_drift
from argus_api.iac.github import LOCAL_GH_AUTH_REF, GitHubClient
from argus_api.models import (
    GitRepositoryModel,
    IacDriftRecordModel,
    IacPullRequestModel,
)
from argus_api.routers.actions import _assert_writes_enabled
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


class ApproveProposalRequest(BaseModel):
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def _github(request: Request, auth: AuthContext) -> GitHubClient:
    settings = request.app.state.settings
    if (
        not settings.github_enabled
        or settings.env.value != "local"
        or settings.github_tenant_id != auth.tenant_id
        or not settings.github_owner
    ):
        raise Forbidden("Local GitHub integration is not enabled for this tenant.")
    return GitHubClient(settings.github_owner, settings.github_repositories)


@router.get("/github/status", summary="Local GitHub integration configuration")
async def github_status(
    request: Request,
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    try:
        client = _github(request, auth)
    except Forbidden:
        return {"enabled": False, "mode": "disabled"}
    return {
        "enabled": True,
        "mode": "local-gh-keyring",
        "owner": client.owner,
        "publication": "approval-required-draft-markdown-proposals",
    }


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
            "status": r.status if r.auth_token_ref == LOCAL_GH_AUTH_REF else "unverified",
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/repositories", status_code=201, summary="Connect an IaC Git repository")
async def create_repository(
    body: RepositoryCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    if body.provider != "github":
        raise UnprocessableEntity("Only validated GitHub repositories are supported.")
    verified = await _github(request, auth).verify_repository(
        body.repo_url, body.default_branch, body.iac_path
    )
    existing = (
        await session.execute(
            select(GitRepositoryModel).where(
                GitRepositoryModel.tenant_id == auth.tenant_id,
                GitRepositoryModel.repo_url == verified["repo_url"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise Conflict("Repository is already connected for this tenant.")
    repo = GitRepositoryModel(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        provider=body.provider,
        repo_url=verified["repo_url"],
        default_branch=body.default_branch,
        iac_path=body.iac_path,
        status="active",
        auth_token_ref=LOCAL_GH_AUTH_REF,
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
            "proposal_hash": hashlib.sha256(r.hcl_diff.encode()).hexdigest(),
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/prs", status_code=201, summary="Prepare a local GitOps proposal for approval")
async def synthesize_pr(
    body: SynthesizePrRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> dict[str, Any]:
    # Preparation is local only. No GitHub branch or PR is created here.
    github = _github(request, auth)
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

    if repo is None and body.repo_id is None:
        repo = (
            await session.execute(
                select(GitRepositoryModel)
                .where(
                    GitRepositoryModel.tenant_id == auth.tenant_id,
                    GitRepositoryModel.auth_token_ref == LOCAL_GH_AUTH_REF,
                    GitRepositoryModel.status == "active",
                )
                .order_by(desc(GitRepositoryModel.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()

    if repo is None:
        raise NotFound("Connect a validated repository before preparing a proposal.")
    github.check_scope(repo.repo_url)
    if repo.auth_token_ref != LOCAL_GH_AUTH_REF or repo.status != "active":
        raise Conflict("Reconnect this repository using real GitHub validation.")
    if body.action_id is not None:
        raise UnprocessableEntity(
            "This proposal flow does not execute or approve existing AWS action plans."
        )
    proposal_id = new_uuid7()
    title = f"Argus remediation proposal: {body.action_type}"[:255]
    content = (
        "# Argus remediation proposal\n\n"
        "**Proposal only. No Terraform changes have been generated or validated.**\n\n"
        "Review resource ownership, IaC mapping, account identity and costs before "
        "writing an implementation. Merging this document does not apply infrastructure.\n\n"
        f"Proposal ID: `{proposal_id}`\n\n"
        "Requested remediation:\n\n```json\n"
        + json.dumps(body.model_dump(mode="json"), sort_keys=True, indent=2)
        + "\n```\n"
    )
    pr_model = IacPullRequestModel(
        id=proposal_id,
        tenant_id=auth.tenant_id,
        action_id=None,
        repo_id=repo.id,
        pr_url="",
        pr_number=0,
        title=title,
        branch_name=f"argus/proposal-{proposal_id.hex}",
        hcl_diff=content,
        status="PENDING_APPROVAL",
    )
    session.add(pr_model)
    await session.flush()
    await append_audit(
        session,
        auth=auth,
        action="iac.proposal.prepared",
        resource_type="gitops_proposal",
        resource_id=str(pr_model.id),
        metadata={
            "repo_id": str(repo.id),
            "proposal_hash": hashlib.sha256(content.encode()).hexdigest(),
        },
    )

    return {
        "id": str(pr_model.id),
        "pr_url": pr_model.pr_url,
        "pr_number": pr_model.pr_number,
        "branch_name": pr_model.branch_name,
        "title": pr_model.title,
        "hcl_diff": pr_model.hcl_diff,
        "status": pr_model.status,
        "proposal_hash": hashlib.sha256(content.encode()).hexdigest(),
    }


@router.post("/prs/{proposal_id}/approve", summary="Approve and publish a real draft proposal PR")
async def approve_proposal(
    proposal_id: UUID,
    body: ApproveProposalRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.APPROVE_ACTION)),
) -> dict[str, Any]:
    await _assert_writes_enabled(session, auth.tenant_id, request.app.state.settings)
    github = _github(request, auth)
    proposal = (
        await session.execute(
            select(IacPullRequestModel)
            .where(
                IacPullRequestModel.id == proposal_id,
                IacPullRequestModel.tenant_id == auth.tenant_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise NotFound("Proposal not found.")
    if hashlib.sha256(proposal.hcl_diff.encode()).hexdigest() != body.proposal_hash:
        raise Conflict("Proposal changed. Review its current text before approving.")
    if proposal.status == "OPEN":
        return {"pr_url": proposal.pr_url, "pr_number": proposal.pr_number, "status": "OPEN"}
    if proposal.status != "PENDING_APPROVAL":
        raise Conflict("Only pending proposals can be published.")
    repo = (
        await session.execute(
            select(GitRepositoryModel).where(
                GitRepositoryModel.id == proposal.repo_id,
                GitRepositoryModel.tenant_id == auth.tenant_id,
                GitRepositoryModel.auth_token_ref == LOCAL_GH_AUTH_REF,
                GitRepositoryModel.status == "active",
            )
        )
    ).scalar_one_or_none()
    if repo is None:
        raise NotFound("Validated repository not found.")
    published = await github.publish_proposal(
        repo.repo_url,
        repo.default_branch,
        repo.iac_path,
        proposal.id.hex,
        proposal.title,
        proposal.hcl_diff,
    )
    proposal.pr_url = published["html_url"]
    proposal.pr_number = published["number"]
    proposal.status = "OPEN"
    await session.flush()
    await append_audit(
        session,
        auth=auth,
        action="iac.proposal.approved_and_published",
        resource_type="gitops_proposal",
        resource_id=str(proposal.id),
        metadata={"proposal_hash": body.proposal_hash, "pr_url": proposal.pr_url},
    )
    return {
        "pr_url": proposal.pr_url,
        "pr_number": proposal.pr_number,
        "status": "OPEN",
        "draft": True,
    }
