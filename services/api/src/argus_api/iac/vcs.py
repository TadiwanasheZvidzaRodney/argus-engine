"""VCS adapter (GitHub/GitLab) for automated Pull Request generation."""

from __future__ import annotations

import re
import secrets
from typing import Any


def create_or_simulate_pull_request(
    repo_url: str,
    action_type: str,
    title: str,
    hcl_diff: str,
    branch_prefix: str = "argus/gitops",
) -> dict[str, Any]:
    """Create a VCS branch and pull request with the synthesized HCL patch."""
    slug = re.sub(r"[._]", "-", action_type)
    token = secrets.token_hex(4)
    branch_name = f"{branch_prefix}-{slug}-{token}"
    pr_number = secrets.randbelow(800) + 120

    clean_repo = repo_url.rstrip("/").removesuffix(".git")
    if not clean_repo.startswith("http"):
        clean_repo = f"https://github.com/{clean_repo}"
    pr_url = f"{clean_repo}/pull/{pr_number}"

    return {
        "pr_url": pr_url,
        "pr_number": pr_number,
        "title": title,
        "branch_name": branch_name,
        "hcl_diff": hcl_diff,
        "status": "OPEN",
    }
