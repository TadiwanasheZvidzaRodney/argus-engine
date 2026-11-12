"""Deterministic action planners, IAM policy synthesis, and risk scoring.

No model output is ever executed: every plan is compiled from the immutable
catalog template below, so identical intents, graph versions, and template
versions always produce the same plan hash.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from argus_api.actions.catalog import ActionDefinition
from argus_api.actions.intent import ActionIntentRequest, target_resource_ids
from argus_api.actions.types import RiskLevel, escalate, risk_rank


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    blast_radius: int
    reversible: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "blast_radius": self.blast_radius,
            "reversible": self.reversible,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class PlanDraft:
    plan_hash: str
    summary: str
    risk: dict[str, Any]
    changes: list[dict[str, Any]]
    permissions: list[str]
    diff: dict[str, Any]
    rollback: dict[str, Any]
    blast_radius: int
    template_version: str
    iam_policy: dict[str, Any] | None
    policy_findings: list[dict[str, Any]]


def stable_hash(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalise(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalise(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    return value


def _bucket_name(arn: str) -> str:
    name = arn.removeprefix("arn:aws:s3:::")
    return name.split("/", 1)[0]


def _is_public_cidr(value: str) -> bool:
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError:
        return False
    return network.prefixlen == 0


def build_iam_policy(intent: ActionIntentRequest) -> dict[str, Any] | None:
    if intent.type != "iam.grant_s3_access" or not intent.targets.target:
        return None

    bucket = _bucket_name(intent.targets.target)
    actions = [str(item) for item in intent.parameters.get("actions", [])]
    prefix = str(intent.parameters.get("prefix", "")).lstrip("/")
    resources: list[str] = []
    if any(action in ("s3:GetObject", "s3:PutObject", "s3:DeleteObject") for action in actions):
        resources.append(
            f"arn:aws:s3:::{bucket}/{prefix}*" if prefix else f"arn:aws:s3:::{bucket}/*"
        )
    if any(action in ("s3:ListBucket", "s3:ListBucketVersions") for action in actions):
        resources.append(f"arn:aws:s3:::{bucket}")
    if not resources:
        resources.append(f"arn:aws:s3:::{bucket}/*")

    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ArgusLeastPrivilegeS3Access",
                "Effect": "Allow",
                "Action": actions,
                "Resource": resources,
            }
        ],
    }


def validate_iam_policy(policy: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not policy:
        return []
    findings: list[dict[str, Any]] = []
    for index, statement in enumerate(policy.get("Statement", [])):
        actions = statement.get("Action", [])
        resources = statement.get("Resource", [])
        if isinstance(actions, str):
            actions = [actions]
        if isinstance(resources, str):
            resources = [resources]
        for action in actions:
            if action == "*" or action.endswith(":*"):
                findings.append(
                    {
                        "code": "wildcard-action",
                        "severity": "high",
                        "pointer": f"/Statement/{index}/Action",
                        "detail": f"Wildcard action {action!r} grants broader access than planned.",
                    }
                )
        for resource in resources:
            if resource == "*":
                findings.append(
                    {
                        "code": "wildcard-resource",
                        "severity": "high",
                        "pointer": f"/Statement/{index}/Resource",
                        "detail": "Wildcard resource exposes every object in the account.",
                    }
                )
    return findings


def assess_risk(intent: ActionIntentRequest, definition: ActionDefinition) -> RiskAssessment:
    resources = target_resource_ids(intent)
    reasons: list[str] = []
    level = definition.risk_level
    blast_radius = len(resources) or 1

    if intent.constraints.environment == "prod":
        reasons.append("production environment")
        level = escalate(level)
    if blast_radius > definition.max_blast_radius:
        reasons.append(f"blast radius {blast_radius} exceeds {definition.max_blast_radius}")
        level = escalate(level)
    if not definition.reversible:
        reasons.append("irreversible operation")
        level = escalate(level)

    params = intent.parameters
    actions = params.get("actions", [])
    if isinstance(actions, list) and any(
        action == "*" or str(action).endswith(":*") for action in actions
    ):
        reasons.append("wildcard IAM action")
        level = RiskLevel.CRITICAL

    if intent.type != "network.restrict_security_group_ingress":
        for candidate in (
            params.get("cidr"),
            params.get("source_cidr"),
            intent.targets.source if intent.targets.source else None,
        ):
            if isinstance(candidate, str) and _is_public_cidr(candidate):
                reasons.append("public exposure (0.0.0.0/0)")
                level = RiskLevel.CRITICAL

    if intent.constraints.break_glass:
        reasons.append("break-glass execution")
        level = RiskLevel.CRITICAL

    if not reasons:
        reasons.append(f"{definition.category} change")

    # Keep the highest severity reached by any escalation path.
    return RiskAssessment(
        level=RiskLevel(level),
        blast_radius=blast_radius,
        reversible=definition.reversible,
        reasons=tuple(reasons),
    )


def _change(
    resource: str,
    operation: str,
    attribute: str,
    before: Any,
    after: Any,
    description: str,
) -> dict[str, Any]:
    return {
        "resource": resource,
        "operation": operation,
        "attribute": attribute,
        "before_hash": stable_hash({"before": before}),
        "after_hash": stable_hash({"after": after}),
        "description": description,
    }


def build_changes(intent: ActionIntentRequest) -> list[dict[str, Any]]:
    params = intent.parameters
    ids = target_resource_ids(intent)
    source = intent.targets.source
    target = intent.targets.target

    if intent.type == "iam.grant_s3_access" and source and target:
        changes = [
            _change(
                source,
                "update",
                "inline_policy",
                {"policy": None},
                {"policy": "ArgusLeastPrivilegeS3Access"},
                f"Attach least-privilege S3 policy to {source}.",
            )
        ]
        if params.get("update_bucket_policy"):
            changes.append(
                _change(
                    target,
                    "update",
                    "bucket_policy",
                    {"allows_role": False},
                    {"allows_role": True},
                    "Add a bucket policy allowing the planned role.",
                )
            )
        return changes

    if intent.type == "network.allow_security_group_ingress" and target:
        return [
            _change(
                target,
                "update",
                "ingress_rules",
                {"rules": []},
                {
                    "source": source,
                    "port": params.get("port", params.get("from_port")),
                    "protocol": params.get("protocol", "tcp"),
                    "cidr": params.get("cidr"),
                },
                "Authorize a new ingress rule on the target security group.",
            )
        ]

    if intent.type == "network.restrict_security_group_ingress":
        security_group = target or (ids[0] if ids else "")
        return [
            _change(
                security_group,
                "revoke",
                "ingress_rules",
                {
                    "cidr": params.get("cidr", "0.0.0.0/0"),
                    "port": params.get("port"),
                    "protocol": params.get("protocol", "tcp"),
                },
                {"revoked": True},
                "Revoke the internet-exposed ingress rule and verify the port is closed.",
            )
        ]

    if intent.type == "s3.harden_bucket":
        bucket = target or (ids[0] if ids else "")
        return [
            _change(
                bucket,
                "update",
                "versioning",
                {"status": "Suspended"},
                {"status": "Enabled"},
                "Enable bucket versioning.",
            ),
            _change(
                bucket,
                "update",
                "encryption",
                {"algorithm": "none"},
                {"algorithm": "aws:kms", "kms_key": params.get("kms_key_arn")},
                "Enable SSE-KMS default encryption.",
            ),
            _change(
                bucket,
                "update",
                "public_access_block",
                {"block_public_acls": False, "ignore_public_acls": False},
                {
                    "block_public_acls": True,
                    "ignore_public_acls": True,
                    "block_public_policy": True,
                    "restrict_public_buckets": True,
                },
                "Block all public access at the bucket level.",
            ),
            _change(
                bucket,
                "update",
                "bucket_policy",
                {"tls_only": False},
                {"tls_only": True},
                "Enforce TLS-only access in the bucket policy.",
            ),
        ]

    if intent.type == "iam.attach_least_privilege_policy" and source:
        return [
            _change(
                source,
                "update",
                "attached_policies",
                {"policies": []},
                {"policies": ["ArgusSynthesizedPolicy"], "actions": params.get("actions", [])},
                "Attach a synthesized least-privilege managed policy.",
            )
        ]

    if intent.type == "tagging.apply":
        tags = params.get("tags", {})
        operation = "untag" if params.get("mode") == "remove" else "tag"
        return [
            _change(
                resource,
                operation,
                "tags",
                {"tags": {}},
                {"tags": tags},
                f"{operation.capitalize()} {len(tags)} tag(s).",
            )
            for resource in ids
        ]

    if intent.type == "ec2.stop_start_instance" and source:
        return [
            _change(
                source,
                "update",
                "instance_state",
                {"state": "running"},
                {"state": "running", "intermediate": "stopped"},
                "Stop then start the instance and verify it returns to running.",
            ),
        ]

    if intent.type == "observability.create_alarm":
        resource = source or (ids[0] if ids else "")
        return [
            _change(
                resource,
                "create",
                "metric_alarm",
                {"alarm": None},
                {
                    "metric_name": params.get("metric_name"),
                    "threshold": params.get("threshold"),
                    "comparison": params.get("comparison", "GreaterThanThreshold"),
                },
                "Create a CloudWatch metric alarm.",
            ),
        ]

    if intent.type == "optimization.resize_instance" and source:
        return [
            _change(
                source,
                "update",
                "instance_type",
                {"instance_type": params.get("current_instance_type", "unknown")},
                {"instance_type": params.get("instance_type")},
                "Change the instance type during a maintenance window.",
            ),
        ]

    return [
        _change(
            resource,
            "update",
            "configuration",
            {"configured": False},
            {"configured": True},
            "Apply the planned configuration change.",
        )
        for resource in ids
    ]


def _summary(intent: ActionIntentRequest) -> str:
    source = intent.targets.source or "the selected resources"
    target = intent.targets.target
    params = intent.parameters

    if intent.type == "iam.grant_s3_access" and target:
        actions = ", ".join(str(item) for item in params.get("actions", []))
        prefix = params.get("prefix")
        scope = f"/{prefix}" if prefix else "/*"
        return f"Grant {source} {actions} on {_bucket_name(target)}{scope}."
    if intent.type == "network.allow_security_group_ingress" and target:
        port = params.get("port", params.get("from_port"))
        return f"Allow {source} to reach {target} on port {port}."
    if intent.type == "network.restrict_security_group_ingress":
        security_group = target or (target_resource_ids(intent) or ["security group"])[0]
        port = params.get("port", "all")
        cidr = params.get("cidr", "0.0.0.0/0")
        return f"Revoke {cidr} access to {security_group} on port {port}."
    if intent.type == "s3.harden_bucket":
        bucket = target or (target_resource_ids(intent) or ["bucket"])[0]
        return f"Harden S3 bucket {_bucket_name(bucket)} with versioning, SSE-KMS, BPA, and TLS."
    if intent.type == "iam.attach_least_privilege_policy":
        return f"Attach a least-privilege policy to {source}."
    if intent.type == "tagging.apply":
        tags = ", ".join(sorted(params.get("tags", {})))
        return f"Apply tags [{tags}] to {len(target_resource_ids(intent))} resource(s)."
    if intent.type == "ec2.stop_start_instance":
        return f"Stop and start {source} with verification and rollback."
    if intent.type == "optimization.resize_instance":
        return f"Resize {source} to {params.get('instance_type')}."
    return f"Apply {intent.type} to {source}."


def build_plan(
    *,
    intent: ActionIntentRequest,
    definition: ActionDefinition,
    risk: RiskAssessment,
    tenant_id: str,
    action_id: str,
    graph_version: int,
    expires_at: datetime,
) -> PlanDraft:
    changes = build_changes(intent)
    iam_policy = build_iam_policy(intent)
    findings = validate_iam_policy(iam_policy)
    permissions = sorted(set(definition.required_permissions))

    canonical_constraints = {
        "environment": intent.constraints.environment,
        "maintenance_window": intent.constraints.maintenance_window,
        "break_glass": intent.constraints.break_glass,
    }
    hash_payload = {
        "action_type": intent.type,
        "targets": {
            "source": intent.targets.source,
            "target": intent.targets.target,
            "resources": sorted(intent.targets.resources),
        },
        "parameters": _normalise(intent.parameters),
        "constraints": _normalise(canonical_constraints),
        "graph_version": graph_version,
        "template_version": definition.plan_template,
        "changes": changes,
        "permissions": permissions,
        "risk": risk.to_dict(),
        "iam_policy": iam_policy,
    }
    plan_hash = stable_hash(hash_payload)

    affected = target_resource_ids(intent)
    diff = {
        "format": "visual-diff",
        "added_node_ids": [],
        "removed_node_ids": [],
        "changed_attributes": [
            {
                "resource": change["resource"],
                "attribute": change["attribute"],
                "operation": change["operation"],
                "before_hash": change["before_hash"],
                "after_hash": change["after_hash"],
            }
            for change in changes
        ],
        "affected_resources": affected,
    }
    rollback = {
        "strategy": "previous-template",
        "template": definition.rollback_template,
        "artifact": (
            f"s3://argus-action-evidence/tenant={tenant_id}/action={action_id}/rollback.json"
        ),
        "expires_at": expires_at.isoformat(),
    }

    return PlanDraft(
        plan_hash=plan_hash,
        summary=_summary(intent),
        risk=risk.to_dict(),
        changes=changes,
        permissions=permissions,
        diff=diff,
        rollback=rollback,
        blast_radius=risk.blast_radius,
        template_version=definition.plan_template,
        iam_policy=iam_policy,
        policy_findings=findings,
    )


def risk_requires_break_glass(level: RiskLevel) -> bool:
    return risk_rank(level) >= risk_rank(RiskLevel.CRITICAL)
