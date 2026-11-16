"""Phase 11: Operations Alerts, Notifications Hub, and Escalation Engine.

Revision ID: 0011_phase11_ops_alerts
Revises: 0010_phase10_gitops
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_phase11_ops_alerts"
down_revision: str | None = "0010_phase10_gitops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHASE11_RLS_TABLES = ("ops_alerts",)


def upgrade() -> None:
    op.create_table(
        "ops_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_key", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="warning"),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="ecs"),
        sa.Column("resource_id", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="FIRING"),
        sa.Column("requires_action", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("repeat_interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "notification_email",
            sa.String(length=255),
            nullable=False,
            server_default="devops@zimworx.com",
        ),
        sa.Column("notification_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "last_notified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        "idx_ops_alerts_tenant_status",
        "ops_alerts",
        ["tenant_id", "status"],
    )
    op.create_index(
        "idx_ops_alerts_tenant_key",
        "ops_alerts",
        ["tenant_id", "alert_key"],
    )

    # Enable Row-Level Security
    for table in PHASE11_RLS_TABLES:
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
    for table in reversed(PHASE11_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("ops_alerts")
