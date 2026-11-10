"""Pydantic and typed data models for Neo4j nodes and edges."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GraphNode(BaseModel):
    """Canonical graph node contract (Phase 2 schema v1)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(min_length=1, max_length=2048, description="Canonical ARN or URN")
    arn: str = Field(min_length=1, max_length=2048)
    type: str = Field(pattern=r"^AWS::[A-Za-z0-9]+::[A-Za-z0-9]+$")
    name: str = Field(default="", max_length=256)
    tenant_id: str = Field(pattern=r"^tnt_[0-9a-fA-F-]+$")
    account_id: str = Field(pattern=r"^[0-9]{12}$")
    region: str = Field(pattern=r"^[a-z]{2}(-[a-z]+)+-[0-9]$")
    state: str = Field(default="available", max_length=64)
    tags: dict[str, str] = Field(default_factory=dict)
    source: str = Field(default="direct-api", max_length=128)
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    deleted_at: datetime | None = None
    raw_ref: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)

    @property
    def secondary_label(self) -> str:
        """Derive secondary Neo4j label from type, e.g. AWS::EC2::Instance -> Instance."""
        parts = self.type.split("::")
        return parts[-1] if len(parts) == 3 else "Resource"


class GraphEdge(BaseModel):
    """Canonical directed relationship between two graph nodes."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    source_id: str = Field(min_length=1, max_length=2048)
    target_id: str = Field(min_length=1, max_length=2048)
    type: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    tenant_id: str = Field(pattern=r"^tnt_[0-9a-fA-F-]+$")
    properties: dict[str, Any] = Field(default_factory=dict)
