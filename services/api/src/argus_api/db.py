"""Database engine construction and readiness probe."""

from __future__ import annotations

from argus_core.settings import Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(settings: Settings, *, pool_size: int = 5) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_size=pool_size,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=False,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def probe(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.execute(text("select 1"))


async def expected_schema_version(engine: AsyncEngine) -> str | None:
    """Read the schema version stamped by the latest migration."""
    async with engine.connect() as connection:
        result = await connection.execute(text("select version from schema_metadata limit 1"))
        value = result.scalar_one_or_none()
        return str(value) if value is not None else None
