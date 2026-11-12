"""Automated compliance evidence collection and cryptographic hashing."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from argus_core.events import new_uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.models import (
    ComplianceControlModel,
    ComplianceEvidenceModel,
    FindingModel,
)


def compute_evidence_hash(payload: dict[str, Any]) -> str:
    """Deterministic SHA-256 hash over sorted JSON evidence."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def collect_compliance_evidence(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    framework: str | None = None,
) -> list[dict[str, Any]]:
    """Scan security posture and seal cryptographic evidence for each compliance control."""
    now = datetime.now(tz=UTC)
    query = select(ComplianceControlModel)
    if framework:
        query = query.where(ComplianceControlModel.framework == framework)
    controls = (await session.execute(query)).scalars().all()

    # Load active findings for tenant
    findings_query = await session.execute(
        select(FindingModel).where(
            FindingModel.tenant_id == tenant_id,
            FindingModel.status.in_(["OPEN", "ACKNOWLEDGED"]),
        )
    )
    active_findings = findings_query.scalars().all()

    evidence_records: list[dict[str, Any]] = []

    for ctrl in controls:
        rule_ids = set(ctrl.rule_mappings or [])
        mapped_findings = [f for f in active_findings if f.rule_id in rule_ids]

        if not mapped_findings:
            status = "PASS"
        elif any(f.severity in ("critical", "high") for f in mapped_findings):
            status = "FAIL"
        else:
            status = "WARN"

        evidence_payload = {
            "control_id": ctrl.control_id,
            "framework": ctrl.framework,
            "title": ctrl.title,
            "domain": ctrl.domain,
            "status": status,
            "timestamp": now.isoformat(),
            "tenant_id": str(tenant_id),
            "findings_evaluated": len(rule_ids),
            "open_defects": [
                {
                    "finding_id": str(f.id),
                    "rule_id": f.rule_id,
                    "severity": f.severity,
                    "resource_id": f.resource_id,
                    "evidence_hash": f.evidence_hash,
                }
                for f in mapped_findings
            ],
        }

        evidence_hash = compute_evidence_hash(evidence_payload)

        record = ComplianceEvidenceModel(
            id=new_uuid7(),
            tenant_id=tenant_id,
            framework=ctrl.framework,
            control_id=ctrl.control_id,
            status=status,
            evidence_payload=evidence_payload,
            evidence_hash=evidence_hash,
            collected_at=now,
            expires_at=now + timedelta(days=90),
        )
        session.add(record)
        evidence_records.append(
            {
                "control_id": ctrl.control_id,
                "framework": ctrl.framework,
                "status": status,
                "evidence_hash": evidence_hash,
                "collected_at": now.isoformat(),
                "defects_count": len(mapped_findings),
            }
        )

    await session.flush()
    return evidence_records
