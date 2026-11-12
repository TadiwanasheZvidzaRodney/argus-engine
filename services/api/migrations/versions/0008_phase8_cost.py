"""Phase 8: Cost Intelligence, Optimization Recommendations, Budgets, and Sync Jobs.

Revision ID: 0008_phase8_cost
Revises: 0007_phase7_security
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_phase8_cost"
down_revision: str | None = "0007_phase7_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHASE8_RLS_TABLES = (
    "cost_daily",
    "cost_resource_estimates",
    "cost_reconciliation",
    "cost_budgets",
    "cost_recommendations",
    "cost_sync_jobs",
)


def upgrade() -> None:
    # 1. cost_daily — Daily aggregates by account, service, usage_type, and allocation tags.
    op.create_table(
        "cost_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.String(length=12), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("service", sa.String(length=128), nullable=False),
        sa.Column("usage_type", sa.String(length=128), nullable=False),
        sa.Column("tag_key", sa.String(length=128), nullable=True),
        sa.Column("tag_value", sa.String(length=256), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_cost_daily_tenant_period",
        "cost_daily",
        ["tenant_id", "period_date"],
    )
    op.create_index(
        "idx_cost_daily_tenant_service",
        "cost_daily",
        ["tenant_id", "service"],
    )
    op.create_index(
        "idx_cost_daily_tenant_account",
        "cost_daily",
        ["tenant_id", "account_id"],
    )

    # 2. cost_resource_estimates — Estimated resource-level cost with confidence labels.
    op.create_table(
        "cost_resource_estimates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", sa.String(length=2048), nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_cost_estimates_dedupe",
        "cost_resource_estimates",
        ["tenant_id", "resource_id", "period_date"],
        unique=True,
    )
    op.create_index(
        "idx_cost_estimates_tenant_period",
        "cost_resource_estimates",
        ["tenant_id", "period_date"],
    )

    # 3. cost_reconciliation — Invariant tracking: allocated + unallocated = total.
    op.create_table(
        "cost_reconciliation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("unallocated_amount", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("variance_pct", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="reconciled"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_cost_reconcile_tenant",
        "cost_reconciliation",
        ["tenant_id", "period_start", "period_end"],
        unique=True,
    )

    # 4. cost_budgets — Budget thresholds and tracking.
    op.create_table(
        "cost_budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False, server_default="tenant"),
        sa.Column("scope_value", sa.String(length=256), nullable=True),
        sa.Column("threshold_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False, server_default="monthly"),
        sa.Column("notification_channel", sa.String(length=256), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_cost_budgets_tenant",
        "cost_budgets",
        ["tenant_id", "enabled"],
    )

    # 5. cost_recommendations — Optimization rules with savings and Phase 6 handoff.
    op.create_table(
        "cost_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=2048), nullable=False),
        sa.Column("resource_type", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("estimated_monthly_savings", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("remediation_action", sa.String(length=128), nullable=True),
        sa.Column("remediation_action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_cost_recommendations_dedupe",
        "cost_recommendations",
        ["tenant_id", "rule_id", "resource_id"],
        unique=True,
    )
    op.create_index(
        "idx_cost_recommendations_status",
        "cost_recommendations",
        ["tenant_id", "status"],
    )

    # 6. cost_sync_jobs — Ingestion job tracking and freshness metadata.
    op.create_table(
        "cost_sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.String(length=12), nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="SUCCEEDED"),
        sa.Column("records_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_cost_sync_jobs_tenant",
        "cost_sync_jobs",
        ["tenant_id", "created_at"],
    )

    # Enable Row-Level Security on all tenant tables
    for table in PHASE8_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
            """
        )


def downgrade() -> None:
    for table in reversed(PHASE8_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("cost_sync_jobs")
    op.drop_table("cost_recommendations")
    op.drop_table("cost_budgets")
    op.drop_table("cost_reconciliation")
    op.drop_table("cost_resource_estimates")
    op.drop_table("cost_daily")
