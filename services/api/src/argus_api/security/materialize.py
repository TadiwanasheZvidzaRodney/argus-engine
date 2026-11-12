"""Materialise security graph edges (`EXPOSES`, `CAN_ACCESS`).

The materialised edges make attack-path traversal cheap and deterministic. They
are derived state: recomputed whenever the tenant graph changes and safe to drop
and rebuild.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from argus_api.security.rules import (
    SENSITIVE_TYPES,
    SecurityGraph,
    _is_public_cidr,
    _policy_statements,
    _string_list,
    iter_ingress_rules,
)

if TYPE_CHECKING:
    from argus_core.graph.repository import GraphRepository

INTERNET_NODE_TYPE = "AWS::Internet::Endpoint"

DATA_ACTIONS: dict[str, set[str]] = {
    "AWS::S3::Bucket": {"s3:getobject", "s3:listbucket", "s3:*", "*"},
    "AWS::RDS::DBInstance": {"rds:connect", "rds:*", "*"},
    "AWS::SecretsManager::Secret": {"secretsmanager:getsecretvalue", "secretsmanager:*", "*"},
    "AWS::DynamoDB::Table": {
        "dynamodb:getitem",
        "dynamodb:query",
        "dynamodb:scan",
        "dynamodb:*",
        "*",
    },
    "AWS::EFS::FileSystem": {"elasticfilesystem:*", "*"},
}


def internet_node(tenant_id: str) -> dict[str, Any]:
    now = datetime.now(tz=UTC).isoformat()
    return {
        "id": f"internet:{tenant_id}",
        "arn": f"arn:argus:internet:{tenant_id}:endpoint",
        "type": INTERNET_NODE_TYPE,
        "name": "Internet",
        "account_id": "000000000000",
        "region": "us-east-1",
        "state": "active",
        "tags": json.dumps({"Sentinel": "true"}),
        "source": "argus-security",
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "raw_ref": None,
        "properties": json.dumps({"sentinel": True}),
    }


def _role_actions(node: dict[str, Any]) -> set[str]:
    actions: set[str] = set()
    for statement in _policy_statements(node):
        effect = str(statement.get("Effect", statement.get("effect", "Allow"))).lower()
        if effect != "allow":
            continue
        actions.update(action.lower() for action in _string_list(statement.get("Action")))
    return actions


async def materialize_security_graph(
    repo: GraphRepository,
    tenant_id: str,
    graph: SecurityGraph,
) -> dict[str, int]:
    """Rebuild EXPOSES/CAN_ACCESS edges and the Internet sentinel."""
    sentinel = internet_node(tenant_id)
    await repo.upsert_raw_nodes(tenant_id, [sentinel])

    exposes: list[dict[str, Any]] = []
    for node in graph.nodes:
        node_type = str(node.get("type", ""))
        properties = SecurityGraph.properties_for(node)
        evidence: dict[str, Any] = {"resource_type": node_type}
        exposed = False

        if node_type == "AWS::EC2::SecurityGroup":
            for ingress in iter_ingress_rules(node):
                if not _is_public_cidr(ingress["cidr"]):
                    continue
                exposed = True
                evidence = {
                    "resource_type": node_type,
                    "cidr": ingress["cidr"],
                    "protocol": ingress["protocol"],
                    "from_port": ingress["from_port"],
                    "to_port": ingress["to_port"],
                }
                exposes.append(
                    {
                        "source_id": str(node["id"]),
                        "target_id": sentinel["id"],
                        "type": "EXPOSES",
                        "properties": evidence,
                    }
                )
        elif node_type == "AWS::ElasticLoadBalancingV2::LoadBalancer":
            if str(properties.get("scheme", "")).lower() == "internet-facing":
                exposed = True
                evidence = {"resource_type": node_type, "scheme": "internet-facing"}
                exposes.append(
                    {
                        "source_id": str(node["id"]),
                        "target_id": sentinel["id"],
                        "type": "EXPOSES",
                        "properties": evidence,
                    }
                )
        elif node_type == "AWS::S3::Bucket" and (
            properties.get("policy_public") is True or properties.get("acl_public") is True
        ):
            exposed = True
            exposes.append(
                {
                    "source_id": str(node["id"]),
                    "target_id": sentinel["id"],
                    "type": "EXPOSES",
                    "properties": {"resource_type": node_type, "public": True},
                }
            )
        if exposed:
            # Mark derived exposure on the node for the UI overlay.
            await repo.set_security_metadata(tenant_id, str(node["id"]), exposed=True)

    access: list[dict[str, Any]] = []
    sensitive_by_account: dict[str, list[dict[str, Any]]] = {}
    for node in graph.nodes:
        if str(node.get("type", "")) in SENSITIVE_TYPES:
            account = str(node.get("account_id", ""))
            sensitive_by_account.setdefault(account, []).append(node)

    for role in graph.nodes_of_type("AWS::IAM::Role"):
        actions = _role_actions(role)
        account = str(role.get("account_id", ""))
        for target in sensitive_by_account.get(account, []):
            target_type = str(target.get("type", ""))
            allowed = actions & DATA_ACTIONS.get(target_type, set())
            if not allowed:
                continue
            access.append(
                {
                    "source_id": str(role["id"]),
                    "target_id": str(target["id"]),
                    "type": "CAN_ACCESS",
                    "properties": {
                        "actions": sorted(allowed),
                        "confidence": "high",
                        "evidence": "role-policy",
                    },
                }
            )

    await repo.replace_security_edges(tenant_id, [*exposes, *access])
    return {"exposes": len(exposes), "can_access": len(access)}


__all__ = ["DATA_ACTIONS", "INTERNET_NODE_TYPE", "internet_node", "materialize_security_graph"]
