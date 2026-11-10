from __future__ import annotations

from uuid import UUID

from argus_api.auth import AuthContext, Permission, Role


def test_owner_has_all_permissions() -> None:
    auth = AuthContext(
        user_id=UUID("0190c3a1-0000-7000-8000-000000000001"),
        email="owner@argus.local",
        tenant_id=UUID("0190c3a1-0000-7000-8000-000000000002"),
        role=Role.OWNER,
    )
    for perm in Permission:
        assert auth.has_permission(perm) is True


def test_viewer_has_only_read_topology() -> None:
    auth = AuthContext(
        user_id=UUID("0190c3a1-0000-7000-8000-000000000001"),
        email="viewer@argus.local",
        tenant_id=UUID("0190c3a1-0000-7000-8000-000000000002"),
        role=Role.VIEWER,
    )
    assert auth.has_permission(Permission.READ_TOPOLOGY) is True
    assert auth.has_permission(Permission.MANAGE_ACCOUNTS) is False
    assert auth.has_permission(Permission.REQUEST_ACTION) is False
    assert auth.has_permission(Permission.APPROVE_ACTION) is False
    assert auth.has_permission(Permission.READ_AUDIT) is False


def test_operator_and_approver_separation() -> None:
    operator = AuthContext(
        user_id=UUID("0190c3a1-0000-7000-8000-000000000001"),
        email="op@argus.local",
        tenant_id=UUID("0190c3a1-0000-7000-8000-000000000002"),
        role=Role.OPERATOR,
    )
    approver = AuthContext(
        user_id=UUID("0190c3a1-0000-7000-8000-000000000003"),
        email="approver@argus.local",
        tenant_id=UUID("0190c3a1-0000-7000-8000-000000000002"),
        role=Role.APPROVER,
    )
    assert operator.has_permission(Permission.REQUEST_ACTION) is True
    assert operator.has_permission(Permission.APPROVE_ACTION) is False

    assert approver.has_permission(Permission.APPROVE_ACTION) is True
    assert approver.has_permission(Permission.REQUEST_ACTION) is False


def test_account_and_region_scoping() -> None:
    scoped = AuthContext(
        user_id=UUID("0190c3a1-0000-7000-8000-000000000001"),
        email="dev@argus.local",
        tenant_id=UUID("0190c3a1-0000-7000-8000-000000000002"),
        role=Role.OPERATOR,
        account_scopes=("123456789012",),
        region_scopes=("us-east-1", "eu-west-1"),
    )
    assert scoped.can_access_account("123456789012") is True
    assert scoped.can_access_account("999999999999") is False

    assert scoped.can_access_region("us-east-1") is True
    assert scoped.can_access_region("ap-southeast-1") is False


def test_unscoped_user_can_access_all() -> None:
    unscoped = AuthContext(
        user_id=UUID("0190c3a1-0000-7000-8000-000000000001"),
        email="admin@argus.local",
        tenant_id=UUID("0190c3a1-0000-7000-8000-000000000002"),
        role=Role.ADMIN,
    )
    assert unscoped.can_access_account("any-account") is True
    assert unscoped.can_access_region("any-region") is True
