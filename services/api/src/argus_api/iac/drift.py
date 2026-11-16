"""IaC drift detection between live graph topology and Terraform definitions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def detect_iac_drift(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Scan topology graph for ClickOps drift (manual untracked rules or tags)."""
    now = datetime.now(tz=UTC)
    drifted: list[dict[str, Any]] = []

    for node in nodes:
        node_id = str(node.get("id", ""))
        node_type = str(node.get("type", ""))
        props = dict(node.get("properties") or {})
        tags = dict(node.get("tags") or {})

        # 1. Security Group ClickOps drift (open ingress rule not in baseline)
        if node_type == "AWS::EC2::SecurityGroup":
            rules = props.get("ingress_rules", [])
            has_public_ssh = any(
                r.get("from_port") == 22 and r.get("cidr") in ("0.0.0.0/0", "::/0")
                for r in rules
                if isinstance(r, dict)
            )
            if has_public_ssh:
                drifted.append(
                    {
                        "resource_id": node_id,
                        "resource_type": node_type,
                        "iac_file_path": "terraform/security_groups.tf",
                        "iac_block_type": "aws_security_group",
                        "iac_block_name": node.get("name", "security_group"),
                        "drift_details": {
                            "drift_type": "UNTRACKED_CLICKOPS_INGRESS",
                            "severity": "critical",
                            "message": (
                                "Public SSH ingress rule (port 22, 0.0.0.0/0) added outside "
                                "Terraform."
                            ),
                            "live_value": {"port": 22, "cidr": "0.0.0.0/0"},
                            "expected_iac_value": None,
                        },
                        "detected_at": now.isoformat(),
                    }
                )

        # 2. Compute sizing ClickOps drift
        if node_type == "AWS::EC2::Instance":
            inst_type = str(props.get("instance_type", "m5.xlarge"))
            expected_type = str(props.get("expected_iac_instance_type", ""))
            if expected_type and inst_type != expected_type:
                drifted.append(
                    {
                        "resource_id": node_id,
                        "resource_type": node_type,
                        "iac_file_path": "terraform/compute.tf",
                        "iac_block_type": "aws_instance",
                        "iac_block_name": node.get("name", "instance"),
                        "drift_details": {
                            "drift_type": "MODIFIED_INSTANCE_TYPE",
                            "severity": "medium",
                            "message": (
                                f"Instance modified to {inst_type} in console; Terraform defines "
                                f"{expected_type}."
                            ),
                            "live_value": inst_type,
                            "expected_iac_value": expected_type,
                        },
                        "detected_at": now.isoformat(),
                    }
                )

        # 3. Missing mandatory tags
        if (
            node_type.startswith("AWS::")
            and not node_type.startswith("AWS::Internet")
            and "Environment" not in tags
            and "ManagedBy" not in tags
        ):
            drifted.append(
                {
                    "resource_id": node_id,
                    "resource_type": node_type,
                    "iac_file_path": "terraform/main.tf",
                    "iac_block_type": "aws_resource",
                    "iac_block_name": node.get("name", "resource"),
                    "drift_details": {
                        "drift_type": "MISSING_TAGS",
                        "severity": "low",
                        "message": (
                            "Resource is missing mandatory 'Environment' and 'ManagedBy' tags "
                            "defined in Terraform."
                        ),
                        "live_value": tags,
                        "expected_iac_value": {
                            "Environment": "production",
                            "ManagedBy": "terraform",
                        },
                    },
                    "detected_at": now.isoformat(),
                }
            )

    return drifted
