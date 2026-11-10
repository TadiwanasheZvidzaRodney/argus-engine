"""Phase 4: Graph Snapshots and Snapshot Diffs.

Revision ID: 0005_phase4_snapshots
Revises: 0004_phase3_events
Create Date: 2026-11-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase4_snapshots"
down_revision: str | None = "0004_phase3_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHASE4_RLS_TABLES = (
    "graph_snapshots",
    "graph_snapshot_diffs",
)


def upgrade() -> None:
    # 1. graph_snapshots
    op.create_table(
        "graph_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False, server_default="full"),
        sa.Column("node_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("edge_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("manifest_uri", sa.String(length=512), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_snapshots_tenant", "graph_snapshots", ["tenant_id", "created_at"])

    # 2. graph_snapshot_diffs
    op.create_table(
        "graph_snapshot_diffs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "base_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("graph_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("graph_snapshots.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("added_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("removed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("modified_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("diff_summary", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_diffs_tenant", "graph_snapshot_diffs", ["tenant_id"])

    # --- Row-Level Security ---
    for table in PHASE4_RLS_TABLES:
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
    for table in reversed(PHASE4_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("graph_snapshot_diffs")
    op.drop_table("graph_snapshots")
