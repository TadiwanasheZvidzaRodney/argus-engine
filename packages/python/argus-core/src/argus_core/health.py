"""Health and readiness report shapes.

Liveness must never touch dependencies (a Redis blip should not restart the
fleet); readiness must. Both share this report so dashboards and alerts parse
one schema.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from argus_core.settings import Settings


class CheckState(StrEnum):
    OK = "ok"
    FAIL = "fail"
    SKIPPED = "skipped"


class CheckResult(BaseModel):
    name: str
    state: CheckState
    latency_ms: float | None = None
    detail: str | None = None


class HealthReport(BaseModel):
    status: CheckState
    service: str
    version: str
    commit: str
    env: str
    checks: list[CheckResult] = Field(default_factory=list)
    time: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


Check = Callable[[], Awaitable[CheckResult]]


async def run_check(name: str, probe: Callable[[], Awaitable[None]]) -> CheckResult:
    started = time.perf_counter()
    try:
        await probe()
    except Exception as exc:
        return CheckResult(
            name=name,
            state=CheckState.FAIL,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            detail=type(exc).__name__,
        )
    return CheckResult(
        name=name,
        state=CheckState.OK,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )


async def build_report(settings: Settings, checks: Sequence[Check]) -> HealthReport:
    results = [await check() for check in checks]
    status = CheckState.FAIL if any(r.state is CheckState.FAIL for r in results) else CheckState.OK
    return HealthReport(
        status=status,
        service=settings.service_name,
        version=settings.service_version,
        commit=settings.commit_sha,
        env=settings.env.value,
        checks=results,
    )


async def liveness_report(settings: Settings) -> HealthReport:
    """No dependency checks: if the event loop can answer, the process is alive."""
    return HealthReport(
        status=CheckState.OK,
        service=settings.service_name,
        version=settings.service_version,
        commit=settings.commit_sha,
        env=settings.env.value,
    )
