"""Phase 0 demo endpoints.

They exist to prove the shared conventions end-to-end (cursor pagination,
idempotent writes, problem details, correlation headers) and are deleted when
real graph endpoints land in Phase 4. Nothing here touches AWS or a database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from argus_core.errors import UnprocessableEntity
from argus_core.events import new_uuid7
from argus_core.pagination import CursorError, Page, decode_cursor
from argus_core.settings import Settings
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

_REGIONS = ("us-east-1", "us-west-2", "eu-west-1", "ap-southeast-2")


class DemoResource(BaseModel):
    id: str
    name: str
    region: str
    created_at: datetime


class CreateDemoResource(BaseModel):
    name: str = Field(min_length=1, max_length=128, examples=["payments-api"])
    region: str = Field(default="us-east-1", examples=["us-east-1"])


def build_demo_router(settings: Settings) -> APIRouter:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    resources: list[DemoResource] = [
        DemoResource(
            id=f"res_{index:04d}",
            name=f"resource-{index:04d}",
            region=_REGIONS[index % len(_REGIONS)],
            created_at=base + timedelta(minutes=index),
        )
        for index in range(75)
    ]
    router = APIRouter(prefix="/api/v1/demo", tags=["demo"])

    @router.get(
        "/resources",
        response_model=Page[DemoResource],
        summary="Cursor-paginated demo collection",
    )
    async def list_resources(
        limit: int = Query(default=25, ge=1, le=100),
        cursor: str | None = Query(default=None),
    ) -> Page[DemoResource]:
        start = 0
        if cursor:
            try:
                payload = decode_cursor(cursor, secret=settings.cursor_secret.get_secret_value())
            except CursorError as exc:
                raise UnprocessableEntity(
                    "The pagination cursor is invalid or has expired."
                ) from exc
            start = int(payload.get("index", 0))
            if start < 0 or start > len(resources):
                raise UnprocessableEntity("The pagination cursor is out of range.")

        page = resources[start : start + limit]
        next_index = start + limit
        next_payload = {"index": next_index} if next_index < len(resources) else None
        return Page[DemoResource].build(
            page,
            limit=limit,
            next_payload=next_payload,
            secret=settings.cursor_secret.get_secret_value(),
        )

    @router.post(
        "/resources",
        response_model=DemoResource,
        status_code=201,
        summary="Idempotent demo mutation",
        description="Requires an Idempotency-Key header; replays return the original response.",
    )
    async def create_resource(body: CreateDemoResource) -> DemoResource:
        resource = DemoResource(
            id=f"res_{new_uuid7().hex[:12]}",
            name=body.name,
            region=body.region,
            created_at=datetime.now(tz=UTC),
        )
        resources.append(resource)
        return resource

    return router
