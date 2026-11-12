"""Cost allocation engine, resource cost estimator, and monthly reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from argus_api.cost.types import CostConfidence

# Estimated monthly pricing constants (USD)
EC2_PRICING_MONTHLY: dict[str, float] = {
    "t3.micro": 8.50,
    "t3.small": 17.00,
    "t3.medium": 34.00,
    "m5.large": 72.00,
    "m5.xlarge": 144.00,
    "m5.2xlarge": 288.00,
    "c5.xlarge": 128.00,
    "r5.xlarge": 184.00,
    "m6g.xlarge": 115.00,  # Graviton
}

RDS_PRICING_MONTHLY: dict[str, float] = {
    "db.t3.medium": 52.00,
    "db.m5.large": 135.00,
    "db.m5.xlarge": 270.00,
    "db.r6g.xlarge": 375.00,
}

EBS_GP3_PER_GB_MONTH = 0.08
ALB_BASE_MONTHLY = 22.50


@dataclass(frozen=True)
class ResourceCostEstimate:
    resource_id: str
    resource_type: str
    daily_amount: float
    monthly_amount: float
    confidence: CostConfidence
    method: str
    currency: str = "USD"


def estimate_resource_cost(node: dict[str, Any]) -> ResourceCostEstimate:
    """Derive estimated cost, confidence level, and calculation method for a graph node."""
    node_type = str(node.get("type", ""))
    props = dict(node.get("properties") or {})
    res_id = str(node.get("id", ""))

    if node_type == "AWS::EC2::Instance":
        inst_type = str(props.get("instance_type", "m5.xlarge"))
        monthly = EC2_PRICING_MONTHLY.get(inst_type, 144.00)
        daily = round(monthly / 30.0, 4)
        return ResourceCostEstimate(
            resource_id=res_id,
            resource_type=node_type,
            daily_amount=daily,
            monthly_amount=monthly,
            confidence=CostConfidence.ESTIMATED,
            method=f"On-demand baseline for {inst_type} running 24h/day.",
        )

    if node_type == "AWS::EC2::Volume":
        size_gib = int(props.get("size_gib", 100))
        monthly = round(size_gib * EBS_GP3_PER_GB_MONTH, 2)
        daily = round(monthly / 30.0, 4)
        return ResourceCostEstimate(
            resource_id=res_id,
            resource_type=node_type,
            daily_amount=daily,
            monthly_amount=monthly,
            confidence=CostConfidence.ALLOCATED,
            method=f"EBS gp3 storage rate (${EBS_GP3_PER_GB_MONTH}/GB-mo) for {size_gib} GiB.",
        )

    if node_type == "AWS::RDS::DBInstance":
        inst_class = str(props.get("instance_class", "db.r6g.xlarge"))
        monthly = RDS_PRICING_MONTHLY.get(inst_class, 375.00)
        daily = round(monthly / 30.0, 4)
        return ResourceCostEstimate(
            resource_id=res_id,
            resource_type=node_type,
            daily_amount=daily,
            monthly_amount=monthly,
            confidence=CostConfidence.ESTIMATED,
            method=f"Single-region RDS pricing for {inst_class} with provisioned storage.",
        )

    if node_type == "AWS::ElasticLoadBalancingV2::LoadBalancer":
        monthly = ALB_BASE_MONTHLY
        daily = round(monthly / 30.0, 4)
        return ResourceCostEstimate(
            resource_id=res_id,
            resource_type=node_type,
            daily_amount=daily,
            monthly_amount=monthly,
            confidence=CostConfidence.ALLOCATED,
            method="Base ALB provisioned hourly fee ($0.0225/hr) excluding LCU throughput.",
        )

    if node_type == "AWS::S3::Bucket":
        monthly = 24.00
        daily = round(monthly / 30.0, 4)
        return ResourceCostEstimate(
            resource_id=res_id,
            resource_type=node_type,
            daily_amount=daily,
            monthly_amount=monthly,
            confidence=CostConfidence.ESTIMATED,
            method="S3 Standard storage tier prorated from monthly volume telemetry.",
        )

    if node_type == "AWS::Lambda::Function":
        monthly = 12.00
        daily = round(monthly / 30.0, 4)
        return ResourceCostEstimate(
            resource_id=res_id,
            resource_type=node_type,
            daily_amount=daily,
            monthly_amount=monthly,
            confidence=CostConfidence.ESTIMATED,
            method="Estimated execution compute (duration x memory) from invocation telemetry.",
        )

    if node_type == "AWS::SecretsManager::Secret":
        monthly = 0.40
        daily = round(monthly / 30.0, 4)
        return ResourceCostEstimate(
            resource_id=res_id,
            resource_type=node_type,
            daily_amount=daily,
            monthly_amount=monthly,
            confidence=CostConfidence.ALLOCATED,
            method="AWS Secrets Manager active secret standard charge ($0.40/secret/mo).",
        )

    return ResourceCostEstimate(
        resource_id=res_id,
        resource_type=node_type,
        daily_amount=0.0,
        monthly_amount=0.0,
        confidence=CostConfidence.UNKNOWN,
        method="Zero direct charge or shared infrastructure item.",
    )


def reconcile_period_totals(
    total_service_spend: float,
    allocated_resource_spend: float,
) -> tuple[float, float, float]:
    """Calculate allocated, unallocated, and variance percentage.

    Invariant: allocated + unallocated = total_service_spend.
    """
    total = max(0.0, total_service_spend)
    allocated = min(total, max(0.0, allocated_resource_spend))
    unallocated = round(total - allocated, 4)
    variance_pct = round(abs((allocated + unallocated) - total) / (total or 1.0) * 100, 3)
    return allocated, unallocated, variance_pct
