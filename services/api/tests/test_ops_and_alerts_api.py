from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from argus_api.ops.service import check_and_escalate_repeated_alerts
from argus_core.events import new_uuid7
from argus_core.graph.client import build_graph_driver
from argus_core.graph.repository import GraphRepository
from argus_core.settings import Settings
from argus_worker.discovery.adapters.sample_data import build_enterprise_topology
from argus_worker.discovery.resolvers import RelationshipResolver
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

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


def test_ops_wallboard_aggregated_payload(client: TestClient, seeded_tenant: str) -> None:
    res = client.get("/api/v1/ops/wallboard", headers=_headers(seeded_tenant))
    assert res.status_code == 200, res.text
    data = res.json()

    assert "status_banner" in data
    assert data["status_banner"]["state"] in ("ALL_CLEAR", "ALERTS_FIRING")
    assert "golden_signals" in data
    assert data["golden_signals"]["availability_percent"] >= 99.0
    assert data["golden_signals"]["latency_p95_ms"] > 0
    assert len(data["ecs_systems"]) >= 1
    assert "database_vitals" in data
    assert "alb_vitals" in data


def test_trigger_alert_and_acknowledge_lifecycle(client: TestClient, seeded_tenant: str) -> None:
    # 1. Trigger an action-required operational alert
    trig_res = client.post(
        "/api/v1/ops/alerts",
        json={
            "alert_key": "ecs-task-crash-loop",
            "title": "ECS api-service task crash loop detected",
            "description": "Container exited with code 137 (OOMKilled) 3 times in 10 minutes.",
            "source": "ecs",
            "severity": "critical",
            "resource_id": f"arn:aws:ecs:us-west-2:{ACCOUNT}:service/api-service",
            "requires_action": True,
            "notification_email": "devops@zimworx.com",
        },
        headers=_headers(seeded_tenant),
    )
    assert trig_res.status_code == 201, trig_res.text
    alert_info = trig_res.json()
    alert_id = alert_info["id"]
    assert alert_info["status"] == "FIRING"
    assert alert_info["notification_count"] == 1

    # 2. Verify wallboard banner changes to ALERTS_FIRING
    wb_res = client.get("/api/v1/ops/wallboard", headers=_headers(seeded_tenant))
    assert wb_res.status_code == 200
    assert wb_res.json()["status_banner"]["state"] == "ALERTS_FIRING"
    assert wb_res.json()["status_banner"]["firing_alerts_count"] >= 1

    # 3. Acknowledge alert
    ack_res = client.post(
        f"/api/v1/ops/alerts/{alert_id}/ack",
        headers=_headers(seeded_tenant),
    )
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == "ACKNOWLEDGED"

    # 4. Resolve alert
    resolve_res = client.post(
        f"/api/v1/ops/alerts/{alert_id}/resolve",
        headers=_headers(seeded_tenant),
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "RESOLVED"


async def test_repeated_alert_escalation_engine() -> None:
    settings = Settings(_env_file=None)
    engine = create_async_engine(settings.database_url, echo=False)
    tenant_id = new_uuid7()

    async with engine.begin() as conn:
        alert_id = new_uuid7()
        stale_time = datetime.now(tz=UTC) - timedelta(minutes=45)
        await conn.execute(
            text("""
                INSERT INTO ops_alerts (
                    id, tenant_id, alert_key, severity, title, description, source,
                    status, requires_action, repeat_interval_minutes, notification_email,
                    notification_count, last_notified_at
                ) VALUES (
                    :id, :tid, 'ecs-oom-stale', 'critical', 'Critical Memory Breach',
                    'Service memory exceeded limit.', 'ecs', 'FIRING', true, 30,
                    'devops@zimworx.com', 1, :stale
                );
            """),
            {"id": alert_id, "tid": tenant_id, "stale": stale_time},
        )

    # Use session to trigger escalation check
    from argus_api.db import build_session_factory

    factory = build_session_factory(engine)
    async with factory() as session:
        escalated = await check_and_escalate_repeated_alerts(session, tenant_id)
        assert escalated >= 1

    await engine.dispose()


def test_test_email_dispatch_to_devops_group(client: TestClient, seeded_tenant: str) -> None:
    res = client.post(
        "/api/v1/ops/alerts/test-email",
        json={
            "to_email": "devops@zimworx.com",
            "subject": "[TEST] Argus Engine Operations Hub Verification",
            "message": "Testing SMTP mailer delivery to devops@zimworx.com.",
        },
        headers=_headers(seeded_tenant),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["to_email"] == "devops@zimworx.com"
    assert data["success"] is True
    assert data["mode"] == "mailpit"


def test_ops_alerts_tenant_isolation(client: TestClient, seeded_tenant: str) -> None:
    client.post(
        "/api/v1/ops/alerts",
        json={
            "alert_key": "tenant-a-test",
            "title": "Tenant A Exclusive Alert",
            "description": "Should not be seen by Tenant B.",
        },
        headers=_headers(seeded_tenant),
    )

    other = str(new_uuid7())
    res = client.get("/api/v1/ops/alerts", headers=_headers(other))
    assert res.status_code == 200
    assert len(res.json()) == 0
