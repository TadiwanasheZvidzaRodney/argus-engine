"""Local GitHub CLI/keyring bridge. No tokens in requests or database rows."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import subprocess
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

from argus_core.errors import Forbidden, ServiceUnavailable, UnprocessableEntity

LOCAL_GH_AUTH_REF = "local-gh-keyring"


def _pr_result(data: Any, slug: str) -> dict[str, Any]:
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("number"), int)
        or data["number"] <= 0
        or data.get("html_url") != f"https://github.com/{slug}/pull/{data['number']}"
    ):
        raise ServiceUnavailable("GitHub returned an unexpected pull request response.")
    return dict(data)


def github_slug(url: str) -> str:
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)/?", url)
    if not match:
        raise UnprocessableEntity(
            "Use an HTTPS github.com owner/repository URL without credentials."
        )
    owner, repo = match.groups()
    repo = repo.removesuffix(".git")
    if repo in {"", ".", ".."}:
        raise UnprocessableEntity("Invalid GitHub repository.")
    return f"{owner}/{repo}"


def validate_location(branch: str, path: str) -> str:
    if (
        not re.fullmatch(r"[A-Za-z0-9_./-]+", branch)
        or ".." in branch
        or "//" in branch
        or branch.endswith(("/", ".", ".lock"))
        or branch.startswith(("/", "-"))
    ):
        raise UnprocessableEntity("Invalid repository branch.")
    cleaned = path.strip("/")
    if (
        path.startswith("/")
        or "\\" in path
        or any(part in {".", ".."} for part in path.split("/") if part)
    ):
        raise UnprocessableEntity("IaC path must be a repository-relative directory.")
    return str(PurePosixPath(cleaned)) if cleaned else ""


class GitHubClient:
    def __init__(self, owner: str, allowed_repositories: list[str]) -> None:
        self.owner = owner
        self.allowed = {item.casefold() for item in allowed_repositories}

    def check_scope(self, repo_url: str) -> str:
        slug = github_slug(repo_url)
        if slug.casefold() not in self.allowed or slug.split("/")[0].casefold() != (
            self.owner.casefold()
        ):
            raise Forbidden("Repository is outside the configured GitHub allowlist.")
        return slug

    async def api(
        self,
        path: str,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> Any:
        def run() -> Any:
            args = ["gh", "api", "--hostname", "github.com", "--method", method, path]
            if payload is not None:
                args += ["--input", "-"]
            try:
                result = subprocess.run(  # noqa: S603 - fixed executable; no shell
                    args,
                    input=json.dumps(payload) if payload is not None else None,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                )
                return json.loads(result.stdout) if result.stdout.strip() else {}
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                # stderr may contain private data. Never return it or a token to clients.
                raise ServiceUnavailable(
                    "GitHub request failed. Check local gh authentication and repository access."
                ) from exc

        return await asyncio.to_thread(run)

    async def verify_repository(self, repo_url: str, branch: str, path: str) -> dict[str, Any]:
        slug = self.check_scope(repo_url)
        directory = validate_location(branch, path)
        identity = await self.api("/user")
        if identity.get("login", "").casefold() != self.owner.casefold():
            raise Forbidden("The active GitHub CLI login does not match the configured owner.")
        repo = await self.api(f"/repos/{slug}")
        if repo.get("archived") or not repo.get("permissions", {}).get("push"):
            raise Forbidden("Repository must be writable and not archived for approved draft PRs.")
        await self.api(f"/repos/{slug}/branches/{quote(branch, safe='')}")
        content = await self.api(
            f"/repos/{slug}/contents/{quote(directory, safe='/')}?ref={quote(branch, safe='')}"
        )
        if not isinstance(content, list):
            raise UnprocessableEntity("IaC path must point to an existing directory.")
        return {"repo_url": f"https://github.com/{slug}", "slug": slug, "directory": directory}

    async def publish_proposal(
        self,
        repo_url: str,
        base: str,
        path: str,
        proposal_id: str,
        title: str,
        content: str,
    ) -> dict[str, Any]:
        verified = await self.verify_repository(repo_url, base, path)
        slug = verified["slug"]
        branch = f"argus/proposal-{proposal_id}"
        existing = await self.api(
            f"/repos/{slug}/pulls?state=all&head={quote(self.owner + ':' + branch, safe='')}"
        )
        if existing:
            return _pr_result(existing[0], slug)
        # Deterministic branch + file + PR lookup makes retries recoverable.
        branches = await self.api(f"/repos/{slug}/git/matching-refs/heads/{branch}")
        if not any(item["ref"] == f"refs/heads/{branch}" for item in branches):
            base_ref = await self.api(f"/repos/{slug}/git/ref/heads/{quote(base, safe='')}")
            await self.api(
                f"/repos/{slug}/git/refs",
                "POST",
                {
                    "ref": f"refs/heads/{branch}",
                    "sha": base_ref["object"]["sha"],
                },
            )
        tree = await self.api(f"/repos/{slug}/git/trees/{quote(branch, safe='')}?recursive=1")
        file_path = f".argus/proposals/{proposal_id}.md"
        blob_sha = next(
            (entry["sha"] for entry in tree.get("tree", []) if entry["path"] == file_path), None
        )
        if blob_sha is None:
            await self.api(
                f"/repos/{slug}/contents/{file_path}",
                "PUT",
                {
                    "message": f"docs: add approved Argus proposal {proposal_id}",
                    "content": base64.b64encode(content.encode()).decode(),
                    "branch": branch,
                },
            )
        else:
            blob = await self.api(f"/repos/{slug}/git/blobs/{blob_sha}")
            if base64.b64decode(blob["content"]).decode() != content:
                raise UnprocessableEntity(
                    "Existing proposal content differs; refusing to overwrite."
                )
        result = await self.api(
            f"/repos/{slug}/pulls",
            "POST",
            {
                "title": title,
                "head": branch,
                "base": base,
                "draft": True,
                "body": (
                    f"Approved Argus proposal `{proposal_id}`. Review `{file_path}`.\n\n"
                    "This PR contains a Markdown proposal only, not executable Terraform changes. "
                    "No AWS resources were modified. No automatic merge or deployment."
                ),
            },
        )
        return _pr_result(result, slug)
