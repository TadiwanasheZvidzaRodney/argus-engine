"""Resource inventory, detail, and direct relationship endpoints."""

from __future__ import annotations

import base64
from typing import Any

from argus_core.errors import NotFound
from argus_core.pagination import Page, decode_cursor
from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, Field

from argus_api.auth import AuthContext, Permission, require_permission
from argus_api.routers.sync import _get_graph_repo

router = APIRouter(prefix="/api/v1/resources", tags=["resources"])


class ResourceItem(BaseModel):
    id: str
    arn: str
    type: str
    name: str
    account_id: str
    region: str
    state: str
    tags: dict[str, str] = Field(default_factory=dict)
    version: int = 1


class ResourceDetailResponse(BaseModel):
    id: str
    arn: str
    type: str
    name: str
    account_id: str
    region: str
    state: str
    tags: dict[str, str] = Field(default_factory=dict)
    version: int
    parent_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    raw_ref: str | None = None
    created_at: str
    updated_at: str


class RelationshipItem(BaseModel):
    source: str
    target: str
    type: str
    direction: str  # outgoing | incoming
    other_type: str | None = None
    other_name: str | None = None


def _decode_resource_key(key: str) -> str:
    # Accept URL-safe base64 encoded ARN or raw ARN
    if key.startswith("arn:") or key.startswith("urn:"):
        return key
    try:
        padding = "=" * (-len(key) % 4)
        return base64.urlsafe_b64decode(key + padding).decode("utf-8")
    except Exception:
        return key


@router.get("", response_model=Page[ResourceItem], summary="List resources with filters")
async def list_resources(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    types: list[str] | None = Query(default=None),
    account_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
    state: str | None = Query(default=None),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> Page[ResourceItem]:
    secret = request.app.state.settings.cursor_secret.get_secret_value()
    repo = _get_graph_repo(request)

    after_id: str | None = None
    if cursor:
        cursor_data = decode_cursor(cursor, secret=secret)
        after_id = str(cursor_data["after_id"])

    raw_items = await repo.list_resources(
        f"tnt_{auth.tenant_id}",
        types=types,
        account_id=account_id,
        region=region,
        state=state,
        limit=limit,
        after_id=after_id,
    )

    has_more = len(raw_items) > limit
    page_records = raw_items[:limit]

    next_payload = None
    if has_more and page_records:
        next_payload = {"after_id": page_records[-1]["id"]}

    items = [
        ResourceItem(
            id=r["id"],
            arn=r["arn"],
            type=r["type"],
            name=r.get("name", ""),
            account_id=r["account_id"],
            region=r["region"],
            state=r.get("state", "available"),
            tags=r.get("tags") if isinstance(r.get("tags"), dict) else {},
            version=int(r.get("version", 1)),
        )
        for r in page_records
        if auth.can_access_account(r["account_id"]) and auth.can_access_region(r["region"])
    ]

    return Page[ResourceItem].build(
        items,
        limit=limit,
        next_payload=next_payload,
        secret=secret,
    )


@router.get("/{resource_key}", response_model=ResourceDetailResponse, summary="Get resource detail")
async def get_resource_detail(
    request: Request,
    resource_key: str = Path(..., description="Raw or Base64URL-encoded ARN/URN"),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> ResourceDetailResponse:
    resource_id = _decode_resource_key(resource_key)
    repo = _get_graph_repo(request)

    node = await repo.get_resource_detail(f"tnt_{auth.tenant_id}", resource_id)
    if not node:
        raise NotFound(f"Resource {resource_id} not found.")

    can_acc = auth.can_access_account(node["account_id"])
    can_reg = auth.can_access_region(node["region"])
    if not can_acc or not can_reg:
        raise NotFound(f"Resource {resource_id} not found.")

    return ResourceDetailResponse(
        id=node["id"],
        arn=node["arn"],
        type=node["type"],
        name=node.get("name", ""),
        account_id=node["account_id"],
        region=node["region"],
        state=node.get("state", "available"),
        tags=node.get("tags") if isinstance(node.get("tags"), dict) else {},
        version=int(node.get("version", 1)),
        parent_id=node.get("parent_id"),
        properties=node.get("properties") if isinstance(node.get("properties"), dict) else {},
        raw_ref=node.get("raw_ref"),
        created_at=str(node.get("created_at", "")),
        updated_at=str(node.get("updated_at", "")),
    )


@router.get(
    "/{resource_key}/relationships",
    response_model=list[RelationshipItem],
    summary="List direct relationships",
)
async def get_resource_relationships(
    request: Request,
    resource_key: str = Path(...),
    limit: int = Query(default=100, ge=1, le=500),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[RelationshipItem]:
    resource_id = _decode_resource_key(resource_key)
    repo = _get_graph_repo(request)

    raw_rels = await repo.get_resource_relationships(
        f"tnt_{auth.tenant_id}", resource_id, limit=limit
    )
    return [
        RelationshipItem(
            source=r["source"],
            target=r["target"],
            type=r["type"],
            direction=r["direction"],
            other_type=r.get("other_type"),
            other_name=r.get("other_name"),
        )
        for r in raw_rels
    ]
