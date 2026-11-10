"""Typed, environment-driven configuration shared by every service."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_CURSOR_SECRET = "local-dev-cursor-secret-change-me"  # noqa: S105
_DEV_NEO4J_PASSWORD = "argus-local-password"  # noqa: S105


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"

    @property
    def is_production_like(self) -> bool:
        return self in (Environment.STAGING, Environment.PROD)


class Settings(BaseSettings):
    """Runtime settings. Every field is overridable via an ``ARGUS_`` env var."""

    model_config = SettingsConfigDict(
        env_prefix="ARGUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    # Identity of the running service; injected at build time.
    service_name: str = "argus-api"
    service_version: str = "0.1.0"
    commit_sha: str = "dev"
    env: Environment = Environment.LOCAL
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # Tenancy + auth
    auth_mode: Literal["stub", "oidc"] = "stub"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    default_tenant_id: str | None = None

    # HTTP
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    max_page_size: int = 200
    default_page_size: int = 50

    # Data stores
    database_url: str = "postgresql+asyncpg://argus:argus@localhost:5432/argus"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr(_DEV_NEO4J_PASSWORD)
    redis_url: str = "redis://localhost:6379/0"
    queue_url: str = "redis://localhost:6379/1"

    # Request integrity
    cursor_secret: SecretStr = SecretStr(_DEV_CURSOR_SECRET)
    idempotency_ttl_seconds: int = 86_400
    idempotency_lock_seconds: int = 30

    # AWS
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None

    # Observability
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None
    otel_sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    sentry_dsn: str | None = None

    @model_validator(mode="after")
    def _reject_dev_secrets_in_production(self) -> Settings:
        if not self.env.is_production_like:
            return self
        problems: list[str] = []
        if self.cursor_secret.get_secret_value() == _DEV_CURSOR_SECRET:
            problems.append("ARGUS_CURSOR_SECRET must be replaced outside local/dev")
        if self.auth_mode != "oidc":
            problems.append("ARGUS_AUTH_MODE must be 'oidc' outside local/dev")
        if not self.oidc_issuer:
            problems.append("ARGUS_OIDC_ISSUER is required outside local/dev")
        if self.otel_enabled and not self.otel_exporter_otlp_endpoint:
            problems.append("ARGUS_OTEL_EXPORTER_OTLP_ENDPOINT is required when tracing is on")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_local(self) -> bool:
        return self.env in (Environment.LOCAL, Environment.TEST)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton.

    Services import this; tests construct ``Settings(...)`` directly to avoid
    leaking cached environment state between cases.
    """
    return Settings()
