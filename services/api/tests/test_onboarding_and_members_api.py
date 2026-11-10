from __future__ import annotations

import secrets

from fastapi.testclient import TestClient


def test_me_endpoint_returns_identity(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "demo@argus.local"
    assert data["tenant_id"].startswith("tnt_")
    assert data["role"] == "owner"
    assert "read:topology" in data["permissions"]


def test_account_onboarding_flow(client: TestClient) -> None:
    # Use a random 12-digit numeric account id for test repeatability
    unique_acc = f"99{secrets.randbelow(10**10):010d}"

    # 1. Start onboarding
    body = {
        "account_id": unique_acc,
        "alias": "production-workloads",
    }
    response = client.post(
        "/api/v1/aws-accounts/onboarding",
        json=body,
        headers={"Idempotency-Key": f"onboard-{unique_acc}-01"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["account_id"] == unique_acc
    assert data["external_id"].startswith("ext_")
    assert "console.aws.amazon.com/cloudformation" in data["cloudformation_url"]

    # 2. Duplicate onboarding is rejected with 409 Conflict
    dup_res = client.post(
        "/api/v1/aws-accounts/onboarding",
        json=body,
        headers={"Idempotency-Key": f"onboard-{unique_acc}-02"},
    )
    assert dup_res.status_code == 409

    # 3. Validate account connection
    val_res = client.post(
        f"/api/v1/aws-accounts/{unique_acc}/validate",
        headers={"Idempotency-Key": f"validate-{unique_acc}-01"},
    )
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["status"] == "active"
    assert "us-east-1" in val_data["enabled_regions"]

    # 4. List accounts shows the newly validated account
    list_res = client.get("/api/v1/aws-accounts")
    assert list_res.status_code == 200
    accounts = list_res.json()
    assert any(acc["account_id"] == unique_acc and acc["status"] == "active" for acc in accounts)


def test_member_and_invitation_flow(client: TestClient) -> None:
    me = client.get("/api/v1/me").json()
    tenant_id = me["tenant_id"]

    # 1. Invite a new team member
    unique_email = f"alice-{secrets.token_hex(4)}@argus.local"
    invite_res = client.post(
        f"/api/v1/tenants/{tenant_id}/invitations",
        json={"email": unique_email, "role": "operator"},
        headers={"Idempotency-Key": f"invite-{secrets.token_hex(4)}"},
    )
    assert invite_res.status_code == 201
    invite_data = invite_res.json()
    assert invite_data["email"] == unique_email
    assert invite_data["role"] == "operator"

    # 2. List members includes the seeded owner
    members_res = client.get(f"/api/v1/tenants/{tenant_id}/members")
    assert members_res.status_code == 200
    members = members_res.json()
    assert any(m["email"] == "demo@argus.local" and m["role"] == "owner" for m in members)


def test_audit_events_and_verification(client: TestClient) -> None:
    # 1. Query audit events
    audit_res = client.get("/api/v1/audit-events", params={"limit": 10})
    assert audit_res.status_code == 200
    data = audit_res.json()
    assert "items" in data
    assert len(data["items"]) >= 1

    # 2. Verify hash chain integrity
    verify_res = client.post(
        "/api/v1/audit-events/verify",
        headers={"Idempotency-Key": f"verify-audit-{secrets.token_hex(4)}"},
    )
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["chain_valid"] is True
