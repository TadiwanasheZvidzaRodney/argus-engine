"""Application factory for the Argus API.

Everything is injectable so tests never need a live Postgres or Redis, and the
same factory serves local dev, staging, and production with different settings.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from argus_core.errors import Problem
from argus_core.health import Check, run_check
from argus_core.idempotency import IdempotencyStore, InMemoryIdempotencyStore, RedisIdempotencyStore
from argus_core.logging import configure_logging
from argus_core.middleware import RequestContextMiddleware
from argus_core.settings import Environment
from argus_core.telemetry import configure_telemetry
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from argus_api.db import build_engine, probe
from argus_api.errors import install_exception_handlers
from argus_api.middleware import IdempotencyMiddleware, SecurityHeadersMiddleware
from argus_api.routers.demo import build_demo_router
from argus_api.routers.health import build_health_router
from argus_api.routers.meta import build_meta_router
from argus_api.settings import ApiSettings


def _redis_ping(client: Redis) -> Any:
    async def check() -> None:
        await client.ping()

    return check


def _default_checks(engine: AsyncEngine, redis_client: Redis) -> list[Check]:
    return [
        lambda: run_check("postgres", lambda: probe(engine)),
        lambda: run_check("redis", _redis_ping(redis_client)),
    ]


def create_app(
    settings: ApiSettings | None = None,
    *,
    ready_checks: Sequence[Check] | None = None,
    idempotency_store: IdempotencyStore | None = None,
) -> FastAPI:
    settings = settings or ApiSettings()
    configure_logging(settings)
    configure_telemetry(settings)

    redis_client: Redis | None = None
    if idempotency_store is None:
        if settings.env is Environment.TEST:
            idempotency_store = InMemoryIdempotencyStore()
        else:
            redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
            idempotency_store = RedisIdempotencyStore(redis_client)

    engine = build_engine(settings)
    checks = (
        list(ready_checks)
        if ready_checks is not None
        else (_default_checks(engine, redis_client) if redis_client is not None else [])
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()
        if redis_client is not None:
            await redis_client.aclose()

    app = FastAPI(
        title="Argus Engine API",
        version=settings.service_version,
        description=(
            "Read and administration API for the Argus AWS topology graph. "
            "All errors use RFC 9457 problem details."
        ),
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        root_path=settings.root_path,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.idempotency_store = idempotency_store

    install_exception_handlers(app)

    app.include_router(build_health_router(settings, lambda: checks))
    app.include_router(build_meta_router(settings))
    if settings.docs_enabled or settings.env is not Environment.PROD:
        app.include_router(build_demo_router(settings))

    # Added innermost first; Starlette applies the last-added middleware outermost.
    app.add_middleware(
        IdempotencyMiddleware,
        store=idempotency_store,
        ttl_seconds=settings.idempotency_ttl_seconds,
        lock_seconds=settings.idempotency_lock_seconds,
        max_body_bytes=settings.max_request_bytes,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-Id"],
        expose_headers=["X-Request-Id", "X-Trace-Id", "X-Idempotent-Replay"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware)

    if settings.otel_enabled:
        FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz")

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components["Problem"] = Problem.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        components["FieldError"] = Problem.model_json_schema()["$defs"]["FieldError"]
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app


def app_factory() -> FastAPI:
    """ASGI entry point for ``uvicorn argus_api.main:app_factory --factory``."""
    return create_app()
