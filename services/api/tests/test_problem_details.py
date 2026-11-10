from __future__ import annotations

from fastapi.testclient import TestClient

PROBLEM = "application/problem+json"


def test_unknown_route_returns_problem_details(client: TestClient) -> None:
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["status"] == 404
    assert body["type"].endswith("/not-found")
    assert body["instance"] == "/api/v1/nope"
    assert body["request_id"].startswith("req_")
    assert body["title"]


def test_validation_errors_use_field_pointers(client: TestClient) -> None:
    response = client.post(
        "/api/v1/demo/resources",
        json={"name": ""},
        headers={"Idempotency-Key": "validation-key-0001"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["type"].endswith("/validation-failed")
    pointers = {error["pointer"] for error in body["errors"]}
    assert "/name" in pointers


def test_errors_never_leak_internal_detail(client: TestClient) -> None:
    body = client.get("/api/v1/missing-resource").json()
    assert "traceback" not in str(body).lower()
    assert body["detail"]
