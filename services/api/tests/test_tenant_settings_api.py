from __future__ import annotations

import secrets

import pytest
from argus_core.events import new_uuid7
from argus_core.settings import Settings
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = str(new_uuid7())


def _headers(tenant: str, role: str = "owner", key: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"stub:{OWNER}:{tenant}:{role}:{role}@argus.local",
        "Idempotency-Key": key or f"key-{secrets.token_hex(8)}",
    }


@pytest.fixture
async def sample_tenant() -> str:
    settings = Settings(_env_file=None)
    engine = create_async_engine(settings.database_url)
    tenant_id = new_uuid7()
    token = secrets.token_hex(6)
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, name, slug) VALUES (:id, :name, :slug);"),
            {
                "id": tenant_id,
                "name": f"Tenant-{token}",
                "slug": f"slug-{token}",
            },
        )
    try:
        yield str(tenant_id)
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})
        await engine.dispose()


def test_get_and_update_tenant_settings(client: TestClient, sample_tenant: str) -> None:
    # 1. Fetch defaults
    get_res = client.get("/api/v1/settings/tenant", headers=_headers(sample_tenant))
    assert get_res.status_code == 200, get_res.text
    initial = get_res.json()
    assert initial["alert_email"]
    assert initial["alert_repeat_minutes"] == 30
    assert initial["default_region"] == "us-west-2"

    # 2. Update settings to a personal address
    new_email = "tadiwa.personal@example.com"
    put_res = client.put(
        "/api/v1/settings/tenant",
        json={
            "alert_email": new_email,
            "alert_repeat_minutes": 15,
            "alert_slack_webhook": "https://hooks.slack.com/services/T00/B00/X00",
            "default_region": "us-west-2",
        },
        headers=_headers(sample_tenant),
    )
    assert put_res.status_code == 200, put_res.text
    updated = put_res.json()
    assert updated["alert_email"] == new_email
    assert updated["alert_repeat_minutes"] == 15
    assert updated["alert_slack_webhook"] == "https://hooks.slack.com/services/T00/B00/X00"

    # 3. Verify get returns updated email
    verified = client.get("/api/v1/settings/tenant", headers=_headers(sample_tenant)).json()
    assert verified["alert_email"] == new_email
    assert verified["alert_repeat_minutes"] == 15


def test_dynamic_alert_email_used_when_triggering_alerts(
    client: TestClient, sample_tenant: str
) -> None:
    custom_email = "incident-response@company.org"

    # Configure tenant email
    client.put(
        "/api/v1/settings/tenant",
        json={
            "alert_email": custom_email,
            "alert_repeat_minutes": 15,
            "default_region": "us-west-2",
        },
        headers=_headers(sample_tenant),
    )

    # Trigger alert with default email
    alert_res = client.post(
        "/api/v1/ops/alerts",
        json={
            "alert_key": "dynamic-email-test",
            "title": "Dynamic Email Dispatch Test",
            "description": "Checking alert email resolves from tenant settings.",
            "source": "ecs",
            "severity": "critical",
        },
        headers=_headers(sample_tenant),
    )
    assert alert_res.status_code == 201

    # Verify alert received the tenant's configured email
    alerts = client.get("/api/v1/ops/alerts", headers=_headers(sample_tenant)).json()
    assert len(alerts) >= 1
    target_alert = next(a for a in alerts if a["alert_key"] == "dynamic-email-test")
    assert target_alert["notification_email"] == custom_email


async def test_tenant_settings_isolation(client: TestClient) -> None:
    settings = Settings(_env_file=None)
    engine = create_async_engine(settings.database_url)
    tenant_a = new_uuid7()
    tenant_b = new_uuid7()
    async with engine.begin() as conn:
        for tid in (tenant_a, tenant_b):
            token = secrets.token_hex(6)
            await conn.execute(
                text("INSERT INTO tenants (id, name, slug) VALUES (:id, :name, :slug);"),
                {"id": tid, "name": f"Tenant-{token}", "slug": f"slug-{token}"},
            )
    await engine.dispose()

    client.put(
        "/api/v1/settings/tenant",
        json={
            "alert_email": "tenant-a@example.com",
            "alert_repeat_minutes": 15,
            "default_region": "us-east-1",
        },
        headers=_headers(str(tenant_a)),
    )

    settings_b = client.get("/api/v1/settings/tenant", headers=_headers(str(tenant_b))).json()
    assert settings_b["alert_email"] != "tenant-a@example.com"
