from __future__ import annotations

import secrets

import pytest
from argus_api.telemetry.anomaly import detect_anomalies
from argus_api.telemetry.catalog import MetricDefinition
from argus_api.telemetry.collector import generate_series
from argus_core.events import new_uuid7
from argus_core.graph.client import build_graph_driver
from argus_core.graph.repository import GraphRepository
from argus_core.settings import Settings
from argus_worker.discovery.adapters.sample_data import build_enterprise_topology
from argus_worker.discovery.resolvers import RelationshipResolver
from fastapi.testclient import TestClient

ACCOUNT = "123456789012"
OWNER = str(new_uuid7())


def _headers(tenant: str, role: str = "owner", key: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"stub:{OWNER}:{tenant}:{role}:{role}@argus.local",
        "Idempotency-Key": key or f"key-{secrets.token_hex(8)}",
    }


@pytest.fixture
async def seeded_tenant() -> str:
    tenant = str(new_uuid7())
    tenant_key = f"tnt_{tenant}"
    driver = build_graph_driver(Settings(_env_file=None))
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


def _instance_arn() -> str:
    return f"arn:aws:ec2:us-east-1:{ACCOUNT}:instance/i-0{ACCOUNT[:4]}11223344"


def test_catalog_lists_expected_metrics(client: TestClient, seeded_tenant: str) -> None:
    response = client.get("/api/v1/telemetry/catalog", headers=_headers(seeded_tenant))
    assert response.status_code == 200, response.text
    catalog = {item["resource_type"]: item for item in response.json()}
    assert "AWS::EC2::Instance" in catalog
    names = {metric["name"] for metric in catalog["AWS::EC2::Instance"]["metrics"]}
    assert {"CPUUtilization", "NetworkIn", "StatusCheckFailed"} <= names
    assert "AWS::RDS::DBInstance" in catalog
    assert "AWS::Lambda::Function" in catalog


def test_snapshot_returns_deterministic_points(client: TestClient, seeded_tenant: str) -> None:
    body = {
        "resource_ids": [_instance_arn()],
        "metrics": ["CPUUtilization", "NetworkIn"],
        "resolution": 60,
        "periods": 12,
    }
    first = client.post("/api/v1/telemetry/snapshot", json=body, headers=_headers(seeded_tenant))
    assert first.status_code == 200, first.text
    payload = first.json()
    assert len(payload["samples"]) == 2
    for sample in payload["samples"]:
        assert len(sample["points"]) == 12
        assert sample["unit"] in {"Percent", "Bytes"}
        assert sample["resolution"] == 60
    cpu = next(sample for sample in payload["samples"] if sample["metric"] == "CPUUtilization")
    second = client.post(
        "/api/v1/telemetry/snapshot", json=body, headers=_headers(seeded_tenant)
    ).json()
    cpu_second = next(
        sample for sample in second["samples"] if sample["metric"] == "CPUUtilization"
    )
    assert cpu["points"] == cpu_second["points"]
    assert payload["quota"]["metric_requests"] >= 2


def test_subscription_lifecycle_and_stream(client: TestClient, seeded_tenant: str) -> None:
    created = client.post(
        "/api/v1/telemetry/subscriptions",
        json={
            "resource_ids": [_instance_arn()],
            "metrics": ["CPUUtilization"],
            "resolution": 60,
        },
        headers=_headers(seeded_tenant),
    )
    assert created.status_code == 201, created.text
    subscription = created.json()
    assert subscription["status"] == "active"
    assert subscription["quota"] is not None

    fetched = client.get(
        f"/api/v1/telemetry/subscriptions/{subscription['id']}",
        headers=_headers(seeded_tenant),
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == subscription["id"]

    stream = client.get(
        "/api/v1/telemetry/stream",
        params={"subscription_id": subscription["id"], "periods": 3, "iterations": 1},
        headers=_headers(seeded_tenant),
    )
    assert stream.status_code == 200, stream.text
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: telemetry.sample" in stream.text
    assert subscription["id"] in stream.text
    assert "CPUUtilization" in stream.text

    cancelled = client.delete(
        f"/api/v1/telemetry/subscriptions/{subscription['id']}",
        headers=_headers(seeded_tenant),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_subscriptions_are_tenant_isolated(client: TestClient, seeded_tenant: str) -> None:
    created = client.post(
        "/api/v1/telemetry/subscriptions",
        json={
            "resource_ids": [_instance_arn()],
            "metrics": ["CPUUtilization"],
            "resolution": 300,
        },
        headers=_headers(seeded_tenant),
    ).json()
    other = str(new_uuid7())
    response = client.get(
        f"/api/v1/telemetry/subscriptions/{created['id']}",
        headers=_headers(other),
    )
    assert response.status_code == 404

    quota = client.get("/api/v1/telemetry/quota", headers=_headers(other))
    assert quota.status_code == 200
    assert quota.json()["metric_requests"] == 0


def test_subscription_validation(client: TestClient, seeded_tenant: str) -> None:
    bad_resolution = client.post(
        "/api/v1/telemetry/subscriptions",
        json={
            "resource_ids": [_instance_arn()],
            "metrics": ["CPUUtilization"],
            "resolution": 42,
        },
        headers=_headers(seeded_tenant),
    )
    assert bad_resolution.status_code == 422

    missing_metrics = client.post(
        "/api/v1/telemetry/subscriptions",
        json={"resource_ids": [_instance_arn()], "metrics": [], "resolution": 60},
        headers=_headers(seeded_tenant),
    )
    assert missing_metrics.status_code == 422


def test_anomaly_detection_threshold_and_z_score() -> None:
    metric = MetricDefinition("CPUUtilization", "Percent", threshold=80.0)
    points = [(index * 60_000, 20.0 + index * 0.2) for index in range(20)]
    points.append((20 * 60_000, 99.0))
    anomalies = detect_anomalies(points, metric)
    kinds = {anomaly.kind for anomaly in anomalies}
    assert "threshold" in kinds
    assert "z-score" in kinds
    assert all(anomaly.value for anomaly in anomalies)


def test_series_generation_is_deterministic_and_downsamplable() -> None:
    first = generate_series(
        resource_id=_instance_arn(),
        resource_type="AWS::EC2::Instance",
        metric="CPUUtilization",
        resolution=60,
        periods=10,
    )
    second = generate_series(
        resource_id=_instance_arn(),
        resource_type="AWS::EC2::Instance",
        metric="CPUUtilization",
        resolution=60,
        periods=10,
    )
    assert first.points == second.points
    assert first.unit == "Percent"
    assert all(0 <= value <= 300 for _, value in first.points)
