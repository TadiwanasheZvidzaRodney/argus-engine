from __future__ import annotations

from argus_worker.discovery.adapters.base import normalize_tags
from argus_worker.discovery.adapters.sample_data import build_enterprise_topology
from argus_worker.discovery.catalog import is_supported_type
from argus_worker.discovery.resolvers import RelationshipResolver
from argus_worker.discovery.synthetic import make_synthetic_urn

TENANT = "tnt_0190c3a1-0000-7000-8000-000000000001"
ACCOUNT = "123456789012"


def test_catalog_supported_types() -> None:
    assert is_supported_type("AWS::EC2::Instance") is True
    assert is_supported_type("AWS::EC2::VPC") is True
    assert is_supported_type("AWS::S3::Bucket") is True
    assert is_supported_type("AWS::Unsupported::Robot") is False


def test_synthetic_urn_generation() -> None:
    urn = make_synthetic_urn(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        region="us-east-1",
        resource_type="AWS::EC2::RouteTable",
        natural_key="rtb-012345",
    )
    assert urn == f"urn:argus:{TENANT}:{ACCOUNT}:us-east-1:aws-ec2-routetable:rtb-012345"


def test_tag_normalization() -> None:
    list_tags = [{"Key": "Environment", "Value": "prod"}, {"Key": "Owner", "Value": "sre"}]
    assert normalize_tags(list_tags) == {"Environment": "prod", "Owner": "sre"}

    dict_tags = {"Project": "Argus"}
    assert normalize_tags(dict_tags) == {"Project": "Argus"}
    assert normalize_tags(None) == {}


def test_enterprise_topology_and_relationship_resolution() -> None:
    nodes = build_enterprise_topology(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        region="us-east-1",
    )
    assert len(nodes) >= 10
    types = {n.type for n in nodes}
    assert "AWS::EC2::VPC" in types
    assert "AWS::EC2::Subnet" in types
    assert "AWS::EC2::Instance" in types
    assert "AWS::S3::Bucket" in types

    edges = RelationshipResolver.resolve(TENANT, nodes)
    assert len(edges) >= 8

    edge_types = {e.type for e in edges}
    assert "CONTAINS" in edge_types
    assert "ROUTES_TO" in edge_types
    assert "MEMBER_OF" in edge_types
    assert "ATTACHED_TO" in edge_types
    assert "ASSUMES" in edge_types
    assert "TARGETS" in edge_types

    # Every edge must carry tenant_id
    assert all(e.tenant_id == TENANT for e in edges)
