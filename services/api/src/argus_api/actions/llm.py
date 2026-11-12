"""LLM gateway contract with a safe deterministic fallback.

The default implementation performs no model call: it maps a narrow set of
well-understood phrases into typed intents. Model output is never trusted for
planning, so an unavailable or compromised provider degrades to this path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "ignore the above",
    "ignore your instructions",
    "ignore guardrails",
    "bypass guardrails",
    "system prompt",
    "disregard your",
    "you are now",
    "jailbreak",
)

_ARN = r"arn:aws:[a-zA-Z0-9\-]+:[a-z0-9\-]*:[0-9]{12}:[^\s,;]+|arn:aws:s3:::[\w.\-/]+"
_INSTANCE = r"i-[0-9a-f]{8,17}"


@dataclass(frozen=True)
class ParsedIntent:
    action_type: str | None
    confidence: float
    targets: dict[str, Any]
    parameters: dict[str, Any]
    constraints: dict[str, Any]
    rationale: str
    rejected: bool = False
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "confidence": self.confidence,
            "targets": self.targets,
            "parameters": self.parameters,
            "constraints": self.constraints,
            "rationale": self.rationale,
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
        }


def _rejected(reason: str) -> ParsedIntent:
    return ParsedIntent(
        action_type=None,
        confidence=0.0,
        targets={},
        parameters={},
        constraints={},
        rationale="Untrusted instruction pattern detected; request ignored.",
        rejected=True,
        rejection_reason=reason,
    )


def parse_natural_language(text: str) -> ParsedIntent:
    lowered = text.lower()
    for marker in _INJECTION_MARKERS:
        if marker in lowered:
            return _rejected(f"prompt-injection marker: {marker}")

    # Stop/start an EC2 instance.
    instance = re.search(_INSTANCE, text)
    if instance and "stop" in lowered and ("instance" in lowered or "ec2" in lowered):
        return ParsedIntent(
            action_type="ec2.stop_start_instance",
            confidence=0.9,
            targets={"source": instance.group(0)},
            parameters={},
            constraints={"environment": "staging"},
            rationale="Detected a stop/start request for an EC2 instance.",
        )

    # Tag one or more resources.
    if "tag" in lowered:
        resources = re.findall(_ARN, text)
        tags = dict(re.findall(r"([A-Za-z][\w:.\-]{0,63})=([^\s,;]+)", text))
        if resources and tags:
            return ParsedIntent(
                action_type="tagging.apply",
                confidence=0.75,
                targets={"resources": sorted(set(resources))},
                parameters={"tags": tags},
                constraints={"environment": "staging"},
                rationale="Detected tag key/value pairs and target resources.",
            )

    # Harden an S3 bucket.
    bucket = re.search(r"arn:aws:s3:::[\w.\-]+", text)
    if bucket and ("harden" in lowered or "encrypt" in lowered or "block public" in lowered):
        return ParsedIntent(
            action_type="s3.harden_bucket",
            confidence=0.8,
            targets={"target": bucket.group(0)},
            parameters={},
            constraints={"environment": "staging"},
            rationale="Detected a bucket hardening request.",
        )

    # Allow ingress from a CIDR.
    port_match = re.search(r"port\s+(\d{1,5})", lowered)
    cidr_match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})", text)
    security_group = re.search(r"sg-[0-9a-f]+", text)
    if port_match and cidr_match and security_group:
        return ParsedIntent(
            action_type="network.allow_security_group_ingress",
            confidence=0.7,
            targets={"source": cidr_match.group(1), "target": security_group.group(0)},
            parameters={"port": int(port_match.group(1)), "protocol": "tcp"},
            constraints={"environment": "staging"},
            rationale="Detected ingress, port, and source CIDR.",
        )

    # Resize an instance.
    resize_type = re.search(r"to\s+(t3|m5|m6i|c5|c6g|r5|r6g)\.[a-z0-9]+", lowered)
    if instance and ("resize" in lowered or "instance type" in lowered) and resize_type:
        return ParsedIntent(
            action_type="optimization.resize_instance",
            confidence=0.7,
            targets={"source": instance.group(0)},
            parameters={"instance_type": resize_type.group(0).removeprefix("to ").strip()},
            constraints={"environment": "staging", "maintenance_window": True},
            rationale="Detected an instance resize request with a target type.",
        )

    # Grant S3 access from a role ARN.
    role = re.search(r"arn:aws:iam::[0-9]{12}:role/[\w+=,.@\-/]+", text)
    if role and bucket and ("grant" in lowered or "access" in lowered):
        actions = [
            action
            for action in ("s3:GetObject", "s3:PutObject", "s3:ListBucket")
            if action.lower().split(":", 1)[1].split("object")[0] in lowered
            or action == "s3:GetObject"
        ]
        return ParsedIntent(
            action_type="iam.grant_s3_access",
            confidence=0.7,
            targets={"source": role.group(0), "target": bucket.group(0)},
            parameters={"actions": actions or ["s3:GetObject"]},
            constraints={"environment": "staging"},
            rationale="Detected a role-to-bucket access grant.",
        )

    return ParsedIntent(
        action_type=None,
        confidence=0.0,
        targets={},
        parameters={},
        constraints={},
        rationale="No supported action matched; use the deterministic action flow.",
    )


def explain_plan(summary: str, risk: dict[str, Any]) -> str:
    reasons = ", ".join(risk.get("reasons", []))
    return (
        f"{summary} Risk is {risk.get('level', 'unknown')} with a blast radius of "
        f"{risk.get('blast_radius', '?')}. Drivers: {reasons}."
    )
