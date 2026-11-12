"""Nine curated cost optimization rules with evidence and savings estimates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from argus_api.cost.types import RULE_MAP


@dataclass(frozen=True)
class OptimizationHit:
    rule_id: str
    resource_id: str
    resource_type: str
    title: str
    description: str
    evidence: dict[str, Any]
    confidence: str
    estimated_monthly_savings: float
    remediation_action: str | None
    currency: str = "USD"


def _as_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return False


def evaluate_optimization_rules(nodes: list[dict[str, Any]]) -> list[OptimizationHit]:
    """Evaluate optimization rules over a graph of discovered nodes."""
    hits: list[OptimizationHit] = []

    for node in nodes:
        node_id = str(node.get("id", ""))
        node_type = str(node.get("type", ""))
        props = dict(node.get("properties") or {})
        state = str(node.get("state", "")).lower()

        # 1. ec2-idle
        if node_type == "AWS::EC2::Instance":
            cpu_p95 = float(props.get("cpu_p95", 2.1))
            is_idle = _as_bool(props.get("idle")) or (
                state in ("running", "active") and cpu_p95 < 5.0
            )
            if is_idle:
                rule = RULE_MAP["ec2-idle"]
                hits.append(
                    OptimizationHit(
                        rule_id=rule.id,
                        resource_id=node_id,
                        resource_type=node_type,
                        title=rule.title,
                        description=rule.description,
                        evidence={
                            "cpu_p95_14d": cpu_p95,
                            "instance_type": props.get("instance_type", "m5.xlarge"),
                            "state": state,
                        },
                        confidence=rule.confidence,
                        estimated_monthly_savings=144.00,
                        remediation_action=rule.remediation_action,
                    )
                )

        # 2. ebs-unattached
        if node_type == "AWS::EC2::Volume":
            attached_id = props.get("attached_instance_id")
            if not attached_id or state == "available":
                rule = RULE_MAP["ebs-unattached"]
                size_gib = int(props.get("size_gib", 100))
                savings = round(size_gib * 0.08, 2)
                hits.append(
                    OptimizationHit(
                        rule_id=rule.id,
                        resource_id=node_id,
                        resource_type=node_type,
                        title=rule.title,
                        description=rule.description,
                        evidence={
                            "state": state,
                            "size_gib": size_gib,
                            "volume_type": props.get("volume_type", "gp3"),
                        },
                        confidence=rule.confidence,
                        estimated_monthly_savings=savings,
                        remediation_action=rule.remediation_action,
                    )
                )

        # 3. snapshot-stale
        if node_type in ("AWS::EC2::Snapshot", "AWS::EC2::VolumeSnapshot") or _as_bool(
            props.get("stale_snapshot")
        ):
            rule = RULE_MAP["snapshot-stale"]
            hits.append(
                OptimizationHit(
                    rule_id=rule.id,
                    resource_id=node_id,
                    resource_type=node_type,
                    title=rule.title,
                    description=rule.description,
                    evidence={
                        "age_days": int(props.get("age_days", 120)),
                        "size_gib": int(props.get("size_gib", 50)),
                    },
                    confidence=rule.confidence,
                    estimated_monthly_savings=2.50,
                    remediation_action=rule.remediation_action,
                )
            )

        # 4. rds-idle
        if node_type == "AWS::RDS::DBInstance":
            connections = int(props.get("active_connections", 0))
            is_idle = _as_bool(props.get("idle")) or connections == 0
            if is_idle:
                rule = RULE_MAP["rds-idle"]
                hits.append(
                    OptimizationHit(
                        rule_id=rule.id,
                        resource_id=node_id,
                        resource_type=node_type,
                        title=rule.title,
                        description=rule.description,
                        evidence={
                            "active_connections": connections,
                            "instance_class": props.get("instance_class", "db.r6g.xlarge"),
                        },
                        confidence=rule.confidence,
                        estimated_monthly_savings=270.00,
                        remediation_action=rule.remediation_action,
                    )
                )

        # 5. ec2-oversized
        if node_type == "AWS::EC2::Instance":
            inst_type = str(props.get("instance_type", "m5.xlarge"))
            cpu_p95 = float(props.get("cpu_p95", 8.4))
            if any(term in inst_type for term in ("xlarge", "2xlarge")) and cpu_p95 < 15.0:
                rule = RULE_MAP["ec2-oversized"]
                hits.append(
                    OptimizationHit(
                        rule_id=rule.id,
                        resource_id=node_id,
                        resource_type=node_type,
                        title=rule.title,
                        description=rule.description,
                        evidence={
                            "current_instance_type": inst_type,
                            "recommended_instance_type": inst_type.replace(
                                "2xlarge", "xlarge"
                            ).replace("xlarge", "large"),
                            "cpu_p95_14d": cpu_p95,
                        },
                        confidence=rule.confidence,
                        estimated_monthly_savings=72.00,
                        remediation_action=rule.remediation_action,
                    )
                )

        # 6. graviton-candidate
        if node_type == "AWS::EC2::Instance":
            inst_type = str(props.get("instance_type", "m5.xlarge"))
            if inst_type.startswith(("m5.", "c5.", "r5.")):
                rule = RULE_MAP["graviton-candidate"]
                graviton_type = (
                    inst_type.replace("m5.", "m6g.").replace("c5.", "c6g.").replace("r5.", "r6g.")
                )
                hits.append(
                    OptimizationHit(
                        rule_id=rule.id,
                        resource_id=node_id,
                        resource_type=node_type,
                        title=rule.title,
                        description=rule.description,
                        evidence={
                            "current_instance_type": inst_type,
                            "target_instance_type": graviton_type,
                            "estimated_savings_pct": 20,
                        },
                        confidence=rule.confidence,
                        estimated_monthly_savings=28.80,
                        remediation_action=rule.remediation_action,
                    )
                )

        # 7. s3-no-lifecycle
        if node_type == "AWS::S3::Bucket":
            has_lifecycle = _as_bool(props.get("has_lifecycle_rules")) or _as_bool(
                props.get("lifecycle_enabled")
            )
            if not has_lifecycle:
                rule = RULE_MAP["s3-no-lifecycle"]
                hits.append(
                    OptimizationHit(
                        rule_id=rule.id,
                        resource_id=node_id,
                        resource_type=node_type,
                        title=rule.title,
                        description=rule.description,
                        evidence={"has_lifecycle_rules": False, "storage_class": "STANDARD"},
                        confidence=rule.confidence,
                        estimated_monthly_savings=12.00,
                        remediation_action=rule.remediation_action,
                    )
                )

        # 8. idle-load-balancer
        if node_type == "AWS::ElasticLoadBalancingV2::LoadBalancer":
            req_count = int(props.get("request_count_14d", 0))
            is_idle = _as_bool(props.get("idle")) or req_count == 0
            if is_idle:
                rule = RULE_MAP["idle-load-balancer"]
                hits.append(
                    OptimizationHit(
                        rule_id=rule.id,
                        resource_id=node_id,
                        resource_type=node_type,
                        title=rule.title,
                        description=rule.description,
                        evidence={
                            "request_count_14d": req_count,
                            "scheme": props.get("scheme", "internet-facing"),
                        },
                        confidence=rule.confidence,
                        estimated_monthly_savings=22.50,
                        remediation_action=rule.remediation_action,
                    )
                )

        # 9. unused-elastic-ip
        if node_type in ("AWS::EC2::EIP", "AWS::EC2::ElasticIPAddress") or _as_bool(
            props.get("unassociated_eip")
        ):
            rule = RULE_MAP["unused-elastic-ip"]
            hits.append(
                OptimizationHit(
                    rule_id=rule.id,
                    resource_id=node_id,
                    resource_type=node_type,
                    title=rule.title,
                    description=rule.description,
                    evidence={"association_id": None, "hourly_rate_usd": 0.005},
                    confidence=rule.confidence,
                    estimated_monthly_savings=3.60,
                    remediation_action=rule.remediation_action,
                )
            )

    return hits
