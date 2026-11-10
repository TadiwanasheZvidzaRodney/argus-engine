from __future__ import annotations

from typing import Any

import pytest
from argus_core.health import CheckState, build_report, liveness_report, run_check
from argus_core.middleware import RequestContextMiddleware
from argus_core.settings import Settings


async def test_liveness_does_not_require_dependencies() -> None:
    report = await liveness_report(Settings(_env_file=None))
    assert report.status is CheckState.OK
    assert report.checks == []


async def test_readiness_reports_failed_dependency() -> None:
    async def broken() -> None:
        raise TimeoutError

    async def healthy() -> None:
        return None

    report = await build_report(
        Settings(_env_file=None),
        [lambda: run_check("redis", healthy), lambda: run_check("postgres", broken)],
    )
    assert report.status is CheckState.FAIL
    assert {c.name: c.state for c in report.checks} == {
        "redis": CheckState.OK,
        "postgres": CheckState.FAIL,
    }


async def test_probe_failures_never_escape() -> None:
    async def broken() -> None:
        raise ConnectionError("boom")

    result = await run_check("neo4j", broken)
    assert result.state is CheckState.FAIL
    assert result.detail == "ConnectionError"


class _Harness:
    """Drives the middleware with a minimal ASGI app and records the exchange."""

    def __init__(self, settings: Settings, headers: list[tuple[bytes, bytes]]) -> None:
        self.settings = settings
        self.scope: dict[str, Any] = {
            "type": "http",
            "method": "GET",
            "path": "/healthz",
            "headers": headers,
            "state": {},
        }
        self.sent: list[dict[str, Any]] = []

    async def __aenter__(self) -> _Harness:
        async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        async def send(message: dict[str, Any]) -> None:
            self.sent.append(message)

        middleware = RequestContextMiddleware(app, self.settings)
        await middleware(self.scope, None, send)
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    @property
    def response_headers(self) -> dict[bytes, bytes]:
        return dict(self.sent[0]["headers"])

    @property
    def state(self) -> dict[str, Any]:
        return self.scope["state"]


async def test_generates_request_id_when_absent() -> None:
    async with _Harness(Settings(_env_file=None), []) as harness:
        assert harness.response_headers[b"x-request-id"].startswith(b"req_")
        assert harness.state["request_id"].startswith("req_")


async def test_accepts_well_formed_request_id() -> None:
    async with _Harness(
        Settings(_env_file=None), [(b"x-request-id", b"req_client-supplied-1234")]
    ) as harness:
        assert harness.response_headers[b"x-request-id"] == b"req_client-supplied-1234"


@pytest.mark.parametrize(
    "injected", [b"short", b"bad value with spaces", b"x" * 200, b"../../etc/passwd"]
)
async def test_rejects_unsafe_request_ids(injected: bytes) -> None:
    async with _Harness(Settings(_env_file=None), [(b"x-request-id", injected)]) as harness:
        assert harness.response_headers[b"x-request-id"] != injected
        assert harness.response_headers[b"x-request-id"].startswith(b"req_")


async def test_tenant_header_is_bound_in_local_only() -> None:
    async with _Harness(
        Settings(_env_file=None), [(b"x-argus-tenant", b"tnt_0190c3a1-0000-7000-8000-000000000000")]
    ) as local:
        assert local.state["tenant_id"] == "tnt_0190c3a1-0000-7000-8000-000000000000"

    async with _Harness(
        Settings(_env_file=None, env="dev"),
        [(b"x-argus-tenant", b"tnt_0190c3a1-0000-7000-8000-000000000000")],
    ) as dev:
        # Outside local, tenancy comes from the verified token, never a header.
        assert dev.state["tenant_id"] is None
