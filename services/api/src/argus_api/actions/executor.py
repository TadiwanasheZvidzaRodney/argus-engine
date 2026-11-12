"""Execution orchestration: resource locks, verification, and rollback drills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from argus_core.errors import Conflict, UnprocessableEntity
from argus_core.events import new_uuid7
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.actions.catalog import ActionDefinition
from argus_api.actions.types import ActionStatus, ExecutionStatus
from argus_api.models import (
    ActionExecutionModel,
    ActionLockModel,
    ActionPlanModel,
    ActionRequestModel,
)

LOCK_TTL_MINUTES = 30


@dataclass(frozen=True)
class ExecutionOutcome:
    status: ExecutionStatus
    verification: dict[str, Any]
    error: str | None = None
    rolled_back: bool = False


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def acquire_locks(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    action_id: UUID,
    resources: list[str],
    ttl_minutes: int = LOCK_TTL_MINUTES,
) -> list[str]:
    if not resources:
        raise UnprocessableEntity("Execution requires at least one target resource.")
    now = _now()
    await session.execute(
        delete(ActionLockModel).where(
            ActionLockModel.tenant_id == tenant_id,
            ActionLockModel.expires_at < now,
        )
    )
    existing = (
        (
            await session.execute(
                select(ActionLockModel).where(
                    ActionLockModel.tenant_id == tenant_id,
                    ActionLockModel.resource_key.in_(resources),
                )
            )
        )
        .scalars()
        .all()
    )
    conflicts = sorted({lock.resource_key for lock in existing if lock.action_id != action_id})
    if conflicts:
        raise Conflict("Resources are locked by another in-flight action: " + ", ".join(conflicts))

    locked = {lock.resource_key for lock in existing}
    expires_at = now + timedelta(minutes=ttl_minutes)
    for resource in resources:
        if resource in locked:
            continue
        session.add(
            ActionLockModel(
                id=new_uuid7(),
                tenant_id=tenant_id,
                resource_key=resource,
                action_id=action_id,
                acquired_at=now,
                expires_at=expires_at,
            )
        )
    await session.flush()
    return resources


async def release_locks(session: AsyncSession, *, tenant_id: UUID, action_id: UUID) -> None:
    await session.execute(
        delete(ActionLockModel).where(
            ActionLockModel.tenant_id == tenant_id,
            ActionLockModel.action_id == action_id,
        )
    )


def verify_plan(plan: ActionPlanModel, definition: ActionDefinition) -> dict[str, Any]:
    """Deterministic post-condition verification for the synthetic executor."""
    checks: list[dict[str, Any]] = []
    passed = True

    if not plan.changes:
        checks.append(
            {"check": "changes_present", "passed": False, "detail": "Plan has no changes."}
        )
        passed = False
    else:
        checks.append(
            {
                "check": "changes_present",
                "passed": True,
                "detail": f"{len(plan.changes)} change(s) compiled.",
            }
        )

    for change in plan.changes:
        ok = bool(change.get("resource")) and bool(change.get("after_hash"))
        if not ok:
            passed = False
        checks.append(
            {
                "check": "change_applied",
                "resource": change.get("resource"),
                "attribute": change.get("attribute"),
                "passed": ok,
            }
        )

    rollback_ready = bool(plan.rollback.get("template"))
    if not rollback_ready:
        passed = False
    checks.append(
        {
            "check": "rollback_available",
            "passed": rollback_ready,
            "detail": plan.rollback.get("strategy"),
        }
    )

    return {
        "status": "passed" if passed else "failed",
        "checked_resources": len({change.get("resource") for change in plan.changes}),
        "definition": definition.action_type,
        "checks": checks,
        "verified_at": _now().isoformat(),
    }


async def execute_plan(
    session: AsyncSession,
    *,
    action: ActionRequestModel,
    plan: ActionPlanModel,
    definition: ActionDefinition,
    sandbox: bool,
) -> tuple[ActionExecutionModel, ExecutionOutcome]:
    now = _now()
    execution = ActionExecutionModel(
        id=new_uuid7(),
        tenant_id=action.tenant_id,
        action_id=action.id,
        plan_id=plan.id,
        status=ExecutionStatus.EXECUTING.value,
        state_machine_arn=f"arn:aws:states:us-east-1:000000000000:execution:argus-action:{action.id.hex}",
        started_at=now,
    )
    session.add(execution)
    await session.flush()

    simulate_failure = bool(action.constraints.get("simulate_failure")) and sandbox
    if simulate_failure:
        execution.status = ExecutionStatus.FAILED.value
        execution.error = "Injected sandbox failure before apply."
        execution.completed_at = _now()
        action.status = ActionStatus.FAILED.value
        await session.flush()
        return execution, ExecutionOutcome(
            status=ExecutionStatus.FAILED,
            verification={"status": "not-run", "reason": "execution failed"},
            error=execution.error,
        )

    verification = verify_plan(plan, definition)
    execution.status = (
        ExecutionStatus.SUCCEEDED.value
        if verification["status"] == "passed"
        else ExecutionStatus.FAILED.value
    )
    execution.verification = verification
    execution.completed_at = _now()
    if verification["status"] == "passed":
        action.status = ActionStatus.SUCCEEDED.value
        outcome_status = ExecutionStatus.SUCCEEDED
        error = None
    else:
        action.status = ActionStatus.FAILED.value
        execution.error = "Post-execution verification failed."
        outcome_status = ExecutionStatus.FAILED
        error = execution.error

    await session.flush()
    return execution, ExecutionOutcome(
        status=outcome_status,
        verification=verification,
        error=error,
    )


async def rollback_execution(
    session: AsyncSession,
    *,
    action: ActionRequestModel,
    execution: ActionExecutionModel,
    sandbox: bool,
) -> ExecutionOutcome:
    action.status = ActionStatus.ROLLING_BACK.value
    execution.rollback_status = "in_progress"
    await session.flush()

    if bool(action.constraints.get("simulate_rollback_failure")) and sandbox:
        action.status = ActionStatus.ROLLBACK_FAILED.value
        execution.rollback_status = "failed"
        execution.completed_at = _now()
        await session.flush()
        return ExecutionOutcome(
            status=ExecutionStatus.FAILED,
            verification=execution.verification,
            error="Injected sandbox rollback failure.",
            rolled_back=False,
        )

    action.status = ActionStatus.ROLLED_BACK.value
    execution.rollback_status = "succeeded"
    execution.completed_at = _now()
    verification = dict(execution.verification or {})
    verification["rollback"] = {
        "status": "succeeded",
        "rolled_back_at": _now().isoformat(),
    }
    execution.verification = verification
    await session.flush()
    return ExecutionOutcome(
        status=ExecutionStatus.ROLLED_BACK,
        verification=verification,
        rolled_back=True,
    )
