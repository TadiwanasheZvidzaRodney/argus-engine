"""Evidence-based dashboard projections. Never synthesizes cloud telemetry."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Literal

from argus_api.models import FindingEventModel, FindingModel
from argus_api.security.rules import SecurityGraph

SecurityRange = Literal["today", "24h", "7d", "14d", "30d"]
OPEN = {"OPEN", "ACKNOWLEDGED"}
WEIGHTS = {"critical": 15, "high": 8, "medium": 3, "low": 1}
DOMAIN_TYPES = {
    "iam": ("IAM & access hygiene", {"AWS::IAM::User", "AWS::IAM::Role"}),
    "storage": (
        "Storage & encryption",
        {"AWS::S3::Bucket", "AWS::EC2::Volume", "AWS::RDS::DBInstance"},
    ),
    "network": (
        "Network boundary",
        {
            "AWS::EC2::SecurityGroup",
            "AWS::RDS::DBInstance",
            "AWS::Lambda::Function",
            "AWS::ApiGateway::RestApi",
            "AWS::ApiGatewayV2::Api",
        },
    ),
    "governance": (
        "Logging & governance",
        {"AWS::CloudTrail::Trail", "AWS::GuardDuty::Detector"},
    ),
}


def finding_domain(row: FindingModel) -> str | None:
    # Account-level missing-control findings may be anchored to a VPC rather
    # than a Trail/Detector. Classify by rule, not by the anchor's type.
    if row.rule_id.startswith(("cloudtrail-", "guardduty-")):
        return "governance"
    if row.rule_id.startswith("iam-"):
        return "iam"
    if row.rule_id.startswith(("sg-", "lambda-", "apigw-")) or (
        row.rule_id == "rds-publicly-accessible"
    ):
        return "network"
    if row.rule_id.startswith(("s3-", "ebs-", "rds-")):
        return "storage"
    return next(
        (key for key, (_label, types) in DOMAIN_TYPES.items() if row.resource_type in types),
        None,
    )


def risk_score(rows: Sequence[FindingModel], path_count: int = 0) -> int:
    """Argus heuristic, not a control pass rate or compliance certification."""
    penalty = sum(WEIGHTS.get(row.severity, 0) for row in rows if row.status in OPEN)
    return max(0, 100 - penalty - 20 * path_count)


def score_grade(score: int) -> str:
    return (
        "A"
        if score >= 90
        else "B"
        if score >= 80
        else "C"
        if score >= 70
        else ("D" if score >= 60 else "F")
    )


def time_window(time_range: SecurityRange, now: datetime) -> tuple[datetime, timedelta]:
    if time_range == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0), timedelta(hours=1)
    if time_range == "24h":
        return now - timedelta(hours=24), timedelta(hours=1)
    days = {"7d": 7, "14d": 14, "30d": 30}[time_range]
    return now - timedelta(days=days), timedelta(days=1)


def finding_history(
    rows: Sequence[FindingModel],
    events: Sequence[FindingEventModel],
    time_range: SecurityRange,
    now: datetime,
) -> dict[str, Any]:
    """Replay recorded transitions, including reopen/suppress/accept/acknowledge.

    Before the first recorded observation counts are unknown, not zero. Severity
    is the finding's current classification: old severity versions aren't stored.
    """
    start, step = time_window(time_range, now)
    by_id = {row.id: row for row in rows}
    transitions = [
        (event.created_at, str(event.id), event.finding_id, event.to_status)
        for event in events
        if event.finding_id in by_id and event.to_status and event.created_at <= now
    ]
    opened_ids = {
        event.finding_id
        for event in events
        if event.finding_id in by_id and event.from_status is None and event.to_status in OPEN
    }
    legacy = False
    for row in rows:
        if row.id not in opened_ids and row.first_seen <= now:
            # Legacy imports can have no lifecycle log. Only use known timestamps;
            # do not invent intervening status changes.
            transitions.append((row.first_seen, "", row.id, "OPEN"))
            legacy = True
            if row.resolved_at and row.resolved_at <= now:
                transitions.append((row.resolved_at, "~", row.id, "RESOLVED"))
    transitions.sort(key=lambda item: (item[0], item[1]))
    observed_since = min((row.first_seen for row in rows), default=None)
    state: dict[Any, str] = {}
    cursor = 0
    points = []
    bucket = start
    while bucket <= now:
        end = min(bucket + step, now)
        opened = resolved = 0
        for_window = 0
        while cursor < len(transitions) and transitions[cursor][0] <= end:
            at, _key, finding_id, status = transitions[cursor]
            previous = state.get(finding_id)
            if at >= bucket:
                opened += int(status in OPEN and previous not in OPEN)
                resolved += int(status == "RESOLVED" and previous != "RESOLVED")
                for_window += int(previous != status)
            state[finding_id] = str(status)
            cursor += 1
        counts = dict.fromkeys(WEIGHTS, 0)
        for finding_id, status in state.items():
            if status in OPEN:
                severity = by_id[finding_id].severity
                counts[severity] = counts.get(severity, 0) + 1
        known = observed_since is not None and end >= observed_since
        points.append(
            {
                "timestamp": end.isoformat(),
                "bucket_start": bucket.isoformat(),
                "opened": opened if known else None,
                "resolved": resolved if known else None,
                "active": sum(counts.values()) if known else None,
                "transitions": for_window if known else None,
                **{severity: count if known else None for severity, count in counts.items()},
            }
        )
        if end == now:
            break
        bucket += step
    return {
        "time_range": time_range,
        "window_start": start.isoformat(),
        "window_end": now.isoformat(),
        "timezone": "UTC",
        "observed_since": observed_since.isoformat() if observed_since else None,
        "history_partial": legacy,
        "trend_history": points,
    }


def posture(
    rows: Sequence[FindingModel],
    graph: SecurityGraph | None,
    paths: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    last_observed = max((row.last_seen for row in rows), default=None)
    # No findings is not evidence that a successful clean scan ever happened.
    available = bool(rows) and graph is not None and bool(graph.nodes) and paths is not None
    score = risk_score(rows, paths["count"]) if available and paths is not None else None
    domains = []
    for key, (label, types) in DOMAIN_TYPES.items():
        domain_rows = [row for row in rows if finding_domain(row) == key]
        nodes = [node for node in graph.nodes if node.get("type") in types] if graph else []
        domain_score = (
            risk_score(domain_rows) if domain_rows and graph is not None and graph.nodes else None
        )
        domains.append(
            {
                "id": key,
                "label": label,
                "score": domain_score,
                "resources_observed": len(nodes) if graph is not None else None,
                "open_findings": sum(row.status in OPEN for row in domain_rows),
                "status": "recorded_findings"
                if domain_score is not None
                else "coverage_unverified",
            }
        )
    return {
        "score": score,
        "grade": score_grade(score) if score is not None else None,
        "last_finding_observed_at": last_observed.isoformat() if last_observed else None,
        "stale": last_observed is not None and now - last_observed > timedelta(days=1),
        "graph_available": graph is not None,
        "resources_observed": len(graph.nodes) if graph else None,
        "domains": domains,
        "score_method": (
            "Argus risk indicator: 100 minus 15/8/3/1 per open or acknowledged "
            "critical/high/medium/low finding, minus 20 per returned internet path, "
            "floored at 0. Accepted and suppressed findings are excluded. "
            "Graph/path coverage may be bounded. Not a CIS pass rate or certification. "
            "No finding records means scan coverage is unverified."
        ),
    }
