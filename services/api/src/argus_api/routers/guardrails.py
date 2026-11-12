"""Guardrail configuration and kill-switch administration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.actions.audit import append_audit
from argus_api.actions.guardrails import (
    get_kill_switch,
    load_effective_rules,
    set_kill_switch,
    upsert_rule,
)
from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission

router = APIRouter(prefix="/api/v1", tags=["guardrails"])


class GuardrailRuleResponse(BaseModel):
    name: str
    rule_type: str
    config: dict[str, Any]
    enabled: bool
    version: str


class GuardrailRuleUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    rule_type: str = Field(min_length=1, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    version: str = Field(default="1.0.0", max_length=32)


class GuardrailUpdateRequest(BaseModel):
    rules: list[GuardrailRuleUpdate] = Field(min_length=1, max_length=50)


class KillSwitchStateResponse(BaseModel):
    tenant_enabled: bool
    global_enabled: bool
    reasons: list[str]


class KillSwitchUpdateRequest(BaseModel):
    scope: str = Field(default="tenant", pattern=r"^(tenant|global)$")
    enabled: bool
    reason: str | None = Field(default=None, max_length=2000)


@router.get(
    "/guardrails",
    response_model=list[GuardrailRuleResponse],
    summary="List effective guardrail rules",
)
async def list_guardrails(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[GuardrailRuleResponse]:
    rules = await load_effective_rules(session, auth.tenant_id)
    return [
        GuardrailRuleResponse(
            name=rule.name,
            rule_type=rule.rule_type,
            config=rule.config,
            enabled=rule.enabled,
            version=rule.version,
        )
        for rule in rules.values()
    ]


@router.put(
    "/guardrails",
    response_model=list[GuardrailRuleResponse],
    summary="Update guardrail rules",
)
async def update_guardrails(
    body: GuardrailUpdateRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.ADMIN_SETTINGS)),
) -> list[GuardrailRuleResponse]:
    for rule in body.rules:
        await upsert_rule(
            session,
            auth.tenant_id,
            name=rule.name,
            rule_type=rule.rule_type,
            config=rule.config,
            enabled=rule.enabled,
            version=rule.version,
        )
    await append_audit(
        session,
        auth=auth,
        action="guardrails.updated",
        resource_type="guardrail",
        resource_id=str(auth.tenant_id),
        metadata={"rules": [rule.name for rule in body.rules]},
    )
    rules = await load_effective_rules(session, auth.tenant_id)
    return [
        GuardrailRuleResponse(
            name=rule.name,
            rule_type=rule.rule_type,
            config=rule.config,
            enabled=rule.enabled,
            version=rule.version,
        )
        for rule in rules.values()
    ]


@router.get(
    "/kill-switch",
    response_model=KillSwitchStateResponse,
    summary="Read global and tenant kill-switch state",
)
async def read_kill_switch(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> KillSwitchStateResponse:
    _enabled, reasons = await get_kill_switch(session, auth.tenant_id)
    return KillSwitchStateResponse(
        tenant_enabled=any(reason.startswith("tenant:") for reason in reasons),
        global_enabled=any(reason.startswith("global:") for reason in reasons),
        reasons=reasons,
    )


@router.post(
    "/kill-switch",
    response_model=KillSwitchStateResponse,
    summary="Enable or disable writes for the tenant or globally",
)
async def write_kill_switch(
    body: KillSwitchUpdateRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.ADMIN_SETTINGS)),
) -> KillSwitchStateResponse:
    tenant_id = None if body.scope == "global" else auth.tenant_id
    await set_kill_switch(
        session,
        tenant_id=tenant_id,
        scope=body.scope,
        enabled=body.enabled,
        reason=body.reason,
        actor_id=auth.user_id,
    )
    await append_audit(
        session,
        auth=auth,
        action="kill_switch.updated",
        resource_type="kill_switch",
        resource_id=str(tenant_id) if tenant_id else "global",
        metadata={
            "scope": body.scope,
            "enabled": body.enabled,
            "reason": body.reason,
        },
    )
    _enabled, reasons = await get_kill_switch(session, auth.tenant_id)
    return KillSwitchStateResponse(
        tenant_enabled=any(reason.startswith("tenant:") for reason in reasons),
        global_enabled=any(reason.startswith("global:") for reason in reasons),
        reasons=reasons,
    )
