"""Phase 9: Compliance Evidence Locker, Usage Metering, Degraded Modes, and SLO Status.

Revision ID: 0009_phase9_hardening_ga
Revises: 0008_phase8_cost
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_phase9_hardening_ga"
down_revision: str | None = "0008_phase8_cost"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHASE9_RLS_TABLES = (
    "usage_metering",
    "compliance_evidence",
)


def upgrade() -> None:
    # 1. usage_metering — Per-tenant consumption across compute, events, telemetry, and actions.
    op.create_table(
        "usage_metering",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("resources_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metric_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actions_planned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actions_executed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(precision=12, scale=4),
            nullable=False,
            server_default="0",
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
    op.create_index(
        "idx_usage_metering_tenant_period",
        "usage_metering",
        ["tenant_id", "period_date"],
        unique=True,
    )

    # 2. compliance_controls — Static framework catalog (SOC 2, CIS-AWS, NIST-800-53, ISO-27001).
    op.create_table(
        "compliance_controls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("framework", sa.String(length=32), nullable=False),
        sa.Column("control_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="high"),
        sa.Column("automated", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("rule_mappings", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_compliance_controls_lookup",
        "compliance_controls",
        ["framework", "control_id"],
        unique=True,
    )

    # 3. compliance_evidence — Cryptographically verifiable evidence locker records.
    op.create_table(
        "compliance_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework", sa.String(length=32), nullable=False),
        sa.Column("control_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PASS"),
        sa.Column("evidence_payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_compliance_evidence_tenant_ctrl",
        "compliance_evidence",
        ["tenant_id", "framework", "control_id"],
    )

    # 4. degraded_modes — Global or per-tenant operational degraded mode flags and circuit breakers.
    op.create_table(
        "degraded_modes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("live_paused", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("telemetry_paused", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("actions_disabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("maintenance_message", sa.Text(), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # 5. system_slo_status — Real-time SLO tracking and error budget burn.
    op.create_table(
        "system_slo_status",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slo_name", sa.String(length=64), nullable=False),
        sa.Column("target_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("current_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("error_budget_burn_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="healthy"),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_system_slo_name",
        "system_slo_status",
        ["slo_name"],
        unique=True,
    )

    # Enable Row-Level Security on tenant-scoped tables
    for table in PHASE9_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
            """
        )

    # Seed curated compliance controls
    op.execute(
        """
        INSERT INTO compliance_controls (id, framework, control_id, title, description, domain, severity, automated, rule_mappings)
        VALUES
        ('0190c3a1-9001-7000-8000-000000000001', 'SOC2', 'CC6.1', 'Logical Access Security', 'Logical access to system components is restricted based on least privilege and role-based policies.', 'Access Control', 'critical', true, '["iam-wildcard-action-resource", "iam-privilege-escalation", "iam-trust-wildcard-principal"]'),
        ('0190c3a1-9001-7000-8000-000000000002', 'SOC2', 'CC6.6', 'Perimeter & Network Segmentation', 'Network boundaries restrict unauthorized network connections and open administrative ports.', 'Network Security', 'critical', true, '["sg-public-admin-port", "sg-public-all-ports", "rds-publicly-accessible"]'),
        ('0190c3a1-9001-7000-8000-000000000003', 'SOC2', 'CC6.7', 'Data Transmission Protection', 'Data in transit over public and internal networks is encrypted using TLS.', 'Data Protection', 'high', true, '["s3-no-tls-enforcement"]'),
        ('0190c3a1-9001-7000-8000-000000000004', 'SOC2', 'CC6.8', 'Encryption of Data at Rest', 'Data storage repositories protect data at rest using approved cryptographic algorithms.', 'Data Protection', 'high', true, '["s3-no-default-encryption", "ebs-unencrypted", "rds-unencrypted"]'),
        ('0190c3a1-9001-7000-8000-000000000005', 'SOC2', 'CC7.2', 'Security Vulnerability Monitoring', 'System vulnerabilities and misconfigurations are continuously identified and triaged.', 'Monitoring', 'high', true, '["guardduty-disabled", "cloudtrail-not-multiregion"]'),
        ('0190c3a1-9001-7000-8000-000000000006', 'SOC2', 'CC8.1', 'Authorized Change Management', 'Configuration changes are planned, diffed, approved, and verified with rollback capabilities.', 'Change Management', 'critical', true, '[]'),
        ('0190c3a1-9001-7000-8000-000000000007', 'CIS-AWS', 'CIS-1.16', 'Avoid Wildcard IAM Policies', 'Ensure IAM policies do not allow broad administrative wildcards.', 'IAM', 'high', true, '["iam-wildcard-action-resource"]'),
        ('0190c3a1-9001-7000-8000-000000000008', 'CIS-AWS', 'CIS-2.1', 'Ensure S3 Buckets are not Public', 'S3 buckets should prohibit public read or write access.', 'Storage', 'critical', true, '["s3-public-policy"]'),
        ('0190c3a1-9001-7000-8000-000000000009', 'CIS-AWS', 'CIS-5.2', 'Restrict Ingress Traffic on Admin Ports', 'Security groups must not allow 0.0.0.0/0 ingress to port 22, 3389, or database ports.', 'Networking', 'critical', true, '["sg-public-admin-port"]'),
        ('0190c3a1-9001-7000-8000-000000000010', 'NIST-800-53', 'AC-3', 'Access Enforcement', 'Enforce approved authorizations for logical access to information and system resources.', 'Access Control', 'high', true, '["s3-public-policy", "lambda-public-url", "apigw-unauthenticated"]')
        ON CONFLICT DO NOTHING;
        """
    )


def downgrade() -> None:
    for table in reversed(PHASE9_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("system_slo_status")
    op.drop_table("degraded_modes")
    op.drop_table("compliance_evidence")
    op.drop_table("compliance_controls")
    op.drop_table("usage_metering")
