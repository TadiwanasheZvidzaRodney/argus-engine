from __future__ import annotations

from fastapi.testclient import TestClient

KEY = "create-resource-key-0001"
BODY = {"name": "payments-api", "region": "eu-west-1"}


def test_mutation_without_key_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/demo/resources", json=BODY)
    assert response.status_code == 400
    assert response.json()["type"].endswith("/idempotency-key-required")


def test_malformed_key_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/demo/resources", json=BODY, headers={"Idempotency-Key": "short"}
    )
    assert response.status_code == 400
    assert response.json()["type"].endswith("/idempotency-key-invalid")


def test_same_key_and_body_replays_original_response(client: TestClient) -> None:
    first = client.post("/api/v1/demo/resources", json=BODY, headers={"Idempotency-Key": KEY})
    assert first.status_code == 201

    replay = client.post("/api/v1/demo/resources", json=BODY, headers={"Idempotency-Key": KEY})
    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert replay.headers["x-idempotent-replay"] == "true"
    assert "x-idempotent-replay" not in first.headers


def test_same_key_with_different_body_conflicts(client: TestClient) -> None:
    client.post("/api/v1/demo/resources", json=BODY, headers={"Idempotency-Key": KEY})
    conflict = client.post(
        "/api/v1/demo/resources",
        json={**BODY, "name": "other-api"},
        headers={"Idempotency-Key": KEY},
    )
    assert conflict.status_code == 409
    assert conflict.json()["type"].endswith("/idempotency-key-reuse")


def test_idempotency_is_scoped_per_key(client: TestClient) -> None:
    first = client.post(
        "/api/v1/demo/resources", json=BODY, headers={"Idempotency-Key": "key-a-00000001"}
    )
    second = client.post(
        "/api/v1/demo/resources", json=BODY, headers={"Idempotency-Key": "key-b-00000001"}
    )
    assert first.json()["id"] != second.json()["id"]
