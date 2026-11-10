"""Tenant members and invitations management router."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argus_core.errors import NotFound
from argus_core.events import new_uuid7
from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.auth import (
    AuthContext,
    Permission,
    Role,
    get_tenant_db,
    require_permission,
)
from argus_api.models import Invitation, Membership, User

router = APIRouter(prefix="/api/v1/tenants", tags=["members"])


class MemberResponse(BaseModel):
    user_id: str
    email: str
    role: str
    status: str
    account_scopes: list[str] | None = None
    region_scopes: list[str] | None = None
    joined_at: datetime


class InviteMemberRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Role = Role.VIEWER


class InvitationResponse(BaseModel):
    invitation_id: str
    email: str
    role: str
    expires_at: datetime


class UpdateMemberRequest(BaseModel):
    role: Role
    account_scopes: list[str] | None = None
    region_scopes: list[str] | None = None


@router.get(
    "/{tenant_id}/members", response_model=list[MemberResponse], summary="List tenant members"
)
async def list_members(
    tenant_id: str = Path(..., description="Tenant ID (tnt_...)"),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[MemberResponse]:
    tid = UUID(tenant_id.removeprefix("tnt_"))
    stmt = (
        select(Membership, User)
        .join(User, Membership.user_id == User.id)
        .where(Membership.tenant_id == tid)
    )
    result = await session.execute(stmt)
    records = result.all()

    return [
        MemberResponse(
            user_id=f"usr_{user.id.hex}",
            email=user.email,
            role=mem.role,
            status=mem.status,
            account_scopes=mem.account_scopes,
            region_scopes=mem.region_scopes,
            joined_at=mem.created_at,
        )
        for mem, user in records
    ]


@router.post(
    "/{tenant_id}/invitations",
    response_model=InvitationResponse,
    status_code=201,
    summary="Invite a new member",
)
async def invite_member(
    body: InviteMemberRequest,
    tenant_id: str = Path(...),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_MEMBERS)),
) -> InvitationResponse:
    tid = UUID(tenant_id.removeprefix("tnt_"))
    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        id=new_uuid7(),
        tenant_id=tid,
        email=body.email,
        role=body.role.value,
        token_hash=token,
        invited_by=auth.user_id,
        expires_at=datetime.now(tz=UTC) + timedelta(days=7),
    )
    session.add(invitation)
    await session.flush()

    return InvitationResponse(
        invitation_id=f"inv_{invitation.id.hex}",
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
    )


@router.patch(
    "/{tenant_id}/members/{user_id}", response_model=MemberResponse, summary="Update member role"
)
async def update_member(
    body: UpdateMemberRequest,
    tenant_id: str = Path(...),
    user_id: str = Path(...),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_MEMBERS)),
) -> MemberResponse:
    tid = UUID(tenant_id.removeprefix("tnt_"))
    uid = UUID(user_id.removeprefix("usr_"))

    stmt = select(Membership).where(Membership.tenant_id == tid, Membership.user_id == uid)
    result = await session.execute(stmt)
    membership = result.scalar_one_or_none()
    if not membership:
        raise NotFound(f"Member {user_id} not found in this tenant.")

    membership.role = body.role.value
    membership.account_scopes = body.account_scopes
    membership.region_scopes = body.region_scopes
    await session.flush()

    user_stmt = select(User).where(User.id == uid)
    user_res = await session.execute(user_stmt)
    user = user_res.scalar_one()

    return MemberResponse(
        user_id=f"usr_{user.id.hex}",
        email=user.email,
        role=membership.role,
        status=membership.status,
        account_scopes=membership.account_scopes,
        region_scopes=membership.region_scopes,
        joined_at=membership.created_at,
    )


@router.delete("/{tenant_id}/members/{user_id}", status_code=204, summary="Remove a member")
async def remove_member(
    tenant_id: str = Path(...),
    user_id: str = Path(...),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_MEMBERS)),
) -> None:
    tid = UUID(tenant_id.removeprefix("tnt_"))
    uid = UUID(user_id.removeprefix("usr_"))

    stmt = delete(Membership).where(Membership.tenant_id == tid, Membership.user_id == uid)
    await session.execute(stmt)
