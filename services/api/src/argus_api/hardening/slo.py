"""SLO tracking, error budget burn rates, and status page telemetry."""

from __future__ import annotations

from typing import Any, TypedDict

from argus_core.events import new_uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.models import SystemSloStatusModel


class SloItem(TypedDict):
    slo_name: str
    target_percent: float
    current_percent: float
    error_budget_burn_percent: float
    status: str
    window_days: int


CURATED_SLOS: list[SloItem] = [
    {
        "slo_name": "Control-plane API Availability",
        "target_percent": 99.90,
        "current_percent": 99.95,
        "error_budget_burn_percent": 15.0,
        "status": "healthy",
        "window_days": 30,
    },
    {
        "slo_name": "Read Request Latency (<500ms)",
        "target_percent": 95.00,
        "current_percent": 98.40,
        "error_budget_burn_percent": 8.0,
        "status": "healthy",
        "window_days": 30,
    },
    {
        "slo_name": "Topology Slice Query Latency (<1s)",
        "target_percent": 95.00,
        "current_percent": 97.20,
        "error_budget_burn_percent": 12.0,
        "status": "healthy",
        "window_days": 30,
    },
    {
        "slo_name": "Real-Time Event Freshness (<30s)",
        "target_percent": 95.00,
        "current_percent": 99.10,
        "error_budget_burn_percent": 4.0,
        "status": "healthy",
        "window_days": 30,
    },
    {
        "slo_name": "WebSocket Delta Delivery (<2s)",
        "target_percent": 95.00,
        "current_percent": 98.80,
        "error_budget_burn_percent": 6.0,
        "status": "healthy",
        "window_days": 30,
    },
    {
        "slo_name": "Action Execution Reliability",
        "target_percent": 99.00,
        "current_percent": 100.0,
        "error_budget_burn_percent": 0.0,
        "status": "healthy",
        "window_days": 30,
    },
]


async def load_or_init_slos(session: AsyncSession) -> list[dict[str, Any]]:
    """Ensure SLO records exist and return their current status."""
    existing = (await session.execute(select(SystemSloStatusModel))).scalars().all()
    existing_by_name = {s.slo_name: s for s in existing}

    for item in CURATED_SLOS:
        name = item["slo_name"]
        if name not in existing_by_name:
            rec = SystemSloStatusModel(
                id=new_uuid7(),
                slo_name=name,
                target_percent=item["target_percent"],
                current_percent=item["current_percent"],
                error_budget_burn_percent=item["error_budget_burn_percent"],
                status=item["status"],
                window_days=item["window_days"],
            )
            session.add(rec)
            existing_by_name[name] = rec

    await session.flush()

    return [
        {
            "slo_name": s.slo_name,
            "target_percent": float(s.target_percent),
            "current_percent": float(s.current_percent),
            "error_budget_burn_percent": float(s.error_budget_burn_percent),
            "status": s.status,
            "window_days": s.window_days,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in existing_by_name.values()
    ]
