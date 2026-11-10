from __future__ import annotations

import secrets

from fastapi.testclient import TestClient

ACCOUNT = "123456789012"


def test_event_ingest_and_deduplication(client: TestClient) -> None:
    event_id = f"aws-config-evt-{secrets.token_hex(8)}"
    raw_payload = {
        "configurationItem": {
            "configurationItemStatus": "OK",
            "ARN": f"arn:aws:ec2:us-east-1:{ACCOUNT}:instance/i-ingest-{secrets.token_hex(4)}",
            "resourceType": "AWS::EC2::Instance",
            "awsAccountId": ACCOUNT,
            "awsRegion": "us-east-1",
            "configurationStateId": "1",
            "tags": [{"Key": "Env", "Value": "staging"}],
            "configuration": {"instanceType": "t3.medium"},
        }
    }

    # 1. Ingest event
    res1 = client.post(
        "/api/v1/events/ingest",
        json={"event_id": event_id, "source": "aws.config", "payload": raw_payload},
        headers={"Idempotency-Key": f"idem-{event_id}-1"},
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "applied"
    assert data1["seq"] is not None

    # 2. Duplicate ingest with same event_id
    res2 = client.post(
        "/api/v1/events/ingest",
        json={"event_id": event_id, "source": "aws.config", "payload": raw_payload},
        headers={"Idempotency-Key": f"idem-{event_id}-2"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "duplicate"


def test_dlq_and_replay_endpoints(client: TestClient) -> None:
    # 1. List DLQ items
    dlq_res = client.get("/api/v1/events/dlq")
    assert dlq_res.status_code == 200
    assert isinstance(dlq_res.json(), list)

    # 2. Trigger replay
    replay_res = client.post(
        "/api/v1/events/replay",
        json={},
        headers={"Idempotency-Key": f"idem-replay-{secrets.token_hex(4)}"},
    )
    assert replay_res.status_code == 200
    assert replay_res.json()["status"] == "replayed"
