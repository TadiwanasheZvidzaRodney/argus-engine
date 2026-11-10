"""Phase 2: Discovery Pipeline, Sync Jobs, and Resource Coverage.

Revision ID: 0003_phase2_discovery
Revises: 0002_phase1_identity
Create Date: 2026-11-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_phase2_discovery"
down_revision: str | None = "0002_phase1_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHASE2_RLS_TABLES = (
    "sync_jobs",
    "sync_job_shards",
    "resource_coverage",
)


def upgrade() -> None:
    # 1. sync_jobs
    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("aws_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("region", sa.String(length=32), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="backfill"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resource_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_sync_jobs_tenant", "sync_jobs", ["tenant_id", "created_at"])
    op.create_index("idx_sync_jobs_account", "sync_jobs", ["account_id", "status"])

    # 2. sync_job_shards
    op.create_table(
        "sync_job_shards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sync_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("items_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_upserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_sync_shards_job", "sync_job_shards", ["job_id", "status"])
    op.create_index("idx_sync_shards_tenant", "sync_job_shards", ["tenant_id"])

    # 3. resource_coverage
    op.create_table(
        "resource_coverage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("aws_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(length=128), nullable=False),
        sa.Column("supported", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_coverage_tenant", "resource_coverage", ["tenant_id"])
    op.create_index(
        "idx_coverage_unique",
        "resource_coverage",
        ["tenant_id", "account_id", "resource_type"],
        unique=True,
    )

    # --- Row-Level Security ---
    for table in PHASE2_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
            """
        )


def downgrade() -> None:
    for table in reversed(PHASE2_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("resource_coverage")
    op.drop_table("sync_job_shards")
    op.drop_table("sync_jobs")
