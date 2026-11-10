"""Normalizes raw AWS Config and CloudTrail events into canonical Graph deltas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from argus_core.graph.models import GraphEdge, GraphNode
from argus_worker.discovery.adapters.base import normalize_tags
from argus_worker.discovery.resolvers import RelationshipResolver


@dataclass(frozen=True)
class NormalizedDelta:
    tenant_id: str
    account_id: str
    region: str
    resource_id: str
    change_type: str  # UPSERT | DELETE
    node: GraphNode | None
    edges: list[GraphEdge]
    actor: str | None
    capture_time: datetime
    version: int


def normalize_config_event(tenant_id: str, payload: dict[str, Any]) -> NormalizedDelta | None:
    """Normalize an AWS Config ConfigurationItemChangeNotification payload."""
    item = payload.get("configurationItem")
    if not item or not isinstance(item, dict):
        return None

    change_type_raw = str(item.get("configurationItemStatus", "OK")).upper()
    is_delete = any(k in change_type_raw for k in ("DELETED", "DELETE", "RESOURCEDELETED"))

    arn = str(item.get("ARN") or item.get("arn") or "")
    resource_type = str(item.get("resourceType") or "")
    account_id = str(item.get("awsAccountId") or "")
    region = str(item.get("awsRegion") or "")

    if not arn or not resource_type or not account_id or not region:
        return None

    capture_str = item.get("configurationItemCaptureTime")
    try:
        capture_time = (
            datetime.fromisoformat(capture_str).astimezone(UTC)
            if capture_str
            else datetime.now(tz=UTC)
        )
    except Exception:
        capture_time = datetime.now(tz=UTC)

    version_str = str(item.get("configurationStateId", "1"))
    version = int("".join(filter(str.isdigit, version_str)) or "1")

    if is_delete:
        return NormalizedDelta(
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            resource_id=arn,
            change_type="DELETE",
            node=None,
            edges=[],
            actor=None,
            capture_time=capture_time,
            version=version,
        )

    # Convert tags & properties
    tags = normalize_tags(item.get("tags"))
    configuration = item.get("configuration") or {}
    properties: dict[str, Any] = {}
    if isinstance(configuration, dict):
        properties.update(configuration)

    node_name = str(item.get("resourceName") or tags.get("Name") or arn.split("/")[-1])

    node = GraphNode(
        id=arn,
        arn=arn,
        type=resource_type,
        name=node_name,
        tenant_id=tenant_id,
        account_id=account_id,
        region=region,
        state="available",
        tags=tags,
        source="aws.config",
        version=version,
        updated_at=capture_time,
        properties=properties,
    )

    edges = RelationshipResolver.resolve(tenant_id, [node])

    return NormalizedDelta(
        tenant_id=tenant_id,
        account_id=account_id,
        region=region,
        resource_id=arn,
        change_type="UPSERT",
        node=node,
        edges=edges,
        actor=None,
        capture_time=capture_time,
        version=version,
    )


def normalize_cloudtrail_event(tenant_id: str, payload: dict[str, Any]) -> NormalizedDelta | None:
    """Normalize a CloudTrail management event for change attribution."""
    detail = payload.get("detail") or payload
    event_name = str(detail.get("eventName", ""))
    account_id = str(detail.get("recipientAccountId") or detail.get("awsRegion") or "")
    region = str(detail.get("awsRegion", "us-east-1"))

    user_identity = detail.get("userIdentity") or {}
    actor = str(user_identity.get("arn") or user_identity.get("userName") or "unknown")

    resources = detail.get("resources") or []
    target_arn = ""
    for r in resources:
        if isinstance(r, dict) and "ARN" in r:
            target_arn = str(r["ARN"])
            break

    if not target_arn:
        return None

    is_delete = any(verb in event_name.lower() for verb in ("delete", "terminate", "drop"))

    return NormalizedDelta(
        tenant_id=tenant_id,
        account_id=account_id,
        region=region,
        resource_id=target_arn,
        change_type="DELETE" if is_delete else "UPSERT",
        node=None,  # CloudTrail only signals mutations
        # detailed properties come from Config or Describe
        edges=[],
        actor=actor,
        capture_time=datetime.now(tz=UTC),
        version=1,
    )
