from __future__ import annotations

import secrets

import pytest
from argus_core.graph.client import build_graph_driver
from argus_core.graph.models import GraphEdge, GraphNode
from argus_core.graph.repository import GraphRepository
from argus_core.settings import Settings


@pytest.fixture
def repo() -> GraphRepository:
    driver = build_graph_driver(Settings(_env_file=None))
    return GraphRepository(driver)


async def test_graph_repository_upsert_and_neighborhood(repo: GraphRepository) -> None:
    tenant_id = f"tnt_{secrets.token_hex(16)}"
    account_id = "111122223333"

    vpc_arn = f"arn:aws:ec2:us-east-1:{account_id}:vpc/vpc-test1"
    subnet_arn = f"arn:aws:ec2:us-east-1:{account_id}:subnet/subnet-test1"

    nodes = [
        GraphNode(
            id=vpc_arn,
            arn=vpc_arn,
            type="AWS::EC2::VPC",
            name="test-vpc",
            tenant_id=tenant_id,
            account_id=account_id,
            region="us-east-1",
            properties={"cidr": "10.0.0.0/16"},
        ),
        GraphNode(
            id=subnet_arn,
            arn=subnet_arn,
            type="AWS::EC2::Subnet",
            name="test-subnet",
            tenant_id=tenant_id,
            account_id=account_id,
            region="us-east-1",
            properties={"cidr": "10.0.1.0/24"},
        ),
    ]

    edges = [
        GraphEdge(
            source_id=vpc_arn,
            target_id=subnet_arn,
            type="CONTAINS",
            tenant_id=tenant_id,
        )
    ]

    # 1. Upsert nodes & edges
    assert await repo.upsert_nodes(tenant_id, nodes) == 2
    assert await repo.upsert_edges(tenant_id, edges) == 1

    # 2. Query neighborhood
    neighborhood = await repo.query_neighborhood(tenant_id, root_id=vpc_arn, depth=1)
    assert neighborhood["root"] is not None
    assert neighborhood["root"]["id"] == vpc_arn
    assert len(neighborhood["nodes"]) == 2
    assert len(neighborhood["edges"]) == 1
    assert neighborhood["edges"][0]["type"] == "CONTAINS"

    # 3. Multi-tenant isolation: another tenant cannot see this VPC
    other_tenant = f"tnt_{secrets.token_hex(16)}"
    isolated = await repo.query_neighborhood(other_tenant, root_id=vpc_arn, depth=1)
    assert isolated["root"] is None
    assert isolated["nodes"] == []


async def test_tenant_guardrail_rejects_missing_tenant_id(repo: GraphRepository) -> None:
    with pytest.raises(ValueError, match="Invalid or missing tenant_id"):
        await repo.count_summary("invalid-tenant")

    with pytest.raises(ValueError, match="Invalid or missing tenant_id"):
        await repo.upsert_nodes("", [])
