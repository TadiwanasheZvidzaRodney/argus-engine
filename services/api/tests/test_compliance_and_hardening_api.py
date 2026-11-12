from __future__ import annotations

import secrets

import pytest
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
    settings = Settings(_env_file=None)
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


def test_compliance_frameworks_and_controls_catalog(client: TestClient, seeded_tenant: str) -> None:
    resp = client.get("/api/v1/compliance/frameworks", headers=_headers(seeded_tenant))
    assert resp.status_code == 200, resp.text
    frameworks = resp.json()
    assert len(frameworks) >= 3
    fw_names = {f["framework"] for f in frameworks}
    assert {"SOC2", "CIS-AWS", "NIST-800-53"} <= fw_names

    controls_resp = client.get(
        "/api/v1/compliance/controls",
        params={"framework": "SOC2"},
        headers=_headers(seeded_tenant),
    )
    assert controls_resp.status_code == 200
    controls = controls_resp.json()
    assert len(controls) >= 5
    ctrl_ids = {c["control_id"] for c in controls}
    assert {"CC6.1", "CC6.6", "CC6.8", "CC7.2", "CC8.1"} <= ctrl_ids


def test_automated_evidence_collection_and_locker(client: TestClient, seeded_tenant: str) -> None:
    # Trigger security scan first to create realistic findings
    client.post("/api/v1/security/scan", json={}, headers=_headers(seeded_tenant))

    # Run automated evidence collection
    collect_resp = client.post(
        "/api/v1/compliance/collect",
        params={"framework": "SOC2"},
        headers=_headers(seeded_tenant),
    )
    assert collect_resp.status_code == 200, collect_resp.text
    records = collect_resp.json()
    assert len(records) > 0
    assert all(r["evidence_hash"] for r in records)

    # Check evidence for CC6.6 (Perimeter & Network Segmentation)
    ev_resp = client.get(
        "/api/v1/compliance/evidence/CC6.6",
        params={"framework": "SOC2"},
        headers=_headers(seeded_tenant),
    )
    assert ev_resp.status_code == 200, ev_resp.text
    ev = ev_resp.json()
    assert ev["control_id"] == "CC6.6"
    assert ev["framework"] == "SOC2"
    assert len(ev["evidence_hash"]) == 64
    assert ev["status"] in ("PASS", "FAIL", "WARN")
    assert "timestamp" in ev["payload"]


def test_compliance_export_audit_package(client: TestClient, seeded_tenant: str) -> None:
    # Run collection
    client.post(
        "/api/v1/compliance/collect",
        params={"framework": "SOC2"},
        headers=_headers(seeded_tenant),
    )

    export_resp = client.get(
        "/api/v1/compliance/export",
        params={"framework": "SOC2"},
        headers=_headers(seeded_tenant),
    )
    assert export_resp.status_code == 200, export_resp.text
    data = export_resp.json()
    assert data["verification_status"] == "SEALED_IMMUTABLE"
    assert data["package_signature"].startswith("sha256:")
    manifest = data["manifest"]
    assert manifest["framework"] == "SOC2"
    assert manifest["total_controls"] > 0
    assert "compliance_score_percent" in manifest
    assert len(manifest["controls"]) > 0


def test_system_status_and_slos(client: TestClient) -> None:
    resp = client.get("/api/v1/admin/status")
    assert resp.status_code == 200, resp.text
    status_data = resp.json()
    assert status_data["overall_status"] in ("OPERATIONAL", "DEGRADED")
    assert len(status_data["dependencies"]) >= 4
    assert len(status_data["slos"]) >= 5

    slo_names = {s["slo_name"] for s in status_data["slos"]}
    assert "Control-plane API Availability" in slo_names
    assert "Read Request Latency (<500ms)" in slo_names
    assert all("error_budget_burn_percent" in s for s in status_data["slos"])


def test_degraded_modes_lifecycle(client: TestClient, seeded_tenant: str) -> None:
    # Read initial status
    initial = client.get("/api/v1/admin/degraded", headers=_headers(seeded_tenant))
    assert initial.status_code == 200

    # Set degraded mode (read-only, actions disabled)
    updated = client.post(
        "/api/v1/admin/degraded",
        json={
            "read_only": True,
            "actions_disabled": True,
            "maintenance_message": "Scheduled maintenance window.",
            "scope": "tenant",
        },
        headers=_headers(seeded_tenant),
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()
    assert data["read_only"] is True
    assert data["actions_disabled"] is True
    assert data["is_degraded"] is True
    assert data["maintenance_message"] == "Scheduled maintenance window."

    # Reset
    reset = client.post(
        "/api/v1/admin/degraded",
        json={"read_only": False, "actions_disabled": False, "scope": "tenant"},
        headers=_headers(seeded_tenant),
    )
    assert reset.status_code == 200
    assert reset.json()["is_degraded"] is False


def test_usage_metering_and_unit_economics(client: TestClient, seeded_tenant: str) -> None:
    record_resp = client.post(
        "/api/v1/admin/metering/record",
        json={
            "resources_count": 250,
            "events_ingested": 1000,
            "metric_requests": 500,
            "actions_planned": 5,
            "actions_executed": 2,
            "storage_bytes": 1048576,
        },
        headers=_headers(seeded_tenant),
    )
    assert record_resp.status_code == 200, record_resp.text
    metering = record_resp.json()
    assert metering["resources_count"] == 250
    assert metering["estimated_cost_usd"] > 0

    list_resp = client.get("/api/v1/admin/metering", headers=_headers(seeded_tenant))
    assert list_resp.status_code == 200
    history = list_resp.json()
    assert len(history) >= 1
    assert history[0]["resources_count"] == 250


def test_dr_failover_drill_simulation(client: TestClient, seeded_tenant: str) -> None:
    resp = client.post("/api/v1/admin/dr-drill", headers=_headers(seeded_tenant))
    assert resp.status_code == 200, resp.text
    drill = resp.json()
    assert drill["overall_status"] == "SUCCESS"
    assert drill["primary_region"] == "us-east-1"
    assert drill["recovery_region"] == "us-west-2"
    assert drill["rto_achieved_minutes"] <= 60
    assert drill["rpo_achieved_minutes"] <= 15
    assert len(drill["checks"]) >= 4


def test_compliance_and_metering_tenant_isolation(client: TestClient, seeded_tenant: str) -> None:
    client.post(
        "/api/v1/compliance/collect",
        params={"framework": "SOC2"},
        headers=_headers(seeded_tenant),
    )

    other = str(new_uuid7())
    other_evidence = client.get(
        "/api/v1/compliance/evidence/CC6.1",
        params={"framework": "SOC2"},
        headers=_headers(other),
    )
    assert other_evidence.status_code == 404

    other_metering = client.get("/api/v1/admin/metering", headers=_headers(other))
    assert other_metering.status_code == 200
    assert len(other_metering.json()) == 0
