"""Static action catalog.

The catalog is intentionally code-defined and versioned: the database table is a
read projection used for listing/enablement, while planners always use these
immutable definitions so a compromised row cannot silently change a template.
"""

from __future__ import annotations

from dataclasses import dataclass

from argus_api.actions.types import RiskLevel


@dataclass(frozen=True)
class ActionDefinition:
    action_type: str
    category: str
    name: str
    description: str
    risk_level: RiskLevel
    required_permissions: tuple[str, ...]
    plan_template: str
    rollback_template: str
    reversible: bool
    max_blast_radius: int
    version: str = "1.0.0"


CATALOG: dict[str, ActionDefinition] = {
    "iam.grant_s3_access": ActionDefinition(
        action_type="iam.grant_s3_access",
        category="identity_access",
        name="Grant S3 access to a role",
        description=(
            "Attach a least-privilege inline policy granting a compute role read or write "
            "access to a specific S3 bucket and prefix."
        ),
        risk_level=RiskLevel.MEDIUM,
        required_permissions=(
            "iam:GetRolePolicy",
            "iam:PutRolePolicy",
            "s3:GetBucketPolicy",
            "access-analyzer:ValidatePolicy",
        ),
        plan_template="iam-grant-s3-v3",
        rollback_template="iam-grant-s3-rollback-v1",
        reversible=True,
        max_blast_radius=2,
    ),
    "network.allow_security_group_ingress": ActionDefinition(
        action_type="network.allow_security_group_ingress",
        category="network_exposure",
        name="Allow security group ingress",
        description=(
            "Authorize ingress from a source security group or CIDR to a target security "
            "group on a specific port range."
        ),
        risk_level=RiskLevel.HIGH,
        required_permissions=(
            "ec2:AuthorizeSecurityGroupIngress",
            "ec2:DescribeSecurityGroups",
            "ec2:RevokeSecurityGroupIngress",
        ),
        plan_template="sg-ingress-v2",
        rollback_template="sg-ingress-rollback-v1",
        reversible=True,
        max_blast_radius=4,
    ),
    "s3.harden_bucket": ActionDefinition(
        action_type="s3.harden_bucket",
        category="data_protection",
        name="Harden an S3 bucket",
        description=(
            "Enable versioning, SSE-KMS default encryption, Block Public Access, and a "
            "TLS-only bucket policy."
        ),
        risk_level=RiskLevel.HIGH,
        required_permissions=(
            "s3:PutBucketVersioning",
            "s3:PutEncryptionConfiguration",
            "s3:PutBucketPublicAccessBlock",
            "s3:PutBucketPolicy",
        ),
        plan_template="s3-harden-v3",
        rollback_template="s3-harden-rollback-v1",
        reversible=True,
        max_blast_radius=1,
    ),
    "iam.attach_least_privilege_policy": ActionDefinition(
        action_type="iam.attach_least_privilege_policy",
        category="identity_access",
        name="Attach a least-privilege IAM policy",
        description=(
            "Synthesize and attach a scoped managed policy to a role after Access Analyzer "
            "validation."
        ),
        risk_level=RiskLevel.HIGH,
        required_permissions=(
            "iam:CreatePolicy",
            "iam:AttachRolePolicy",
            "iam:GetPolicy",
            "access-analyzer:ValidatePolicy",
            "access-analyzer:CheckNoNewAccess",
        ),
        plan_template="iam-least-privilege-v2",
        rollback_template="iam-least-privilege-rollback-v1",
        reversible=True,
        max_blast_radius=3,
    ),
    "tagging.apply": ActionDefinition(
        action_type="tagging.apply",
        category="resource_configuration",
        name="Apply or remove tags",
        description="Apply or remove a set of tags across selected resources.",
        risk_level=RiskLevel.LOW,
        required_permissions=(
            "tag:GetResources",
            "tag:TagResources",
            "tag:UntagResources",
        ),
        plan_template="tagging-v1",
        rollback_template="tagging-rollback-v1",
        reversible=True,
        max_blast_radius=100,
    ),
    "ec2.stop_start_instance": ActionDefinition(
        action_type="ec2.stop_start_instance",
        category="lifecycle",
        name="Stop and start an EC2 instance",
        description=(
            "Stop an EC2 instance and start it again, with post-action state verification "
            "and a compensating rollback."
        ),
        risk_level=RiskLevel.MEDIUM,
        required_permissions=(
            "ec2:StopInstances",
            "ec2:StartInstances",
            "ec2:DescribeInstances",
        ),
        plan_template="ec2-stop-start-v1",
        rollback_template="ec2-stop-start-rollback-v1",
        reversible=True,
        max_blast_radius=1,
    ),
    "observability.create_alarm": ActionDefinition(
        action_type="observability.create_alarm",
        category="observability",
        name="Create a CloudWatch alarm",
        description="Create a CloudWatch metric alarm with the supplied thresholds and actions.",
        risk_level=RiskLevel.LOW,
        required_permissions=(
            "cloudwatch:PutMetricAlarm",
            "cloudwatch:DescribeAlarms",
        ),
        plan_template="cloudwatch-alarm-v1",
        rollback_template="cloudwatch-alarm-rollback-v1",
        reversible=True,
        max_blast_radius=1,
    ),
    "optimization.resize_instance": ActionDefinition(
        action_type="optimization.resize_instance",
        category="optimization",
        name="Resize an EC2 instance",
        description="Change an instance type during a declared maintenance window with rollback.",
        risk_level=RiskLevel.MEDIUM,
        required_permissions=(
            "ec2:ModifyInstanceAttribute",
            "ec2:StopInstances",
            "ec2:StartInstances",
            "ec2:DescribeInstances",
        ),
        plan_template="ec2-resize-v1",
        rollback_template="ec2-resize-rollback-v1",
        reversible=True,
        max_blast_radius=1,
    ),
    "network.restrict_security_group_ingress": ActionDefinition(
        action_type="network.restrict_security_group_ingress",
        category="network_exposure",
        name="Restrict security group ingress",
        description=(
            "Revoke an internet-exposed ingress rule from a security group and verify that "
            "the exposed port is no longer reachable from 0.0.0.0/0."
        ),
        risk_level=RiskLevel.HIGH,
        required_permissions=(
            "ec2:RevokeSecurityGroupIngress",
            "ec2:DescribeSecurityGroups",
            "ec2:AuthorizeSecurityGroupIngress",
        ),
        plan_template="sg-restrict-v1",
        rollback_template="sg-restrict-rollback-v1",
        reversible=True,
        max_blast_radius=4,
    ),
}


def get_definition(action_type: str) -> ActionDefinition | None:
    return CATALOG.get(action_type)
