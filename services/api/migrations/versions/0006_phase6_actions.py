"""Phase 6: MCP Action Engine, Approvals, Guardrails and Evidence.

Revision ID: 0006_phase6_actions
Revises: 0005_phase4_snapshots
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_phase6_actions"
down_revision: str | None = "0005_phase4_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHASE6_RLS_TABLES = (
    "action_requests",
    "action_plans",
    "action_approvals",
    "action_executions",
    "action_locks",
    "action_evidence",
    "guardrail_rules",
    "kill_switch_state",
)

ACTION_CATALOG_ROWS: tuple[dict[str, Any], ...] = (
    {
        "id": "0190c3a1-0006-7000-8000-000000000001",
        "action_type": "iam.grant_s3_access",
        "category": "identity_access",
        "name": "Grant S3 access to a role",
        "description": (
            "Attach a least-privilege inline policy granting a compute role read or write "
            "access to a specific S3 bucket and prefix."
        ),
        "risk_level": "medium",
        "required_permissions": [
            "iam:GetRolePolicy",
            "iam:PutRolePolicy",
            "s3:GetBucketPolicy",
            "access-analyzer:ValidatePolicy",
        ],
        "plan_template": "iam-grant-s3-v3",
        "rollback_template": "iam-grant-s3-rollback-v1",
        "reversible": True,
        "max_blast_radius": 2,
        "version": "1.0.0",
    },
    {
        "id": "0190c3a1-0006-7000-8000-000000000002",
        "action_type": "network.allow_security_group_ingress",
        "category": "network_exposure",
        "name": "Allow security group ingress",
        "description": (
            "Authorize ingress from a source security group or CIDR to a target security "
            "group on a specific port range."
        ),
        "risk_level": "high",
        "required_permissions": [
            "ec2:AuthorizeSecurityGroupIngress",
            "ec2:DescribeSecurityGroups",
            "ec2:RevokeSecurityGroupIngress",
        ],
        "plan_template": "sg-ingress-v2",
        "rollback_template": "sg-ingress-rollback-v1",
        "reversible": True,
        "max_blast_radius": 4,
        "version": "1.0.0",
    },
    {
        "id": "0190c3a1-0006-7000-8000-000000000003",
        "action_type": "s3.harden_bucket",
        "category": "data_protection",
        "name": "Harden an S3 bucket",
        "description": (
            "Enable versioning, SSE-KMS default encryption, Block Public Access, and a "
            "TLS-only bucket policy."
        ),
        "risk_level": "high",
        "required_permissions": [
            "s3:PutBucketVersioning",
            "s3:PutEncryptionConfiguration",
            "s3:PutBucketPublicAccessBlock",
            "s3:PutBucketPolicy",
        ],
        "plan_template": "s3-harden-v3",
        "rollback_template": "s3-harden-rollback-v1",
        "reversible": True,
        "max_blast_radius": 1,
        "version": "1.0.0",
    },
    {
        "id": "0190c3a1-0006-7000-8000-000000000004",
        "action_type": "iam.attach_least_privilege_policy",
        "category": "identity_access",
        "name": "Attach a least-privilege IAM policy",
        "description": (
            "Synthesize and attach a scoped managed policy to a role after Access Analyzer "
            "validation."
        ),
        "risk_level": "high",
        "required_permissions": [
            "iam:CreatePolicy",
            "iam:AttachRolePolicy",
            "iam:GetPolicy",
            "access-analyzer:ValidatePolicy",
            "access-analyzer:CheckNoNewAccess",
        ],
        "plan_template": "iam-least-privilege-v2",
        "rollback_template": "iam-least-privilege-rollback-v1",
        "reversible": True,
        "max_blast_radius": 3,
        "version": "1.0.0",
    },
    {
        "id": "0190c3a1-0006-7000-8000-000000000005",
        "action_type": "tagging.apply",
        "category": "resource_configuration",
        "name": "Apply or remove tags",
        "description": "Apply or remove a set of tags across selected resources.",
        "risk_level": "low",
        "required_permissions": [
            "tag:GetResources",
            "tag:TagResources",
            "tag:UntagResources",
        ],
        "plan_template": "tagging-v1",
        "rollback_template": "tagging-rollback-v1",
        "reversible": True,
        "max_blast_radius": 100,
        "version": "1.0.0",
    },
    {
        "id": "0190c3a1-0006-7000-8000-000000000006",
        "action_type": "ec2.stop_start_instance",
        "category": "lifecycle",
        "name": "Stop and start an EC2 instance",
        "description": (
            "Stop an EC2 instance and start it again, with post-action state verification "
            "and a compensating rollback."
        ),
        "risk_level": "medium",
        "required_permissions": [
            "ec2:StopInstances",
            "ec2:StartInstances",
            "ec2:DescribeInstances",
        ],
        "plan_template": "ec2-stop-start-v1",
        "rollback_template": "ec2-stop-start-rollback-v1",
        "reversible": True,
        "max_blast_radius": 1,
        "version": "1.0.0",
    },
    {
        "id": "0190c3a1-0006-7000-8000-000000000007",
        "action_type": "observability.create_alarm",
        "category": "observability",
        "name": "Create a CloudWatch alarm",
        "description": "Create a CloudWatch metric alarm with the supplied thresholds and actions.",
        "risk_level": "low",
        "required_permissions": [
            "cloudwatch:PutMetricAlarm",
            "cloudwatch:DescribeAlarms",
        ],
        "plan_template": "cloudwatch-alarm-v1",
        "rollback_template": "cloudwatch-alarm-rollback-v1",
        "reversible": True,
        "max_blast_radius": 1,
        "version": "1.0.0",
    },
    {
        "id": "0190c3a1-0006-7000-8000-000000000008",
        "action_type": "optimization.resize_instance",
        "category": "optimization",
        "name": "Resize an EC2 instance",
        "description": "Change an instance type during a declared maintenance window with rollback.",
        "risk_level": "medium",
        "required_permissions": [
            "ec2:ModifyInstanceAttribute",
            "ec2:StopInstances",
            "ec2:StartInstances",
            "ec2:DescribeInstances",
        ],
        "plan_template": "ec2-resize-v1",
        "rollback_template": "ec2-resize-rollback-v1",
        "reversible": True,
        "max_blast_radius": 1,
        "version": "1.0.0",
    },
)


def upgrade() -> None:
    # 1. Global action catalog (no tenant scope: definitions are shared).
    op.create_table(
        "action_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action_type", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("required_permissions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("plan_template", sa.String(length=64), nullable=False),
        sa.Column("rollback_template", sa.String(length=64), nullable=False),
        sa.Column("reversible", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("max_blast_radius", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="1.0.0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_catalog_action_type", "action_catalog", ["action_type"], unique=True)

    catalog_table = sa.table(
        "action_catalog",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("action_type", sa.String()),
        sa.column("category", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("risk_level", sa.String()),
        sa.column("required_permissions", postgresql.JSONB()),
        sa.column("plan_template", sa.String()),
        sa.column("rollback_template", sa.String()),
        sa.column("reversible", sa.Boolean()),
        sa.column("max_blast_radius", sa.Integer()),
        sa.column("version", sa.String()),
    )
    op.bulk_insert(catalog_table, [dict(row) for row in ACTION_CATALOG_ROWS])

    # 2. action_requests
    op.create_table(
        "action_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("targets", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("constraints", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="low"),
        sa.Column("graph_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_action_requests_tenant_idem",
        "action_requests",
        ["tenant_id", "idempotency_key"],
        unique=True,
    )
    op.create_index("idx_action_requests_tenant_status", "action_requests", ["tenant_id", "status"])
    op.create_index(
        "idx_action_requests_tenant_created", "action_requests", ["tenant_id", "created_at"]
    )

    # 3. action_plans
    op.create_table(
        "action_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan_hash", sa.String(length=64), nullable=False),
        sa.Column("graph_version", sa.Integer(), nullable=False),
        sa.Column("template_version", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("risk", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("changes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("permissions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("diff", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("rollback", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("blast_radius", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("approved_hash", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_action_plans_action", "action_plans", ["action_id", "created_at"])

    # 4. action_approvals
    op.create_table(
        "action_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_email", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("plan_hash", sa.String(length=64), nullable=False),
        sa.Column("mfa_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_action_approvals_action", "action_approvals", ["action_id", "created_at"])

    # 5. action_executions
    op.create_table(
        "action_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="EXECUTING"),
        sa.Column("state_machine_arn", sa.String(length=512), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("rollback_status", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("verification", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_action_executions_action", "action_executions", ["action_id", "started_at"]
    )

    # 6. action_locks
    op.create_table(
        "action_locks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_key", sa.String(length=512), nullable=False),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_action_locks_resource",
        "action_locks",
        ["tenant_id", "resource_key"],
        unique=True,
    )

    # 7. action_evidence
    op.create_table(
        "action_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("uri", sa.String(length=512), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_action_evidence_action", "action_evidence", ["action_id", "created_at"])

    # 8. guardrail_rules
    op.create_table(
        "guardrail_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="1.0.0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_guardrail_rules_tenant_name",
        "guardrail_rules",
        ["tenant_id", "name"],
        unique=True,
    )

    # 9. kill_switch_state (tenant_id NULL means the global switch)
    op.create_table(
        "kill_switch_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="tenant"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("activated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_kill_switch_scope", "kill_switch_state", ["scope", "tenant_id"], unique=True
    )

    # --- Row-Level Security ---
    for table in PHASE6_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        if table == "kill_switch_state":
            # The global row (tenant_id IS NULL) is shared read-only context.
            op.execute(
                f"""
                CREATE POLICY tenant_isolation_policy ON {table}
                USING (
                    tenant_id IS NULL
                    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                )
                WITH CHECK (
                    tenant_id IS NULL
                    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                );
                """
            )
        else:
            op.execute(
                f"""
                CREATE POLICY tenant_isolation_policy ON {table}
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
                """
            )


def downgrade() -> None:
    for table in reversed(PHASE6_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("kill_switch_state")
    op.drop_table("guardrail_rules")
    op.drop_table("action_evidence")
    op.drop_table("action_locks")
    op.drop_table("action_executions")
    op.drop_table("action_approvals")
    op.drop_table("action_plans")
    op.drop_table("action_requests")
    op.drop_table("action_catalog")
