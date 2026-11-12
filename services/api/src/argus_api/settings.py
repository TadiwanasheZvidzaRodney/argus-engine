from __future__ import annotations

from typing import Literal

from argus_core.settings import Settings
from pydantic import Field


class ApiSettings(Settings):
    """API-specific settings layered on the shared contract."""

    service_name: str = "argus-api"
    host: str = "0.0.0.0"  # noqa: S104 - bind-all is correct inside a container
    port: int = 8000
    root_path: str = ""
    docs_enabled: bool = True
    document_public_api: bool = False
    max_request_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    rate_limit_per_minute: int = 600
    log_format: Literal["json", "console"] = "json"
    # Instance-wide kill switch. Per-tenant switches are stored in PostgreSQL.
    writes_enabled: bool = True
    # Phase 7 telemetry quotas and cost controls.
    telemetry_daily_metric_budget: int = Field(default=100_000, ge=1)
    telemetry_max_resources_per_subscription: int = Field(default=500, ge=1)
    telemetry_max_metrics_per_resource: int = Field(default=6, ge=1)
    telemetry_max_subscriptions_per_user: int = Field(default=20, ge=1)
    telemetry_subscription_ttl_seconds: int = Field(default=900, ge=30)
    telemetry_degraded_resolution_seconds: int = Field(default=300, ge=60)
    telemetry_cache_ttl_seconds: int = Field(default=60, ge=1)
    telemetry_cost_per_metric_usd: float = Field(default=0.00001, ge=0)
    telemetry_sse_keepalive_seconds: int = Field(default=15, ge=5)
