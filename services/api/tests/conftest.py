from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from argus_api.main import create_app
from argus_api.settings import ApiSettings
from argus_core.health import CheckState, run_check
from argus_core.idempotency import InMemoryIdempotencyStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


def make_settings(**overrides: Any) -> ApiSettings:
    defaults: dict[str, Any] = {
        "env": "test",
        "docs_enabled": True,
        "log_format": "json",
        "cors_origins": ["http://localhost:3000"],
        "_env_file": None,
    }
    defaults.update(overrides)
    return ApiSettings(**defaults)


@pytest.fixture
def store() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


@pytest.fixture
def app(store: InMemoryIdempotencyStore) -> FastAPI:
    return create_app(make_settings(), ready_checks=[], idempotency_store=store)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def failing_client() -> Iterator[TestClient]:
    async def broken() -> None:
        raise ConnectionError("postgres down")

    app = create_app(
        make_settings(),
        ready_checks=[lambda: run_check("postgres", broken)],
        idempotency_store=InMemoryIdempotencyStore(),
    )
    with TestClient(app) as test_client:
        yield test_client


__all__ = ["CheckState", "make_settings"]
