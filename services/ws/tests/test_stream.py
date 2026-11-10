from __future__ import annotations

import json

import pytest
from argus_core.settings import Settings
from argus_ws.main import create_app
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

TENANT = "tnt_0190c3a1-0000-7000-8000-000000000000"


@pytest.fixture
def client() -> TestClient:
    settings = Settings(service_name="argus-ws", env="test", _env_file=None)
    return TestClient(create_app(settings))


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "argus-ws"


def test_hello_frame_binds_tenant(client: TestClient) -> None:
    with client.websocket_connect(f"/ws/v1/stream?tenant_id={TENANT}") as ws:
        hello = json.loads(ws.receive_text())
    assert hello["v"] == 1
    assert hello["type"] == "hello"
    assert hello["seq"] == 0
    assert hello["data"]["tenant_id"] == TENANT
    assert hello["data"]["protocol_version"] == 1
    assert hello["data"]["heartbeat_seconds"] >= 5


def test_subscribe_is_acknowledged_with_increasing_seq(client: TestClient) -> None:
    with client.websocket_connect(f"/ws/v1/stream?tenant_id={TENANT}") as ws:
        assert json.loads(ws.receive_text())["type"] == "hello"
        ws.send_text(json.dumps({"v": 1, "type": "subscribe", "topics": ["resource.*"]}))
        ack = json.loads(ws.receive_text())
    assert ack["type"] == "ack"
    assert ack["seq"] == 1
    assert ack["data"]["topics"] == ["resource.*"]


def test_invalid_frame_returns_error_without_dropping_connection(client: TestClient) -> None:
    with client.websocket_connect(f"/ws/v1/stream?tenant_id={TENANT}") as ws:
        json.loads(ws.receive_text())
        ws.send_text("{not json")
        error = json.loads(ws.receive_text())
        assert error["type"] == "error"
        assert error["data"]["code"] == "invalid-frame"

        ws.send_text(json.dumps({"v": 1, "type": "subscribe", "topics": ["finding.*"]}))
        assert json.loads(ws.receive_text())["type"] == "ack"


def test_malformed_tenant_is_refused(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as refusal,
        client.websocket_connect("/ws/v1/stream?tenant_id=not-a-tenant") as ws,
    ):
        ws.receive_text()
    assert refusal.value.code == 1008


def test_oidc_mode_refuses_until_phase_1() -> None:
    settings = Settings(service_name="argus-ws", env="test", auth_mode="oidc", _env_file=None)
    with (
        TestClient(create_app(settings)) as oidc_client,
        pytest.raises(WebSocketDisconnect) as refusal,
        oidc_client.websocket_connect(f"/ws/v1/stream?tenant_id={TENANT}") as ws,
    ):
        ws.receive_text()
    assert refusal.value.code == 1008
