from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from argus_api.auth import AuthContext, Role
from argus_api.iac.github import GitHubClient, github_slug, validate_location
from argus_api.routers.iac import _github
from argus_api.settings import ApiSettings
from argus_core.errors import Forbidden, UnprocessableEntity
from argus_core.settings import Environment


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/user/repo",
        "https://github.com/user/repo?token=secret",
        "https://token@github.com/user/repo",
        "https://github.com/user/../repo",
        "git@github.com:user/repo.git",
    ],
)
def test_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(UnprocessableEntity):
        github_slug(url)


def test_scope_and_paths() -> None:
    client = GitHubClient("owner", ["owner/infra"])
    assert client.check_scope("https://github.com/owner/infra.git") == "owner/infra"
    with pytest.raises(Forbidden):
        client.check_scope("https://github.com/other/infra")
    for path in ["../private", "/etc/passwd", "terraform/../../x", "terraform\\secret"]:
        with pytest.raises(UnprocessableEntity):
            validate_location("main", path)
    assert validate_location("main", "terraform/") == "terraform"


def test_local_keyring_bridge_requires_explicit_tenant_binding() -> None:
    tenant = UUID("0190c3a1-0000-7000-8000-000000000001")
    auth = AuthContext(user_id=tenant, tenant_id=tenant, email="test@example.test", role=Role.OWNER)
    settings = ApiSettings(_env_file=None, github_enabled=True, github_owner="owner")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    with pytest.raises(Forbidden):
        _github(request, auth)
    request.app.state.settings = settings.model_copy(update={"github_tenant_id": tenant})
    assert _github(request, auth).owner == "owner"
    request.app.state.settings = settings.model_copy(
        update={"env": Environment.PROD, "github_tenant_id": tenant}
    )
    with pytest.raises(Forbidden):
        _github(request, auth)


async def test_validation_checks_login_branch_and_directory() -> None:
    client = GitHubClient("owner", ["owner/infra"])
    client.api = AsyncMock(
        side_effect=[
            {"login": "owner"},
            {"permissions": {"push": True}},
            {"name": "main"},
            [],
        ]
    )
    verified = await client.verify_repository(
        "https://github.com/owner/infra", "main", "terraform/"
    )
    assert verified["directory"] == "terraform"
    assert client.api.await_count == 4


async def test_rejects_wrong_active_login() -> None:
    client = GitHubClient("owner", ["owner/infra"])
    client.api = AsyncMock(return_value={"login": "organization-user"})
    with pytest.raises(Forbidden):
        await client.verify_repository("https://github.com/owner/infra", "main", "terraform")
    assert client.api.await_count == 1


async def test_publication_creates_only_markdown_draft() -> None:
    client = GitHubClient("owner", ["owner/infra"])
    client.verify_repository = AsyncMock(return_value={"slug": "owner/infra"})
    client.api = AsyncMock(
        side_effect=[
            [],
            [],
            {"object": {"sha": "base"}},
            {},
            {"tree": []},
            {},
            {"number": 2, "html_url": "https://github.com/owner/infra/pull/2"},
        ]
    )
    result = await client.publish_proposal(
        "https://github.com/owner/infra",
        "main",
        "terraform",
        "1234",
        "Proposal",
        "Reviewed text",
    )
    assert result["number"] == 2
    calls = client.api.call_args_list
    assert calls[-1].args[2]["draft"] is True
    file_call = calls[-2]
    assert file_call.args[0].endswith("/contents/.argus/proposals/1234.md")
    assert base64.b64decode(file_call.args[2]["content"]) == b"Reviewed text"
    assert not any("merge" in call.args[0] for call in calls)


async def test_publication_retry_recovers_existing_pr() -> None:
    client = GitHubClient("owner", ["owner/infra"])
    client.verify_repository = AsyncMock(return_value={"slug": "owner/infra"})
    client.api = AsyncMock(
        return_value=[{"number": 2, "html_url": "https://github.com/owner/infra/pull/2"}]
    )
    assert (
        await client.publish_proposal(
            "https://github.com/owner/infra",
            "main",
            "terraform",
            "1234",
            "Proposal",
            "Reviewed",
        )
    )["number"] == 2
    client.api.assert_awaited_once()
