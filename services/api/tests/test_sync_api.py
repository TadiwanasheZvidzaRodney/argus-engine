from __future__ import annotations

import secrets

from fastapi.testclient import TestClient


def test_sync_job_lifecycle_and_topology_summary(client: TestClient) -> None:
    # 1. Onboard an account to sync
    acc_id = f"88{secrets.randbelow(10**10):010d}"
    client.post(
        "/api/v1/aws-accounts/onboarding",
        json={"account_id": acc_id, "alias": "sync-test-acc"},
        headers={"Idempotency-Key": f"sync-onboard-{acc_id}"},
    )
    client.post(
        f"/api/v1/aws-accounts/{acc_id}/validate",
        headers={"Idempotency-Key": f"sync-validate-{acc_id}"},
    )

    # 2. Trigger sync job
    start_res = client.post(
        "/api/v1/sync-jobs",
        json={"account_id": acc_id, "type": "backfill"},
        headers={"Idempotency-Key": f"start-sync-{acc_id}"},
    )
    assert start_res.status_code == 201
    job_data = start_res.json()
    assert job_data["status"] == "succeeded"
    assert job_data["account_id"] == acc_id
    assert job_data["resource_count"] > 0
    assert len(job_data["shards"]) >= 1

    # 3. List sync jobs includes this job
    jobs_res = client.get("/api/v1/sync-jobs")
    assert jobs_res.status_code == 200
    jobs = jobs_res.json()
    assert any(j["id"] == job_data["id"] for j in jobs)

    # 4. Resource coverage reports mapped types
    cov_res = client.get(f"/api/v1/aws-accounts/{acc_id}/coverage")
    assert cov_res.status_code == 200
    coverage = cov_res.json()
    assert len(coverage) >= 5
    types = {c["resource_type"] for c in coverage}
    assert "AWS::EC2::VPC" in types
    assert "AWS::EC2::Instance" in types

    # 5. Topology summary reflects live nodes and edges
    summary_res = client.get("/api/v1/topology/summary")
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["nodes"] >= job_data["resource_count"]
    assert summary["edges"] > 0

    # 6. Neighborhood traversal finds the VPC and its children
    vpc_arn = f"arn:aws:ec2:us-east-1:{acc_id}:vpc/vpc-0{acc_id[:4]}1122"
    neighbor_res = client.get(
        "/api/v1/topology/neighborhood",
        params={"root_id": vpc_arn, "depth": 1},
    )
    assert neighbor_res.status_code == 200
    neighbor_data = neighbor_res.json()
    assert neighbor_data["root"] is not None
    assert neighbor_data["root"]["id"] == vpc_arn
    assert len(neighbor_data["nodes"]) >= 2
    assert len(neighbor_data["edges"]) >= 1
