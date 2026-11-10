"""Base discovery adapter interfaces and tag normalizers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from argus_core.graph.models import GraphNode


def normalize_tags(raw_tags: list[dict[str, str]] | dict[str, str] | None) -> dict[str, str]:
    """Normalize various AWS tag representations into a standard string dictionary."""
    if not raw_tags:
        return {}
    if isinstance(raw_tags, dict):
        return {str(k): str(v) for k, v in raw_tags.items()}
    result: dict[str, str] = {}
    for entry in raw_tags:
        if isinstance(entry, dict) and "Key" in entry and "Value" in entry:
            result[entry["Key"]] = entry["Value"]
    return result


@runtime_checkable
class DiscoveryAdapter(Protocol):
    async def discover(
        self,
        *,
        tenant_id: str,
        account_id: str,
        region: str,
    ) -> list[GraphNode]: ...
