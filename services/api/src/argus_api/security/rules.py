"""Code-defined, versioned security rules evaluated over a bounded subgraph.

Rules are intentionally *not* customer-authored in Phase 7. Every evaluator is
deterministic and operates only on the tenant-scoped subgraph that the API
loaded from Neo4j; no client-supplied Cypher is ever executed.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

ADMIN_PORTS = frozenset({22, 3389, 3306, 5432, 6379, 9200, 27017})
PUBLIC_CIDRS = frozenset({"0.0.0.0/0", "::/0", "0.0.0.0/0 "})
SENSITIVE_TYPES = frozenset(
    {
        "AWS::S3::Bucket",
        "AWS::RDS::DBInstance",
        "AWS::SecretsManager::Secret",
        "AWS::DynamoDB::Table",
        "AWS::EFS::FileSystem",
    }
)
ESCALATION_ACTIONS = frozenset(
    {
        "iam:createpolicyversion",
        "iam:attachuserpolicy",
        "iam:attachrolepolicy",
        "iam:putuserpolicy",
        "iam:putrolepolicy",
        "iam:updateassumerolepolicy",
        "sts:assumerole",
        "lambda:createfunction",
        "lambda:updatefunctioncode",
        "ec2:runinstances",
        "ecs:runtask",
    }
)


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    rule_version: str
    severity: str
    title: str
    description: str
    resource_id: str
    resource_type: str
    account_id: str | None
    region: str | None
    finding_key: str
    evidence: dict[str, Any]
    remediation_action: str | None = None

    @property
    def evidence_hash(self) -> str:
        payload = json.dumps(self.evidence, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Rule:
    id: str
    version: str
    severity: str
    title: str
    description: str
    resource_types: tuple[str, ...]
    evaluator: Callable[[Rule, SecurityGraph], list[RuleHit]]
    remediation_action: str | None = None
    references: tuple[str, ...] = ()
    changelog: str = ""

    @property
    def definition_hash(self) -> str:
        payload = json.dumps(
            {
                "id": self.id,
                "version": self.version,
                "severity": self.severity,
                "title": self.title,
                "resource_types": list(self.resource_types),
                "remediation_action": self.remediation_action,
                "references": list(self.references),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _props(node: dict[str, Any]) -> dict[str, Any]:
    raw = node.get("properties")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _tags(node: dict[str, Any]) -> dict[str, str]:
    raw = node.get("tags")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "enabled", "on"}:
            return True
        if lowered in {"false", "no", "disabled", "off"}:
            return False
    return None


def _is_public_cidr(value: str) -> bool:
    return value.strip() in PUBLIC_CIDRS


def _full_port_range(from_port: int, to_port: int, protocol: str) -> bool:
    if protocol in {"-1", "all"}:
        return True
    return from_port <= 0 and to_port >= 65535


def iter_ingress_rules(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Normalise the several ingress shapes emitted by discovery adapters."""
    props = _props(node)
    structured = props.get("ingress_rules")
    if isinstance(structured, list):
        for item in structured:
            if not isinstance(item, dict):
                continue
            yield {
                "protocol": str(item.get("protocol", "tcp")).lower(),
                "from_port": _to_int(item.get("from_port", item.get("port", -1))),
                "to_port": _to_int(
                    item.get("to_port", item.get("port", item.get("from_port", -1)))
                ),
                "cidr": str(
                    item.get("cidr")
                    or item.get("cidr_ipv4")
                    or item.get("cidr_ipv6")
                    or item.get("source", "")
                ),
                "description": str(item.get("description", "")),
            }
        return

    cidrs = props.get("inbound_cidrs")
    if not isinstance(cidrs, list) or not cidrs:
        public = _as_bool(props.get("public_ingress")) or _as_bool(props.get("public"))
        cidrs = ["0.0.0.0/0"] if public else []
    ports = props.get("inbound_ports")
    if _as_bool(props.get("inbound_all_ports")):
        ports = [0]
        all_ports = True
    else:
        all_ports = False
    if not isinstance(ports, list):
        return
    for port in ports:
        if not isinstance(port, int):
            continue
        for cidr in cidrs:
            if not isinstance(cidr, str):
                continue
            yield {
                "protocol": "all" if all_ports else "tcp",
                "from_port": 0 if all_ports else port,
                "to_port": 65535 if all_ports else port,
                "cidr": cidr,
                "description": "",
            }


def _hit(rule: Rule, node: dict[str, Any], key: str, evidence: dict[str, Any]) -> RuleHit:
    return RuleHit(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=rule.severity,
        title=rule.title,
        description=rule.description,
        resource_id=str(node.get("id", "")),
        resource_type=str(node.get("type", "")),
        account_id=str(node.get("account_id")) if node.get("account_id") else None,
        region=str(node.get("region")) if node.get("region") else None,
        finding_key=key,
        evidence=evidence,
        remediation_action=rule.remediation_action,
    )


def _policy_statements(node: dict[str, Any]) -> list[dict[str, Any]]:
    props = _props(node)
    documents = props.get("policy_documents")
    if not isinstance(documents, list):
        documents = [documents] if isinstance(documents, dict) else []
    statements: list[dict[str, Any]] = []
    for document in documents:
        if isinstance(document, str):
            try:
                document = json.loads(document)
            except (ValueError, TypeError):
                continue
        if not isinstance(document, dict):
            continue
        raw = document.get("Statement", document.get("statement", []))
        if isinstance(raw, dict):
            raw = [raw]
        if isinstance(raw, list):
            statements.extend(item for item in raw if isinstance(item, dict))
    return statements


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


# ---------------------------------------------------------------------------
# Rule evaluators
# ---------------------------------------------------------------------------


def _eval_sg_public(node: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Classify public ingress rules: (rule_id, finding_key, evidence)."""
    results: list[tuple[str, str, dict[str, Any]]] = []
    for ingress in iter_ingress_rules(node):
        cidr = ingress["cidr"]
        if not _is_public_cidr(cidr):
            continue
        from_port = ingress["from_port"]
        to_port = ingress["to_port"]
        evidence = {
            "security_group_id": node.get("id"),
            "cidr": cidr,
            "protocol": ingress["protocol"],
            "from_port": from_port,
            "to_port": to_port,
        }
        if _full_port_range(from_port, to_port, ingress["protocol"]):
            results.append(("sg-public-all-ports", f"all:{cidr}", evidence))
            continue
        exposed = sorted(port for port in ADMIN_PORTS if from_port <= port <= to_port)
        if exposed:
            for port in exposed:
                results.append(
                    (
                        "sg-public-admin-port",
                        f"{port}:{cidr}",
                        {**evidence, "port": port},
                    )
                )
        else:
            results.append(
                (
                    "sg-public-uncommon-port",
                    f"{from_port}-{to_port}:{cidr}",
                    evidence,
                )
            )
    return results


def _eval_sg_internet_ingress(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::EC2::SecurityGroup"):
        for rule_id, key, evidence in _eval_sg_public(node):
            if rule_id == rule.id:
                hits.append(_hit(rule, node, key, evidence))
    return hits


def _eval_s3_public(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::S3::Bucket"):
        props = _props(node)
        acl_public = _as_bool(props.get("acl_public")) is True or str(
            props.get("acl", "")
        ).lower() in {"public-read", "public-read-write"}
        policy_public = _as_bool(props.get("policy_public")) is True
        bpa_disabled = _as_bool(props.get("public_access_block")) is False
        if not (acl_public or policy_public or bpa_disabled):
            continue
        grants = []
        if acl_public:
            grants.append("acl")
        if policy_public:
            grants.append("bucket-policy")
        if bpa_disabled:
            grants.append("public-access-block-disabled")
        hits.append(
            _hit(
                rule,
                node,
                "public",
                {"bucket": node.get("arn") or node.get("id"), "grants": grants},
            )
        )
    return hits


def _eval_s3_encryption(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::S3::Bucket"):
        props = _props(node)
        algorithm = props.get("default_encryption") or props.get("sse_algorithm")
        if _as_bool(props.get("default_encryption")) is False or not algorithm:
            hits.append(
                _hit(rule, node, "encryption", {"bucket": node.get("arn") or node.get("id")})
            )
    return hits


def _eval_s3_tls(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::S3::Bucket"):
        props = _props(node)
        if _as_bool(props.get("tls_enforced")) is not True:
            hits.append(_hit(rule, node, "tls", {"bucket": node.get("arn") or node.get("id")}))
    return hits


def _eval_s3_versioning(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::S3::Bucket"):
        props = _props(node)
        tags = _tags(node)
        is_data_bucket = "DataClassification" in tags or "data" in str(node.get("name", "")).lower()
        if not is_data_bucket:
            continue
        if str(props.get("versioning", "Suspended")).lower() != "enabled":
            hits.append(
                _hit(
                    rule,
                    node,
                    "versioning",
                    {"bucket": node.get("arn") or node.get("id"), "versioning": "disabled"},
                )
            )
    return hits


def _eval_ebs_encryption(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::EC2::Volume"):
        if _as_bool(_props(node).get("encrypted")) is not True:
            hits.append(_hit(rule, node, "encrypted", {"encrypted": False}))
    return hits


def _eval_rds_encryption(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::RDS::DBInstance"):
        if _as_bool(_props(node).get("storage_encrypted")) is not True:
            hits.append(_hit(rule, node, "storage-encrypted", {"storage_encrypted": False}))
    return hits


def _eval_rds_public(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::RDS::DBInstance"):
        if _as_bool(_props(node).get("publicly_accessible")) is True:
            hits.append(_hit(rule, node, "public", {"publicly_accessible": True}))
    return hits


def _eval_iam_wildcard(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::IAM::Role"):
        for index, statement in enumerate(_policy_statements(node)):
            actions = _string_list(statement.get("Action", statement.get("action")))
            resources = _string_list(statement.get("Resource", statement.get("resource")))
            effect = str(statement.get("Effect", statement.get("effect", "Allow"))).lower()
            if effect != "allow":
                continue
            if "*" in actions and "*" in resources:
                hits.append(
                    _hit(
                        rule,
                        node,
                        f"statement-{index}",
                        {
                            "role": node.get("arn") or node.get("id"),
                            "statement_index": index,
                            "actions": actions,
                            "resources": resources,
                        },
                    )
                )
                break
    return hits


def _eval_iam_escalation(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::IAM::Role"):
        actions: set[str] = set()
        for statement in _policy_statements(node):
            effect = str(statement.get("Effect", statement.get("effect", "Allow"))).lower()
            if effect != "allow":
                continue
            actions.update(action.lower() for action in _string_list(statement.get("Action")))
        dangerous = sorted(actions & ESCALATION_ACTIONS)
        if dangerous:
            hits.append(
                _hit(
                    rule,
                    node,
                    "escalation",
                    {"role": node.get("arn") or node.get("id"), "actions": dangerous},
                )
            )
    return hits


def _role_trust(node: dict[str, Any]) -> tuple[list[str], str | None]:
    props = _props(node)
    principals = _string_list(props.get("trusted_principals"))
    trust = props.get("assume_role_policy")
    condition = props.get("trust_condition")
    if isinstance(trust, str):
        try:
            trust = json.loads(trust)
        except (ValueError, TypeError):
            trust = {"raw": trust}
    if isinstance(trust, dict):
        statements = trust.get("Statement", trust.get("statement", []))
        if isinstance(statements, dict):
            statements = [statements]
        if isinstance(statements, list):
            for statement in statements:
                if not isinstance(statement, dict):
                    continue
                principal = statement.get("Principal", statement.get("principal"))
                if isinstance(principal, str):
                    principals.append(principal)
                elif isinstance(principal, dict):
                    principals.extend(_string_list(principal.get("AWS")))
                    principals.extend(_string_list(principal.get("Service")))
                cond = statement.get("Condition")
                if isinstance(cond, dict):
                    condition = json.dumps(cond, sort_keys=True)
    elif isinstance(trust, str):
        principals.append(trust)
    return principals, condition


def _eval_iam_trust_wildcard(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::IAM::Role"):
        principals, _ = _role_trust(node)
        if any(principal.strip() == "*" for principal in principals):
            hits.append(_hit(rule, node, "trust-wildcard", {"principals": principals}))
    return hits


def _eval_iam_cross_account(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::IAM::Role"):
        trusted_accounts = _string_list(_props(node).get("trusted_accounts"))
        org_scoped = _as_bool(_props(node).get("organization_scoped")) is True
        if org_scoped:
            continue
        outside = sorted(
            account
            for account in trusted_accounts
            if account.isdigit() and account != str(node.get("account_id"))
        )
        if outside:
            hits.append(_hit(rule, node, "cross-account", {"trusted_accounts": outside}))
    return hits


def _eval_iam_old_access_key(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    cutoff = datetime.now(tz=UTC) - timedelta(days=90)
    for node in graph.nodes_of_type("AWS::IAM::User"):
        keys = _props(node).get("access_keys")
        if not isinstance(keys, list):
            continue
        for key in keys:
            if not isinstance(key, dict):
                continue
            if str(key.get("status", "Active")).lower() != "active":
                continue
            created_raw = key.get("create_date") or key.get("created_at")
            if not created_raw:
                continue
            try:
                created = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if created < cutoff:
                hits.append(
                    _hit(
                        rule,
                        node,
                        f"key:{key.get('access_key_id', 'unknown')}",
                        {
                            "user": node.get("arn") or node.get("id"),
                            "access_key_id": key.get("access_key_id"),
                            "create_date": created.isoformat(),
                            "age_days": (datetime.now(tz=UTC) - created).days,
                        },
                    )
                )
    return hits


def _eval_iam_root_access_key(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::IAM::User"):
        props = _props(node)
        is_root = _as_bool(props.get("is_root")) is True or str(node.get("arn", "")).endswith(
            ":root"
        )
        if is_root and _as_bool(props.get("has_access_key")) is True:
            hits.append(
                _hit(
                    rule,
                    node,
                    "root-key",
                    {"account_id": node.get("account_id"), "has_access_key": True},
                )
            )
    return hits


def _eval_lambda_public_url(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for node in graph.nodes_of_type("AWS::Lambda::Function"):
        props = _props(node)
        auth_type = str(
            props.get("function_url_auth_type", props.get("url_auth_type", "AWS_IAM"))
        ).upper()
        if _as_bool(props.get("function_url_public")) is True or auth_type == "NONE":
            hits.append(_hit(rule, node, "function-url", {"auth_type": auth_type}))
    return hits


def _eval_apigw_unauthenticated(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    api_types = ("AWS::ApiGateway::RestApi", "AWS::ApiGatewayV2::Api")
    for api_type in api_types:
        for node in graph.nodes_of_type(api_type):
            routes = _props(node).get("routes")
            if not isinstance(routes, list):
                continue
            for route in routes:
                if not isinstance(route, dict):
                    continue
                authorization = str(route.get("authorization", "NONE")).upper()
                if authorization in {"NONE", ""}:
                    key = f"{route.get('method', 'ANY')}:{route.get('path', '/')}"
                    hits.append(
                        _hit(
                            rule,
                            node,
                            key,
                            {
                                "api": node.get("arn") or node.get("id"),
                                "method": route.get("method"),
                                "path": route.get("path"),
                                "authorization": "NONE",
                            },
                        )
                    )
    return hits


def _accounts(graph: SecurityGraph) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for node in graph.nodes:
        account = node.get("account_id")
        if not account or str(account) == "000000000000":
            continue
        if node.get("type") == "AWS::Internet::Endpoint":
            continue
        if str(account) not in result:
            result[str(account)] = node
    return result


def _eval_cloudtrail_multiregion(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    trails = graph.nodes_of_type("AWS::CloudTrail::Trail")
    by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trail in trails:
        if trail.get("account_id"):
            by_account[str(trail["account_id"])].append(trail)
    for account, sample in _accounts(graph).items():
        account_trails = by_account.get(account, [])
        multi = any(
            _as_bool(_props(trail).get("is_multi_region")) is True for trail in account_trails
        )
        if multi:
            continue
        anchor = account_trails[0] if account_trails else sample
        hits.append(
            _hit(
                rule,
                anchor,
                "cloudtrail-multiregion",
                {
                    "account_id": account,
                    "trail_count": len(account_trails),
                    "is_multi_region": False,
                },
            )
        )
    return hits


def _eval_guardduty_disabled(rule: Rule, graph: SecurityGraph) -> list[RuleHit]:
    hits: list[RuleHit] = []
    detectors = graph.nodes_of_type("AWS::GuardDuty::Detector")
    by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for detector in detectors:
        if detector.get("account_id"):
            by_account[str(detector["account_id"])].append(detector)
    for account, sample in _accounts(graph).items():
        candidates = by_account.get(account, [])
        enabled = any(
            str(_props(detector).get("status", "ENABLED")).upper() == "ENABLED"
            for detector in candidates
        )
        if enabled:
            continue
        anchor = candidates[0] if candidates else sample
        hits.append(
            _hit(
                rule,
                anchor,
                "guardduty",
                {
                    "account_id": account,
                    "detector_count": len(candidates),
                    "status": "DISABLED" if candidates else "MISSING",
                },
            )
        )
    return hits


class SecurityGraph:
    """Small, immutable-ish view of the loaded subgraph used by evaluators."""

    def __init__(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        self.nodes = nodes
        self.edges = edges
        self.node_by_id: dict[str, dict[str, Any]] = {
            str(node["id"]): node for node in nodes if node.get("id")
        }
        self.outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            self.outgoing[source].append(edge)
            self.incoming[target].append(edge)
        self._by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in nodes:
            self._by_type[str(node.get("type", ""))].append(node)

    def nodes_of_type(self, *types: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for node_type in types:
            found.extend(self._by_type.get(node_type, []))
        return found

    def related(
        self,
        node_id: str,
        *,
        edge_types: Iterable[str] | None = None,
        direction: str = "out",
        target_types: Iterable[str] | None = None,
    ) -> list[tuple[dict[str, Any], str]]:
        allowed_edges = set(edge_types) if edge_types is not None else None
        allowed_types = set(target_types) if target_types is not None else None
        bucket = self.outgoing if direction == "out" else self.incoming
        results: list[tuple[dict[str, Any], str]] = []
        for edge in bucket.get(node_id, []):
            if allowed_edges is not None and edge.get("type") not in allowed_edges:
                continue
            other_id = edge.get("target") if direction == "out" else edge.get("source")
            other = self.node_by_id.get(str(other_id))
            if other is None:
                continue
            if allowed_types is not None and other.get("type") not in allowed_types:
                continue
            results.append((other, str(edge.get("type"))))
        return results

    def properties(self, node: dict[str, Any]) -> dict[str, Any]:
        return _props(node)

    @staticmethod
    def properties_for(node: dict[str, Any]) -> dict[str, Any]:
        return _props(node)


def _make_rule(
    *,
    rule_id: str,
    severity: str,
    title: str,
    description: str,
    resource_types: tuple[str, ...],
    evaluator: Callable[[Rule, SecurityGraph], list[RuleHit]],
    remediation_action: str | None = None,
    references: tuple[str, ...] = (),
    version: str = "1",
) -> Rule:
    return Rule(
        id=rule_id,
        version=version,
        severity=severity,
        title=title,
        description=description,
        resource_types=resource_types,
        evaluator=evaluator,
        remediation_action=remediation_action,
        references=references,
    )


RULES: tuple[Rule, ...] = (
    _make_rule(
        rule_id="sg-public-admin-port",
        severity="critical",
        title="Security group exposes an administrative port to the internet",
        description=(
            "An ingress rule allows 0.0.0.0/0 or ::/0 to reach an administrative or "
            "database port. Restrict the source to a trusted network or remove the rule."
        ),
        resource_types=("AWS::EC2::SecurityGroup",),
        evaluator=_eval_sg_internet_ingress,
        remediation_action="network.restrict_security_group_ingress",
        references=("CIS-AWS-5.2", "NIST-AC-4"),
    ),
    _make_rule(
        rule_id="sg-public-all-ports",
        severity="high",
        title="Security group exposes all ports to the internet",
        description=(
            "An ingress rule allows the entire port range from the internet, removing "
            "network segmentation for every attached resource."
        ),
        resource_types=("AWS::EC2::SecurityGroup",),
        evaluator=_eval_sg_internet_ingress,
        remediation_action="network.restrict_security_group_ingress",
        references=("CIS-AWS-5.2",),
    ),
    _make_rule(
        rule_id="sg-public-uncommon-port",
        severity="medium",
        title="Security group exposes a non-standard port to the internet",
        description=(
            "An ingress rule allows arbitrary internet traffic to a port that is not "
            "recognised as an administrative or data service."
        ),
        resource_types=("AWS::EC2::SecurityGroup",),
        evaluator=_eval_sg_internet_ingress,
        remediation_action="network.restrict_security_group_ingress",
        references=("NIST-AC-4",),
    ),
    _make_rule(
        rule_id="s3-public-policy",
        severity="critical",
        title="S3 bucket permits public access",
        description=(
            "The bucket ACL, bucket policy, or public access block configuration allows "
            "unauthenticated principals to read objects."
        ),
        resource_types=("AWS::S3::Bucket",),
        evaluator=_eval_s3_public,
        remediation_action="s3.harden_bucket",
        references=("CIS-AWS-2.1", "NIST-AC-3"),
    ),
    _make_rule(
        rule_id="s3-no-default-encryption",
        severity="medium",
        title="S3 bucket lacks default server-side encryption",
        description=(
            "Objects written to the bucket are not encrypted at rest by a default SSE "
            "configuration."
        ),
        resource_types=("AWS::S3::Bucket",),
        evaluator=_eval_s3_encryption,
        remediation_action="s3.harden_bucket",
        references=("CIS-AWS-2.1.1",),
    ),
    _make_rule(
        rule_id="s3-no-tls-enforcement",
        severity="medium",
        title="S3 bucket does not enforce TLS-only access",
        description=(
            "The bucket policy does not deny requests made over plaintext HTTP, allowing "
            "data to traverse the network unencrypted."
        ),
        resource_types=("AWS::S3::Bucket",),
        evaluator=_eval_s3_tls,
        remediation_action="s3.harden_bucket",
        references=("CIS-AWS-2.1.2",),
    ),
    _make_rule(
        rule_id="s3-no-versioning",
        severity="low",
        title="Data bucket does not enable versioning",
        description=(
            "Versioning protects data buckets against accidental deletion and ransomware "
            "overwrites."
        ),
        resource_types=("AWS::S3::Bucket",),
        evaluator=_eval_s3_versioning,
        remediation_action="s3.harden_bucket",
        references=("CIS-AWS-2.1.3",),
    ),
    _make_rule(
        rule_id="ebs-unencrypted",
        severity="medium",
        title="EBS volume is not encrypted",
        description="The EBS volume stores data at rest without AWS-managed encryption.",
        resource_types=("AWS::EC2::Volume",),
        evaluator=_eval_ebs_encryption,
        references=("CIS-AWS-2.2.1",),
    ),
    _make_rule(
        rule_id="rds-unencrypted",
        severity="medium",
        title="RDS instance storage is not encrypted",
        description="The database instance does not enable storage encryption at rest.",
        resource_types=("AWS::RDS::DBInstance",),
        evaluator=_eval_rds_encryption,
        references=("CIS-AWS-2.3.1",),
    ),
    _make_rule(
        rule_id="rds-publicly-accessible",
        severity="critical",
        title="RDS instance is publicly accessible",
        description=(
            "The database instance is assigned a public endpoint, exposing the database "
            "directly to the internet."
        ),
        resource_types=("AWS::RDS::DBInstance",),
        evaluator=_eval_rds_public,
        references=("CIS-AWS-2.3.2", "NIST-AC-4"),
    ),
    _make_rule(
        rule_id="iam-wildcard-action-resource",
        severity="high",
        title="IAM policy grants wildcard action on wildcard resource",
        description=(
            "A role policy statement allows Action:* on Resource:*, granting full account "
            "access if the role is compromised."
        ),
        resource_types=("AWS::IAM::Role",),
        evaluator=_eval_iam_wildcard,
        remediation_action="iam.attach_least_privilege_policy",
        references=("CIS-AWS-1.16", "NIST-AC-6"),
    ),
    _make_rule(
        rule_id="iam-privilege-escalation",
        severity="critical",
        title="IAM policy grants a privilege-escalation primitive",
        description=(
            "The role can create policy versions, attach policies, pass roles, or create "
            "compute resources that assume a more privileged identity."
        ),
        resource_types=("AWS::IAM::Role",),
        evaluator=_eval_iam_escalation,
        remediation_action="iam.attach_least_privilege_policy",
        references=("NIST-AC-6", "MITRE-T1078"),
    ),
    _make_rule(
        rule_id="iam-trust-wildcard-principal",
        severity="critical",
        title="IAM role trust policy allows any principal",
        description=(
            "The role trust policy uses a wildcard principal, letting any AWS identity "
            "assume the role."
        ),
        resource_types=("AWS::IAM::Role",),
        evaluator=_eval_iam_trust_wildcard,
        references=("CIS-AWS-1.17",),
    ),
    _make_rule(
        rule_id="iam-cross-account-trust-outside-org",
        severity="high",
        title="IAM role trusts an account outside the organization",
        description=(
            "The role can be assumed by an account that is not part of the tenant's AWS "
            "Organization."
        ),
        resource_types=("AWS::IAM::Role",),
        evaluator=_eval_iam_cross_account,
        references=("CIS-AWS-1.20",),
    ),
    _make_rule(
        rule_id="iam-old-access-key",
        severity="medium",
        title="IAM access key is older than 90 days",
        description="Long-lived active access keys increase the impact of credential leakage.",
        resource_types=("AWS::IAM::User",),
        evaluator=_eval_iam_old_access_key,
        references=("CIS-AWS-1.14",),
    ),
    _make_rule(
        rule_id="iam-root-access-key",
        severity="critical",
        title="Root account has an active access key",
        description=(
            "The root user should never have programmatic access keys; use scoped roles "
            "and federation instead."
        ),
        resource_types=("AWS::IAM::User",),
        evaluator=_eval_iam_root_access_key,
        references=("CIS-AWS-1.4",),
    ),
    _make_rule(
        rule_id="lambda-public-url",
        severity="high",
        title="Lambda function URL allows unauthenticated access",
        description=(
            "The function URL uses AuthType NONE, letting anyone on the internet invoke "
            "the function."
        ),
        resource_types=("AWS::Lambda::Function",),
        evaluator=_eval_lambda_public_url,
        references=("NIST-AC-3",),
    ),
    _make_rule(
        rule_id="apigw-unauthenticated",
        severity="high",
        title="API Gateway route has no authorization",
        description=(
            "An API Gateway route is configured with authorization NONE, exposing the "
            "backend without an identity check."
        ),
        resource_types=("AWS::ApiGateway::RestApi", "AWS::ApiGatewayV2::Api"),
        evaluator=_eval_apigw_unauthenticated,
        references=("NIST-AC-3",),
    ),
    _make_rule(
        rule_id="cloudtrail-not-multiregion",
        severity="medium",
        title="CloudTrail is not enabled as a multi-region trail",
        description=(
            "Audit logging is limited or absent, leaving API activity in other regions unrecorded."
        ),
        resource_types=("AWS::CloudTrail::Trail",),
        evaluator=_eval_cloudtrail_multiregion,
        references=("CIS-AWS-3.1",),
    ),
    _make_rule(
        rule_id="guardduty-disabled",
        severity="medium",
        title="GuardDuty detector is missing or disabled",
        description=(
            "Threat detection is not active for the account, so suspicious API and "
            "network activity is not surfaced."
        ),
        resource_types=("AWS::GuardDuty::Detector",),
        evaluator=_eval_guardduty_disabled,
        references=("CIS-AWS-4.1",),
    ),
)

RULE_BY_ID: dict[str, Rule] = {rule.id: rule for rule in RULES}


def evaluate_rules(graph: SecurityGraph, rules: Iterable[Rule] = RULES) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for rule in rules:
        hits.extend(rule.evaluator(rule, graph))
    return hits


__all__ = [
    "ADMIN_PORTS",
    "RULES",
    "RULE_BY_ID",
    "SENSITIVE_TYPES",
    "Rule",
    "RuleHit",
    "SecurityGraph",
    "evaluate_rules",
    "iter_ingress_rules",
]
