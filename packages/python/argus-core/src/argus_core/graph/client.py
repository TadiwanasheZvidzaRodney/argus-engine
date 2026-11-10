"""Neo4j driver construction and lifecycle management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from argus_core.settings import Settings
from neo4j import AsyncDriver, AsyncGraphDatabase

if TYPE_CHECKING:
    pass


def build_graph_driver(settings: Settings) -> AsyncDriver:
    """Build an asynchronous Neo4j Bolt driver."""
    auth = (settings.neo4j_user, settings.neo4j_password.get_secret_value())
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=auth,
        max_connection_pool_size=25,
        connection_timeout=5.0,
    )


async def graph_probe(driver: AsyncDriver) -> None:
    """Readiness probe checking Neo4j Bolt connectivity."""
    async with driver.session() as session:
        result = await session.run("RETURN 1 AS alive")
        record = await result.single()
        if not record or record["alive"] != 1:
            raise ConnectionError("Neo4j probe query returned invalid response")
