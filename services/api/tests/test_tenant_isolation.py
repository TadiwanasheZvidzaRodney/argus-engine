from __future__ import annotations

import secrets

from argus_api.db import build_session_factory
from argus_api.models import AwsAccount, Tenant, User
from argus_core.events import new_uuid7
from argus_core.settings import Settings
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine


async def test_postgres_row_level_security_isolation() -> None:
    settings = Settings(_env_file=None)
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = build_session_factory(engine)

    tenant_a = new_uuid7()
    tenant_b = new_uuid7()
    user_a = new_uuid7()
    user_b = new_uuid7()

    token_a = secrets.token_hex(6)
    token_b = secrets.token_hex(6)

    # 1. Bootstrap Tenant A and Tenant B as admin (bypassing RLS)
    async with session_factory() as admin_sess, admin_sess.begin():
        admin_sess.add_all(
            [
                Tenant(id=tenant_a, name="Tenant Alpha", slug=f"alpha-{token_a}"),
                Tenant(id=tenant_b, name="Tenant Beta", slug=f"beta-{token_b}"),
                User(id=user_a, email=f"user-a-{token_a}@alpha.local", name="User Alpha"),
                User(id=user_b, email=f"user-b-{token_b}@beta.local", name="User Beta"),
            ]
        )

    # 2. Tenant A creates an AWS Account under non-superuser RLS role
    account_a_id = new_uuid7()
    async with session_factory() as sess_a, sess_a.begin():
        await sess_a.execute(text("SET ROLE argus_app"))
        await sess_a.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_a)},
        )
        sess_a.add(
            AwsAccount(
                id=account_a_id,
                tenant_id=tenant_a,
                account_id="111111111111",
                alias="alpha-main",
                read_role_arn="arn:aws:iam::111111111111:role/ArgusRole",
                external_id_secret_ref="ref-alpha",
                external_id_fingerprint="fp-alpha",
                created_by=user_a,
            )
        )

    # 3. Tenant B queries the aws_accounts table under Tenant B context
    async with session_factory() as sess_b, sess_b.begin():
        await sess_b.execute(text("SET ROLE argus_app"))
        await sess_b.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_b)},
        )
        # Tenant B must see 0 accounts
        result = await sess_b.execute(select(AwsAccount))
        accounts = result.scalars().all()
        assert len(accounts) == 0

        # Tenant B directly querying Tenant A's account ID must return None
        targeted = await sess_b.execute(select(AwsAccount).where(AwsAccount.id == account_a_id))
        assert targeted.scalar_one_or_none() is None

    # 4. Tenant A queries and sees exactly their account
    async with session_factory() as sess_a, sess_a.begin():
        await sess_a.execute(text("SET ROLE argus_app"))
        await sess_a.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_a)},
        )
        result = await sess_a.execute(select(AwsAccount))
        accounts = result.scalars().all()
        assert len(accounts) == 1
        assert accounts[0].account_id == "111111111111"

    await engine.dispose()
