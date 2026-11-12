"""Finding lifecycle engine: evaluate rules, deduplicate, reopen, and resolve."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from argus_core.events import new_uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.models import (
    FindingEventModel,
    FindingModel,
    FindingSuppressionModel,
    SecurityRuleVersionModel,
)
from argus_api.security.rules import RULES, Rule, SecurityGraph, evaluate_rules

ACTIVE_STATUSES = frozenset({"OPEN", "ACKNOWLEDGED", "RISK_ACCEPTED", "SUPPRESSED"})
TERMINAL_STATUSES = frozenset({"RESOLVED"})


@dataclass
class ScanResult:
    scan_id: str
    rules_evaluated: int
    hits: int
    created: int = 0
    updated: int = 0
    reopened: int = 0
    resolved: int = 0
    suppressed: int = 0
    findings: list[dict[str, Any]] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def sync_rule_versions(session: AsyncSession, rules: Iterable[Rule] = RULES) -> None:
    result = await session.execute(select(SecurityRuleVersionModel))
    existing = {(row.rule_id, row.version) for row in result.scalars().all()}
    for rule in rules:
        if (rule.id, rule.version) in existing:
            continue
        session.add(
            SecurityRuleVersionModel(
                id=new_uuid7(),
                rule_id=rule.id,
                version=rule.version,
                definition_hash=rule.definition_hash,
                changelog=rule.changelog or "Initial curated rule.",
                enabled=True,
            )
        )
    await session.flush()


async def _active_suppressions(
    session: AsyncSession, tenant_id: UUID, finding_ids: Sequence[UUID]
) -> set[UUID]:
    if not finding_ids:
        return set()
    now = _now()
    result = await session.execute(
        select(FindingSuppressionModel.finding_id).where(
            FindingSuppressionModel.tenant_id == tenant_id,
            FindingSuppressionModel.finding_id.in_(finding_ids),
            FindingSuppressionModel.expires_at > now,
            FindingSuppressionModel.revoked_at.is_(None),
        )
    )
    return set(result.scalars().all())


def _append_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    finding_id: UUID,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    actor_id: UUID | None = None,
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


async def run_security_scan(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    graph: SecurityGraph,
    rules: Iterable[Rule] = RULES,
    actor_id: UUID | None = None,
    scan_id: UUID | None = None,
    scope_accounts: Sequence[str] | None = None,
    scope_regions: Sequence[str] | None = None,
) -> ScanResult:
    """Evaluate rules and reconcile findings for the tenant's current graph."""
    rule_list = list(rules)
    scan_id = scan_id or new_uuid7()
    now = _now()

    await sync_rule_versions(session, rule_list)
    hits = evaluate_rules(graph, rule_list)

    existing_result = await session.execute(
        select(FindingModel).where(
            FindingModel.tenant_id == tenant_id,
            FindingModel.rule_id.in_([rule.id for rule in rule_list]),
        )
    )
    existing = {
        (row.rule_id, row.resource_id, row.finding_key): row
        for row in existing_result.scalars().all()
    }
    suppressed_ids = await _active_suppressions(
        session, tenant_id, [row.id for row in existing.values()]
    )

    result = ScanResult(
        scan_id=str(scan_id),
        rules_evaluated=len(rule_list),
        hits=len(hits),
    )
    seen: set[tuple[str, str, str]] = set()

    for hit in hits:
        key = (hit.rule_id, hit.resource_id, hit.finding_key)
        seen.add(key)
        finding = existing.get(key)
        if finding is None:
            finding = FindingModel(
                id=new_uuid7(),
                tenant_id=tenant_id,
                rule_id=hit.rule_id,
                rule_version=hit.rule_version,
                severity=hit.severity,
                status="OPEN",
                title=hit.title,
                description=hit.description,
                resource_id=hit.resource_id,
                resource_type=hit.resource_type,
                account_id=hit.account_id,
                region=hit.region,
                finding_key=hit.finding_key,
                evidence=hit.evidence,
                evidence_hash=hit.evidence_hash,
                remediation_action=hit.remediation_action,
                first_seen=now,
                last_seen=now,
                last_scan_id=scan_id,
            )
            session.add(finding)
            await session.flush()
            _append_event(
                session,
                tenant_id=tenant_id,
                finding_id=finding.id,
                event_type="opened",
                from_status=None,
                to_status="OPEN",
                actor_id=actor_id,
                metadata={"scan_id": str(scan_id), "rule_version": hit.rule_version},
            )
            result.created += 1
            result.findings.append(_finding_summary(finding))
            continue

        previous_status = finding.status
        previous_hash = finding.evidence_hash
        evidence_changed = previous_hash != hit.evidence_hash
        next_status = previous_status
        event_type: str | None = None
        event_metadata: dict[str, Any] = {"scan_id": str(scan_id)}

        if previous_status == "RISK_ACCEPTED" and (
            finding.risk_accepted_until is None or finding.risk_accepted_until <= now
        ):
            next_status = "OPEN"
            event_type = "risk_acceptance_expired"

        if finding.id in suppressed_ids:
            next_status = "SUPPRESSED"
        elif previous_status == "SUPPRESSED" and finding.id not in suppressed_ids:
            next_status = "OPEN"
            event_type = "suppression_expired"

        if evidence_changed and previous_status in TERMINAL_STATUSES | {"SUPPRESSED"}:
            next_status = "OPEN"
            event_type = "reopened"
            event_metadata["previous_evidence_hash"] = previous_hash
        elif evidence_changed and event_type is None:
            event_type = "evidence_changed"
            event_metadata["previous_evidence_hash"] = previous_hash

        finding.rule_version = hit.rule_version
        finding.severity = hit.severity
        finding.title = hit.title
        finding.description = hit.description
        finding.resource_type = hit.resource_type
        finding.account_id = hit.account_id
        finding.region = hit.region
        finding.evidence = hit.evidence
        finding.evidence_hash = hit.evidence_hash
        finding.remediation_action = hit.remediation_action
        finding.last_seen = now
        finding.last_scan_id = scan_id
        finding.status = next_status
        if next_status == "RESOLVED":
            finding.resolved_at = now
        elif next_status in {"OPEN", "ACKNOWLEDGED"}:
            finding.resolved_at = None

        if event_type is not None:
            _append_event(
                session,
                tenant_id=tenant_id,
                finding_id=finding.id,
                event_type=event_type,
                from_status=previous_status,
                to_status=next_status,
                actor_id=actor_id,
                metadata=event_metadata,
            )
            if event_type == "reopened":
                result.reopened += 1
        result.updated += 1
        result.findings.append(_finding_summary(finding))

    # Resolve findings that were previously active but are no longer present.
    for key, finding in existing.items():
        if key in seen:
            continue
        if finding.status not in ACTIVE_STATUSES:
            continue
        if scope_accounts and finding.account_id not in set(scope_accounts):
            continue
        if scope_regions and finding.region not in set(scope_regions):
            continue
        previous_status = finding.status
        finding.status = "RESOLVED"
        finding.resolved_at = now
        finding.last_scan_id = scan_id
        _append_event(
            session,
            tenant_id=tenant_id,
            finding_id=finding.id,
            event_type="resolved",
            from_status=previous_status,
            to_status="RESOLVED",
            actor_id=actor_id,
            metadata={"scan_id": str(scan_id), "reason": "not-observed"},
        )
        result.resolved += 1

    await session.flush()
    result.suppressed = sum(1 for item in result.findings if item["status"] == "SUPPRESSED")
    return result


def _finding_summary(finding: FindingModel) -> dict[str, Any]:
    return {
        "id": str(finding.id),
        "rule_id": finding.rule_id,
        "resource_id": finding.resource_id,
        "severity": finding.severity,
        "status": finding.status,
    }


async def latest_scan_summary(session: AsyncSession, tenant_id: UUID) -> dict[str, Any]:
    result = await session.execute(select(FindingModel).where(FindingModel.tenant_id == tenant_id))
    rows = result.scalars().all()
    by_severity: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for row in rows:
        by_severity[row.severity] = by_severity.get(row.severity, 0) + 1
        by_status[row.status] = by_status.get(row.status, 0) + 1
    return {
        "total": len(rows),
        "by_severity": by_severity,
        "by_status": by_status,
    }


__all__ = [
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "ScanResult",
    "latest_scan_summary",
    "run_security_scan",
    "sync_rule_versions",
]
