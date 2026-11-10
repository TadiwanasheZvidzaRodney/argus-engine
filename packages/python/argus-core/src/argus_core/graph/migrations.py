"""Neo4j schema constraints, indexes, and versioning migrations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from argus_core.logging import get_logger

if TYPE_CHECKING:
    from neo4j import AsyncDriver

SCHEMA_VERSION = "0.2.0"

CONSTRAINTS = (
    """
    CREATE CONSTRAINT resource_tenant_id_unique IF NOT EXISTS
    FOR (r:Resource) REQUIRE (r.tenant_id, r.id) IS UNIQUE
    """,
    """
    CREATE CONSTRAINT schema_version_unique IF NOT EXISTS
    FOR (m:_SchemaMetadata) REQUIRE m.version IS UNIQUE
    """,
)

INDEXES = (
    """
    CREATE INDEX resource_tenant_type IF NOT EXISTS
    FOR (r:Resource) ON (r.tenant_id, r.type)
    """,
    """
    CREATE INDEX resource_tenant_account IF NOT EXISTS
    FOR (r:Resource) ON (r.tenant_id, r.account_id)
    """,
    """
    CREATE INDEX resource_tenant_region IF NOT EXISTS
    FOR (r:Resource) ON (r.tenant_id, r.region)
    """,
)


async def apply_graph_migrations(driver: AsyncDriver) -> None:
    """Apply Neo4j constraints, indexes, and record migration version."""
    log = get_logger("graph.migrations")
    async with driver.session() as session:
        for stmt in CONSTRAINTS:
            await session.run(stmt.strip())
        for stmt in INDEXES:
            await session.run(stmt.strip())

        # Stamp migration version
        await session.run(
            """
            MERGE (m:_SchemaMetadata {version: $version})
            ON CREATE SET m.applied_at = datetime()
            """,
            {"version": SCHEMA_VERSION},
        )
    log.info("graph.schema.migrated", version=SCHEMA_VERSION)
