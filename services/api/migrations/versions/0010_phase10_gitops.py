"""Phase 10: GitOps Bridge, IaC Drift Detection, and Pull Request Synthesis.

Revision ID: 0010_phase10_gitops
Revises: 0009_phase9_hardening_ga
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_phase10_gitops"
down_revision: str | None = "0009_phase9_hardening_ga"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHASE10_RLS_TABLES = (
    "git_repositories",
    "iac_drift_records",
    "iac_pull_requests",
)


def upgrade() -> None:
    # 1. git_repositories — Customer IaC repositories (GitHub/GitLab).
    op.create_table(
        "git_repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="github"),
        sa.Column("repo_url", sa.String(length=512), nullable=False),
        sa.Column("default_branch", sa.String(length=128), nullable=False, server_default="main"),
        sa.Column("iac_path", sa.String(length=256), nullable=False, server_default="terraform/"),
        sa.Column("auth_token_ref", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
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
        "idx_git_repositories_tenant",
        "git_repositories",
        ["tenant_id", "status"],
    )

    # 2. iac_drift_records — Discovered drift between live graph nodes and Terraform definitions.
    op.create_table(
        "iac_drift_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", sa.String(length=2048), nullable=False),
        sa.Column("resource_type", sa.String(length=128), nullable=False),
        sa.Column("iac_file_path", sa.String(length=512), nullable=False),
        sa.Column("iac_block_type", sa.String(length=128), nullable=False),
        sa.Column("iac_block_name", sa.String(length=128), nullable=False),
        sa.Column("drift_details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRIFTED"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_iac_drift_tenant_res",
        "iac_drift_records",
        ["tenant_id", "resource_id"],
    )
    op.create_index(
        "idx_iac_drift_status",
        "iac_drift_records",
        ["tenant_id", "status"],
    )

    # 3. iac_pull_requests — Synthesized Pull Requests with HCL diffs for actions and drift fixes.
    op.create_table(
        "iac_pull_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pr_url", sa.String(length=512), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("branch_name", sa.String(length=128), nullable=False),
        sa.Column("hcl_diff", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
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
        "idx_iac_prs_tenant",
        "iac_pull_requests",
        ["tenant_id", "status"],
    )
    op.create_index(
        "idx_iac_prs_action",
        "iac_pull_requests",
        ["action_id"],
    )

    # Enable Row-Level Security on all tenant tables
    for table in PHASE10_RLS_TABLES:
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
    for table in reversed(PHASE10_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("iac_pull_requests")
    op.drop_table("iac_drift_records")
    op.drop_table("git_repositories")
