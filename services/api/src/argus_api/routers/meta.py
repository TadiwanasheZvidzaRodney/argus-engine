"""Service metadata; the handshake clients use to confirm API compatibility."""

from __future__ import annotations

from datetime import UTC, datetime

from argus_core.settings import Settings
from fastapi import APIRouter
from pydantic import BaseModel, Field

API_VERSION = "v1"


class MetaResponse(BaseModel):
    service: str
    version: str
    commit: str
    env: str
    api_version: str = API_VERSION
    capabilities: list[str] = Field(default_factory=list)
    server_time: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


def build_meta_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["meta"])

    @router.get("/meta", response_model=MetaResponse, summary="Service metadata")
    async def meta() -> MetaResponse:
        return MetaResponse(
            service=settings.service_name,
            version=settings.service_version,
            commit=settings.commit_sha,
            env=settings.env.value,
            capabilities=["pagination:v1", "idempotency:v1", "problem-details:rfc9457"],
        )

    return router
