"""Typed contracts and definitions for Phase 8 cost intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CostConfidence(StrEnum):
    EXACT = "exact"
    ALLOCATED = "allocated"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class BudgetScopeType(StrEnum):
    TENANT = "tenant"
    ACCOUNT = "account"
    SERVICE = "service"
    TAG = "tag"


class BudgetPeriod(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class RecommendationStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISMISSED = "DISMISSED"
    REMEDIATED = "REMEDIATED"


@dataclass(frozen=True)
class OptimizationRule:
    id: str
    title: str
    description: str
    resource_type: str
    confidence: str
    remediation_action: str | None = None
    default_risk: str = "medium"


OPTIMIZATION_RULES: tuple[OptimizationRule, ...] = (
    OptimizationRule(
        id="ec2-idle",
        title="EC2 instance is idle",
        description=(
            "The instance has sustained CPU utilization p95 < 5% over the past 14 days. "
            "Consider stopping or terminating it."
        ),
        resource_type="AWS::EC2::Instance",
        confidence="high",
        remediation_action="ec2.stop_start_instance",
        default_risk="medium",
    ),
    OptimizationRule(
        id="ebs-unattached",
        title="Unattached EBS volume incurring storage cost",
        description=(
            "The volume has remained in 'available' state without an attached instance "
            "for more than 7 days."
        ),
        resource_type="AWS::EC2::Volume",
        confidence="high",
        remediation_action=None,
        default_risk="low",
    ),
    OptimizationRule(
        id="snapshot-stale",
        title="EBS snapshot exceeds retention window",
        description=(
            "The snapshot is older than 90 days and is not referenced by an active AMI "
            "or compliance lock."
        ),
        resource_type="AWS::EC2::Snapshot",
        confidence="medium",
        remediation_action=None,
        default_risk="low",
    ),
    OptimizationRule(
        id="rds-idle",
        title="RDS instance has negligible database traffic",
        description=(
            "The database has recorded zero active connections and low CPU over the "
            "14-day evaluation window."
        ),
        resource_type="AWS::RDS::DBInstance",
        confidence="medium",
        remediation_action=None,
        default_risk="medium",
    ),
    OptimizationRule(
        id="ec2-oversized",
        title="EC2 instance is oversized for its workload",
        description=(
            "CPU utilization peak is well below family capacity. Downsizing instance "
            "class would reduce run rate by ~50%."
        ),
        resource_type="AWS::EC2::Instance",
        confidence="high",
        remediation_action="optimization.resize_instance",
        default_risk="medium",
    ),
    OptimizationRule(
        id="graviton-candidate",
        title="Instance is a candidate for AWS Graviton upgrade",
        description=(
            "Workload is running on x86 compute that has a direct Graviton counterpart "
            "delivering ~20% better price-performance."
        ),
        resource_type="AWS::EC2::Instance",
        confidence="medium",
        remediation_action="optimization.resize_instance",
        default_risk="medium",
    ),
    OptimizationRule(
        id="s3-no-lifecycle",
        title="S3 bucket has no lifecycle transition rules",
        description=(
            "Objects remain in S3 Standard indefinitely without transition to "
            "Infrequent Access or Glacier."
        ),
        resource_type="AWS::S3::Bucket",
        confidence="medium",
        remediation_action=None,
        default_risk="low",
    ),
    OptimizationRule(
        id="idle-load-balancer",
        title="Load balancer received zero target requests",
        description=(
            "The Application Load Balancer has routed no traffic over the past 14 days "
            "while incurring base hourly charges."
        ),
        resource_type="AWS::ElasticLoadBalancingV2::LoadBalancer",
        confidence="high",
        remediation_action=None,
        default_risk="low",
    ),
    OptimizationRule(
        id="unused-elastic-ip",
        title="Unassociated Elastic IP incurring idle hourly fee",
        description=(
            "The allocated Elastic IP address is not attached to any running instance "
            "or network interface."
        ),
        resource_type="AWS::EC2::EIP",
        confidence="high",
        remediation_action=None,
        default_risk="low",
    ),
)

RULE_MAP: dict[str, OptimizationRule] = {rule.id: rule for rule in OPTIMIZATION_RULES}
