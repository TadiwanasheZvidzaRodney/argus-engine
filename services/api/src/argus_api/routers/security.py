"""Security dashboard, scan triggers, overlay, and attack-path API."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from argus_core.events import new_uuid7
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.models import AttackPathCacheModel, FindingModel
from argus_api.routers.sync import _get_graph_repo
from argus_api.security.attack_paths import compute_attack_paths
from argus_api.security.engine import run_security_scan
from argus_api.security.materialize import materialize_security_graph
from argus_api.security.rules import (
    RULES,
    SENSITIVE_TYPES,
    SecurityGraph,
    iter_ingress_rules,
)

router = APIRouter(prefix="/api/v1/security", tags=["security"])

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class ScanRequest(BaseModel):
    accounts: list[str] | None = None
    regions: list[str] | None = None
    materialize: bool = True


class ScanResponse(BaseModel):
    scan_id: str
    rules_evaluated: int
    hits: int
    created: int
    updated: int
    reopened: int
    resolved: int
    suppressed: int


class AttackPathRequest(BaseModel):
    source: str = Field(default="internet", max_length=64)
    target_types: list[str] | None = None
    max_depth: int = Field(default=8, ge=1, le=8)
    limit: int = Field(default=25, ge=1, le=100)
    accounts: list[str] | None = None
    regions: list[str] | None = None


class RuleResponse(BaseModel):
    id: str
    version: str
    severity: str
    title: str
    description: str
    resource_types: list[str]
    remediation_action: str | None
    references: list[str]
    definition_hash: str


async def _load_graph(
    request: Request,
    auth: AuthContext,
    accounts: list[str] | None = None,
    regions: list[str] | None = None,
) -> SecurityGraph:
    repo = _get_graph_repo(request)
    payload = await repo.load_security_subgraph(
        f"tnt_{auth.tenant_id}", accounts=accounts, regions=regions
    )
    return SecurityGraph(payload["nodes"], payload["edges"])


@router.get("/summary", summary="Security posture summary")
async def security_summary(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    rows = (
        (
            await session.execute(
                select(FindingModel).where(FindingModel.tenant_id == auth.tenant_id)
            )
        )
        .scalars()
        .all()
    )
    by_severity: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_account: dict[str, int] = {}
    by_region: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    open_by_severity: dict[str, int] = {}
    trend: dict[str, dict[str, int]] = {}

    now = datetime.now(tz=UTC)
    for offset in range(13, -1, -1):
        day = (now - timedelta(days=offset)).date().isoformat()
        trend[day] = {"opened": 0, "resolved": 0}

    for row in rows:
        by_severity[row.severity] = by_severity.get(row.severity, 0) + 1
        by_status[row.status] = by_status.get(row.status, 0) + 1
        by_rule[row.rule_id] = by_rule.get(row.rule_id, 0) + 1
        if row.account_id:
            by_account[row.account_id] = by_account.get(row.account_id, 0) + 1
        if row.region:
            by_region[row.region] = by_region.get(row.region, 0) + 1
        if row.status in {"OPEN", "ACKNOWLEDGED"}:
            open_by_severity[row.severity] = open_by_severity.get(row.severity, 0) + 1
        opened_day = row.first_seen.date().isoformat()
        if opened_day in trend:
            trend[opened_day]["opened"] += 1
        if row.resolved_at:
            resolved_day = row.resolved_at.date().isoformat()
            if resolved_day in trend:
                trend[resolved_day]["resolved"] += 1

    top_rows = sorted(
        (row for row in rows if row.status in {"OPEN", "ACKNOWLEDGED"}),
        key=lambda row: (-SEVERITY_RANK.get(row.severity, 0), row.first_seen),
    )[:10]

    return {
        "total": len(rows),
        "open_total": sum(open_by_severity.values()),
        "by_severity": by_severity,
        "open_by_severity": open_by_severity,
        "by_status": by_status,
        "by_account": by_account,
        "by_region": by_region,
        "by_rule": by_rule,
        "trend": [{"date": day, **counts} for day, counts in sorted(trend.items())],
        "top_risks": [
            {
                "id": str(row.id),
                "rule_id": row.rule_id,
                "severity": row.severity,
                "status": row.status,
                "title": row.title,
                "resource_id": row.resource_id,
                "first_seen": row.first_seen.isoformat(),
            }
            for row in top_rows
        ],
    }


@router.get("/rules", response_model=list[RuleResponse], summary="Security rule catalog")
async def security_rules(
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[RuleResponse]:
    return [
        RuleResponse(
            id=rule.id,
            version=rule.version,
            severity=rule.severity,
            title=rule.title,
            description=rule.description,
            resource_types=list(rule.resource_types),
            remediation_action=rule.remediation_action,
            references=list(rule.references),
            definition_hash=rule.definition_hash,
        )
        for rule in RULES
    ]


@router.get("/overlay", summary="Node security overlay")
async def security_overlay(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    rows = (
        (
            await session.execute(
                select(FindingModel).where(
                    FindingModel.tenant_id == auth.tenant_id,
                    FindingModel.status.in_(["OPEN", "ACKNOWLEDGED", "RISK_ACCEPTED"]),
                )
            )
        )
        .scalars()
        .all()
    )
    resources: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = resources.setdefault(
            row.resource_id,
            {
                "resource_id": row.resource_id,
                "max_severity": "low",
                "open_count": 0,
                "rule_ids": [],
                "statuses": [],
            },
        )
        entry["open_count"] += 1
        if SEVERITY_RANK.get(row.severity, 0) > SEVERITY_RANK.get(entry["max_severity"], 0):
            entry["max_severity"] = row.severity
        if row.rule_id not in entry["rule_ids"]:
            entry["rule_ids"].append(row.rule_id)
        if row.status not in entry["statuses"]:
            entry["statuses"].append(row.status)
    return {
        "resources": resources,
        "counts": {
            "resources_with_findings": len(resources),
            "findings": len(rows),
        },
    }


@router.post("/scan", response_model=ScanResponse, summary="Trigger a security scan")
async def trigger_scan(
    body: ScanRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> ScanResponse:
    graph = await _load_graph(request, auth, body.accounts, body.regions)
    if body.materialize:
        repo = _get_graph_repo(request)
        await materialize_security_graph(repo, f"tnt_{auth.tenant_id}", graph)
    result = await run_security_scan(
        session,
        tenant_id=auth.tenant_id,
        graph=graph,
        actor_id=auth.user_id,
        scan_id=new_uuid7(),
        scope_accounts=body.accounts,
        scope_regions=body.regions,
    )
    return ScanResponse(
        scan_id=result.scan_id,
        rules_evaluated=result.rules_evaluated,
        hits=result.hits,
        created=result.created,
        updated=result.updated,
        reopened=result.reopened,
        resolved=result.resolved,
        suppressed=result.suppressed,
    )


@router.post("/attack-paths", summary="Compute ranked internet attack paths")
async def attack_paths(
    body: AttackPathRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    target_types = body.target_types or sorted(SENSITIVE_TYPES)
    cache_payload = {
        "target_types": sorted(target_types),
        "max_depth": body.max_depth,
        "limit": body.limit,
        "accounts": sorted(body.accounts or []),
        "regions": sorted(body.regions or []),
    }
    query_hash = hashlib.sha256(
        json.dumps(cache_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    repo = _get_graph_repo(request)
    tenant_key = f"tnt_{auth.tenant_id}"
    summary = await repo.count_summary(tenant_key)
    graph_version = int(summary["nodes"]) * 100_000 + int(summary["edges"])
    now = datetime.now(tz=UTC)

    cached = (
        await session.execute(
            select(AttackPathCacheModel).where(
                AttackPathCacheModel.tenant_id == auth.tenant_id,
                AttackPathCacheModel.query_hash == query_hash,
            )
        )
    ).scalar_one_or_none()
    if cached is not None and cached.expires_at > now and cached.graph_version == graph_version:
        return {**cached.result, "cached": True}

    graph = await _load_graph(request, auth, body.accounts, body.regions)
    result = compute_attack_paths(
        graph,
        target_types=target_types,
        max_depth=body.max_depth,
        limit=body.limit,
        accounts=body.accounts,
        regions=body.regions,
    ).to_dict()

    if cached is None:
        session.add(
            AttackPathCacheModel(
                id=new_uuid7(),
                tenant_id=auth.tenant_id,
                query_hash=query_hash,
                graph_version=graph_version,
                result=result,
                expires_at=now + timedelta(minutes=2),
            )
        )
    else:
        cached.graph_version = graph_version
        cached.result = result
        cached.expires_at = now + timedelta(minutes=2)
    await session.flush()
    return {**result, "cached": False}


@router.get("/exposures", summary="Internet-exposed resources")
async def security_exposures(
    request: Request,
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    graph = await _load_graph(request, auth)
    exposed: list[dict[str, Any]] = []
    for node in graph.nodes:
        if node.get("type") != "AWS::EC2::SecurityGroup":
            continue
        for ingress in iter_ingress_rules(node):
            if ingress["cidr"] not in {"0.0.0.0/0", "::/0"}:
                continue
            exposed.append(
                {
                    "resource_id": node.get("id"),
                    "name": node.get("name"),
                    "account_id": node.get("account_id"),
                    "region": node.get("region"),
                    "cidr": ingress["cidr"],
                    "port": ingress["from_port"],
                    "protocol": ingress["protocol"],
                }
            )
    unique = {item["resource_id"]: item for item in exposed}
    return {"exposures": list(unique.values()), "count": len(unique)}


__all__ = ["router"]
