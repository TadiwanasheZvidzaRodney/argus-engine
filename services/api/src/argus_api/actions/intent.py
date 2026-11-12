"""Typed action intents and pre-flight validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from argus_core.errors import FieldError, UnprocessableEntity
from pydantic import BaseModel, ConfigDict, Field

from argus_api.actions.catalog import ActionDefinition


class ActionTargets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = Field(default=None, max_length=512)
    target: str | None = Field(default=None, max_length=512)
    resources: list[str] = Field(default_factory=list, max_length=200)

    def all_ids(self) -> list[str]:
        values = [value for value in (self.source, self.target) if value]
        values.extend(self.resources)
        return sorted({value for value in values if value})


class ActionConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_at: datetime | None = None
    environment: Literal["dev", "staging", "prod"] = "staging"
    maintenance_window: bool = False
    break_glass: bool = False
    incident_id: str | None = Field(default=None, max_length=128)
    simulate_failure: bool = Field(
        default=False,
        description="Sandbox-only fault injection; refused outside local/test environments.",
    )
    tags: dict[str, str] = Field(default_factory=dict)


class ActionIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=3, max_length=128)
    targets: ActionTargets = Field(default_factory=ActionTargets)
    parameters: dict[str, Any] = Field(default_factory=dict)
    constraints: ActionConstraints = Field(default_factory=ActionConstraints)
    justification: str = Field(min_length=10, max_length=2000)


def target_resource_ids(intent: ActionIntentRequest) -> list[str]:
    return intent.targets.all_ids()


def _field(pointer: str, code: str, detail: str) -> FieldError:
    return FieldError(pointer=pointer, code=code, detail=detail)


def validate_intent(intent: ActionIntentRequest, definition: ActionDefinition) -> None:
    """Validate the intent against the definition's parameter contract."""
    errors: list[FieldError] = []

    if not target_resource_ids(intent):
        errors.append(
            _field("/targets", "target-required", "At least one target resource is required.")
        )

    params = intent.parameters
    action_type = definition.action_type

    if action_type == "iam.grant_s3_access":
        if not intent.targets.source:
            errors.append(
                _field("/targets/source", "source-required", "A role or compute role is required.")
            )
        if not intent.targets.target:
            errors.append(
                _field("/targets/target", "target-required", "An S3 bucket ARN is required.")
            )
        actions = params.get("actions", [])
        if not isinstance(actions, list) or not actions:
            errors.append(
                _field(
                    "/parameters/actions",
                    "actions-required",
                    "At least one S3 action (e.g. s3:GetObject) is required.",
                )
            )
        elif not all(isinstance(item, str) for item in actions):
            errors.append(
                _field("/parameters/actions", "actions-invalid", "Actions must be strings.")
            )
        prefix = params.get("prefix")
        if prefix is not None and not isinstance(prefix, str):
            errors.append(
                _field("/parameters/prefix", "prefix-invalid", "Prefix must be a string.")
            )

    elif action_type == "network.allow_security_group_ingress":
        if not intent.targets.source:
            errors.append(
                _field("/targets/source", "source-required", "A source SG or CIDR is required.")
            )
        if not intent.targets.target:
            errors.append(
                _field("/targets/target", "target-required", "A target security group is required.")
            )
        port = params.get("port", params.get("from_port"))
        if not isinstance(port, int) or not 1 <= port <= 65535:
            errors.append(
                _field(
                    "/parameters/port",
                    "port-invalid",
                    "Port must be an integer between 1 and 65535.",
                )
            )
        protocol = params.get("protocol", "tcp")
        if protocol not in ("tcp", "udp", "icmp"):
            errors.append(
                _field(
                    "/parameters/protocol",
                    "protocol-invalid",
                    "Protocol must be tcp, udp, or icmp.",
                )
            )

    elif action_type == "network.restrict_security_group_ingress":
        if not intent.targets.target and not intent.targets.resources:
            errors.append(
                _field(
                    "/targets",
                    "target-required",
                    "A security group ARN is required.",
                )
            )
        cidr = params.get("cidr", "0.0.0.0/0")
        if not isinstance(cidr, str) or not cidr:
            errors.append(
                _field("/parameters/cidr", "cidr-invalid", "CIDR must be a non-empty string.")
            )
        port = params.get("port")
        if port is not None and (not isinstance(port, int) or not 1 <= port <= 65535):
            errors.append(
                _field(
                    "/parameters/port",
                    "port-invalid",
                    "Port must be an integer between 1 and 65535.",
                )
            )
        protocol = params.get("protocol", "tcp")
        if protocol not in ("tcp", "udp", "icmp", "all"):
            errors.append(
                _field(
                    "/parameters/protocol",
                    "protocol-invalid",
                    "Protocol must be tcp, udp, icmp, or all.",
                )
            )

    elif action_type == "s3.harden_bucket":
        if not intent.targets.target and not intent.targets.resources:
            errors.append(_field("/targets", "target-required", "A bucket ARN is required."))

    elif action_type == "iam.attach_least_privilege_policy":
        if not intent.targets.source:
            errors.append(_field("/targets/source", "source-required", "A role ARN is required."))
        actions = params.get("actions", [])
        if not isinstance(actions, list) or not actions:
            errors.append(
                _field(
                    "/parameters/actions",
                    "actions-required",
                    "At least one allowed action is required.",
                )
            )

    elif action_type == "tagging.apply":
        tags = params.get("tags", {})
        if not isinstance(tags, dict) or not tags:
            errors.append(
                _field("/parameters/tags", "tags-required", "At least one tag is required.")
            )
        elif not all(isinstance(k, str) and isinstance(v, str) for k, v in tags.items()):
            errors.append(
                _field("/parameters/tags", "tags-invalid", "Tag keys and values must be strings.")
            )
        if not intent.targets.resources:
            errors.append(
                _field(
                    "/targets/resources",
                    "resources-required",
                    "Tagging requires an explicit resource list.",
                )
            )

    elif action_type == "ec2.stop_start_instance":
        if not intent.targets.source:
            errors.append(
                _field("/targets/source", "source-required", "An EC2 instance is required.")
            )

    elif action_type == "observability.create_alarm":
        metric = params.get("metric_name")
        if not isinstance(metric, str) or not metric:
            errors.append(
                _field(
                    "/parameters/metric_name",
                    "metric-required",
                    "A CloudWatch metric name is required.",
                )
            )
        threshold = params.get("threshold")
        if not isinstance(threshold, (int, float)):
            errors.append(
                _field(
                    "/parameters/threshold",
                    "threshold-invalid",
                    "Threshold must be numeric.",
                )
            )

    elif action_type == "optimization.resize_instance":
        if not intent.targets.source:
            errors.append(
                _field("/targets/source", "source-required", "An EC2 instance is required.")
            )
        instance_type = params.get("instance_type")
        if not isinstance(instance_type, str) or not instance_type:
            errors.append(
                _field(
                    "/parameters/instance_type",
                    "instance-type-required",
                    "A target instance type is required.",
                )
            )

    if errors:
        raise UnprocessableEntity(f"Intent for {action_type} failed validation.", errors=errors)
