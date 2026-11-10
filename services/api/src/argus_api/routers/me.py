"""Current user identity and tenant context router."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from argus_api.auth import AuthContext, get_current_auth

router = APIRouter(prefix="/api/v1", tags=["identity"])


class MeResponse(BaseModel):
    user_id: str
    email: str
    tenant_id: str
    role: str
    permissions: list[str] = Field(default_factory=list)
    account_scopes: list[str] | None = None
    region_scopes: list[str] | None = None


@router.get("/me", response_model=MeResponse, summary="Get current user identity")
async def get_me(auth: AuthContext = Depends(get_current_auth)) -> MeResponse:
    from argus_api.auth import ROLE_PERMISSIONS

    perms = [p.value for p in ROLE_PERMISSIONS.get(auth.role, frozenset())]
    return MeResponse(
        user_id=f"usr_{auth.user_id.hex}",
        email=auth.email,
        tenant_id=f"tnt_{auth.tenant_id}",
        role=auth.role.value,
        permissions=sorted(perms),
        account_scopes=list(auth.account_scopes) if auth.account_scopes else None,
        region_scopes=list(auth.region_scopes) if auth.region_scopes else None,
    )
