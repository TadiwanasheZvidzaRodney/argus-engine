from __future__ import annotations

import secrets

import pytest
from argus_api.cost.adapter import generate_daily_costs
from argus_api.cost.allocation import estimate_resource_cost, reconcile_period_totals
from argus_api.cost.rules import evaluate_optimization_rules
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


def test_cost_adapter_and_backfill_generation() -> None:
    # 30-day generation
    records_30d = generate_daily_costs(account_id=ACCOUNT, days=30)
    assert len(records_30d) > 0
    assert all(r.currency == "USD" for r in records_30d)
    assert all(r.amount > 0 for r in records_30d)

    # 365-day backfill generation
    records_12m = generate_daily_costs(account_id=ACCOUNT, days=365)
    assert len(records_12m) == len(records_30d) * 365 // 30 or len(records_12m) > 1000
    dates = {r.period_date for r in records_12m}
    assert len(dates) == 365


def test_allocation_and_reconciliation_invariant() -> None:
    # Estimate resource cost with confidence
    ec2_node = {
        "id": f"arn:aws:ec2:us-east-1:{ACCOUNT}:instance/i-0011223344",
        "type": "AWS::EC2::Instance",
        "properties": {"instance_type": "m5.xlarge"},
    }
    estimate = estimate_resource_cost(ec2_node)
    assert estimate.confidence.value == "estimated"
    assert estimate.monthly_amount == 144.00
    assert "On-demand baseline" in estimate.method

    vol_node = {
        "id": f"arn:aws:ec2:us-east-1:{ACCOUNT}:volume/vol-0011223344",
        "type": "AWS::EC2::Volume",
        "properties": {"size_gib": 200, "volume_type": "gp3"},
    }
    vol_estimate = estimate_resource_cost(vol_node)
    assert vol_estimate.confidence.value == "allocated"
    assert vol_estimate.monthly_amount == 16.00
    assert "EBS gp3" in vol_estimate.method

    # Invariant: allocated + unallocated == total
    total = 1000.00
    allocated, unallocated, variance = reconcile_period_totals(total, 750.00)
    assert allocated == 750.00
    assert unallocated == 250.00
    assert allocated + unallocated == total
    assert variance < 2.0


def test_nine_optimization_rules_produce_expected_hits() -> None:
    fixtures = [
        # 1. ec2-idle
        {
            "id": "arn:aws:ec2:us-east-1:123456789012:instance/i-idle",
            "type": "AWS::EC2::Instance",
            "state": "running",
            "properties": {"cpu_p95": 2.1, "instance_type": "m5.xlarge"},
        },
        # 2. ebs-unattached
        {
            "id": "arn:aws:ec2:us-east-1:123456789012:volume/vol-unattached",
            "type": "AWS::EC2::Volume",
            "state": "available",
            "properties": {"size_gib": 100, "attached_instance_id": None},
        },
        # 3. snapshot-stale
        {
            "id": "arn:aws:ec2:us-east-1:123456789012:snapshot/snap-stale",
            "type": "AWS::EC2::Snapshot",
            "state": "completed",
            "properties": {"age_days": 120, "size_gib": 50},
        },
        # 4. rds-idle
        {
            "id": "arn:aws:rds:us-east-1:123456789012:db:db-idle",
            "type": "AWS::RDS::DBInstance",
            "state": "available",
            "properties": {"active_connections": 0, "instance_class": "db.r6g.xlarge"},
        },
        # 5. ec2-oversized
        {
            "id": "arn:aws:ec2:us-east-1:123456789012:instance/i-oversized",
            "type": "AWS::EC2::Instance",
            "state": "running",
            "properties": {"instance_type": "m5.2xlarge", "cpu_p95": 8.0},
        },
        # 6. graviton-candidate
        {
            "id": "arn:aws:ec2:us-east-1:123456789012:instance/i-graviton",
            "type": "AWS::EC2::Instance",
            "state": "running",
            "properties": {"instance_type": "m5.large"},
        },
        # 7. s3-no-lifecycle
        {
            "id": "arn:aws:s3:::argus-no-lifecycle-bucket",
            "type": "AWS::S3::Bucket",
            "state": "active",
            "properties": {"has_lifecycle_rules": False},
        },
        # 8. idle-load-balancer
        {
            "id": f"arn:aws:elasticloadbalancing:us-east-1:{ACCOUNT}:loadbalancer/app/alb-idle",
            "type": "AWS::ElasticLoadBalancingV2::LoadBalancer",
            "state": "active",
            "properties": {"request_count_14d": 0},
        },
        # 9. unused-elastic-ip
        {
            "id": "arn:aws:ec2:us-east-1:123456789012:elastic-ip/eipalloc-123",
            "type": "AWS::EC2::EIP",
            "state": "unassociated",
            "properties": {"unassociated_eip": True},
        },
    ]

    hits = evaluate_optimization_rules(fixtures)
    assert len(hits) >= 9
    rule_ids = {h.rule_id for h in hits}
    assert {
        "ec2-idle",
        "ebs-unattached",
        "snapshot-stale",
        "rds-idle",
        "ec2-oversized",
        "graviton-candidate",
        "s3-no-lifecycle",
        "idle-load-balancer",
        "unused-elastic-ip",
    } <= rule_ids


def test_cost_sync_summary_and_breakdown_flow(client: TestClient, seeded_tenant: str) -> None:
    # Trigger sync
    sync_resp = client.post(
        "/api/v1/cost/sync",
        json={"account_id": ACCOUNT, "days": 30, "region": "us-east-1"},
        headers=_headers(seeded_tenant),
    )
    assert sync_resp.status_code == 200, sync_resp.text
    sync_data = sync_resp.json()
    assert sync_data["records_ingested"] > 0
    assert sync_data["total_spend"] > 0

    # Summary
    summary_resp = client.get("/api/v1/cost/summary", headers=_headers(seeded_tenant))
    assert summary_resp.status_code == 200, summary_resp.text
    summary = summary_resp.json()
    assert summary["total"] > 0
    assert summary["allocated"] > 0
    assert summary["unallocated"] >= 0
    assert summary["currency"] == "USD"
    assert len(summary["groups"]) > 0

    # Breakdown by service
    service_breakdown = client.get(
        "/api/v1/cost/breakdown",
        params={"dimension": "service", "days": 30},
        headers=_headers(seeded_tenant),
    )
    assert service_breakdown.status_code == 200
    assert len(service_breakdown.json()["items"]) > 0

    # Breakdown by tag:Environment
    tag_breakdown = client.get(
        "/api/v1/cost/breakdown",
        params={"dimension": "tag:Environment", "days": 30},
        headers=_headers(seeded_tenant),
    )
    assert tag_breakdown.status_code == 200
    assert len(tag_breakdown.json()["items"]) > 0

    # Trend and Forecast
    trend_resp = client.get(
        "/api/v1/cost/trend", params={"days": 30}, headers=_headers(seeded_tenant)
    )
    assert trend_resp.status_code == 200
    trend = trend_resp.json()
    assert len(trend["points"]) > 0
    assert trend["forecast_monthly"] > 0

    # Top spenders
    top_resp = client.get("/api/v1/cost/top", params={"limit": 5}, headers=_headers(seeded_tenant))
    assert top_resp.status_code == 200
    assert len(top_resp.json()["resources"]) > 0


def test_recommendation_lifecycle_and_remediation_handoff(
    client: TestClient, seeded_tenant: str
) -> None:
    # Run sync to evaluate recommendations on seeded graph
    client.post(
        "/api/v1/cost/sync",
        json={"account_id": ACCOUNT, "days": 30},
        headers=_headers(seeded_tenant),
    )

    # List recommendations
    recs_resp = client.get("/api/v1/cost/recommendations", headers=_headers(seeded_tenant))
    assert recs_resp.status_code == 200
    recs = recs_resp.json()
    assert len(recs) > 0

    # Find one with a remediation action (e.g. ec2-idle or graviton-candidate)
    remediable = next((r for r in recs if r.get("remediation")), None)
    assert remediable is not None
    rec_id = remediable["id"]

    # Acknowledge recommendation
    ack_resp = client.patch(
        f"/api/v1/cost/recommendations/{rec_id}",
        json={"status": "ACKNOWLEDGED"},
        headers=_headers(seeded_tenant),
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["status"] == "ACKNOWLEDGED"

    # Remediate via Phase 6 action engine
    rem_resp = client.post(
        f"/api/v1/cost/recommendations/{rec_id}/remediate",
        json={"constraints": {"environment": "staging"}},
        headers=_headers(seeded_tenant),
    )
    assert rem_resp.status_code == 200, rem_resp.text
    action_data = rem_resp.json()["action"]
    assert action_data["status"] == "PENDING_APPROVAL"
    assert action_data["action_type"] in (
        "ec2.stop_start_instance",
        "optimization.resize_instance",
    )


def test_budget_crud_and_threshold_tracking(client: TestClient, seeded_tenant: str) -> None:
    # Create budget
    create_resp = client.post(
        "/api/v1/cost/budgets",
        json={
            "name": "Production Monthly Cap",
            "scope_type": "tenant",
            "threshold_amount": 5000.00,
            "period": "monthly",
            "notification_channel": "slack:#finops-alerts",
        },
        headers=_headers(seeded_tenant),
    )
    assert create_resp.status_code == 201, create_resp.text
    bgt_id = create_resp.json()["id"]

    # List budgets
    list_resp = client.get("/api/v1/cost/budgets", headers=_headers(seeded_tenant))
    assert list_resp.status_code == 200
    budgets = list_resp.json()
    assert any(b["id"] == bgt_id for b in budgets)
    item = next(b for b in budgets if b["id"] == bgt_id)
    assert item["threshold_amount"] == 5000.00
    assert "percent_used" in item

    # Update budget
    update_resp = client.put(
        f"/api/v1/cost/budgets/{bgt_id}",
        json={"threshold_amount": 7500.00},
        headers=_headers(seeded_tenant),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["threshold_amount"] == 7500.00

    # Delete budget
    del_resp = client.delete(f"/api/v1/cost/budgets/{bgt_id}", headers=_headers(seeded_tenant))
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True


def test_cost_tenant_isolation(client: TestClient, seeded_tenant: str) -> None:
    client.post(
        "/api/v1/cost/sync",
        json={"account_id": ACCOUNT, "days": 15},
        headers=_headers(seeded_tenant),
    )

    other_tenant = str(new_uuid7())
    other_summary = client.get("/api/v1/cost/summary", headers=_headers(other_tenant))
    assert other_summary.status_code == 200
    assert other_summary.json()["total"] == 0.0
    assert other_summary.json()["groups"] == []

    other_recs = client.get("/api/v1/cost/recommendations", headers=_headers(other_tenant))
    assert other_recs.status_code == 200
    assert len(other_recs.json()) == 0
