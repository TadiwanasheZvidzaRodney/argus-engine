"""Action request, approval, execution, rollback, and evidence API."""

from __future__ import annotations

import contextlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from argus_core.errors import (
    Conflict,
    FieldError,
    Forbidden,
    NotFound,
    UnprocessableEntity,
)
from argus_core.events import new_uuid7
from argus_core.pagination import Page, decode_cursor
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.actions.audit import append_audit, append_evidence
from argus_api.actions.catalog import ActionDefinition, get_definition
from argus_api.actions.executor import (
    acquire_locks,
    execute_plan,
    release_locks,
    rollback_execution,
)
from argus_api.actions.guardrails import (
    enforce_rate_limit,
    evaluate_guardrails,
    get_kill_switch,
    load_effective_rules,
    parse_arn,
)
from argus_api.actions.intent import ActionIntentRequest, target_resource_ids, validate_intent
from argus_api.actions.llm import explain_plan, parse_natural_language
from argus_api.actions.planner import assess_risk, build_plan
from argus_api.actions.types import (
    ActionStatus,
    ApprovalDecision,
    RiskLevel,
    approval_policy_for,
    risk_from_str,
)
from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.models import (
    ActionApprovalModel,
    ActionCatalogEntry,
    ActionEvidenceModel,
    ActionExecutionModel,
    ActionPlanModel,
    ActionRequestModel,
)
from argus_api.routers.sync import _get_graph_repo

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])

_SANDBOX_ENVS = {"local", "test"}
_TERMINAL_STATUSES = {
    ActionStatus.REJECTED.value,
    ActionStatus.EXPIRED.value,
    ActionStatus.CANCELLED.value,
    ActionStatus.ROLLED_BACK.value,
    ActionStatus.ROLLBACK_FAILED.value,
}


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------


class CatalogItem(BaseModel):
    action_type: str
    category: str
    name: str
    description: str
    risk_level: str
    required_permissions: list[str]
    plan_template: str
    rollback_template: str
    reversible: bool
    max_blast_radius: int
    enabled: bool
    version: str


class PlanResponse(BaseModel):
    id: str
    plan_hash: str
    graph_version: int
    template_version: str
    summary: str
    risk: dict[str, Any]
    changes: list[dict[str, Any]]
    permissions: list[str]
    diff: dict[str, Any]
    rollback: dict[str, Any]
    blast_radius: int
    approved_hash: str | None = None
    expires_at: datetime
    created_at: datetime


class ApprovalResponse(BaseModel):
    id: str
    approver_id: str
    approver_email: str
    decision: str
    comment: str | None = None
    plan_hash: str
    mfa_at: datetime | None = None
    created_at: datetime


class ExecutionResponse(BaseModel):
    id: str
    status: str
    error: str | None = None
    rollback_status: str
    verification: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None = None


class ActionDetail(BaseModel):
    id: str
    action_type: str
    status: str
    requester_id: str
    targets: dict[str, Any]
    parameters: dict[str, Any]
    constraints: dict[str, Any]
    justification: str
    risk_level: str
    graph_version: int
    plan: PlanResponse | None = None
    approvals: list[ApprovalResponse] = Field(default_factory=list)
    executions: list[ExecutionResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ActionSummary(BaseModel):
    id: str
    action_type: str
    status: str
    requester_id: str
    risk_level: str
    justification: str
    plan_hash: str | None = None
    summary: str | None = None
    blast_radius: int | None = None
    expires_at: datetime | None = None
    created_at: datetime


class ApprovalRequestBody(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)
    mfa_code: str | None = Field(default=None, max_length=12)


class RejectRequestBody(BaseModel):
    comment: str = Field(min_length=3, max_length=2000)


class ParseIntentRequestBody(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class ParseIntentResponse(BaseModel):
    action_type: str | None = None
    confidence: float
    targets: dict[str, Any]
    parameters: dict[str, Any]
    constraints: dict[str, Any]
    rationale: str
    rejected: bool
    rejection_reason: str | None = None


class EvidenceResponse(BaseModel):
    id: str
    kind: str
    uri: str
    checksum: str
    payload: dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _action_ref(action_id: UUID) -> str:
    return f"act_{action_id.hex}"


def _plan_ref(plan_id: UUID) -> str:
    return f"pln_{plan_id.hex}"


def _parse_ref(value: str, prefix: str) -> UUID:
    raw = value.removeprefix(prefix) if value.startswith(prefix) else value
    try:
        return UUID(raw)
    except ValueError as exc:
        raise NotFound(f"{value} is not a valid {prefix.rstrip('_')} identifier.") from exc


def _sandbox(request: Request) -> bool:
    return str(request.app.state.settings.env.value) in _SANDBOX_ENVS


async def _graph_version(request: Request, tenant_id: str) -> int:
    redis = getattr(request.app.state, "redis_client", None)
    if redis is not None:
        try:
            value = await redis.get(f"seq:{tenant_id}")
            return int(value) if value else 1
        except Exception:
            return 1
    return 1


def _assert_scope(auth: AuthContext, intent: ActionIntentRequest) -> None:
    for resource in target_resource_ids(intent):
        account, region = parse_arn(resource)
        if account and not auth.can_access_account(account):
            raise NotFound(f"Resource {resource} not found.")
        if region and not auth.can_access_region(region):
            raise NotFound(f"Resource {resource} not found.")


async def _load_action(
    session: AsyncSession, tenant_id: UUID, action_id: UUID
) -> ActionRequestModel:
    action = (
        await session.execute(
            select(ActionRequestModel).where(
                ActionRequestModel.id == action_id,
                ActionRequestModel.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if action is None:
        raise NotFound(f"Action {_action_ref(action_id)} not found.")
    return action


async def _latest_plan(session: AsyncSession, action_id: UUID) -> ActionPlanModel | None:
    return (
        await session.execute(
            select(ActionPlanModel)
            .where(ActionPlanModel.action_id == action_id)
            .order_by(desc(ActionPlanModel.created_at), desc(ActionPlanModel.id))
            .limit(1)
        )
    ).scalar_one_or_none()


def _plan_response(plan: ActionPlanModel) -> PlanResponse:
    return PlanResponse(
        id=_plan_ref(plan.id),
        plan_hash=plan.plan_hash,
        graph_version=plan.graph_version,
        template_version=plan.template_version,
        summary=plan.summary,
        risk=plan.risk,
        changes=plan.changes,
        permissions=plan.permissions,
        diff=plan.diff,
        rollback=plan.rollback,
        blast_radius=plan.blast_radius,
        approved_hash=plan.approved_hash,
        expires_at=plan.expires_at,
        created_at=plan.created_at,
    )


def _approval_response(row: ActionApprovalModel) -> ApprovalResponse:
    return ApprovalResponse(
        id=row.id.hex,
        approver_id=str(row.approver_id),
        approver_email=row.approver_email,
        decision=row.decision,
        comment=row.comment,
        plan_hash=row.plan_hash,
        mfa_at=row.mfa_at,
        created_at=row.created_at,
    )


def _execution_response(row: ActionExecutionModel) -> ExecutionResponse:
    return ExecutionResponse(
        id=row.id.hex,
        status=row.status,
        error=row.error,
        rollback_status=row.rollback_status,
        verification=row.verification,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


async def _detail(session: AsyncSession, action: ActionRequestModel) -> ActionDetail:
    # A server-side `onupdate` expires the column after an UPDATE; refresh so the
    # response can be built without triggering a sync lazy load.
    await session.refresh(action)
    plan = await _latest_plan(session, action.id)
    approvals = (
        (
            await session.execute(
                select(ActionApprovalModel)
                .where(ActionApprovalModel.action_id == action.id)
                .order_by(ActionApprovalModel.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    executions = (
        (
            await session.execute(
                select(ActionExecutionModel)
                .where(ActionExecutionModel.action_id == action.id)
                .order_by(ActionExecutionModel.started_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return ActionDetail(
        id=_action_ref(action.id),
        action_type=action.action_type,
        status=action.status,
        requester_id=str(action.requester_id),
        targets=action.targets,
        parameters=action.parameters,
        constraints=action.constraints,
        justification=action.justification,
        risk_level=action.risk_level,
        graph_version=action.graph_version,
        plan=_plan_response(plan) if plan else None,
        approvals=[_approval_response(row) for row in approvals],
        executions=[_execution_response(row) for row in executions],
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


def _require_sandbox_or_refuse(request: Request, intent: ActionIntentRequest) -> None:
    if intent.constraints.simulate_failure and not _sandbox(request):
        raise UnprocessableEntity(
            "Fault injection is only available in sandbox environments.",
            errors=[
                FieldError(
                    pointer="/constraints/simulate_failure",
                    code="sandbox-only",
                    detail="Fault injection is refused outside local/test.",
                )
            ],
        )


async def _assert_writes_enabled(session: AsyncSession, tenant_id: UUID, settings: Any) -> None:
    if not bool(getattr(settings, "writes_enabled", True)):
        raise Conflict("Action writes are disabled by the instance kill switch.")
    blocked, reasons = await get_kill_switch(session, tenant_id)
    if blocked:
        raise Conflict("Action writes are disabled: " + "; ".join(reasons))


def _guardrail_errors(violations: list[Any]) -> list[FieldError]:
    return [
        FieldError(pointer="/targets", code=violation.code, detail=violation.detail)
        for violation in violations
    ]


# ---------------------------------------------------------------------------
# Catalog and intent parsing
# ---------------------------------------------------------------------------


@router.get("/catalog", response_model=list[CatalogItem], summary="List supported actions")
async def list_catalog(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[CatalogItem]:
    rows = (
        (await session.execute(select(ActionCatalogEntry).order_by(ActionCatalogEntry.name)))
        .scalars()
        .all()
    )
    return [
        CatalogItem(
            action_type=row.action_type,
            category=row.category,
            name=row.name,
            description=row.description,
            risk_level=row.risk_level,
            required_permissions=row.required_permissions,
            plan_template=row.plan_template,
            rollback_template=row.rollback_template,
            reversible=row.reversible,
            max_blast_radius=row.max_blast_radius,
            enabled=row.enabled,
            version=row.version,
        )
        for row in rows
    ]


@router.post(
    "/parse-intent",
    response_model=ParseIntentResponse,
    summary="Parse a natural-language action request",
)
async def parse_intent(
    body: ParseIntentRequestBody,
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> ParseIntentResponse:
    parsed = parse_natural_language(body.text)
    return ParseIntentResponse(**parsed.to_dict())


# ---------------------------------------------------------------------------
# Create and list actions
# ---------------------------------------------------------------------------


@router.post("", response_model=ActionDetail, status_code=201, summary="Request an action")
async def create_action(
    body: ActionIntentRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> ActionDetail:
    definition = get_definition(body.type)
    if definition is None:
        raise UnprocessableEntity(
            f"Unknown action type {body.type!r}.",
            errors=[
                FieldError(
                    pointer="/type",
                    code="unknown-action",
                    detail="Use GET /api/v1/actions/catalog for the supported set.",
                )
            ],
        )
    validate_intent(body, definition)
    _assert_scope(auth, body)
    _require_sandbox_or_refuse(request, body)

    idempotency_key = request.headers.get("Idempotency-Key", "")
    existing = (
        await session.execute(
            select(ActionRequestModel).where(
                ActionRequestModel.tenant_id == auth.tenant_id,
                ActionRequestModel.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return await _detail(session, existing)

    await _assert_writes_enabled(session, auth.tenant_id, request.app.state.settings)

    risk = assess_risk(body, definition)
    if risk.level is RiskLevel.CRITICAL and not (
        body.constraints.break_glass and body.constraints.incident_id
    ):
        raise UnprocessableEntity(
            "Critical-risk actions require break-glass and an incident ID.",
            errors=[
                FieldError(
                    pointer="/constraints/break_glass",
                    code="break-glass-required",
                    detail="Set break_glass=true and provide an incident_id.",
                )
            ],
        )

    rules = await load_effective_rules(session, auth.tenant_id)
    violations = evaluate_guardrails(intent=body, definition=definition, risk=risk, rules=rules)
    if violations:
        raise UnprocessableEntity(
            "One or more guardrail rules blocked this action.",
            errors=_guardrail_errors(violations),
        )

    rate_config = rules["rate-limits"].config
    await enforce_rate_limit(
        session,
        auth.tenant_id,
        per_hour=int(rate_config.get("per_hour", 50)),
        resource_count=len(target_resource_ids(body)),
        max_resources=int(rate_config.get("max_resources", 100)),
    )

    graph_version = await _graph_version(request, f"tnt_{auth.tenant_id}")
    action_id = new_uuid7()
    policy = approval_policy_for(risk.level)
    expires_at = datetime.now(tz=UTC) + timedelta(minutes=policy.expiry_minutes)

    draft = build_plan(
        intent=body,
        definition=definition,
        risk=risk,
        tenant_id=f"tnt_{auth.tenant_id}",
        action_id=_action_ref(action_id),
        graph_version=graph_version,
        expires_at=expires_at,
    )

    action = ActionRequestModel(
        id=action_id,
        tenant_id=auth.tenant_id,
        action_type=body.type,
        status=ActionStatus.PENDING_APPROVAL.value,
        requester_id=auth.user_id,
        targets=body.targets.model_dump(mode="json"),
        parameters=body.parameters,
        constraints=body.constraints.model_dump(mode="json"),
        justification=body.justification,
        risk_level=risk.level.value,
        graph_version=graph_version,
        idempotency_key=idempotency_key,
    )
    session.add(action)
    await session.flush()

    plan = ActionPlanModel(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        action_id=action.id,
        plan_hash=draft.plan_hash,
        graph_version=graph_version,
        template_version=draft.template_version,
        summary=draft.summary,
        risk=draft.risk,
        changes=draft.changes,
        permissions=draft.permissions,
        diff=draft.diff,
        rollback=draft.rollback,
        blast_radius=draft.blast_radius,
        expires_at=expires_at,
    )
    session.add(plan)
    await session.flush()

    await append_evidence(
        session,
        tenant_id=auth.tenant_id,
        action_id=action.id,
        kind="plan",
        suffix="plan.json",
        payload={
            "plan_id": _plan_ref(plan.id),
            "plan_hash": plan.plan_hash,
            "action_type": action.action_type,
            "summary": plan.summary,
            "risk": plan.risk,
            "changes": plan.changes,
            "permissions": plan.permissions,
            "iam_policy": draft.iam_policy,
            "policy_findings": draft.policy_findings,
        },
    )
    await append_audit(
        session,
        auth=auth,
        action="action.requested",
        resource_type="action",
        resource_id=_action_ref(action.id),
        metadata={
            "action_type": action.action_type,
            "risk_level": action.risk_level,
            "plan_hash": plan.plan_hash,
            "justification": action.justification,
        },
    )
    return await _detail(session, action)


@router.get("", response_model=Page[ActionSummary], summary="List actions")
async def list_actions(
    request: Request,
    status: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> Page[ActionSummary]:
    secret = request.app.state.settings.cursor_secret.get_secret_value()
    stmt = (
        select(ActionRequestModel)
        .where(ActionRequestModel.tenant_id == auth.tenant_id)
        .order_by(desc(ActionRequestModel.created_at), desc(ActionRequestModel.id))
        .limit(limit + 1)
    )
    if status:
        stmt = stmt.where(ActionRequestModel.status == status)
    if action_type:
        stmt = stmt.where(ActionRequestModel.action_type == action_type)
    if cursor:
        cursor_data = decode_cursor(cursor, secret=secret)
        last_time = datetime.fromisoformat(str(cursor_data["created_at"]))
        last_id = UUID(str(cursor_data["id"]))
        stmt = stmt.where(
            (ActionRequestModel.created_at < last_time)
            | ((ActionRequestModel.created_at == last_time) & (ActionRequestModel.id < last_id))
        )

    records = (await session.execute(stmt)).scalars().all()
    has_more = len(records) > limit
    page = records[:limit]

    plans: dict[UUID, ActionPlanModel] = {}
    if page:
        plan_rows = (
            (
                await session.execute(
                    select(ActionPlanModel)
                    .where(ActionPlanModel.action_id.in_([item.id for item in page]))
                    .order_by(ActionPlanModel.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        for plan_row in plan_rows:
            plans[plan_row.action_id] = plan_row

    items = []
    for action in page:
        plan = plans.get(action.id)
        items.append(
            ActionSummary(
                id=_action_ref(action.id),
                action_type=action.action_type,
                status=action.status,
                requester_id=str(action.requester_id),
                risk_level=action.risk_level,
                justification=action.justification,
                plan_hash=plan.plan_hash if plan else None,
                summary=plan.summary if plan else None,
                blast_radius=plan.blast_radius if plan else None,
                expires_at=plan.expires_at if plan else None,
                created_at=action.created_at,
            )
        )

    next_payload = None
    if has_more and page:
        last = page[-1]
        next_payload = {"created_at": last.created_at.isoformat(), "id": str(last.id)}

    return Page[ActionSummary].build(items, limit=limit, next_payload=next_payload, secret=secret)


@router.get(
    "/inbox",
    response_model=list[ActionSummary],
    summary="Approval inbox for the current approver",
)
async def approval_inbox(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.APPROVE_ACTION)),
) -> list[ActionSummary]:
    actions = (
        (
            await session.execute(
                select(ActionRequestModel)
                .where(
                    ActionRequestModel.tenant_id == auth.tenant_id,
                    ActionRequestModel.status == ActionStatus.PENDING_APPROVAL.value,
                    ActionRequestModel.requester_id != auth.user_id,
                )
                .order_by(desc(ActionRequestModel.created_at))
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    result: list[ActionSummary] = []
    for action in actions:
        plan = await _latest_plan(session, action.id)
        result.append(
            ActionSummary(
                id=_action_ref(action.id),
                action_type=action.action_type,
                status=action.status,
                requester_id=str(action.requester_id),
                risk_level=action.risk_level,
                justification=action.justification,
                plan_hash=plan.plan_hash if plan else None,
                summary=plan.summary if plan else None,
                blast_radius=plan.blast_radius if plan else None,
                expires_at=plan.expires_at if plan else None,
                created_at=action.created_at,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Detail, approval, execution
# ---------------------------------------------------------------------------


@router.get("/{action_id}", response_model=ActionDetail, summary="Get action detail")
async def get_action(
    action_id: str,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> ActionDetail:
    action = await _load_action(session, auth.tenant_id, _parse_ref(action_id, "act_"))
    return await _detail(session, action)


@router.post(
    "/{action_id}/approve",
    response_model=ActionDetail,
    summary="Approve the current immutable plan",
)
async def approve_action(
    action_id: str,
    body: ApprovalRequestBody,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.APPROVE_ACTION)),
) -> ActionDetail:
    action = await _load_action(session, auth.tenant_id, _parse_ref(action_id, "act_"))
    if action.status != ActionStatus.PENDING_APPROVAL.value:
        raise Conflict(f"Action is {action.status}; only PENDING_APPROVAL can be approved.")

    plan = await _latest_plan(session, action.id)
    if plan is None:
        raise Conflict("Action has no current plan.")
    if plan.expires_at < datetime.now(tz=UTC):
        action.status = ActionStatus.EXPIRED.value
        await append_audit(
            session,
            auth=auth,
            action="action.expired",
            resource_type="action",
            resource_id=_action_ref(action.id),
            metadata={"plan_hash": plan.plan_hash},
        )
        await session.flush()
        raise Conflict("The plan has expired; re-plan before approving.")

    level = risk_from_str(action.risk_level)
    policy = approval_policy_for(level)

    if action.requester_id == auth.user_id and not policy.requester_may_approve:
        raise Forbidden("Requesters cannot approve their own medium, high, or critical actions.")

    if level is RiskLevel.CRITICAL and not (
        bool(action.constraints.get("break_glass")) and bool(action.constraints.get("incident_id"))
    ):
        raise Forbidden("Critical actions require a break-glass incident before approval.")

    mfa_at: datetime | None = None
    if policy.requires_mfa:
        if not body.mfa_code or re.fullmatch(r"\d{6}", body.mfa_code) is None:
            raise UnprocessableEntity(
                "Step-up MFA is required for this risk level.",
                errors=[
                    FieldError(
                        pointer="/mfa_code",
                        code="mfa-required",
                        detail="Provide the current six-digit MFA code.",
                    )
                ],
            )
        mfa_at = datetime.now(tz=UTC)

    duplicate = (
        await session.execute(
            select(ActionApprovalModel).where(
                ActionApprovalModel.action_id == action.id,
                ActionApprovalModel.plan_id == plan.id,
                ActionApprovalModel.approver_id == auth.user_id,
                ActionApprovalModel.decision == ApprovalDecision.APPROVED.value,
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise Conflict("You have already approved this action.")

    approval = ActionApprovalModel(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        action_id=action.id,
        plan_id=plan.id,
        approver_id=auth.user_id,
        approver_email=auth.email,
        decision=ApprovalDecision.APPROVED.value,
        comment=body.comment,
        plan_hash=plan.plan_hash,
        mfa_at=mfa_at,
    )
    session.add(approval)
    await session.flush()

    approved_count = await session.scalar(
        select(func.count(func.distinct(ActionApprovalModel.approver_id))).where(
            ActionApprovalModel.action_id == action.id,
            ActionApprovalModel.plan_id == plan.id,
            ActionApprovalModel.decision == ApprovalDecision.APPROVED.value,
        )
    )
    if int(approved_count or 0) >= policy.required_approvals:
        action.status = ActionStatus.APPROVED.value
        plan.approved_hash = plan.plan_hash

    await append_evidence(
        session,
        tenant_id=auth.tenant_id,
        action_id=action.id,
        kind="approval",
        suffix=f"approvals/{approval.id.hex}.json",
        payload={
            "approver": auth.email,
            "decision": approval.decision,
            "plan_hash": plan.plan_hash,
            "mfa_at": mfa_at.isoformat() if mfa_at else None,
            "comment": body.comment,
            "approved_count": int(approved_count or 0),
        },
    )
    await append_audit(
        session,
        auth=auth,
        action="action.approved",
        resource_type="action",
        resource_id=_action_ref(action.id),
        metadata={
            "plan_hash": plan.plan_hash,
            "mfa": mfa_at is not None,
            "status": action.status,
        },
    )
    return await _detail(session, action)


@router.post(
    "/{action_id}/reject",
    response_model=ActionDetail,
    summary="Reject the current plan",
)
async def reject_action(
    action_id: str,
    body: RejectRequestBody,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.APPROVE_ACTION)),
) -> ActionDetail:
    action = await _load_action(session, auth.tenant_id, _parse_ref(action_id, "act_"))
    if action.status != ActionStatus.PENDING_APPROVAL.value:
        raise Conflict(f"Action is {action.status}; only PENDING_APPROVAL can be rejected.")
    plan = await _latest_plan(session, action.id)
    if plan is None:
        raise Conflict("Action has no current plan.")

    rejection = ActionApprovalModel(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        action_id=action.id,
        plan_id=plan.id,
        approver_id=auth.user_id,
        approver_email=auth.email,
        decision=ApprovalDecision.REJECTED.value,
        comment=body.comment,
        plan_hash=plan.plan_hash,
    )
    session.add(rejection)
    action.status = ActionStatus.REJECTED.value
    await append_audit(
        session,
        auth=auth,
        action="action.rejected",
        resource_type="action",
        resource_id=_action_ref(action.id),
        metadata={"plan_hash": plan.plan_hash, "comment": body.comment},
    )
    return await _detail(session, action)


@router.post(
    "/{action_id}/execute",
    response_model=ActionDetail,
    summary="Execute an approved immutable plan",
)
async def execute_action(
    action_id: str,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> ActionDetail:
    action = await _load_action(session, auth.tenant_id, _parse_ref(action_id, "act_"))
    if action.status != ActionStatus.APPROVED.value:
        raise Conflict(f"Action is {action.status}; only APPROVED actions can execute.")

    plan = await _latest_plan(session, action.id)
    if plan is None:
        raise Conflict("Action has no current plan.")
    if plan.approved_hash != plan.plan_hash:
        raise Conflict("The plan changed after approval; re-approval is required.")
    if plan.expires_at < datetime.now(tz=UTC):
        action.status = ActionStatus.EXPIRED.value
        await session.flush()
        raise Conflict("The approved plan has expired; re-plan before executing.")

    await _assert_writes_enabled(session, auth.tenant_id, request.app.state.settings)

    definition = get_definition(action.action_type)
    if definition is None:
        raise Conflict(f"Action type {action.action_type} is no longer supported.")

    resources = sorted(
        {
            value
            for key in ("source", "target")
            if isinstance(value := action.targets.get(key), str) and value
        }
        | set(action.targets.get("resources", []))
    )
    await acquire_locks(session, tenant_id=auth.tenant_id, action_id=action.id, resources=resources)
    action.status = ActionStatus.EXECUTING.value
    await session.flush()

    execution, outcome = await execute_plan(
        session,
        action=action,
        plan=plan,
        definition=definition,
        sandbox=_sandbox(request),
    )

    repo = _get_graph_repo(request)
    if outcome.status.value == "SUCCEEDED":
        with contextlib.suppress(Exception):
            await repo.apply_action_metadata(
                f"tnt_{auth.tenant_id}", resources, _action_ref(action.id)
            )
    else:
        await rollback_execution(
            session, action=action, execution=execution, sandbox=_sandbox(request)
        )
        with contextlib.suppress(Exception):
            await repo.clear_action_metadata(f"tnt_{auth.tenant_id}", resources)

    await release_locks(session, tenant_id=auth.tenant_id, action_id=action.id)

    await append_evidence(
        session,
        tenant_id=auth.tenant_id,
        action_id=action.id,
        kind="execution",
        suffix=f"executions/{execution.id.hex}.json",
        payload={
            "execution_id": execution.id.hex,
            "status": execution.status,
            "verification": execution.verification,
            "error": execution.error,
            "rollback_status": execution.rollback_status,
        },
    )
    await append_audit(
        session,
        auth=auth,
        action="action.executed" if outcome.status.value == "SUCCEEDED" else "action.failed",
        resource_type="action",
        resource_id=_action_ref(action.id),
        metadata={
            "plan_hash": plan.plan_hash,
            "execution_id": execution.id.hex,
            "status": action.status,
        },
    )
    return await _detail(session, action)


@router.post(
    "/{action_id}/rollback",
    response_model=ActionDetail,
    summary="Roll back a completed or failed action",
)
async def rollback_action(
    action_id: str,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> ActionDetail:
    action = await _load_action(session, auth.tenant_id, _parse_ref(action_id, "act_"))
    if action.status not in (
        ActionStatus.SUCCEEDED.value,
        ActionStatus.FAILED.value,
        ActionStatus.ROLLBACK_FAILED.value,
    ):
        raise Conflict(f"Action is {action.status}; rollback is not available.")

    execution = (
        await session.execute(
            select(ActionExecutionModel)
            .where(ActionExecutionModel.action_id == action.id)
            .order_by(desc(ActionExecutionModel.started_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if execution is None:
        raise Conflict("Action has no execution to roll back.")

    outcome = await rollback_execution(
        session, action=action, execution=execution, sandbox=_sandbox(request)
    )
    resources = sorted(
        {
            value
            for key in ("source", "target")
            if isinstance(value := action.targets.get(key), str) and value
        }
        | set(action.targets.get("resources", []))
    )
    with contextlib.suppress(Exception):
        await _get_graph_repo(request).clear_action_metadata(f"tnt_{auth.tenant_id}", resources)
    await release_locks(session, tenant_id=auth.tenant_id, action_id=action.id)

    await append_evidence(
        session,
        tenant_id=auth.tenant_id,
        action_id=action.id,
        kind="rollback",
        suffix=f"rollback/{execution.id.hex}.json",
        payload={
            "status": outcome.status.value,
            "rolled_back": outcome.rolled_back,
            "error": outcome.error,
        },
    )
    await append_audit(
        session,
        auth=auth,
        action="action.rolled_back" if outcome.rolled_back else "action.rollback_failed",
        resource_type="action",
        resource_id=_action_ref(action.id),
        metadata={"execution_id": execution.id.hex},
    )
    return await _detail(session, action)


@router.post(
    "/{action_id}/cancel",
    response_model=ActionDetail,
    summary="Cancel a non-executing action",
)
async def cancel_action(
    action_id: str,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> ActionDetail:
    action = await _load_action(session, auth.tenant_id, _parse_ref(action_id, "act_"))
    if auth.user_id != action.requester_id and not auth.has_permission(Permission.ADMIN_SETTINGS):
        raise Forbidden("Only the requester or a tenant admin can cancel this action.")
    if action.status in (
        ActionStatus.EXECUTING.value,
        ActionStatus.VERIFYING.value,
        ActionStatus.SUCCEEDED.value,
    ):
        raise Conflict(f"Action is {action.status} and can no longer be cancelled.")
    action.status = ActionStatus.CANCELLED.value
    await append_audit(
        session,
        auth=auth,
        action="action.cancelled",
        resource_type="action",
        resource_id=_action_ref(action.id),
    )
    return await _detail(session, action)


@router.post(
    "/{action_id}/replan",
    response_model=ActionDetail,
    summary="Recompile the plan against the current graph version",
)
async def replan_action(
    action_id: str,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> ActionDetail:
    action = await _load_action(session, auth.tenant_id, _parse_ref(action_id, "act_"))
    if action.status in (
        ActionStatus.EXECUTING.value,
        ActionStatus.VERIFYING.value,
        ActionStatus.SUCCEEDED.value,
        ActionStatus.CANCELLED.value,
    ):
        raise Conflict(f"Action is {action.status} and cannot be re-planned.")

    definition = get_definition(action.action_type)
    if definition is None:
        raise Conflict(f"Action type {action.action_type} is no longer supported.")

    intent = ActionIntentRequest.model_validate(
        {
            "type": action.action_type,
            "targets": action.targets,
            "parameters": action.parameters,
            "constraints": action.constraints,
            "justification": action.justification,
        }
    )
    risk = assess_risk(intent, definition)
    graph_version = await _graph_version(request, f"tnt_{auth.tenant_id}")
    policy = approval_policy_for(risk.level)
    expires_at = datetime.now(tz=UTC) + timedelta(minutes=policy.expiry_minutes)
    draft = build_plan(
        intent=intent,
        definition=definition,
        risk=risk,
        tenant_id=f"tnt_{auth.tenant_id}",
        action_id=_action_ref(action.id),
        graph_version=graph_version,
        expires_at=expires_at,
    )
    plan = ActionPlanModel(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        action_id=action.id,
        plan_hash=draft.plan_hash,
        graph_version=graph_version,
        template_version=draft.template_version,
        summary=draft.summary,
        risk=draft.risk,
        changes=draft.changes,
        permissions=draft.permissions,
        diff=draft.diff,
        rollback=draft.rollback,
        blast_radius=draft.blast_radius,
        expires_at=expires_at,
    )
    session.add(plan)
    action.status = ActionStatus.PENDING_APPROVAL.value
    action.risk_level = risk.level.value
    action.graph_version = graph_version
    await session.flush()

    await append_evidence(
        session,
        tenant_id=auth.tenant_id,
        action_id=action.id,
        kind="plan",
        suffix=f"plans/{plan.id.hex}.json",
        payload={
            "plan_id": _plan_ref(plan.id),
            "plan_hash": plan.plan_hash,
            "summary": plan.summary,
            "risk": plan.risk,
            "changes": plan.changes,
        },
    )
    await append_audit(
        session,
        auth=auth,
        action="action.replanned",
        resource_type="action",
        resource_id=_action_ref(action.id),
        metadata={"plan_hash": plan.plan_hash, "graph_version": graph_version},
    )
    return await _detail(session, action)


@router.get(
    "/{action_id}/evidence",
    response_model=list[EvidenceResponse],
    summary="List immutable evidence artifacts for an action",
)
async def list_evidence(
    action_id: str,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[EvidenceResponse]:
    action = await _load_action(session, auth.tenant_id, _parse_ref(action_id, "act_"))
    rows = (
        (
            await session.execute(
                select(ActionEvidenceModel)
                .where(ActionEvidenceModel.action_id == action.id)
                .order_by(ActionEvidenceModel.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        EvidenceResponse(
            id=row.id.hex,
            kind=row.kind,
            uri=row.uri,
            checksum=row.checksum,
            payload=row.payload,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get(
    "/{action_id}/explanation",
    summary="Explain plan risk in plain language",
)
async def explain_action(
    action_id: str,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    action = await _load_action(session, auth.tenant_id, _parse_ref(action_id, "act_"))
    plan = await _latest_plan(session, action.id)
    if plan is None:
        raise NotFound("Action has no plan to explain.")
    return {
        "action_id": _action_ref(action.id),
        "plan_hash": plan.plan_hash,
        "explanation": explain_plan(plan.summary, plan.risk),
    }


def _definition_or_404(action_type: str) -> ActionDefinition:
    definition = get_definition(action_type)
    if definition is None:
        raise NotFound(f"Action definition {action_type} not found.")
    return definition
