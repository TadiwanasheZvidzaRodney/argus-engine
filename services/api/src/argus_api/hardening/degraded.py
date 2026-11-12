"""Degraded operational modes, circuit breaker states, and read-only fail-safes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from argus_core.events import new_uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.models import DegradedModeModel


async def get_degraded_status(
    session: AsyncSession,
    tenant_id: UUID | None = None,
) -> dict[str, Any]:
    """Return effective degraded mode state (tenant-specific or global fallback)."""
    # Check tenant-specific override first
    if tenant_id:
        tenant_mode = (
            await session.execute(
                select(DegradedModeModel).where(DegradedModeModel.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if tenant_mode:
            return _serialize_mode(tenant_mode)

    # Fall back to global mode (tenant_id IS NULL)
    global_mode = (
        await session.execute(
            select(DegradedModeModel).where(DegradedModeModel.tenant_id.is_(None))
        )
    ).scalar_one_or_none()

    if global_mode:
        return _serialize_mode(global_mode)

    return {
        "read_only": False,
        "live_paused": False,
        "telemetry_paused": False,
        "actions_disabled": False,
        "maintenance_message": None,
        "is_degraded": False,
    }


async def set_degraded_status(
    session: AsyncSession,
    *,
    tenant_id: UUID | None = None,
    read_only: bool = False,
    live_paused: bool = False,
    telemetry_paused: bool = False,
    actions_disabled: bool = False,
    maintenance_message: str | None = None,
    user_id: UUID | None = None,
) -> dict[str, Any]:
    """Set degraded mode flags for a tenant or globally."""
    query = select(DegradedModeModel)
    query = (
        query.where(DegradedModeModel.tenant_id == tenant_id)
        if tenant_id
        else query.where(DegradedModeModel.tenant_id.is_(None))
    )

    now = datetime.now(tz=UTC)
    mode = (await session.execute(query)).scalar_one_or_none()
    if mode is None:
        mode = DegradedModeModel(
            id=new_uuid7(),
            tenant_id=tenant_id,
            read_only=read_only,
            live_paused=live_paused,
            telemetry_paused=telemetry_paused,
            actions_disabled=actions_disabled,
            maintenance_message=maintenance_message,
            updated_by=user_id,
            updated_at=now,
        )
        session.add(mode)
    else:
        mode.read_only = read_only
        mode.live_paused = live_paused
        mode.telemetry_paused = telemetry_paused
        mode.actions_disabled = actions_disabled
        mode.maintenance_message = maintenance_message
        mode.updated_by = user_id
        mode.updated_at = now

    await session.flush()
    return {
        "read_only": read_only,
        "live_paused": live_paused,
        "telemetry_paused": telemetry_paused,
        "actions_disabled": actions_disabled,
        "maintenance_message": maintenance_message,
        "is_degraded": read_only or live_paused or telemetry_paused or actions_disabled,
        "updated_at": now.isoformat(),
    }


def _serialize_mode(m: DegradedModeModel) -> dict[str, Any]:
    is_degraded = m.read_only or m.live_paused or m.telemetry_paused or m.actions_disabled
    return {
        "read_only": m.read_only,
        "live_paused": m.live_paused,
        "telemetry_paused": m.telemetry_paused,
        "actions_disabled": m.actions_disabled,
        "maintenance_message": m.maintenance_message,
        "is_degraded": is_degraded,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }
