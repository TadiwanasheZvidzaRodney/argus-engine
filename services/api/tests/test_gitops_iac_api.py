from __future__ import annotations

import secrets

import pytest
from argus_api.iac.drift import detect_iac_drift
from argus_api.iac.synthesizer import synthesize_hcl_diff
from argus_api.iac.vcs import create_or_simulate_pull_request
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


def test_hcl_diff_synthesis_for_catalog_actions() -> None:
    # 1. Security Group Ingress Restriction HCL Diff
    sg_diff = synthesize_hcl_diff(
        action_type="network.restrict_security_group_ingress",
        target_resource_id=f"arn:aws:ec2:us-west-2:{ACCOUNT}:security-group/sg-018d4831f0100367d",
        parameters={"port": 22, "cidr": "0.0.0.0/0", "protocol": "tcp"},
    )
    assert sg_diff["file_path"] == "terraform/security_groups.tf"
    assert "aws_security_group" in sg_diff["block_name"]
    assert "-      from_port   = 22" in sg_diff["hcl_diff"]
    assert "Restricted by Argus Engine" in sg_diff["hcl_diff"]

    # 2. EC2 Resize HCL Diff
    resize_diff = synthesize_hcl_diff(
        action_type="optimization.resize_instance",
        target_resource_id=f"arn:aws:ec2:us-west-2:{ACCOUNT}:instance/i-0011223344",
        parameters={"current_instance_type": "m5.xlarge", "instance_type": "m5.large"},
    )
    assert resize_diff["file_path"] == "terraform/compute.tf"
    assert '-    instance_type = "m5.xlarge"' in resize_diff["hcl_diff"]
    assert '+    instance_type = "m5.large"' in resize_diff["hcl_diff"]

    # 3. S3 Bucket Public Access Block HCL Diff
    s3_diff = synthesize_hcl_diff(
        action_type="s3.harden_bucket",
        target_resource_id=f"arn:aws:s3:::my-test-bucket-{ACCOUNT}",
        parameters={},
    )
    assert s3_diff["file_path"] == "terraform/storage.tf"
    assert "aws_s3_bucket_public_access_block" in s3_diff["hcl_diff"]
    assert "block_public_policy     = true" in s3_diff["hcl_diff"]


def test_iac_drift_detection_finds_clickops_changes() -> None:
    test_nodes = [
        {
            "id": f"arn:aws:ec2:us-west-2:{ACCOUNT}:security-group/sg-clickops",
            "type": "AWS::EC2::SecurityGroup",
            "name": "web-sg",
            "properties": {
                "ingress_rules": [
                    {"from_port": 22, "to_port": 22, "cidr": "0.0.0.0/0", "protocol": "tcp"}
                ]
            },
        },
        {
            "id": f"arn:aws:ec2:us-west-2:{ACCOUNT}:instance/i-drifted",
            "type": "AWS::EC2::Instance",
            "name": "app-server",
            "properties": {
                "instance_type": "m5.2xlarge",
                "expected_iac_instance_type": "m5.large",
            },
        },
    ]

    drift = detect_iac_drift(test_nodes)
    assert len(drift) >= 2
    types = {d["drift_details"]["drift_type"] for d in drift}
    assert "UNTRACKED_CLICKOPS_INGRESS" in types
    assert "MODIFIED_INSTANCE_TYPE" in types


def test_pull_request_creation_and_simulation() -> None:
    pr = create_or_simulate_pull_request(
        repo_url="https://github.com/argus-org/infrastructure-terraform",
        action_type="network.restrict_security_group_ingress",
        title="Revoke SSH ingress on sg-018d",
        hcl_diff="--- a/security_groups.tf\n+++ b/security_groups.tf",
    )
    assert pr["status"] == "OPEN"
    assert pr["pr_url"].startswith("https://github.com/argus-org/infrastructure-terraform/pull/")
    assert pr["branch_name"].startswith("argus/gitops-network-restrict-security-group-ingress-")
    assert pr["pr_number"] > 0


def test_gitops_repository_crud_and_listing(client: TestClient, seeded_tenant: str) -> None:
    # 1. Connect Repo
    create_res = client.post(
        "/api/v1/iac/repositories",
        json={
            "provider": "github",
            "repo_url": "https://github.com/acme-corp/aws-terraform-live",
            "default_branch": "main",
            "iac_path": "envs/prod/",
        },
        headers=_headers(seeded_tenant),
    )
    assert create_res.status_code == 201, create_res.text
    repo_data = create_res.json()
    assert repo_data["repo_url"] == "https://github.com/acme-corp/aws-terraform-live"
    assert repo_data["status"] == "active"

    # 2. List Repos
    list_res = client.get("/api/v1/iac/repositories", headers=_headers(seeded_tenant))
    assert list_res.status_code == 200
    repos = list_res.json()
    assert any(r["id"] == repo_data["id"] for r in repos)


def test_drift_scan_and_pull_request_synthesis_flow(client: TestClient, seeded_tenant: str) -> None:
    # 1. Trigger drift scan over graph
    scan_res = client.post("/api/v1/iac/drift/scan", headers=_headers(seeded_tenant))
    assert scan_res.status_code == 200, scan_res.text
    assert "scanned_at" in scan_res.json()

    # 2. List detected drift records
    drift_res = client.get("/api/v1/iac/drift", headers=_headers(seeded_tenant))
    assert drift_res.status_code == 200
    records = drift_res.json()
    assert isinstance(records, list)

    # 3. Synthesize GitOps PR
    pr_res = client.post(
        "/api/v1/iac/prs",
        json={
            "action_type": "network.restrict_security_group_ingress",
            "target_resource_id": f"arn:aws:ec2:us-west-2:{ACCOUNT}:security-group/sg-018d",
            "parameters": {"port": 22, "cidr": "0.0.0.0/0"},
        },
        headers=_headers(seeded_tenant),
    )
    assert pr_res.status_code == 201, pr_res.text
    pr = pr_res.json()
    assert pr["status"] == "OPEN"
    assert pr["pr_url"].startswith("https://github.com/")
    assert pr["hcl_diff"]

    # 4. List PRs
    prs_res = client.get("/api/v1/iac/prs", headers=_headers(seeded_tenant))
    assert prs_res.status_code == 200
    all_prs = prs_res.json()
    assert any(p["id"] == pr["id"] for p in all_prs)


def test_iac_tenant_isolation(client: TestClient, seeded_tenant: str) -> None:
    client.post(
        "/api/v1/iac/repositories",
        json={"repo_url": "https://github.com/tenant-a/terraform-repo"},
        headers=_headers(seeded_tenant),
    )

    other = str(new_uuid7())
    other_repos = client.get("/api/v1/iac/repositories", headers=_headers(other))
    assert other_repos.status_code == 200
    assert len(other_repos.json()) == 0

    other_drift = client.get("/api/v1/iac/drift", headers=_headers(other))
    assert other_drift.status_code == 200
    assert len(other_drift.json()) == 0
