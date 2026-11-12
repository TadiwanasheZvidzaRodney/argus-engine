"""Guardrail engine, approval policy helpers, kill switch, and quotas."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from argus_core.errors import RateLimited, UnprocessableEntity
from argus_core.events import new_uuid7
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.actions.catalog import ActionDefinition
from argus_api.actions.intent import ActionIntentRequest, target_resource_ids
from argus_api.actions.planner import RiskAssessment
from argus_api.actions.types import RiskLevel, approval_policy_for
from argus_api.models import ActionRequestModel, GuardrailRuleModel, KillSwitchStateModel

DEFAULT_RULES: dict[str, tuple[str, dict[str, Any]]] = {
    "protected-resources": ("protected_resources", {"resources": []}),
    "deny-list": ("deny_list", {"resources": []}),
    "allowed-accounts": ("allowed_accounts", {"accounts": []}),
    "allowed-regions": ("allowed_regions", {"regions": []}),
    "blast-radius": ("max_blast_radius", {"limit": 25}),
    "rate-limits": ("rate_limits", {"per_hour": 50, "max_resources": 100}),
    "change-window": ("change_window", {"start_hour": 0, "end_hour": 24, "utc": True}),
    "wildcards": ("wildcards", {"allow": False}),
}


@dataclass(frozen=True)
class GuardrailViolation:
    code: str
    rule: str
    detail: str


@dataclass(frozen=True)
class EffectiveRule:
    name: str
    rule_type: str
    config: dict[str, Any]
    enabled: bool
    version: str = "1.0.0"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def parse_arn(value: str) -> tuple[str | None, str | None]:
    """Return ``(account_id, region)`` from an ARN when present."""
    parts = value.split(":")
    if len(parts) < 6 or parts[0] != "arn":
        return None, None
    region = parts[3] or None
    account = parts[4] or None
    return account, region


def _actions(intent: ActionIntentRequest) -> list[str]:
    raw = intent.parameters.get("actions", [])
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def _public_cidr(intent: ActionIntentRequest) -> bool:
    for candidate in (intent.parameters.get("cidr"), intent.parameters.get("source_cidr")):
        if not isinstance(candidate, str):
            continue
        try:
            if ipaddress.ip_network(candidate, strict=False).prefixlen == 0:
                return True
        except ValueError:
            continue
    return False


def _in_change_window(now: datetime, config: dict[str, Any]) -> bool:
    start = int(config.get("start_hour", 0))
    end = int(config.get("end_hour", 24))
    if start == 0 and end >= 24:
        return True
    hour = now.astimezone(UTC).hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def evaluate_guardrails(
    *,
    intent: ActionIntentRequest,
    definition: ActionDefinition,
    risk: RiskAssessment,
    rules: dict[str, EffectiveRule],
    now: datetime | None = None,
) -> list[GuardrailViolation]:
    now = now or datetime.now(tz=UTC)
    targets = target_resource_ids(intent)
    violations: list[GuardrailViolation] = []

    protected = set(_string_list(rules["protected-resources"].config.get("resources")))
    denied = set(_string_list(rules["deny-list"].config.get("resources")))
    for resource in targets:
        if resource in protected:
            violations.append(
                GuardrailViolation(
                    code="protected-resource",
                    rule="protected-resources",
                    detail=f"{resource} is protected and cannot be mutated by an action.",
                )
            )
        if resource in denied:
            violations.append(
                GuardrailViolation(
                    code="deny-listed-resource",
                    rule="deny-list",
                    detail=f"{resource} is on the tenant deny-list.",
                )
            )

    allowed_accounts = set(_string_list(rules["allowed-accounts"].config.get("accounts")))
    allowed_regions = set(_string_list(rules["allowed-regions"].config.get("regions")))
    if allowed_accounts or allowed_regions:
        for resource in targets:
            account, region = parse_arn(resource)
            if allowed_accounts and account and account not in allowed_accounts:
                violations.append(
                    GuardrailViolation(
                        code="account-not-allowed",
                        rule="allowed-accounts",
                        detail=f"Account {account} is outside the approved action scope.",
                    )
                )
            if allowed_regions and region and region not in allowed_regions:
                violations.append(
                    GuardrailViolation(
                        code="region-not-allowed",
                        rule="allowed-regions",
                        detail=f"Region {region} is outside the approved action scope.",
                    )
                )

    blast_limit = int(rules["blast-radius"].config.get("limit", 25))
    if risk.blast_radius > blast_limit:
        violations.append(
            GuardrailViolation(
                code="blast-radius-exceeded",
                rule="blast-radius",
                detail=(
                    f"Plan touches {risk.blast_radius} resources, above the tenant limit "
                    f"of {blast_limit}."
                ),
            )
        )

    rate_config = rules["rate-limits"].config
    max_resources = int(rate_config.get("max_resources", 100))
    if len(targets) > max_resources:
        violations.append(
            GuardrailViolation(
                code="resource-count-exceeded",
                rule="rate-limits",
                detail=f"Plan touches {len(targets)} resources, above the {max_resources} limit.",
            )
        )

    wildcard_allowed = bool(rules["wildcards"].config.get("allow", False))
    wildcard_actions = [
        action for action in _actions(intent) if action == "*" or action.endswith(":*")
    ]
    if wildcard_actions and not wildcard_allowed:
        violations.append(
            GuardrailViolation(
                code="wildcard-action",
                rule="wildcards",
                detail=f"Wildcard actions are not allowed: {', '.join(wildcard_actions)}.",
            )
        )

    window = rules["change-window"]
    if not _in_change_window(now, window.config) and not intent.constraints.maintenance_window:
        violations.append(
            GuardrailViolation(
                code="outside-change-window",
                rule="change-window",
                detail=(
                    "The action is outside the tenant change window and no maintenance "
                    "window was declared."
                ),
            )
        )

    if (
        _public_cidr(intent)
        and intent.constraints.environment == "prod"
        and not intent.constraints.break_glass
    ):
        violations.append(
            GuardrailViolation(
                code="public-exposure",
                rule="wildcards",
                detail="Public CIDR exposure in production requires a break-glass approval.",
            )
        )

    if (
        not definition.reversible
        and intent.constraints.environment == "prod"
        and not intent.constraints.break_glass
    ):
        violations.append(
            GuardrailViolation(
                code="irreversible-in-production",
                rule="blast-radius",
                detail="Irreversible actions in production require break-glass approval.",
            )
        )

    if (
        risk.level is RiskLevel.CRITICAL
        and intent.constraints.environment == "prod"
        and not intent.constraints.break_glass
    ):
        violations.append(
            GuardrailViolation(
                code="critical-requires-break-glass",
                rule="protected-resources",
                detail="Critical-risk actions require break-glass with an incident ID.",
            )
        )

    return violations


def default_rules() -> dict[str, EffectiveRule]:
    return {
        name: EffectiveRule(name=name, rule_type=rule_type, config=dict(config), enabled=True)
        for name, (rule_type, config) in DEFAULT_RULES.items()
    }


async def load_effective_rules(session: AsyncSession, tenant_id: UUID) -> dict[str, EffectiveRule]:
    effective = default_rules()
    result = await session.execute(
        select(GuardrailRuleModel).where(GuardrailRuleModel.tenant_id == tenant_id)
    )
    for row in result.scalars().all():
        effective[row.name] = EffectiveRule(
            name=row.name,
            rule_type=row.rule_type,
            config=dict(row.config),
            enabled=row.enabled,
            version=row.version,
        )
    return effective


async def upsert_rule(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    name: str,
    rule_type: str,
    config: dict[str, Any],
    enabled: bool,
    version: str = "1.0.0",
) -> GuardrailRuleModel:
    result = await session.execute(
        select(GuardrailRuleModel).where(
            GuardrailRuleModel.tenant_id == tenant_id,
            GuardrailRuleModel.name == name,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = GuardrailRuleModel(
            id=new_uuid7(),
            tenant_id=tenant_id,
            name=name,
            rule_type=rule_type,
            config=config,
            enabled=enabled,
            version=version,
        )
        session.add(row)
    else:
        row.rule_type = rule_type
        row.config = config
        row.enabled = enabled
        row.version = version
    await session.flush()
    return row


async def enforce_rate_limit(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    per_hour: int,
    resource_count: int,
    max_resources: int,
) -> None:
    if resource_count > max_resources:
        raise UnprocessableEntity(
            f"The plan touches {resource_count} resources, above the limit of {max_resources}."
        )
    since = datetime.now(tz=UTC) - timedelta(hours=1)
    count = await session.scalar(
        select(func.count(ActionRequestModel.id)).where(
            ActionRequestModel.tenant_id == tenant_id,
            ActionRequestModel.created_at >= since,
        )
    )
    if int(count or 0) >= per_hour:
        raise RateLimited(
            retry_after_seconds=60,
            detail=f"Tenant action quota of {per_hour}/hour exceeded.",
        )


async def get_kill_switch(session: AsyncSession, tenant_id: UUID) -> tuple[bool, list[str]]:
    result = await session.execute(
        select(KillSwitchStateModel).where(
            or_(
                KillSwitchStateModel.tenant_id == tenant_id,
                KillSwitchStateModel.tenant_id.is_(None),
            )
        )
    )
    reasons: list[str] = []
    enabled = False
    for row in result.scalars().all():
        if row.enabled:
            enabled = True
            reasons.append(f"{row.scope}:{row.reason or 'writes disabled'}")
    return enabled, reasons


async def set_kill_switch(
    session: AsyncSession,
    *,
    tenant_id: UUID | None,
    scope: str,
    enabled: bool,
    reason: str | None,
    actor_id: UUID,
) -> KillSwitchStateModel:
    result = await session.execute(
        select(KillSwitchStateModel).where(
            KillSwitchStateModel.scope == scope,
            KillSwitchStateModel.tenant_id.is_(None)
            if tenant_id is None
            else KillSwitchStateModel.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = KillSwitchStateModel(
            id=new_uuid7(),
            tenant_id=tenant_id,
            scope=scope,
            enabled=enabled,
            reason=reason,
            activated_by=actor_id,
        )
        session.add(row)
    else:
        row.enabled = enabled
        row.reason = reason
        row.activated_by = actor_id
    await session.flush()
    return row


def policy_for_level(level: RiskLevel) -> tuple[int, bool, bool, int]:
    policy = approval_policy_for(level)
    return (
        policy.required_approvals,
        policy.requester_may_approve,
        policy.requires_mfa,
        policy.expiry_minutes,
    )
