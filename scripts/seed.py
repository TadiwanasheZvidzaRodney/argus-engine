"""Seed script for local development and test environments.

Provisions:
1. Demo tenant in `tenants` (UUID: 0190c3a1-0000-7000-8000-000000000001).
2. Demo user in `users` (demo@argus.local).
3. Demo membership in `memberships` with role 'owner'.
4. Initial audit event establishing the tenant chain anchor.
5. Neo4j schema constraints, indexes, and initial topology graph.
"""

from __future__ import annotations

import asyncio
import json
import sys
from uuid import UUID

from argus_core.events import AuditEvent
from argus_core.graph.client import build_graph_driver
from argus_core.graph.migrations import apply_graph_migrations
from argus_core.graph.repository import GraphRepository
from argus_core.logging import configure_logging, get_logger
from argus_core.settings import Environment, Settings
from argus_worker.discovery.adapters.sample_data import build_enterprise_topology
from argus_worker.discovery.resolvers import RelationshipResolver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DEMO_TENANT_ID = UUID("0190c3a1-0000-7000-8000-000000000001")
DEMO_USER_ID = UUID("0190c3a1-0000-7000-8000-0000000000aa")
DEMO_ACCOUNT_ID = "123456789012"
SEED_AUDIT_ID = UUID("0190c3a1-0000-7000-8000-000000000099")


async def seed_postgres(settings: Settings) -> None:
    log = get_logger("seed.postgres")
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        # 1. Tenant
        await conn.execute(
            text(
                """
                insert into tenants (id, name, slug, status, plan)
                values (:id, :name, :slug, 'active', 'enterprise')
                on conflict (id) do update set name = excluded.name;
                """
            ),
            {"id": DEMO_TENANT_ID, "name": "Argus Demo Tenant", "slug": "demo-tenant"},
        )
        log.info("tenant.seeded", tenant_id=f"tnt_{DEMO_TENANT_ID}")

        # 2. User
        await conn.execute(
            text(
                """
                insert into users (id, email, name, status, mfa_enrolled)
                values (:id, :email, :name, 'active', true)
                on conflict (id) do update set name = excluded.name;
                """
            ),
            {"id": DEMO_USER_ID, "email": "demo@argus.local", "name": "Demo Administrator"},
        )
        log.info("user.seeded", user_id=f"usr_{DEMO_USER_ID.hex}")

        # 3. Membership
        await conn.execute(
            text(
                """
                insert into memberships (tenant_id, user_id, role, status)
                values (:tenant_id, :user_id, 'owner', 'active')
                on conflict (tenant_id, user_id) do update set role = excluded.role;
                """
            ),
            {"tenant_id": DEMO_TENANT_ID, "user_id": DEMO_USER_ID},
        )
        log.info("membership.seeded", role="owner")

        # 4. Audit Anchor
        audit = AuditEvent.create(
            id=SEED_AUDIT_ID,
            tenant_id=f"tnt_{DEMO_TENANT_ID}",
            actor_type="system",
            actor_id="seed_script",
            action="tenant.initialized",
            resource_type="tenant",
            resource_id=f"tnt_{DEMO_TENANT_ID}",
            metadata={"environment": settings.env.value},
        )
        # Bypassing RLS for admin seeding
        await conn.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(DEMO_TENANT_ID)},
        )
        await conn.execute(
            text(
                """
                insert into audit_events (
                    id, tenant_id, actor_type, actor_id, action, resource_type,
                    resource_id, metadata, prev_hash, hash
                ) values (
                    :id, :tenant_id, :actor_type, :actor_id, :action, :resource_type,
                    :resource_id, :metadata, :prev_hash, :hash
                ) on conflict (id) do nothing;
                """
            ),
            {
                "id": audit.id,
                "tenant_id": DEMO_TENANT_ID,
                "actor_type": audit.actor_type.value,
                "actor_id": audit.actor_id,
                "action": audit.action,
                "resource_type": audit.resource_type,
                "resource_id": audit.resource_id,
                "metadata": json.dumps(audit.metadata),
                "prev_hash": audit.prev_hash,
                "hash": audit.hash,
            },
        )
        log.info("audit.seeded", hash=audit.hash)

    await engine.dispose()


async def seed_neo4j(settings: Settings) -> None:
    log = get_logger("seed.neo4j")
    driver = build_graph_driver(settings)

    # 1. Apply constraints and indexes
    await apply_graph_migrations(driver)

    # 2. Ingest baseline enterprise topology for demo tenant
    repo = GraphRepository(driver)
    tenant_id = f"tnt_{DEMO_TENANT_ID}"
    nodes = build_enterprise_topology(
        tenant_id=tenant_id,
        account_id=DEMO_ACCOUNT_ID,
        region="us-east-1",
    )
    edges = RelationshipResolver.resolve(tenant_id, nodes)

    await repo.upsert_nodes(tenant_id, nodes)
    await repo.upsert_edges(tenant_id, edges)
    log.info("neo4j.topology.seeded", nodes=len(nodes), edges=len(edges))

    await driver.close()


async def main() -> int:
    settings = Settings(service_name="argus-seed")
    configure_logging(settings)
    log = get_logger("seed")

    if settings.env is Environment.PROD:
        log.error("seed.refused_in_production")
        return 1

    log.info("seed.started", env=settings.env.value)
    try:
        await seed_postgres(settings)
        await seed_neo4j(settings)
        log.info("seed.completed_successfully")
        return 0
    except Exception as exc:
        log.exception("seed.failed", error=str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
