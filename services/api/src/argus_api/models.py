"""SQLAlchemy 2 declarative models for Argus Engine Phase 1.

Covers:
- Tenancy & Identity (tenants, users, memberships, invitations, sessions)
- AWS Accounts & Regions (aws_accounts, aws_regions)
- Audit & Outbox (audit_events, outbox_events)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SchemaMetadata(Base):
    __tablename__ = "schema_metadata"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    plan: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list[Membership]] = relationship("Membership", back_populates="tenant")
    aws_accounts: Mapped[list[AwsAccount]] = relationship("AwsAccount", back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idp_subject: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    mfa_enrolled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list[Membership]] = relationship("Membership", back_populates="user")


class Membership(Base):
    __tablename__ = "memberships"

    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    account_scopes: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    region_scopes: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="memberships")
    user: Mapped[User] = relationship("User", back_populates="memberships")


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    invited_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    mfa_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AwsAccount(Base):
    __tablename__ = "aws_accounts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(String(12), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(128), nullable=True)
    org_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ou_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    read_role_arn: Mapped[str] = mapped_column(String(512), nullable=False)
    write_role_arn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_id_secret_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="aws_accounts")
    regions: Mapped[list[AwsRegion]] = relationship(
        "AwsRegion", back_populates="account", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_tenant_account", "tenant_id", "account_id", unique=True),)


class AwsRegion(Base):
    __tablename__ = "aws_regions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("aws_accounts.id", ondelete="CASCADE"), nullable=False
    )
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    discovery_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending"
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped[AwsAccount] = relationship("AwsAccount", back_populates="regions")

    __table_args__ = (Index("idx_account_region", "account_id", "region", unique=True),)


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_outbox_tenant_idempotency", "tenant_id", "idempotency_key", unique=True),
        Index("idx_outbox_pending", "status", "available_at"),
    )


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("aws_accounts.id", ondelete="CASCADE"), nullable=False
    )
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="backfill")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resource_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    shards: Mapped[list[SyncJobShard]] = relationship("SyncJobShard", back_populates="job")


class SyncJobShard(Base):
    __tablename__ = "sync_job_shards"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sync_jobs.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="queued")
    items_discovered: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    items_upserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped[SyncJob] = relationship("SyncJob", back_populates="shards")


class ResourceCoverage(Base):
    __tablename__ = "resource_coverage"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("aws_accounts.id", ondelete="CASCADE"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    supported: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_coverage_unique", "tenant_id", "account_id", "resource_type", unique=True),
    )


class EventIngestLog(Base):
    __tablename__ = "event_ingest_log"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="processed")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventDlqIndex(Base):
    __tablename__ = "event_dlq_index"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    error_reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("aws_accounts.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(64), nullable=False, server_default="scheduled")
    drift_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    repaired_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GraphSnapshot(Base):
    __tablename__ = "graph_snapshots"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, server_default="full")
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    manifest_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="completed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GraphSnapshotDiff(Base):
    __tablename__ = "graph_snapshot_diffs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    base_snapshot_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("graph_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    target_snapshot_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("graph_snapshots.id", ondelete="CASCADE"), nullable=True
    )
    added_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    removed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    modified_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    diff_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Phase 6 — Action engine, approvals and guardrails
# ---------------------------------------------------------------------------


class ActionCatalogEntry(Base):
    __tablename__ = "action_catalog"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    required_permissions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    plan_template: Mapped[str] = mapped_column(String(64), nullable=False)
    rollback_template: Mapped[str] = mapped_column(String(64), nullable=False)
    reversible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    max_blast_radius: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    version: Mapped[str] = mapped_column(String(32), nullable=False, server_default="1.0.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ActionRequestModel(Base):
    __tablename__ = "action_requests"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="DRAFT")
    requester_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    targets: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    constraints: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, server_default="low")
    graph_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_action_requests_tenant_idem", "tenant_id", "idempotency_key", unique=True),
        Index("idx_action_requests_tenant_status", "tenant_id", "status"),
        Index("idx_action_requests_tenant_created", "tenant_id", "created_at"),
    )


class ActionPlanModel(Base):
    __tablename__ = "action_plans"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    action_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("action_requests.id", ondelete="CASCADE"), nullable=False
    )
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    graph_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    changes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    permissions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    rollback: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    blast_radius: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    approved_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_action_plans_action", "action_id", "created_at"),)


class ActionApprovalModel(Base):
    __tablename__ = "action_approvals"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    action_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("action_requests.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("action_plans.id", ondelete="CASCADE"), nullable=False
    )
    approver_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    approver_email: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mfa_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_action_approvals_action", "action_id", "created_at"),)


class ActionExecutionModel(Base):
    __tablename__ = "action_executions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    action_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("action_requests.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("action_plans.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="EXECUTING")
    state_machine_arn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="none")
    verification: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_action_executions_action", "action_id", "started_at"),)


class ActionLockModel(Base):
    __tablename__ = "action_locks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    resource_key: Mapped[str] = mapped_column(String(512), nullable=False)
    action_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("action_requests.id", ondelete="CASCADE"), nullable=False
    )
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_action_locks_resource", "tenant_id", "resource_key", unique=True),)


class ActionEvidenceModel(Base):
    __tablename__ = "action_evidence"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    action_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("action_requests.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    uri: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_action_evidence_action", "action_id", "created_at"),)


class GuardrailRuleModel(Base):
    __tablename__ = "guardrail_rules"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    version: Mapped[str] = mapped_column(String(32), nullable=False, server_default="1.0.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_guardrail_rules_tenant_name", "tenant_id", "name", unique=True),)


class KillSwitchStateModel(Base):
    __tablename__ = "kill_switch_state"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, server_default="tenant")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    activated_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_kill_switch_scope", "scope", "tenant_id", unique=True),)


# ---------------------------------------------------------------------------
# Phase 7 — Security findings and telemetry
# ---------------------------------------------------------------------------


class FindingModel(Base):
    __tablename__ = "findings"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="OPEN")
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str] = mapped_column(String(2048), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finding_key: Mapped[str] = mapped_column(String(512), nullable=False, server_default="")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    assignee_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    remediation_action: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remediation_action_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    risk_accepted_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_scan_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "idx_findings_dedupe",
            "tenant_id",
            "rule_id",
            "resource_id",
            "finding_key",
            unique=True,
        ),
        Index("idx_findings_tenant_status", "tenant_id", "status"),
        Index("idx_findings_tenant_severity", "tenant_id", "severity"),
        Index("idx_findings_tenant_resource", "tenant_id", "resource_id"),
        Index("idx_findings_tenant_account", "tenant_id", "account_id"),
    )


class FindingEventModel(Base):
    __tablename__ = "finding_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    finding_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_finding_events_finding", "finding_id", "created_at"),
        Index("idx_finding_events_tenant", "tenant_id", "created_at"),
    )


class FindingSuppressionModel(Base):
    __tablename__ = "finding_suppressions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    finding_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, server_default="finding")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_finding_suppressions_finding", "finding_id", "created_at"),
        Index("idx_finding_suppressions_expiry", "tenant_id", "expires_at"),
    )


class SecurityRuleVersionModel(Base):
    __tablename__ = "security_rule_versions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    changelog: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_rule_versions_rule", "rule_id", "version", unique=True),)


class TelemetrySubscriptionModel(Base):
    __tablename__ = "telemetry_subscriptions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    resource_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    metrics: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    resolution: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_telemetry_subscriptions_tenant", "tenant_id", "status"),)


class TelemetryUsageModel(Base):
    __tablename__ = "telemetry_usage"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    period_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    metric_requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    estimated_cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 6), nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_telemetry_usage_tenant_period", "tenant_id", "period_date", unique=True),
    )


class AttackPathCacheModel(Base):
    __tablename__ = "attack_path_cache"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    graph_version: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_attack_path_cache_query", "tenant_id", "query_hash", unique=True),)


# ---------------------------------------------------------------------------
# Phase 8 — Cost intelligence, resource estimates, budgets, recommendations
# ---------------------------------------------------------------------------


class CostDailyModel(Base):
    __tablename__ = "cost_daily"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(12), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    usage_type: Mapped[str] = mapped_column(String(128), nullable=False)
    tag_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tag_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    period_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_cost_daily_tenant_period", "tenant_id", "period_date"),
        Index("idx_cost_daily_tenant_service", "tenant_id", "service"),
        Index("idx_cost_daily_tenant_account", "tenant_id", "account_id"),
    )


class CostResourceEstimateModel(Base):
    __tablename__ = "cost_resource_estimates"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(2048), nullable=False)
    period_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "idx_cost_estimates_dedupe",
            "tenant_id",
            "resource_id",
            "period_date",
            unique=True,
        ),
        Index("idx_cost_estimates_tenant_period", "tenant_id", "period_date"),
    )


class CostReconciliationModel(Base):
    __tablename__ = "cost_reconciliation"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(Date, nullable=False)
    period_end: Mapped[datetime] = mapped_column(Date, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    allocated_amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    unallocated_amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    variance_pct: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="reconciled")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "idx_cost_reconcile_tenant",
            "tenant_id",
            "period_start",
            "period_end",
            unique=True,
        ),
    )


class CostBudgetModel(Base):
    __tablename__ = "cost_budgets"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="tenant")
    scope_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    threshold_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    period: Mapped[str] = mapped_column(String(16), nullable=False, server_default="monthly")
    notification_channel: Mapped[str | None] = mapped_column(String(256), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_cost_budgets_tenant", "tenant_id", "enabled"),)


class CostRecommendationModel(Base):
    __tablename__ = "cost_recommendations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(2048), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, server_default="medium")
    estimated_monthly_savings: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="OPEN")
    remediation_action: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remediation_action_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "idx_cost_recommendations_dedupe",
            "tenant_id",
            "rule_id",
            "resource_id",
            unique=True,
        ),
        Index("idx_cost_recommendations_status", "tenant_id", "status"),
    )


class CostSyncJobModel(Base):
    __tablename__ = "cost_sync_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(12), nullable=False)
    period_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="SUCCEEDED")
    records_ingested: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_cost_sync_jobs_tenant", "tenant_id", "created_at"),)


# ---------------------------------------------------------------------------
# Phase 9 — Hardening, Compliance Evidence Locker, Metering, and Degraded Modes
# ---------------------------------------------------------------------------


class UsageMeteringModel(Base):
    __tablename__ = "usage_metering"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    period_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    resources_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    events_ingested: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    metric_requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    actions_planned: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    actions_executed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    storage_bytes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    estimated_cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_usage_metering_tenant_period", "tenant_id", "period_date", unique=True),
    )


class ComplianceControlModel(Base):
    __tablename__ = "compliance_controls"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    framework: Mapped[str] = mapped_column(String(32), nullable=False)
    control_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, server_default="high")
    automated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    rule_mappings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_compliance_controls_lookup", "framework", "control_id", unique=True),
    )


class ComplianceEvidenceModel(Base):
    __tablename__ = "compliance_evidence"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    framework: Mapped[str] = mapped_column(String(32), nullable=False)
    control_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="PASS")
    evidence_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_compliance_evidence_tenant_ctrl", "tenant_id", "framework", "control_id"),
    )


class DegradedModeModel(Base):
    __tablename__ = "degraded_modes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    live_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    telemetry_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    actions_disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    maintenance_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SystemSloStatusModel(Base):
    __tablename__ = "system_slo_status"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    slo_name: Mapped[str] = mapped_column(String(64), nullable=False)
    target_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    current_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    error_budget_burn_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="healthy")
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_system_slo_name", "slo_name", unique=True),)
