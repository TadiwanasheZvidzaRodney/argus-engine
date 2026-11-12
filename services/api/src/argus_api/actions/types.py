"""Shared action-engine enums and value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def risk_rank(level: RiskLevel) -> int:
    return _RISK_RANK[level]


def escalate(level: RiskLevel, steps: int = 1) -> RiskLevel:
    rank = min(len(_RISK_RANK) - 1, _RISK_RANK[level] + max(0, steps))
    return next(member for member, value in _RISK_RANK.items() if value == rank)


def risk_from_str(value: str) -> RiskLevel:
    return RiskLevel(value.lower())


class ActionStatus(StrEnum):
    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    PLAN_FAILED = "PLAN_FAILED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ExecutionStatus(StrEnum):
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True)
class ApprovalPolicy:
    required_approvals: int
    requester_may_approve: bool
    requires_mfa: bool
    expiry_minutes: int


APPROVAL_POLICIES: dict[RiskLevel, ApprovalPolicy] = {
    RiskLevel.LOW: ApprovalPolicy(
        required_approvals=1,
        requester_may_approve=True,
        requires_mfa=False,
        expiry_minutes=30,
    ),
    RiskLevel.MEDIUM: ApprovalPolicy(
        required_approvals=1,
        requester_may_approve=False,
        requires_mfa=True,
        expiry_minutes=60,
    ),
    RiskLevel.HIGH: ApprovalPolicy(
        required_approvals=2,
        requester_may_approve=False,
        requires_mfa=True,
        expiry_minutes=240,
    ),
    RiskLevel.CRITICAL: ApprovalPolicy(
        required_approvals=2,
        requester_may_approve=False,
        requires_mfa=True,
        expiry_minutes=60,
    ),
}


def approval_policy_for(level: RiskLevel) -> ApprovalPolicy:
    return APPROVAL_POLICIES[level]
