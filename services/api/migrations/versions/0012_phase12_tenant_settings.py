"""Phase 12: Dynamic Tenant Settings and Alert Notification Preferences.

Revision ID: 0012_phase12_tenant_settings
Revises: 0011_phase11_ops_alerts
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_phase12_tenant_settings"
down_revision: str | None = "0011_phase11_ops_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHASE12_RLS_TABLES = ("tenant_settings",)


def upgrade() -> None:
    op.create_table(
        "tenant_settings",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "alert_email",
            sa.String(length=255),
            nullable=False,
            server_default="devops@zimworx.com",
        ),
        sa.Column("alert_slack_webhook", sa.String(length=512), nullable=True),
        sa.Column("alert_repeat_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "default_region", sa.String(length=32), nullable=False, server_default="us-west-2"
        ),
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

    # Enable Row-Level Security
    for table in PHASE12_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
            """
        )

    # Seed default settings for demo tenant
    op.execute(
        """
        INSERT INTO tenant_settings (tenant_id, alert_email, alert_repeat_minutes, default_region)
        VALUES ('0190c3a1-0000-7000-8000-000000000001', 'devops@zimworx.com', 30, 'us-west-2')
        ON CONFLICT (tenant_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    for table in reversed(PHASE12_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("tenant_settings")
