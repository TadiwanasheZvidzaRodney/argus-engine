from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from argus_api.security.attack_paths import compute_attack_paths
from argus_api.security.rules import RULES, SecurityGraph, evaluate_rules
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


def _scan(client: TestClient, tenant: str, payload: dict[str, object] | None = None) -> dict:
    response = client.post(
        "/api/v1/security/scan",
        json=payload or {},
        headers=_headers(tenant),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _safe_graph() -> SecurityGraph:
    nodes = build_enterprise_topology(tenant_id=f"tnt_{new_uuid7()}", account_id=ACCOUNT)
    safe_nodes = []
    for node in nodes:
        props = dict(node.properties)
        if node.type == "AWS::EC2::SecurityGroup":
            props["ingress_rules"] = [
                {
                    "protocol": "tcp",
                    "from_port": 443,
                    "to_port": 443,
                    "cidr": "10.0.0.0/8",
                }
            ]
        elif node.type == "AWS::S3::Bucket":
            props.update(
                {
                    "versioning": "Enabled",
                    "default_encryption": "AES256",
                    "tls_enforced": True,
                    "policy_public": False,
                    "acl_public": False,
                    "public_access_block": True,
                }
            )
        elif node.type == "AWS::EC2::Volume":
            props["encrypted"] = True
        elif node.type == "AWS::RDS::DBInstance":
            props.update({"storage_encrypted": True, "publicly_accessible": False})
        elif node.type == "AWS::IAM::Role" and node.name == "ArgusAppServiceRole-123456":
            props["policy_documents"] = [
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": ["s3:GetObject", "s3:ListBucket"],
                            "Resource": f"arn:aws:s3:::argus-enterprise-data-{ACCOUNT}/*",
                        }
                    ],
                }
            ]
            props["trusted_principals"] = ["ec2.amazonaws.com"]
        elif node.type == "AWS::IAM::User":
            props["access_keys"] = [
                {
                    "access_key_id": "AKIARECENT",
                    "status": "Active",
                    "create_date": datetime.now(tz=UTC).isoformat(),
                }
            ]
        elif node.type == "AWS::Lambda::Function":
            props["function_url_auth_type"] = "AWS_IAM"
        elif node.type == "AWS::ApiGateway::RestApi":
            props["routes"] = [{"method": "GET", "path": "/payments", "authorization": "AWS_IAM"}]
        elif node.type == "AWS::CloudTrail::Trail":
            props["is_multi_region"] = True
        elif node.type == "AWS::GuardDuty::Detector":
            props["status"] = "ENABLED"
        safe_nodes.append({**node.model_dump(mode="json"), "properties": props})

    # Drop the deliberately risky auxiliary identities.
    safe_nodes = [
        node
        for node in safe_nodes
        if node["type"] != "AWS::IAM::Role" or node["name"] in {"ArgusAppServiceRole-123456"}
    ]
    return SecurityGraph(safe_nodes, [])


def test_rule_catalog_contains_twenty_curated_rules() -> None:
    assert len(RULES) == 20
    ids = {rule.id for rule in RULES}
    assert "sg-public-admin-port" in ids
    assert "guardduty-disabled" in ids
    assert all(rule.references for rule in RULES)
    assert all(rule.severity in {"critical", "high", "medium", "low"} for rule in RULES)


def test_rule_positive_and_negative_fixtures() -> None:
    tenant = f"tnt_{new_uuid7()}"
    nodes = build_enterprise_topology(tenant_id=tenant, account_id=ACCOUNT)
    graph = SecurityGraph([node.model_dump(mode="json") for node in nodes], [])
    hits = evaluate_rules(graph)
    rule_ids = {hit.rule_id for hit in hits}
    assert {
        "sg-public-admin-port",
        "sg-public-uncommon-port",
        "s3-public-policy",
        "s3-no-default-encryption",
        "s3-no-tls-enforcement",
        "s3-no-versioning",
        "ebs-unencrypted",
        "rds-unencrypted",
        "iam-privilege-escalation",
        "iam-trust-wildcard-principal",
        "iam-cross-account-trust-outside-org",
        "iam-old-access-key",
        "lambda-public-url",
        "apigw-unauthenticated",
        "cloudtrail-not-multiregion",
        "guardduty-disabled",
    } <= rule_ids
    assert all(hit.finding_key for hit in hits)
    assert all(hit.evidence for hit in hits)

    clean_hits = evaluate_rules(_safe_graph())
    assert clean_hits == []


def test_scan_dedupes_and_produces_findings(client: TestClient, seeded_tenant: str) -> None:
    first = _scan(client, seeded_tenant)
    assert first["created"] > 10
    assert first["rules_evaluated"] == 20

    second = _scan(client, seeded_tenant)
    assert second["created"] == 0
    assert second["updated"] == first["created"]

    response = client.get("/api/v1/findings", headers=_headers(seeded_tenant))
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["has_more"] is False
    assert len(page["items"]) == first["created"]
    severities = {item["severity"] for item in page["items"]}
    assert {"critical", "high", "medium"} <= severities

    summary = client.get("/api/v1/security/summary", headers=_headers(seeded_tenant))
    assert summary.status_code == 200
    assert summary.json()["total"] == first["created"]
    assert summary.json()["open_by_severity"].get("critical", 0) > 0

    rules = client.get("/api/v1/security/rules", headers=_headers(seeded_tenant))
    assert rules.status_code == 200
    assert len(rules.json()) == 20


def test_findings_lifecycle_and_remediation(client: TestClient, seeded_tenant: str) -> None:
    _scan(client, seeded_tenant)
    listing = client.get(
        "/api/v1/findings",
        params={"rule_id": "sg-public-admin-port"},
        headers=_headers(seeded_tenant),
    ).json()
    assert listing["items"]
    finding = listing["items"][0]
    finding_id = finding["id"]

    ack = client.patch(
        f"/api/v1/findings/{finding_id}",
        json={"status": "ACKNOWLEDGED", "comment": "investigating"},
        headers=_headers(seeded_tenant),
    )
    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == "ACKNOWLEDGED"

    expires = (datetime.now(tz=UTC) + timedelta(days=7)).isoformat()
    suppressed = client.patch(
        f"/api/v1/findings/{finding_id}",
        json={
            "status": "SUPPRESSED",
            "suppression_reason": "Compensating control WAF-123",
            "suppression_expires_at": expires,
        },
        headers=_headers(seeded_tenant),
    )
    assert suppressed.status_code == 200, suppressed.text
    assert suppressed.json()["status"] == "SUPPRESSED"
    assert suppressed.json()["suppression"] is not None

    # A rescan must keep the finding suppressed while the suppression is active.
    _scan(client, seeded_tenant)
    detail = client.get(f"/api/v1/findings/{finding_id}", headers=_headers(seeded_tenant))
    assert detail.json()["status"] == "SUPPRESSED"

    reopened = client.patch(
        f"/api/v1/findings/{finding_id}",
        json={"status": "OPEN", "comment": "suppression revoked"},
        headers=_headers(seeded_tenant),
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "OPEN"

    remediation = client.post(
        f"/api/v1/findings/{finding_id}/remediation",
        json={"constraints": {"environment": "staging"}},
        headers=_headers(seeded_tenant),
    )
    assert remediation.status_code == 201, remediation.text
    action = remediation.json()["action"]
    assert action["action_type"] == "network.restrict_security_group_ingress"
    assert action["status"] == "PENDING_APPROVAL"
    assert action["targets"]["target"] == detail.json()["resource_id"]

    refreshed = client.get(f"/api/v1/findings/{finding_id}", headers=_headers(seeded_tenant)).json()
    assert refreshed["remediation_action_id"] is not None
    assert refreshed["events"]


def test_attack_paths_include_golden_internet_to_data(
    client: TestClient, seeded_tenant: str
) -> None:
    _scan(client, seeded_tenant)
    response = client.post(
        "/api/v1/security/attack-paths",
        json={
            "source": "internet",
            "target_types": ["AWS::S3::Bucket", "AWS::RDS::DBInstance"],
            "max_depth": 8,
            "limit": 25,
        },
        headers=_headers(seeded_tenant),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["paths"]
    types = [{hop["type"] for hop in path["hops"]} for path in payload["paths"]]
    assert any("AWS::S3::Bucket" in path for path in types)
    assert any("AWS::IAM::Role" in path for path in types)
    assert all(path["score"] > 0 for path in payload["paths"])

    second = client.post(
        "/api/v1/security/attack-paths",
        json={
            "source": "internet",
            "target_types": ["AWS::S3::Bucket", "AWS::RDS::DBInstance"],
            "max_depth": 8,
            "limit": 25,
        },
        headers=_headers(seeded_tenant),
    )
    assert second.status_code == 200
    assert second.json()["cached"] is True


def test_findings_are_tenant_isolated(client: TestClient, seeded_tenant: str) -> None:
    _scan(client, seeded_tenant)
    other = str(new_uuid7())
    response = client.get("/api/v1/findings", headers=_headers(other))
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_overlay_and_exposures(client: TestClient, seeded_tenant: str) -> None:
    _scan(client, seeded_tenant)
    overlay = client.get("/api/v1/security/overlay", headers=_headers(seeded_tenant))
    assert overlay.status_code == 200
    resources = overlay.json()["resources"]
    assert resources
    assert any(entry["max_severity"] == "critical" for entry in resources.values())

    exposures = client.get("/api/v1/security/exposures", headers=_headers(seeded_tenant))
    assert exposures.status_code == 200
    assert exposures.json()["count"] >= 1
    assert exposures.json()["exposures"][0]["cidr"] in {"0.0.0.0/0", "::/0"}


def test_attack_path_ranking_is_deterministic() -> None:
    tenant = f"tnt_{new_uuid7()}"
    nodes = build_enterprise_topology(tenant_id=tenant, account_id=ACCOUNT)
    edges = [
        {
            "source": edge.source_id,
            "target": edge.target_id,
            "type": edge.type,
            "properties": edge.properties,
        }
        for edge in RelationshipResolver.resolve(tenant, nodes)
    ]
    graph = SecurityGraph([node.model_dump(mode="json") for node in nodes], edges)
    # Add the derived edges without Neo4j so this stays a pure unit test.
    bucket = next(n for n in graph.nodes if n["type"] == "AWS::S3::Bucket")
    role = next(n for n in graph.nodes if n["type"] == "AWS::IAM::Role")
    instance = next(n for n in graph.nodes if n["type"] == "AWS::EC2::Instance")
    graph.edges.append(
        {
            "source": instance["id"],
            "target": role["id"],
            "type": "ASSUMES",
            "properties": {},
        }
    )
    graph.edges.append(
        {
            "source": role["id"],
            "target": bucket["id"],
            "type": "CAN_ACCESS",
            "properties": {},
        }
    )
    graph.__init__(graph.nodes, graph.edges)

    first = compute_attack_paths(graph, target_types=["AWS::S3::Bucket"])
    second = compute_attack_paths(graph, target_types=["AWS::S3::Bucket"])
    assert first.paths
    assert [path["score"] for path in first.paths] == [path["score"] for path in second.paths]
    assert first.paths[0]["hops"][0]["type"] in {
        "AWS::EC2::SecurityGroup",
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        "AWS::Lambda::Function",
        "AWS::S3::Bucket",
    }
