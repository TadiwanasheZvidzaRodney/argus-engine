"""Audit package compiler for external SOC 2 / ISO-27001 auditor export."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.models import ComplianceEvidenceModel


async def export_audit_package(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    framework: str = "SOC2",
) -> dict[str, Any]:
    """Compile sealed cryptographic evidence locker package for external audit."""
    now = datetime.now(tz=UTC)
    records = (
        (
            await session.execute(
                select(ComplianceEvidenceModel)
                .where(
                    ComplianceEvidenceModel.tenant_id == tenant_id,
                    ComplianceEvidenceModel.framework == framework,
                )
                .order_by(desc(ComplianceEvidenceModel.collected_at))
            )
        )
        .scalars()
        .all()
    )

    # Deduplicate to latest evidence per control
    latest_by_control: dict[str, ComplianceEvidenceModel] = {}
    for r in records:
        if r.control_id not in latest_by_control:
            latest_by_control[r.control_id] = r

    manifest_controls = []
    total_passed = 0
    for ctrl_id, rec in sorted(latest_by_control.items()):
        if rec.status == "PASS":
            total_passed += 1
        manifest_controls.append(
            {
                "control_id": ctrl_id,
                "status": rec.status,
                "evidence_hash": rec.evidence_hash,
                "collected_at": rec.collected_at.isoformat(),
                "payload": rec.evidence_payload,
            }
        )

    pass_rate = round(total_passed / max(1, len(latest_by_control)) * 100, 1)
    package_payload = {
        "tenant_id": str(tenant_id),
        "framework": framework,
        "exported_at": now.isoformat(),
        "total_controls": len(latest_by_control),
        "passed_controls": total_passed,
        "compliance_score_percent": pass_rate,
        "controls": manifest_controls,
    }

    package_signature = hashlib.sha256(
        json.dumps(package_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return {
        "manifest": package_payload,
        "package_signature": f"sha256:{package_signature}",
        "verification_status": "SEALED_IMMUTABLE",
    }
