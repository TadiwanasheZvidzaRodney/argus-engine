from __future__ import annotations

import hashlib
from uuid import UUID

from argus_api.credentials import CredentialBroker, generate_external_id


def test_external_id_bundle_generation() -> None:
    tenant_id = UUID("0190c3a1-0000-7000-8000-000000000001")
    bundle = generate_external_id(tenant_id)

    assert bundle.plaintext.startswith("ext_0190c3a10000_")
    assert len(bundle.plaintext) >= 32
    assert hashlib.sha256(bundle.plaintext.encode("utf-8")).hexdigest() == bundle.fingerprint
    assert bundle.fingerprint[:16] in bundle.secret_ref


async def test_credential_broker_assume_role_and_cache() -> None:
    broker = CredentialBroker()
    tenant_id = UUID("0190c3a1-0000-7000-8000-000000000001")
    bundle = generate_external_id(tenant_id)
    broker.register_external_id(bundle.secret_ref, bundle.plaintext)

    role_arn = "arn:aws:iam::123456789012:role/ArgusEngineReadRole-tnt_01"
    first = await broker.assume_role(
        tenant_id=tenant_id,
        account_id="123456789012",
        role_arn=role_arn,
        external_id_secret_ref=bundle.secret_ref,
        purpose="discovery",
        duration_seconds=1800,
    )

    assert first.access_key_id.startswith("ASIA")
    assert first.is_expired is False

    # Second call returns the cached session
    second = await broker.assume_role(
        tenant_id=tenant_id,
        account_id="123456789012",
        role_arn=role_arn,
        external_id_secret_ref=bundle.secret_ref,
        purpose="discovery",
    )
    assert first.access_key_id == second.access_key_id
    assert first.session_token == second.session_token


async def test_credential_broker_validation() -> None:
    broker = CredentialBroker()
    tenant_id = UUID("0190c3a1-0000-7000-8000-000000000001")
    bundle = generate_external_id(tenant_id)
    broker.register_external_id(bundle.secret_ref, bundle.plaintext)

    result = await broker.validate_connection(
        tenant_id=tenant_id,
        account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/ArgusRole",
        external_id_secret_ref=bundle.secret_ref,
    )
    assert result["status"] == "connected"
    assert result["account_id"] == "123456789012"
