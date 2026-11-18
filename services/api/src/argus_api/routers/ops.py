"""Operations Wallboard, Alert Hub, and Escalation Router."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.models import OpsAlertModel
from argus_api.ops.mailer import send_ops_email
from argus_api.ops.service import (
    acknowledge_alert,
    build_ops_wallboard,
    resolve_alert,
    trigger_ops_alert,
)
from argus_api.routers.sync import _get_graph_repo

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])


class TriggerAlertRequest(BaseModel):
    alert_key: str = Field(min_length=3, max_length=255)
    title: str = Field(min_length=3, max_length=512)
    description: str = Field(min_length=3)
    source: str = Field(default="ecs", max_length=64)
    severity: str = Field(default="warning", max_length=16)
    resource_id: str | None = Field(default=None, max_length=2048)
    requires_action: bool = True
    notification_email: str = Field(default="devops@zimworx.com", max_length=255)


class TestEmailRequest(BaseModel):
    to_email: str = Field(default="devops@zimworx.com", max_length=255)
    subject: str = Field(default="[TEST ALERT] Argus Engine Notification Hub")
    message: str = Field(
        default="This is a test notification from the Argus Engine Operations Hub."
    )


@router.get("/wallboard", summary="Operations Wallboard aggregated telemetry and alerts")
async def get_wallboard(
    request: Request,
    range: str = Query(default="today", pattern="^(today|24h|7d|30d)$"),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    repo = _get_graph_repo(request)
    return await build_ops_wallboard(session, auth.tenant_id, repo, time_range=range)


@router.get("/alerts", summary="List operational alerts")
async def list_alerts(
    status: str | None = Query(default=None),
    requires_action: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[dict[str, Any]]:
    query = select(OpsAlertModel).where(OpsAlertModel.tenant_id == auth.tenant_id)
    if status:
        query = query.where(OpsAlertModel.status == status)
    if requires_action is not None:
        query = query.where(OpsAlertModel.requires_action == requires_action)
    query = query.order_by(desc(OpsAlertModel.created_at))

    rows = (await session.execute(query)).scalars().all()
    return [
        {
            "id": str(r.id),
            "alert_key": r.alert_key,
            "severity": r.severity,
            "title": r.title,
            "description": r.description,
            "source": r.source,
            "resource_id": r.resource_id,
            "status": r.status,
            "requires_action": r.requires_action,
            "notification_count": r.notification_count,
            "notification_email": r.notification_email,
            "last_notified_at": r.last_notified_at.isoformat(),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/alerts", status_code=201, summary="Trigger or upsert an operational alert")
async def create_alert(
    body: TriggerAlertRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    alert = await trigger_ops_alert(
        session,
        tenant_id=auth.tenant_id,
        alert_key=body.alert_key,
        title=body.title,
        description=body.description,
        source=body.source,
        severity=body.severity,
        resource_id=body.resource_id,
        requires_action=body.requires_action,
        notification_email=body.notification_email,
    )
    return {
        "id": str(alert.id),
        "status": alert.status,
        "notification_count": alert.notification_count,
        "title": alert.title,
    }


@router.post("/alerts/{alert_id}/ack", summary="Acknowledge alert and snooze repeated emails")
async def ack_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> dict[str, Any]:
    alert = await acknowledge_alert(session, auth.tenant_id, alert_id, user_id=auth.user_id)
    return {"id": str(alert.id), "status": alert.status, "acknowledged_at": alert.acknowledged_at}


@router.post("/alerts/{alert_id}/resolve", summary="Resolve alert and send resolution notice")
async def res_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.REQUEST_ACTION)),
) -> dict[str, Any]:
    alert = await resolve_alert(session, auth.tenant_id, alert_id)
    return {"id": str(alert.id), "status": alert.status, "resolved_at": alert.resolved_at}


@router.post("/alerts/test-email", summary="Send test alert email to verify delivery")
async def send_test_email(
    body: TestEmailRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    settings = request.app.state.settings
    success, err = send_ops_email(
        to_email=body.to_email,
        subject=body.subject,
        text_content=body.message,
    )
    is_mailpit = settings.smtp_host in ("127.0.0.1", "localhost") and settings.smtp_port == 1025
    return {
        "success": success,
        "to_email": body.to_email,
        "mode": "mailpit" if is_mailpit else "smtp",
        "detail": err or ("Captured in local Mailpit" if is_mailpit else "Delivered via SMTP"),
    }
