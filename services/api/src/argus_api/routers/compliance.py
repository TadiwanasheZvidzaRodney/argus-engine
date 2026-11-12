"""Compliance Frameworks, Cryptographic Evidence Locker, and Audit Export Router."""

from __future__ import annotations

from typing import Any

from argus_core.errors import NotFound
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.compliance.collector import collect_compliance_evidence
from argus_api.compliance.export import export_audit_package
from argus_api.models import ComplianceControlModel, ComplianceEvidenceModel

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


@router.get("/frameworks", summary="List supported compliance frameworks and scores")
async def list_frameworks(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[dict[str, Any]]:
    controls = (await session.execute(select(ComplianceControlModel))).scalars().all()
    framework_names = sorted({c.framework for c in controls})

    # Latest evidence for this tenant
    evidence = (
        (
            await session.execute(
                select(ComplianceEvidenceModel)
                .where(ComplianceEvidenceModel.tenant_id == auth.tenant_id)
                .order_by(desc(ComplianceEvidenceModel.collected_at))
            )
        )
        .scalars()
        .all()
    )

    latest_status: dict[tuple[str, str], str] = {}
    for ev in evidence:
        key = (ev.framework, ev.control_id)
        if key not in latest_status:
            latest_status[key] = ev.status

    results = []
    for fw in framework_names:
        fw_controls = [c for c in controls if c.framework == fw]
        passed = sum(1 for c in fw_controls if latest_status.get((fw, c.control_id)) == "PASS")
        failed = sum(1 for c in fw_controls if latest_status.get((fw, c.control_id)) == "FAIL")
        total = len(fw_controls)
        score = round((passed / max(1, total)) * 100, 1)

        results.append(
            {
                "framework": fw,
                "total_controls": total,
                "passed_controls": passed,
                "failed_controls": failed,
                "compliance_score_percent": score,
                "status": "COMPLIANT" if failed == 0 and passed > 0 else "DEFICIENCIES_DETECTED",
            }
        )

    return results


@router.get("/controls", summary="List controls for a compliance framework")
async def list_controls(
    framework: str = Query(default="SOC2"),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[dict[str, Any]]:
    controls = (
        (
            await session.execute(
                select(ComplianceControlModel).where(ComplianceControlModel.framework == framework)
            )
        )
        .scalars()
        .all()
    )

    # Latest evidence per control
    evidence = (
        (
            await session.execute(
                select(ComplianceEvidenceModel)
                .where(
                    ComplianceEvidenceModel.tenant_id == auth.tenant_id,
                    ComplianceEvidenceModel.framework == framework,
                )
                .order_by(desc(ComplianceEvidenceModel.collected_at))
            )
        )
        .scalars()
        .all()
    )

    evidence_by_ctrl: dict[str, ComplianceEvidenceModel] = {}
    for ev in evidence:
        if ev.control_id not in evidence_by_ctrl:
            evidence_by_ctrl[ev.control_id] = ev

    results = []
    for c in controls:
        evidence_record = evidence_by_ctrl.get(c.control_id)
        results.append(
            {
                "id": str(c.id),
                "framework": c.framework,
                "control_id": c.control_id,
                "title": c.title,
                "description": c.description,
                "domain": c.domain,
                "severity": c.severity,
                "automated": c.automated,
                "rule_mappings": c.rule_mappings,
                "status": evidence_record.status
                if evidence_record is not None
                else "NOT_EVALUATED",
                "evidence_hash": evidence_record.evidence_hash
                if evidence_record is not None
                else None,
                "collected_at": evidence_record.collected_at.isoformat()
                if evidence_record is not None
                else None,
            }
        )
    return results


@router.get("/evidence/{control_id}", summary="Retrieve sealed evidence for a control")
async def get_control_evidence(
    control_id: str,
    framework: str = Query(default="SOC2"),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    ev = (
        await session.execute(
            select(ComplianceEvidenceModel)
            .where(
                ComplianceEvidenceModel.tenant_id == auth.tenant_id,
                ComplianceEvidenceModel.framework == framework,
                ComplianceEvidenceModel.control_id == control_id,
            )
            .order_by(desc(ComplianceEvidenceModel.collected_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    if ev is None:
        raise NotFound(f"No evidence collected for control {control_id!r} in {framework!r}.")

    return {
        "id": str(ev.id),
        "framework": ev.framework,
        "control_id": ev.control_id,
        "status": ev.status,
        "evidence_hash": ev.evidence_hash,
        "payload": ev.evidence_payload,
        "collected_at": ev.collected_at.isoformat(),
        "expires_at": ev.expires_at.isoformat(),
    }


@router.post("/collect", summary="Trigger automated compliance evidence collection")
async def trigger_collection(
    framework: str | None = Query(default=None),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> list[dict[str, Any]]:
    return await collect_compliance_evidence(session, tenant_id=auth.tenant_id, framework=framework)


@router.get("/export", summary="Export cryptographically signed audit package")
async def export_audit(
    framework: str = Query(default="SOC2"),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    return await export_audit_package(session, tenant_id=auth.tenant_id, framework=framework)
