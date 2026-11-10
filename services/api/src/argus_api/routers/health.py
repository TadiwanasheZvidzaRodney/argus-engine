"""Health endpoints.

``/healthz`` is liveness and never touches a dependency. ``/readyz`` is
readiness and fails closed when a dependency check fails.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from argus_core.health import Check, CheckState, HealthReport, build_report, liveness_report
from argus_core.settings import Settings
from fastapi import APIRouter, Response

CheckProvider = Callable[[], Sequence[Check]]


def build_health_router(settings: Settings, checks: CheckProvider) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/healthz", response_model=HealthReport, summary="Liveness probe")
    async def healthz() -> HealthReport:
        return await liveness_report(settings)

    @router.get(
        "/readyz",
        response_model=HealthReport,
        responses={503: {"model": HealthReport, "description": "A dependency is unavailable"}},
        summary="Readiness probe",
    )
    async def readyz(response: Response) -> HealthReport:
        report = await build_report(settings, checks())
        if report.status is CheckState.FAIL:
            response.status_code = 503
        return report

    return router
