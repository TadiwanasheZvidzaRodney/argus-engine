"""AWS Account Onboarding, Validation, and Region Registry Router."""

from __future__ import annotations

import urllib.parse
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from argus_core.errors import Conflict, NotFound, UnprocessableEntity
from argus_core.events import new_uuid7
from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from argus_api.auth import (
    AuthContext,
    Permission,
    get_tenant_db,
    require_permission,
)
from argus_api.credentials import CredentialBroker, generate_external_id
from argus_api.models import AwsAccount, AwsRegion

router = APIRouter(prefix="/api/v1/aws-accounts", tags=["aws-accounts"])

DEFAULT_REGIONS = ("us-east-1", "us-west-2", "eu-west-1", "ap-southeast-2")
CFN_TEMPLATE_URL = (
    "https://argus-assets.example.com/cloudformation/ArgusEngineOnboarding.template.yaml"
)


class RegionStatus(BaseModel):
    region: str
    enabled: bool
    discovery_status: str
    last_sync_at: datetime | None = None


class AccountResponse(BaseModel):
    id: str
    account_id: str
    alias: str | None = None
    status: str
    read_role_arn: str
    last_validated_at: datetime | None = None
    created_at: datetime
    regions: list[RegionStatus] = Field(default_factory=list)


class OnboardingStartRequest(BaseModel):
    account_id: str = Field(pattern=r"^[0-9]{12}$", description="12-digit AWS Account ID")
    alias: str | None = Field(default=None, max_length=128)
    role_arn: str | None = Field(
        default=None, description="Pre-created role ARN if not using CloudFormation"
    )


class OnboardingStartResponse(BaseModel):
    account_id: str
    external_id: str
    cloudformation_url: str
    parameters: dict[str, str]


class ValidateAccountResponse(BaseModel):
    account_id: str
    status: str
    validated_at: datetime
    enabled_regions: list[str]


class UpdateRegionsRequest(BaseModel):
    enabled_regions: list[str]


@router.get("", response_model=list[AccountResponse], summary="List connected AWS accounts")
async def list_accounts(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[AccountResponse]:
    stmt = (
        select(AwsAccount)
        .where(AwsAccount.tenant_id == auth.tenant_id)
        .options(selectinload(AwsAccount.regions))
    )
    result = await session.execute(stmt)
    accounts = result.scalars().all()

    return [
        AccountResponse(
            id=f"acc_{acc.id.hex}",
            account_id=acc.account_id,
            alias=acc.alias,
            status=acc.status,
            read_role_arn=acc.read_role_arn,
            last_validated_at=acc.last_validated_at,
            created_at=acc.created_at,
            regions=[
                RegionStatus(
                    region=r.region,
                    enabled=r.enabled,
                    discovery_status=r.discovery_status,
                    last_sync_at=r.last_sync_at,
                )
                for r in acc.regions
            ],
        )
        for acc in accounts
        if auth.can_access_account(acc.account_id)
    ]


@router.post(
    "/onboarding", response_model=OnboardingStartResponse, summary="Start account onboarding"
)
async def start_onboarding(
    body: OnboardingStartRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> OnboardingStartResponse:
    # Check if already registered
    existing_stmt = select(AwsAccount).where(
        AwsAccount.tenant_id == auth.tenant_id, AwsAccount.account_id == body.account_id
    )
    if (await session.execute(existing_stmt)).scalar_one_or_none():
        raise Conflict(f"AWS Account {body.account_id} is already onboarded for this tenant.")

    external_id_bundle = generate_external_id(auth.tenant_id)

    # Register external ID in the credential broker vault
    broker: CredentialBroker = getattr(request.app.state, "credential_broker", CredentialBroker())
    request.app.state.credential_broker = broker
    broker.register_external_id(external_id_bundle.secret_ref, external_id_bundle.plaintext)

    role_arn = (
        body.role_arn
        or f"arn:aws:iam::{body.account_id}:role/ArgusEngineReadRole-tnt_{auth.tenant_id}"
    )

    account = AwsAccount(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        account_id=body.account_id,
        alias=body.alias,
        read_role_arn=role_arn,
        external_id_secret_ref=external_id_bundle.secret_ref,
        external_id_fingerprint=external_id_bundle.fingerprint,
        status="pending",
        created_by=auth.user_id,
    )
    session.add(account)
    await session.flush()

    # Pre-populate default regions
    for reg in DEFAULT_REGIONS:
        session.add(
            AwsRegion(
                id=new_uuid7(),
                tenant_id=auth.tenant_id,
                account_id=account.id,
                region=reg,
                enabled=True,
                discovery_status="pending",
            )
        )

    # Construct one-click CloudFormation launch URL
    stack_name = f"ArgusEngineOnboarding-{body.account_id}"
    cfn_params = {
        "ArgusTenantId": f"tnt_{auth.tenant_id}",
        "ArgusExternalId": external_id_bundle.plaintext,
        "ArgusPlatformAccountId": "111122223333",
    }
    encoded_params = [f"param_{k}={urllib.parse.quote(v)}" for k, v in cfn_params.items()]
    cfn_url = (
        f"https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review"
        f"?templateURL={urllib.parse.quote(CFN_TEMPLATE_URL)}"
        f"&stackName={stack_name}"
        f"&{'&'.join(encoded_params)}"
    )

    return OnboardingStartResponse(
        account_id=body.account_id,
        external_id=external_id_bundle.plaintext,
        cloudformation_url=cfn_url,
        parameters=cfn_params,
    )


@router.post(
    "/{account_ref}/validate", response_model=ValidateAccountResponse, summary="Validate connection"
)
async def validate_account(
    request: Request,
    account_ref: str = Path(..., description="Account UUID or 12-digit AWS Account ID"),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> ValidateAccountResponse:
    # Resolve account
    stmt = (
        select(AwsAccount)
        .where(
            AwsAccount.tenant_id == auth.tenant_id,
            (AwsAccount.account_id == account_ref)
            | (
                AwsAccount.id == UUID(account_ref.removeprefix("acc_"))
                if len(account_ref) > 12
                else False
            ),
        )
        .options(selectinload(AwsAccount.regions))
    )
    account = (await session.execute(stmt)).scalar_one_or_none()
    if not account:
        raise NotFound(f"Account {account_ref} not found.")

    broker: CredentialBroker = getattr(request.app.state, "credential_broker", CredentialBroker())

    now = datetime.now(tz=UTC)
    try:
        await broker.validate_connection(
            tenant_id=auth.tenant_id,
            account_id=account.account_id,
            role_arn=account.read_role_arn,
            external_id_secret_ref=account.external_id_secret_ref,
        )
    except Exception as exc:
        account.status = "error"
        raise UnprocessableEntity(f"Validation failed: {exc}") from exc

    account.status = "active"
    account.last_validated_at = now
    await session.flush()

    return ValidateAccountResponse(
        account_id=account.account_id,
        status=account.status,
        validated_at=now,
        enabled_regions=[r.region for r in account.regions if r.enabled],
    )


@router.get("/{account_ref}/health", summary="Get account connection health")
async def get_account_health(
    account_ref: str = Path(...),
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    stmt = select(AwsAccount).where(
        AwsAccount.tenant_id == auth.tenant_id,
        (AwsAccount.account_id == account_ref)
        | (
            AwsAccount.id == UUID(account_ref.removeprefix("acc_"))
            if len(account_ref) > 12
            else False
        ),
    )
    account = (await session.execute(stmt)).scalar_one_or_none()
    if not account:
        raise NotFound(f"Account {account_ref} not found.")

    return {
        "account_id": account.account_id,
        "status": account.status,
        "last_validated_at": (
            account.last_validated_at.isoformat() if account.last_validated_at else None
        ),
        "health": "ok" if account.status == "active" else "degraded",
    }
