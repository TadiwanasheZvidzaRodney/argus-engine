"""Security findings API: list, detail, lifecycle transitions, remediation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from argus_core.errors import Forbidden, NotFound, UnprocessableEntity
from argus_core.events import new_uuid7
from argus_core.pagination import Page, decode_cursor, encode_cursor
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.actions.intent import (
    ActionConstraints,
    ActionIntentRequest,
    ActionTargets,
)
from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.models import FindingEventModel, FindingModel, FindingSuppressionModel
from argus_api.routers.actions import create_action

router = APIRouter(prefix="/api/v1/findings", tags=["findings"])

FindingStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED", "RISK_ACCEPTED", "SUPPRESSED"]


class FindingSummary(BaseModel):
    id: str
    rule_id: str
    rule_version: str
    severity: str
    status: str
    title: str
    resource_id: str
    resource_type: str
    account_id: str | None = None
    region: str | None = None
    finding_key: str
    assignee_id: str | None = None
    remediation_action: str | None = None
    remediation_action_id: str | None = None
    first_seen: datetime
    last_seen: datetime
    resolved_at: datetime | None = None
    created_at: datetime


class FindingEventResponse(BaseModel):
    id: str
    event_type: str
    actor_id: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class FindingDetail(FindingSummary):
    description: str
    evidence: dict[str, Any]
    evidence_hash: str
    risk_accepted_until: datetime | None = None
    events: list[FindingEventResponse] = Field(default_factory=list)
    suppression: dict[str, Any] | None = None
    remediation: dict[str, Any] | None = None


class FindingPatch(BaseModel):
    status: FindingStatus | None = None
    assignee_id: UUID | None = None
    comment: str | None = Field(default=None, max_length=2000)
    suppression_reason: str | None = Field(default=None, max_length=2000)
    suppression_expires_at: datetime | None = None
    risk_accepted_until: datetime | None = None


class RemediationRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    constraints: ActionConstraints = Field(default_factory=ActionConstraints)
    justification: str | None = Field(default=None, max_length=2000)


def _summary(finding: FindingModel) -> FindingSummary:
    return FindingSummary(
        id=str(finding.id),
        rule_id=finding.rule_id,
        rule_version=finding.rule_version,
        severity=finding.severity,
        status=finding.status,
        title=finding.title,
        resource_id=finding.resource_id,
        resource_type=finding.resource_type,
        account_id=finding.account_id,
        region=finding.region,
        finding_key=finding.finding_key,
        assignee_id=str(finding.assignee_id) if finding.assignee_id else None,
        remediation_action=finding.remediation_action,
        remediation_action_id=(
            str(finding.remediation_action_id) if finding.remediation_action_id else None
        ),
        first_seen=finding.first_seen,
        last_seen=finding.last_seen,
        resolved_at=finding.resolved_at,
        created_at=finding.created_at,
    )


def _event_response(event: FindingEventModel) -> FindingEventResponse:
    return FindingEventResponse(
        id=str(event.id),
        event_type=event.event_type,
        actor_id=str(event.actor_id) if event.actor_id else None,
        from_status=event.from_status,
        to_status=event.to_status,
        comment=event.comment,
        metadata=event.metadata_,
        created_at=event.created_at,
    )


async def _load_finding(session: AsyncSession, tenant_id: UUID, finding_id: UUID) -> FindingModel:
    finding = (
        await session.execute(
            select(FindingModel).where(
                FindingModel.tenant_id == tenant_id,
                FindingModel.id == finding_id,
            )
        )
    ).scalar_one_or_none()
    if finding is None:
        raise NotFound("Finding not found.")
    return finding


async def _detail(session: AsyncSession, finding: FindingModel) -> FindingDetail:
    events = (
        (
            await session.execute(
                select(FindingEventModel)
                .where(FindingEventModel.finding_id == finding.id)
                .order_by(FindingEventModel.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    suppression = (
        await session.execute(
            select(FindingSuppressionModel)
            .where(
                FindingSuppressionModel.finding_id == finding.id,
                FindingSuppressionModel.revoked_at.is_(None),
            )
            .order_by(desc(FindingSuppressionModel.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    summary = _summary(finding)
    return FindingDetail(
        **summary.model_dump(),
        description=finding.description,
        evidence=finding.evidence,
        evidence_hash=finding.evidence_hash,
        risk_accepted_until=finding.risk_accepted_until,
        events=[_event_response(event) for event in events],
        suppression=(
            {
                "id": str(suppression.id),
                "owner_id": str(suppression.owner_id),
                "reason": suppression.reason,
                "expires_at": suppression.expires_at.isoformat(),
                "created_at": suppression.created_at.isoformat(),
            }
            if suppression
            else None
        ),
        remediation=(
            {
                "action_type": finding.remediation_action,
                "action_id": (
                    str(finding.remediation_action_id) if finding.remediation_action_id else None
                ),
            }
            if finding.remediation_action
            else None
        ),
    )


def _append_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    finding_id: UUID,
    actor_id: UUID,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    comment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        FindingEventModel(
            id=new_uuid7(),
            tenant_id=tenant_id,
            finding_id=finding_id,
            actor_id=actor_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            comment=comment,
            metadata_=metadata or {},
        )
    )


@router.get("", response_model=Page[FindingSummary], summary="List security findings")
async def list_findings(
    request: Request,
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
    rule_id: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> Page[FindingSummary]:
    secret = request.app.state.settings.cursor_secret.get_secret_value()
    stmt = (
        select(FindingModel)
        .where(FindingModel.tenant_id == auth.tenant_id)
        .order_by(desc(FindingModel.created_at), desc(FindingModel.id))
        .limit(limit + 1)
    )
    if severity:
        stmt = stmt.where(FindingModel.severity == severity)
    if status:
        stmt = stmt.where(FindingModel.status == status)
    if account_id:
        stmt = stmt.where(FindingModel.account_id == account_id)
    if region:
        stmt = stmt.where(FindingModel.region == region)
    if rule_id:
        stmt = stmt.where(FindingModel.rule_id == rule_id)
    if resource_id:
        stmt = stmt.where(FindingModel.resource_id == resource_id)
    if cursor:
        payload = decode_cursor(cursor, secret=secret)
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        last_id = UUID(str(payload["id"]))
        stmt = stmt.where(
            (FindingModel.created_at < created_at)
            | ((FindingModel.created_at == created_at) & (FindingModel.id < last_id))
        )

    rows = (await session.execute(stmt)).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(
            {"created_at": last.created_at.isoformat(), "id": str(last.id)}, secret=secret
        )
    return Page(
        items=[_summary(row) for row in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{finding_id}", response_model=FindingDetail, summary="Finding detail")
async def get_finding(
    finding_id: str,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> FindingDetail:
    finding = await _load_finding(session, auth.tenant_id, _parse_finding_id(finding_id))
    return await _detail(session, finding)


@router.patch("/{finding_id}", response_model=FindingDetail, summary="Update finding lifecycle")
async def patch_finding(
    finding_id: str,
    body: FindingPatch,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> FindingDetail:
    finding = await _load_finding(session, auth.tenant_id, _parse_finding_id(finding_id))
    previous = finding.status

    if body.assignee_id is not None:
        finding.assignee_id = body.assignee_id
        _append_event(
            session,
            tenant_id=auth.tenant_id,
            finding_id=finding.id,
            actor_id=auth.user_id,
            event_type="assigned",
            from_status=previous,
            to_status=previous,
            comment=body.comment,
            metadata={"assignee_id": str(body.assignee_id)},
        )

    if body.status is None:
        if body.comment:
            _append_event(
                session,
                tenant_id=auth.tenant_id,
                finding_id=finding.id,
                actor_id=auth.user_id,
                event_type="commented",
                from_status=previous,
                to_status=previous,
                comment=body.comment,
            )
        await session.flush()
        return await _detail(session, finding)

    now = datetime.now(tz=UTC)
    new_status = body.status
    if new_status == "RISK_ACCEPTED":
        if not auth.has_permission(Permission.APPROVE_ACTION):
            raise Forbidden("Risk acceptance requires approve:action.")
        expires = body.risk_accepted_until or (now + timedelta(days=30))
        if expires <= now:
            raise UnprocessableEntity("risk_accepted_until must be in the future.")
        finding.risk_accepted_until = expires
    elif new_status == "SUPPRESSED":
        if not auth.has_permission(Permission.APPROVE_ACTION):
            raise Forbidden("Suppression requires approve:action.")
        if not body.suppression_reason:
            raise UnprocessableEntity("suppression_reason is required to suppress a finding.")
        expires = body.suppression_expires_at or (now + timedelta(days=7))
        if expires <= now:
            raise UnprocessableEntity("suppression_expires_at must be in the future.")
        session.add(
            FindingSuppressionModel(
                id=new_uuid7(),
                tenant_id=auth.tenant_id,
                finding_id=finding.id,
                owner_id=auth.user_id,
                reason=body.suppression_reason,
                scope="finding",
                expires_at=expires,
            )
        )
        _append_event(
            session,
            tenant_id=auth.tenant_id,
            finding_id=finding.id,
            actor_id=auth.user_id,
            event_type="suppressed",
            from_status=previous,
            to_status="SUPPRESSED",
            comment=body.suppression_reason,
            metadata={"expires_at": expires.isoformat()},
        )
    elif new_status == "OPEN":
        finding.resolved_at = None
        finding.risk_accepted_until = None
        suppressions = (
            (
                await session.execute(
                    select(FindingSuppressionModel).where(
                        FindingSuppressionModel.finding_id == finding.id,
                        FindingSuppressionModel.revoked_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for suppression in suppressions:
            suppression.revoked_at = now

    finding.status = new_status
    if new_status == "RESOLVED":
        finding.resolved_at = now
    _append_event(
        session,
        tenant_id=auth.tenant_id,
        finding_id=finding.id,
        actor_id=auth.user_id,
        event_type="status_changed",
        from_status=previous,
        to_status=new_status,
        comment=body.comment,
    )
    await session.flush()
    return await _detail(session, finding)


@router.post(
    "/{finding_id}/remediation",
    response_model=dict[str, Any],
    status_code=201,
    summary="Create a Phase 6 action from a finding",
)
async def create_remediation(
    finding_id: str,
    body: RemediationRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> dict[str, Any]:
    finding = await _load_finding(session, auth.tenant_id, _parse_finding_id(finding_id))
    if not finding.remediation_action:
        raise UnprocessableEntity("This finding does not have an automated remediation.")
    if finding.status in {"RESOLVED", "RISK_ACCEPTED", "SUPPRESSED"}:
        raise UnprocessableEntity("Only open or acknowledged findings can be remediated.")

    intent = _remediation_intent(finding, body)
    action = await create_action(intent, request, session, auth)
    action_uuid = _parse_action_ref(action.id)
    finding.remediation_action_id = action_uuid
    _append_event(
        session,
        tenant_id=auth.tenant_id,
        finding_id=finding.id,
        actor_id=auth.user_id,
        event_type="remediation_requested",
        from_status=finding.status,
        to_status=finding.status,
        metadata={"action_id": action.id, "action_type": action.action_type},
    )
    await session.flush()
    return {
        "finding_id": str(finding.id),
        "action": action.model_dump(mode="json"),
    }


def _remediation_intent(finding: FindingModel, body: RemediationRequest) -> ActionIntentRequest:
    evidence = finding.evidence or {}
    parameters: dict[str, Any] = {}
    targets = ActionTargets()
    if finding.remediation_action == "network.restrict_security_group_ingress":
        targets = ActionTargets(target=finding.resource_id)
        parameters = {
            "cidr": evidence.get("cidr", "0.0.0.0/0"),
            "port": evidence.get("port") or evidence.get("from_port"),
            "protocol": evidence.get("protocol", "tcp"),
        }
    elif finding.remediation_action == "s3.harden_bucket":
        targets = ActionTargets(target=finding.resource_id)
    elif finding.remediation_action == "iam.attach_least_privilege_policy":
        targets = ActionTargets(source=finding.resource_id)
        parameters = {"actions": evidence.get("actions") or ["s3:GetObject"]}
    else:
        targets = ActionTargets(resources=[finding.resource_id])

    parameters.update(body.parameters)
    parameters = {key: value for key, value in parameters.items() if value is not None}
    return ActionIntentRequest(
        type=finding.remediation_action,
        targets=targets,
        parameters=parameters,
        constraints=body.constraints,
        justification=body.justification
        or f"Remediate {finding.rule_id} on {finding.resource_id}.",
    )


def _parse_finding_id(value: str) -> UUID:
    raw = value.removeprefix("fnd_")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise NotFound(f"{value} is not a valid finding identifier.") from exc


def _parse_action_ref(value: str) -> UUID:
    raw = value.removeprefix("act_")
    try:
        return UUID(raw)
    except ValueError as exc:  # pragma: no cover - action IDs are server-generated
        raise NotFound(f"{value} is not a valid action identifier.") from exc


__all__ = ["router"]
