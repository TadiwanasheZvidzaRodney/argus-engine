from __future__ import annotations

import json

from argus_core.settings import Settings
from argus_ws.main import create_app
from fastapi.testclient import TestClient

TENANT = "tnt_0190c3a1-0000-7000-8000-000000000001"


def test_stream_resume_command_handling() -> None:
    settings = Settings(service_name="argus-ws", env="test", _env_file=None)
    client = TestClient(create_app(settings))

    with client.websocket_connect(f"/ws/v1/stream?tenant_id={TENANT}") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello"

        # Request resumption from seq 100
        ws.send_text(
            json.dumps({"v": 1, "type": "resume", "resume_from_seq": 100, "topics": ["nodes"]})
        )
        response = json.loads(ws.receive_text())
        # In test mode without Redis stream, gateway gracefully prompts snapshot_required
        assert response["type"] in ("graph.snapshot_required", "ack")
