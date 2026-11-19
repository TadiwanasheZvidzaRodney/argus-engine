from __future__ import annotations

import base64
import secrets
from collections.abc import AsyncIterator

import pytest
from argus_core.events import new_uuid7
from argus_core.graph.client import build_graph_driver
from argus_core.graph.repository import GraphRepository
from argus_core.settings import Settings
from argus_worker.discovery.adapters.sample_data import build_enterprise_topology
from argus_worker.discovery.resolvers import RelationshipResolver
from fastapi.testclient import TestClient

ACCOUNT = "123456789012"
VPC_ARN = f"arn:aws:ec2:us-east-1:{ACCOUNT}:vpc/vpc-0{ACCOUNT[:4]}1122"
SUBNET_ARN = f"arn:aws:ec2:us-east-1:{ACCOUNT}:subnet/subnet-0{ACCOUNT[:4]}5566"
OWNER = str(new_uuid7())


def _headers(tenant: str) -> dict[str, str]:
    return {
        "Authorization": f"stub:{OWNER}:{tenant}:owner:owner@argus.local",
    }


@pytest.fixture
async def graph_tenant() -> AsyncIterator[str]:
    tenant_uuid = new_uuid7()
    tenant_key = f"tnt_{tenant_uuid}"
    settings = Settings(neo4j_uri="bolt://127.0.0.1:7687", _env_file=None)
    driver = build_graph_driver(settings)
    repo = GraphRepository(driver)
    nodes = build_enterprise_topology(tenant_id=tenant_key, account_id=ACCOUNT)
    edges = RelationshipResolver.resolve(tenant_key, nodes)
    await repo.upsert_nodes(tenant_key, nodes)
    await repo.upsert_edges(tenant_key, edges)
    try:
        yield str(tenant_uuid)
    finally:
        async with driver.session() as session:
            await session.run(
                "MATCH (n:Resource {tenant_id: $tenant}) DETACH DELETE n",
                {"tenant": tenant_key},
            )
        await driver.close()


def test_resource_list_and_cursor_pagination(client: TestClient, graph_tenant: str) -> None:
    response = client.get(
        "/api/v1/resources", params={"limit": 5}, headers=_headers(graph_tenant)
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) <= 5
    assert data["has_more"] is True
    assert data["next_cursor"] is not None

    # Fetch second page using cursor
    next_page = client.get(
        "/api/v1/resources",
        params={"limit": 5, "cursor": data["next_cursor"]},
        headers=_headers(graph_tenant),
    )
    assert next_page.status_code == 200
    next_data = next_page.json()
    assert len(next_data["items"]) <= 5


def test_resource_detail_and_relationships(client: TestClient, graph_tenant: str) -> None:
    # 1. Detail using Base64URL-encoded ARN
    encoded_arn = base64.urlsafe_b64encode(VPC_ARN.encode()).decode().rstrip("=")
    detail_res = client.get(f"/api/v1/resources/{encoded_arn}", headers=_headers(graph_tenant))
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["arn"] == VPC_ARN
    assert detail["type"] == "AWS::EC2::VPC"
    assert "cidr_block" in detail["properties"]

    # 2. Relationships of VPC
    rel_res = client.get(
        f"/api/v1/resources/{encoded_arn}/relationships", headers=_headers(graph_tenant)
    )
    assert rel_res.status_code == 200
    rels = rel_res.json()
    assert len(rels) >= 1
    types = {r["type"] for r in rels}
    assert "CONTAINS" in types


def test_topology_query_slice_and_etag_caching(client: TestClient, graph_tenant: str) -> None:
    body = {
        "root": VPC_ARN,
        "depth": 2,
        "max_nodes": 50,
        "max_edges": 100,
    }

    # 1. First query returns 200 with ETag header
    res1 = client.post("/api/v1/topology/query", json=body, headers=_headers(graph_tenant))
    assert res1.status_code == 200
    etag = res1.headers.get("etag")
    assert etag is not None
    data = res1.json()
    assert "nodes" in data
    assert "edges" in data
    assert "groups" in data
    assert data["seq"] >= 1

    # 2. Conditional GET with If-None-Match returns 304 Not Modified
    res2 = client.post(
        "/api/v1/topology/query",
        json=body,
        headers={"If-None-Match": etag, **_headers(graph_tenant)},
    )
    assert res2.status_code == 304


def test_topology_aggregate(client: TestClient, graph_tenant: str) -> None:
    response = client.get("/api/v1/topology/aggregate", headers=_headers(graph_tenant))
    assert response.status_code == 200
    data = response.json()
    assert "by_type" in data
    assert "by_account" in data
    assert "by_region" in data
    assert "AWS::EC2::VPC" in data["by_type"]


def test_topology_search_and_ranking(client: TestClient, graph_tenant: str) -> None:
    response = client.get(
        "/api/v1/topology/search", params={"q": "vpc"}, headers=_headers(graph_tenant)
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    matches = [
        item
        for item in data["items"]
        if "vpc" in item["name"].lower() or "vpc" in item["type"].lower()
    ]
    assert len(matches) >= 1
    assert "types" in data["facets"]
    assert "accounts" in data["facets"]


def test_shortest_path_and_blast_radius(client: TestClient, graph_tenant: str) -> None:
    # 1. Shortest path from VPC to Subnet
    path_res = client.post(
        "/api/v1/topology/paths",
        json={"source_id": VPC_ARN, "target_id": SUBNET_ARN, "max_depth": 3},
        headers=_headers(graph_tenant),
    )
    assert path_res.status_code == 200
    hops = path_res.json()
    assert len(hops) >= 2
    assert hops[0]["node_id"] == VPC_ARN

    # 2. Blast radius from VPC
    blast_res = client.post(
        "/api/v1/topology/blast-radius",
        json={"source_id": VPC_ARN, "max_depth": 2, "max_nodes": 50},
        headers=_headers(graph_tenant),
    )
    assert blast_res.status_code == 200
    blast = blast_res.json()
    assert blast["source"]["id"] == VPC_ARN
    assert blast["reachable_count"] >= 1


def test_snapshots_and_diff(client: TestClient, graph_tenant: str) -> None:
    # 1. Create snapshot
    create_res = client.post(
        "/api/v1/topology/snapshots",
        json={"scope": "full"},
        headers={"Idempotency-Key": f"snap-{secrets.token_hex(4)}", **_headers(graph_tenant)},
    )
    assert create_res.status_code == 201
    snap = create_res.json()
    assert snap["id"].startswith("snp_")
    assert snap["node_count"] > 0

    # 2. List snapshots
    list_res = client.get("/api/v1/topology/snapshots", headers=_headers(graph_tenant))
    assert list_res.status_code == 200
    snaps = list_res.json()
    assert any(s["id"] == snap["id"] for s in snaps)

    # 3. Diff snapshot
    diff_res = client.post(
        "/api/v1/topology/diff",
        json={"base_snapshot_id": snap["id"]},
        headers={"Idempotency-Key": f"diff-{secrets.token_hex(4)}", **_headers(graph_tenant)},
    )
    assert diff_res.status_code == 200
    diff = diff_res.json()
    assert "added_count" in diff
    assert "diff_summary" in diff


def test_graph_version_endpoint(client: TestClient, graph_tenant: str) -> None:
    response = client.get("/api/v1/topology/version", headers=_headers(graph_tenant))
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"].startswith("tnt_")
    assert "seq" in data
    assert "as_of" in data
