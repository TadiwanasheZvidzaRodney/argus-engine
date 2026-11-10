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
