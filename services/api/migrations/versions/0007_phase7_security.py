"""Phase 7: Telemetry, security findings, rule versions, and attack-path cache.

Revision ID: 0007_phase7_security
Revises: 0006_phase6_actions
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_phase7_security"
down_revision: str | None = "0006_phase6_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHASE7_RLS_TABLES = (
    "findings",
    "finding_events",
    "finding_suppressions",
    "telemetry_subscriptions",
    "telemetry_usage",
    "attack_path_cache",
)


def upgrade() -> None:
    # 1. findings — deduplicated security posture per rule/resource/sub-key.
    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("rule_version", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.String(length=2048), nullable=False),
        sa.Column("resource_type", sa.String(length=128), nullable=False),
        sa.Column("account_id", sa.String(length=12), nullable=True),
        sa.Column("region", sa.String(length=32), nullable=True),
        sa.Column("finding_key", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("remediation_action", sa.String(length=128), nullable=True),
        sa.Column("remediation_action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_accepted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_findings_dedupe",
        "findings",
        ["tenant_id", "rule_id", "resource_id", "finding_key"],
        unique=True,
    )
    op.create_index("idx_findings_tenant_status", "findings", ["tenant_id", "status"])
    op.create_index("idx_findings_tenant_severity", "findings", ["tenant_id", "severity"])
    op.create_index("idx_findings_tenant_resource", "findings", ["tenant_id", "resource_id"])
    op.create_index("idx_findings_tenant_account", "findings", ["tenant_id", "account_id"])

    # 2. finding_events — append-only lifecycle trail.
    op.create_table(
        "finding_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "finding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("findings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_finding_events_finding", "finding_events", ["finding_id", "created_at"])
    op.create_index("idx_finding_events_tenant", "finding_events", ["tenant_id", "created_at"])

    # 3. finding_suppressions — time-bounded suppressions with an owner and reason.
    op.create_table(
        "finding_suppressions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "finding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("findings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="finding"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_finding_suppressions_finding",
        "finding_suppressions",
        ["finding_id", "created_at"],
    )
    op.create_index(
        "idx_finding_suppressions_expiry",
        "finding_suppressions",
        ["tenant_id", "expires_at"],
    )

    # 4. security_rule_versions — global rule registry (shared, not tenant scoped).
    op.create_table(
        "security_rule_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_rule_versions_rule",
        "security_rule_versions",
        ["rule_id", "version"],
        unique=True,
    )

    # 5. telemetry_subscriptions — server-side viewport subscriptions.
    op.create_table(
        "telemetry_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("resolution", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_telemetry_subscriptions_tenant",
        "telemetry_subscriptions",
        ["tenant_id", "status"],
    )

    # 6. telemetry_usage — daily per-tenant metric budget and cost accounting.
    op.create_table(
        "telemetry_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("metric_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(precision=12, scale=6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_telemetry_usage_tenant_period",
        "telemetry_usage",
        ["tenant_id", "period_date"],
        unique=True,
    )

    # 7. attack_path_cache — cached path results per tenant/query/graph version.
    op.create_table(
        "attack_path_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("graph_version", sa.Integer(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_attack_path_cache_query",
        "attack_path_cache",
        ["tenant_id", "query_hash"],
        unique=True,
    )

    # 8. Remediation action for exposed security groups (extends the Phase 6 catalog).
    op.execute(
        """
        INSERT INTO action_catalog (
            id, action_type, category, name, description, risk_level,
            required_permissions, plan_template, rollback_template, reversible,
            max_blast_radius, enabled, version
        ) VALUES (
            '0190c3a1-0006-7000-8000-000000000009',
            'network.restrict_security_group_ingress',
            'network_exposure',
            'Restrict security group ingress',
            'Revoke an internet-exposed ingress rule from a security group and verify reachability.',
            'high',
            '["ec2:RevokeSecurityGroupIngress", "ec2:DescribeSecurityGroups", "ec2:AuthorizeSecurityGroupIngress"]'::jsonb,
            'sg-restrict-v1',
            'sg-restrict-rollback-v1',
            true,
            1,
            true,
            '1.0.0'
        ) ON CONFLICT (action_type) DO NOTHING;
        """
    )

    # --- Row-Level Security ---
    for table in PHASE7_RLS_TABLES:
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
    for table in reversed(PHASE7_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute(
        "DELETE FROM action_catalog WHERE action_type = 'network.restrict_security_group_ingress';"
    )
    op.drop_table("attack_path_cache")
    op.drop_table("telemetry_usage")
    op.drop_table("telemetry_subscriptions")
    op.drop_table("security_rule_versions")
    op.drop_table("finding_suppressions")
    op.drop_table("finding_events")
    op.drop_table("findings")
