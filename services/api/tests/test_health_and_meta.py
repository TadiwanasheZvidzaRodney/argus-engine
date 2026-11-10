from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_is_dependency_free(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == []
    assert body["service"] == "argus-api"


def test_readyz_reports_dependencies(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"] == []


def test_readyz_fails_closed_when_dependency_is_down(failing_client: TestClient) -> None:
    response = failing_client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "fail"
    assert body["checks"][0] == {
        "name": "postgres",
        "state": "fail",
        "latency_ms": body["checks"][0]["latency_ms"],
        "detail": "ConnectionError",
    }


def test_health_endpoints_carry_correlation_headers(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.headers["x-request-id"].startswith("req_")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_client_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-Id": "req_client-abc-123"})
    assert response.headers["x-request-id"] == "req_client-abc-123"


def test_meta_describes_the_service(client: TestClient) -> None:
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v1"
    assert body["service"] == "argus-api"
    assert "idempotency:v1" in body["capabilities"]
