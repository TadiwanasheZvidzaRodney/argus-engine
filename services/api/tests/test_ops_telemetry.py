from __future__ import annotations

import secrets
from datetime import UTC, datetime

import pytest
from argus_api.ops.service import generate_ops_timeseries
from argus_core.events import new_uuid7
from argus_core.graph.client import build_graph_driver
from argus_core.graph.repository import GraphRepository
from argus_core.settings import Settings
from argus_worker.discovery.adapters.sample_data import build_enterprise_topology
from argus_worker.discovery.resolvers import RelationshipResolver
from fastapi.testclient import TestClient

ACCOUNT = "123456789012"
OWNER = str(new_uuid7())


def _headers(tenant: str) -> dict[str, str]:
    return {
        "Authorization": f"stub:{OWNER}:{tenant}:owner:owner@argus.local",
        "Idempotency-Key": f"key-{secrets.token_hex(8)}",
    }


@pytest.fixture
async def seeded_tenant() -> str:
    tenant = str(new_uuid7())
    tenant_key = f"tnt_{tenant}"
    settings = Settings(neo4j_uri="bolt://127.0.0.1:7687", _env_file=None)
    driver = build_graph_driver(settings)
    repo = GraphRepository(driver)
    nodes = build_enterprise_topology(tenant_id=tenant_key, account_id=ACCOUNT)
    edges = RelationshipResolver.resolve(tenant_key, nodes)
    await repo.upsert_nodes(tenant_key, nodes)
    await repo.upsert_edges(tenant_key, edges)
    try:
        yield tenant
    finally:
        async with driver.session() as session:
            await session.run(
                "MATCH (n:Resource {tenant_id: $tenant}) DETACH DELETE n",
                {"tenant": tenant_key},
            )
        await driver.close()


def test_generate_ops_timeseries_today_starts_at_midnight() -> None:
    ref = datetime(2026, 11, 18, 14, 30, 0, tzinfo=UTC)
    points = generate_ops_timeseries("today", reference_time=ref)
    assert len(points) >= 2
    # First point must be midnight 00:00
    assert points[0]["time_label"] == "00:00"
    assert points[0]["timestamp"].startswith("2026-11-18T00:00:00")
    # All required golden signal metrics must be present
    for p in points:
        assert "availability_percent" in p
        assert "throughput_req_min" in p
        assert "latency_p95_ms" in p
        assert "latency_p99_ms" in p
        assert "error_rate_percent" in p
        assert "errors_5xx_count" in p
        assert "ecs_running_tasks" in p
        assert "db_pool_errors" in p


def test_generate_ops_timeseries_all_ranges() -> None:
    ref = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)

    p_24h = generate_ops_timeseries("24h", reference_time=ref)
    assert len(p_24h) == 24

    p_7d = generate_ops_timeseries("7d", reference_time=ref)
    assert len(p_7d) == 28

    p_30d = generate_ops_timeseries("30d", reference_time=ref)
    assert len(p_30d) == 30


def test_wallboard_telemetry_endpoint_filters(client: TestClient, seeded_tenant: str) -> None:
    # Test default range ("today")
    res = client.get("/api/v1/ops/wallboard", headers=_headers(seeded_tenant))
    assert res.status_code == 200, res.text
    data = res.json()
    assert "telemetry_history" in data
    assert data["time_range"] == "today"
    assert len(data["telemetry_history"]) >= 2
    assert data["telemetry_history"][0]["time_label"] == "00:00"

    # Test range=7d
    res_7d = client.get("/api/v1/ops/wallboard?range=7d", headers=_headers(seeded_tenant))
    assert res_7d.status_code == 200, res_7d.text
    data_7d = res_7d.json()
    assert data_7d["time_range"] == "7d"
    assert len(data_7d["telemetry_history"]) == 28

    # Test range=30d
    res_30d = client.get("/api/v1/ops/wallboard?range=30d", headers=_headers(seeded_tenant))
    assert res_30d.status_code == 200, res_30d.text
    assert res_30d.json()["time_range"] == "30d"
