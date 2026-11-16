"""Dynamic Tenant Settings and Alert Notification Preferences Router."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.models import Tenant, TenantSettingModel

router = APIRouter(prefix="/api/v1/settings/tenant", tags=["settings"])


class TenantSettingsUpdateRequest(BaseModel):
    alert_email: str = Field(
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        max_length=255,
        description="Email address receiving operational and security alerts",
    )
    alert_repeat_minutes: int = Field(
        default=30, ge=5, le=1440, description="Escalation repeat interval"
    )
    alert_slack_webhook: str | None = Field(default=None, max_length=512)
    default_region: str = Field(default="us-west-2", max_length=32)


@router.get("", summary="Get dynamic tenant configuration and alert preferences")
async def get_tenant_settings(
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    # 1. Load tenant info
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    ).scalar_one_or_none()

    # 2. Load tenant settings
    settings_row = (
        await session.execute(
            select(TenantSettingModel).where(TenantSettingModel.tenant_id == auth.tenant_id)
        )
    ).scalar_one_or_none()

    default_email = getattr(request.app.state.settings, "default_alert_email", "devops@zimworx.com")

    if settings_row is None:
        # Lazy create default row
        settings_row = TenantSettingModel(
            tenant_id=auth.tenant_id,
            alert_email=default_email,
            alert_repeat_minutes=30,
            default_region="us-west-2",
        )
        session.add(settings_row)
        await session.flush()

    return {
        "tenant_id": f"tnt_{auth.tenant_id}",
        "tenant_name": tenant.name if tenant else "Tenant",
        "slug": tenant.slug if tenant else "default",
        "plan": tenant.plan if tenant else "enterprise",
        "alert_email": settings_row.alert_email,
        "alert_repeat_minutes": settings_row.alert_repeat_minutes,
        "alert_slack_webhook": settings_row.alert_slack_webhook,
        "default_region": settings_row.default_region,
        "updated_at": settings_row.updated_at.isoformat() if settings_row.updated_at else None,
    }


@router.put("", summary="Update dynamic tenant alert and operational settings")
async def update_tenant_settings(
    body: TenantSettingsUpdateRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    settings_row = (
        await session.execute(
            select(TenantSettingModel).where(TenantSettingModel.tenant_id == auth.tenant_id)
        )
    ).scalar_one_or_none()

    if settings_row is None:
        settings_row = TenantSettingModel(
            tenant_id=auth.tenant_id,
            alert_email=body.alert_email,
            alert_repeat_minutes=body.alert_repeat_minutes,
            alert_slack_webhook=body.alert_slack_webhook,
            default_region=body.default_region,
            updated_at=now,
        )
        session.add(settings_row)
    else:
        settings_row.alert_email = body.alert_email
        settings_row.alert_repeat_minutes = body.alert_repeat_minutes
        settings_row.alert_slack_webhook = body.alert_slack_webhook
        settings_row.default_region = body.default_region
        settings_row.updated_at = now

    await session.flush()

    return {
        "tenant_id": f"tnt_{auth.tenant_id}",
        "alert_email": settings_row.alert_email,
        "alert_repeat_minutes": settings_row.alert_repeat_minutes,
        "alert_slack_webhook": settings_row.alert_slack_webhook,
        "default_region": settings_row.default_region,
        "updated_at": now.isoformat(),
    }
