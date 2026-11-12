"""Bounded attack-path traversal and ranking over a tenant subgraph.

No client-supplied Cypher: the traversal is expressed in Python over the bounded
subgraph returned by :meth:`GraphRepository.load_security_subgraph`.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from argus_api.security.rules import SENSITIVE_TYPES, SecurityGraph, iter_ingress_rules

MAX_PATHS_EXPANSIONS = 20_000
INTERNET_NODE_TYPE = "AWS::Internet::Endpoint"


@dataclass
class AttackPath:
    hops: list[dict[str, Any]]
    severity: str
    score: int
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class AttackPathResult:
    paths: list[dict[str, Any]]
    generated_at: str
    source: str
    truncated: bool
    evaluated_nodes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "paths": self.paths,
            "count": len(self.paths),
            "truncated": self.truncated,
            "evaluated_nodes": self.evaluated_nodes,
            "generated_at": self.generated_at,
        }


def _is_public_node(node: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    node_type = str(node.get("type", ""))
    props = SecurityGraph.properties_for(node)
    if node_type == "AWS::EC2::SecurityGroup":
        for ingress in iter_ingress_rules(node):
            if ingress["cidr"].strip() in {"0.0.0.0/0", "::/0"}:
                return (
                    True,
                    "EXPOSES",
                    {
                        "cidr": ingress["cidr"],
                        "from_port": ingress["from_port"],
                        "to_port": ingress["to_port"],
                    },
                )
    if (
        node_type == "AWS::ElasticLoadBalancingV2::LoadBalancer"
        and str(props.get("scheme", "")).lower() == "internet-facing"
    ):
        return True, "EXPOSES", {"scheme": "internet-facing", "listener": "443"}
    if node_type == "AWS::S3::Bucket" and (
        props.get("policy_public") is True or props.get("acl_public") is True
    ):
        return True, "PUBLIC_POLICY", {"bucket_public": True}
    if node_type == "AWS::RDS::DBInstance" and props.get("publicly_accessible") is True:
        return True, "PUBLIC_ENDPOINT", {"publicly_accessible": True}
    if node_type == "AWS::Lambda::Function":
        auth = str(props.get("function_url_auth_type", "AWS_IAM")).upper()
        if auth == "NONE" or props.get("function_url_public") is True:
            return True, "PUBLIC_URL", {"auth_type": "NONE"}
    return False, "", {}


def _successors(
    graph: SecurityGraph, node: dict[str, Any]
) -> list[tuple[dict[str, Any], str, str]]:
    node_type = str(node.get("type", ""))
    node_id = str(node.get("id", ""))
    results: list[tuple[dict[str, Any], str, str]] = []

    if node_type == INTERNET_NODE_TYPE:
        for edge in graph.outgoing.get(node_id, []):
            if edge.get("type") not in {"EXPOSES", "PUBLIC_POLICY", "PUBLIC_ENDPOINT"}:
                continue
            target = graph.node_by_id.get(str(edge.get("target")))
            if target is not None:
                results.append((target, "EXPOSES", "Internet reaches an exposed resource"))
        return results

    if node_type == "AWS::EC2::SecurityGroup":
        # Reverse the Instance MEMBER_OF SG edge.
        for related, _edge_type in graph.related(node_id, edge_types={"MEMBER_OF"}, direction="in"):
            results.append((related, "MEMBER_OF", "Resource is attached to the exposed SG"))
        return results

    edge_allowlist: dict[str, set[str]] = {
        "AWS::ElasticLoadBalancingV2::LoadBalancer": {"ROUTES_TO", "TARGETS", "FORWARDS_TO"},
        "AWS::ElasticLoadBalancingV2::TargetGroup": {"TARGETS", "ROUTES_TO"},
        "AWS::EC2::Instance": {"ASSUMES", "CAN_ACCESS", "ATTACHED_TO"},
        "AWS::Lambda::Function": {"ASSUMES", "CAN_ACCESS"},
        "AWS::ECS::Task": {"ASSUMES", "CAN_ACCESS"},
        "AWS::IAM::Role": {"CAN_ACCESS"},
        "AWS::IAM::InstanceProfile": {"ASSUMES", "CAN_ACCESS"},
    }
    allowed = edge_allowlist.get(node_type)
    if not allowed:
        return results
    for edge in graph.outgoing.get(node_id, []):
        if edge.get("type") not in allowed:
            continue
        target = graph.node_by_id.get(str(edge.get("target")))
        if target is None:
            continue
        results.append((target, str(edge.get("type")), _edge_rationale(str(edge.get("type")))))
    return results


def _edge_rationale(edge_type: str) -> str:
    return {
        "ROUTES_TO": "Traffic is routed to the next hop",
        "TARGETS": "The load balancer forwards to this target",
        "ASSUMES": "The workload can assume this IAM role",
        "CAN_ACCESS": "The role's policy grants access to this data store",
        "ATTACHED_TO": "The resource is attached to the workload",
        "MEMBER_OF": "Resource is a member of the exposed security group",
    }.get(edge_type, "Path continues")


def _rank(hops: list[dict[str, Any]], direct: bool, evidence: dict[str, Any]) -> tuple[int, str]:
    types = {str(hop.get("type", "")) for hop in hops}
    score = 50
    if "AWS::S3::Bucket" in types or "AWS::RDS::DBInstance" in types:
        score += 15
    if "AWS::SecretsManager::Secret" in types:
        score += 20
    if "AWS::IAM::Role" in types:
        score += 15
    if direct:
        score += 15
    if evidence.get("public_admin_port"):
        score += 10
    score -= max(0, len(hops) - 2) * 4
    score = max(0, min(100, score))
    if score >= 85:
        severity = "critical"
    elif score >= 65:
        severity = "high"
    elif score >= 45:
        severity = "medium"
    else:
        severity = "low"
    return score, severity


def compute_attack_paths(
    graph: SecurityGraph,
    *,
    target_types: list[str] | None = None,
    max_depth: int = 8,
    limit: int = 25,
    accounts: list[str] | None = None,
    regions: list[str] | None = None,
) -> AttackPathResult:
    targets = set(target_types or SENSITIVE_TYPES)
    depth_limit = max(1, min(max_depth, 8))
    path_limit = max(1, min(limit, 100))
    account_filter = set(accounts or [])
    region_filter = set(regions or [])

    def in_scope(node: dict[str, Any]) -> bool:
        account_ok = not account_filter or str(node.get("account_id")) in account_filter
        region_ok = not region_filter or str(node.get("region")) in region_filter
        return account_ok and region_ok

    entries: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    for node in graph.nodes:
        if not in_scope(node):
            continue
        public, edge_type, evidence = _is_public_node(node)
        if public:
            entries.append((node, edge_type, evidence))

    # Explicit EXPOSES edges created by materialisation (e.g. SG -> Internet).
    for node in graph.nodes:
        if node.get("type") != INTERNET_NODE_TYPE:
            continue
        for edge in graph.outgoing.get(str(node.get("id")), []):
            if edge.get("type") != "EXPOSES":
                continue
            target = graph.node_by_id.get(str(edge.get("target")))
            if target is not None and in_scope(target):
                entries.append((target, "EXPOSES", dict(edge.get("properties") or {})))

    paths: list[AttackPath] = []
    expansions = 0
    truncated = False
    seen_paths: set[tuple[str, ...]] = set()

    for entry, entry_edge, entry_evidence in entries:
        if expansions >= MAX_PATHS_EXPANSIONS or len(paths) >= path_limit:
            truncated = True
            break
        start_hop = {
            "node_id": str(entry.get("id")),
            "name": str(entry.get("name") or entry.get("id")),
            "type": str(entry.get("type")),
            "edge_type": entry_edge,
            "why": "Internet-exposed entry point",
            "evidence": entry_evidence,
        }
        queue: deque[tuple[dict[str, Any], list[dict[str, Any]], frozenset[str]]] = deque(
            [(entry, [start_hop], frozenset({str(entry.get("id"))}))]
        )
        while queue and len(paths) < path_limit:
            node, hops, visited = queue.popleft()
            expansions += 1
            if expansions >= MAX_PATHS_EXPANSIONS:
                truncated = True
                break
            node_type = str(node.get("type", ""))
            if node_type in targets and len(hops) >= 2:
                signature = tuple(str(hop["node_id"]) for hop in hops)
                if signature not in seen_paths:
                    seen_paths.add(signature)
                    direct = len(hops) == 2
                    score, severity = _rank(hops, direct, entry_evidence)
                    paths.append(
                        AttackPath(
                            hops=hops,
                            severity=severity,
                            score=score,
                            evidence={
                                "entry": entry_evidence,
                                "target_type": node_type,
                                "hop_count": len(hops),
                            },
                        )
                    )
            if len(hops) >= depth_limit:
                continue
            for successor, edge_type, why in _successors(graph, node):
                successor_id = str(successor.get("id"))
                if successor_id in visited or not in_scope(successor):
                    continue
                next_hop = {
                    "node_id": successor_id,
                    "name": str(successor.get("name") or successor_id),
                    "type": str(successor.get("type")),
                    "edge_type": edge_type,
                    "why": why,
                    "evidence": {},
                }
                queue.append((successor, [*hops, next_hop], visited | {successor_id}))

    paths.sort(key=lambda item: (-item.score, len(item.hops)))
    return AttackPathResult(
        paths=[
            {
                "hops": item.hops,
                "severity": item.severity,
                "score": item.score,
                "evidence": item.evidence,
            }
            for item in paths[:path_limit]
        ],
        generated_at=datetime.now(tz=UTC).isoformat(),
        source="internet",
        truncated=truncated,
        evaluated_nodes=len(graph.nodes),
    )


__all__ = ["AttackPath", "AttackPathResult", "compute_attack_paths"]
