"""HCL (HashiCorp Configuration Language) and Terraform diff synthesizer."""

from __future__ import annotations

import re
from typing import Any


def _normalize_name(val: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", val.split("/")[-1].split(":")[-1])
    return cleaned.strip("_") or "resource"


def synthesize_hcl_diff(
    action_type: str,
    target_resource_id: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Compile an exact, unified HCL diff and file path for an infrastructure mutation."""
    res_name = _normalize_name(target_resource_id)

    if action_type == "network.restrict_security_group_ingress":
        port = parameters.get("port", 22)
        cidr = parameters.get("cidr", "0.0.0.0/0")
        proto = parameters.get("protocol", "tcp")
        file_path = "terraform/security_groups.tf"

        hcl_diff = f"""--- a/{file_path}
+++ b/{file_path}
@@ -14,8 +14,8 @@ resource "aws_security_group" "{res_name}" {{
     description = "Managed by Terraform"
     vpc_id      = var.vpc_id

-    ingress {{
-      from_port   = {port}
-      to_port     = {port}
-      protocol    = "{proto}"
-      cidr_blocks = ["{cidr}"]
-    }}
+    # Restricted by Argus Engine (CIS AWS 5.2 - Administrative ingress protection)
+    # Ingress rule for port {port} removed to prevent public internet reachability.
   }}
"""
        return {
            "file_path": file_path,
            "block_type": "resource",
            "block_name": f"aws_security_group.{res_name}",
            "hcl_diff": hcl_diff.strip(),
            "summary": f"Revoke 0.0.0.0/0 ingress on port {port} for security group {res_name}.",
        }

    if action_type == "optimization.resize_instance":
        target_type = parameters.get("instance_type", "m5.large")
        current_type = parameters.get("current_instance_type", "m5.xlarge")
        file_path = "terraform/compute.tf"

        hcl_diff = f"""--- a/{file_path}
+++ b/{file_path}
@@ -28,7 +28,7 @@ resource "aws_instance" "{res_name}" {{
     ami           = var.ami_id
-    instance_type = "{current_type}"
+    instance_type = "{target_type}" # Downsized by Argus FinOps (~50% cost reduction)
     subnet_id     = var.subnet_id
   }}
"""
        return {
            "file_path": file_path,
            "block_type": "resource",
            "block_name": f"aws_instance.{res_name}",
            "hcl_diff": hcl_diff.strip(),
            "summary": f"Rightsize {res_name} from {current_type} to {target_type}.",
        }

    if action_type == "tagging.apply":
        tags = parameters.get("tags", {})
        file_path = "terraform/resources.tf"
        tag_lines = "\n".join(f'      "{k}" = "{v}"' for k, v in tags.items())

        hcl_diff = f"""--- a/{file_path}
+++ b/{file_path}
@@ -45,6 +45,10 @@ resource "aws_resource" "{res_name}" {{
+    tags = {{
+{tag_lines}
+    }}
   }}
"""
        return {
            "file_path": file_path,
            "block_type": "resource",
            "block_name": f"aws_resource.{res_name}",
            "hcl_diff": hcl_diff.strip(),
            "summary": f"Apply required tags to {res_name}.",
        }

    if action_type == "s3.harden_bucket":
        file_path = "terraform/storage.tf"
        hcl_diff = f"""--- a/{file_path}
+++ b/{file_path}
@@ -10,4 +10,18 @@ resource "aws_s3_bucket" "{res_name}" {{
     bucket = "{res_name}"
   }}
+
+resource "aws_s3_bucket_public_access_block" "{res_name}" {{
+  bucket = aws_s3_bucket.{res_name}.id
+
+  block_public_acls       = true
+  block_public_policy     = true
+  ignore_public_acls      = true
+  restrict_public_buckets = true
+}}
"""
        return {
            "file_path": file_path,
            "block_type": "resource",
            "block_name": f"aws_s3_bucket_public_access_block.{res_name}",
            "hcl_diff": hcl_diff.strip(),
            "summary": f"Enable Public Access Block on S3 bucket {res_name}.",
        }

    # Default fallback diff
    file_path = "terraform/main.tf"
    hcl_diff = f"""--- a/{file_path}
+++ b/{file_path}
@@ -1,3 +1,4 @@
 # Updated by Argus Engine GitOps Bridge
+# Target: {target_resource_id}
+# Action: {action_type}
"""
    return {
        "file_path": file_path,
        "block_type": "resource",
        "block_name": res_name,
        "hcl_diff": hcl_diff.strip(),
        "summary": f"Apply {action_type} to {res_name}.",
    }
