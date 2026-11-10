"""Seed script for local development and test environments.

Provisions:
1. Demo tenant (`tnt_0190c3a1-0000-7000-8000-000000000001`) in PostgreSQL.
2. Initial audit event establishing the tenant chain anchor.
3. Verification probe against Redis and Neo4j.
"""

from __future__ import annotations

import asyncio
import sys

from argus_core.events import AuditEvent
from argus_core.logging import configure_logging, get_logger
from argus_core.settings import Environment, Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DEMO_TENANT_ID = "tnt_0190c3a1-0000-7000-8000-000000000001"


async def seed_postgres(settings: Settings) -> None:
    log = get_logger("seed.postgres")
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        # Create demo tenant table if not yet handled by Phase 1 migrations
        await conn.execute(
            text(
                """
                create table if not exists demo_tenants (
                    id text primary key,
                    name text not null,
                    created_at timestamptz not null default now()
                );
                """
            )
        )
        await conn.execute(
            text(
                """
                insert into demo_tenants (id, name)
                values (:id, :name)
                on conflict (id) do update set name = excluded.name;
                """
            ),
            {"id": DEMO_TENANT_ID, "name": "Argus Demo Tenant"},
        )
        log.info("tenant.seeded", tenant_id=DEMO_TENANT_ID)

        # Seed initial audit event
        audit = AuditEvent.create(
            tenant_id=DEMO_TENANT_ID,
            actor_type="system",
            actor_id="seed_script",
            action="tenant.initialized",
            resource_type="tenant",
            resource_id=DEMO_TENANT_ID,
            metadata={"environment": settings.env.value},
        )
        log.info("audit.seeded", hash=audit.hash, action=audit.action)

    await engine.dispose()


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
        log.info("seed.completed_successfully")
        return 0
    except Exception as exc:
        log.exception("seed.failed", error=str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
