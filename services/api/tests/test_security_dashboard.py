from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from argus_api.models import FindingEventModel, FindingModel
from argus_api.security.dashboard import (
    finding_history,
    posture,
    risk_score,
    score_grade,
    time_window,
)
from argus_api.security.rules import SecurityGraph
from argus_core.events import new_uuid7

NOW = datetime(2026, 11, 18, 14, 30, tzinfo=UTC)


def finding(severity: str = "high", status: str = "OPEN") -> FindingModel:
    return FindingModel(
        id=new_uuid7(),
        tenant_id=new_uuid7(),
        rule_id="iam-old-access-key",
        resource_type="AWS::IAM::User",
        resource_id="arn:aws:iam::123456789012:user/test",
        status=status,
        severity=severity,
        first_seen=NOW - timedelta(hours=4),
        last_seen=NOW,
    )


def event(row: FindingModel, hour: int, before: str | None, after: str) -> FindingEventModel:
    return FindingEventModel(
        id=new_uuid7(),
        finding_id=row.id,
        tenant_id=row.tenant_id,
        from_status=before,
        to_status=after,
        event_type="status_changed",
        created_at=NOW.replace(hour=hour, minute=15),
    )


def test_indicator_weights_grade_and_clamping() -> None:
    rows = [finding("critical"), finding("high"), finding("medium"), finding("low")]
    assert risk_score(rows) == 73
    assert risk_score(rows, path_count=1) == 53
    assert risk_score([finding("critical") for _ in range(20)]) == 0
    assert risk_score([finding("critical", "SUPPRESSED"), finding("high", "RISK_ACCEPTED")]) == 100
    assert risk_score([finding("high", "ACKNOWLEDGED")]) == 92
    assert [score_grade(s) for s in [100, 90, 89, 80, 79, 70, 69, 60, 59, 0]] == [
        "A",
        "A",
        "B",
        "B",
        "C",
        "C",
        "D",
        "D",
        "F",
        "F",
    ]


@pytest.mark.parametrize(
    ("selected", "hours"),
    [
        ("today", 14.5),
        ("24h", 24),
        ("7d", 168),
        ("14d", 336),
        ("30d", 720),
    ],
)
def test_history_windows_never_extend_into_future(selected, hours) -> None:
    start, _step = time_window(selected, NOW)
    assert start == NOW - timedelta(hours=hours)
    result = finding_history([], [], selected, NOW)
    assert result["trend_history"][-1]["timestamp"] == NOW.isoformat()
    assert all(
        start <= datetime.fromisoformat(p["timestamp"]) <= NOW for p in result["trend_history"]
    )
    assert all(p["active"] is None for p in result["trend_history"])


def test_history_replays_reopen_acknowledge_suppression_and_acceptance() -> None:
    row = finding()
    row.first_seen = NOW.replace(hour=1, minute=15)
    events = [
        event(row, 1, None, "OPEN"),
        event(row, 2, "OPEN", "ACKNOWLEDGED"),
        event(row, 3, "ACKNOWLEDGED", "RESOLVED"),
        event(row, 4, "RESOLVED", "OPEN"),
        event(row, 5, "OPEN", "SUPPRESSED"),
        event(row, 6, "SUPPRESSED", "OPEN"),
        event(row, 7, "OPEN", "RISK_ACCEPTED"),
    ]
    result = finding_history([row], events, "today", NOW)
    points = result["trend_history"]
    assert points[0]["active"] is None  # Don't report safety before first observation.
    assert points[1]["high"] == 1
    assert points[2]["high"] == 1  # Acknowledgement is not a fix.
    assert points[3]["active"] == 0
    assert points[4]["active"] == 1
    assert points[5]["active"] == 0
    assert points[6]["active"] == 1
    assert points[7]["active"] == 0
    assert sum(p["opened"] or 0 for p in points) == 3
    assert sum(p["resolved"] or 0 for p in points) == 1
    assert result["history_partial"] is False


def test_history_carries_backlog_from_before_window_and_ignores_other_findings() -> None:
    row = finding("critical")
    row.first_seen = NOW - timedelta(days=5)
    opened = event(row, 1, None, "OPEN")
    opened.created_at = row.first_seen
    other = finding()
    result = finding_history([row], [opened, event(other, 3, None, "OPEN")], "today", NOW)
    assert all(p["critical"] == 1 and p["opened"] == 0 for p in result["trend_history"])


def test_legacy_history_flag_and_midnight_boundary() -> None:
    row = finding()
    row.first_seen = NOW.replace(hour=0, minute=0, second=0)
    row.resolved_at = NOW.replace(hour=2, minute=0)
    result = finding_history([row], [], "today", NOW)
    assert result["history_partial"] is True
    assert sum(p["opened"] or 0 for p in result["trend_history"]) == 1
    assert sum(p["resolved"] or 0 for p in result["trend_history"]) == 1
    midnight = NOW.replace(hour=0, minute=0)
    assert len(finding_history([], [], "today", midnight)["trend_history"]) == 1


def test_score_requires_observations_and_graph_and_labels_unverified_domains() -> None:
    row = finding()
    graph = SecurityGraph([{"id": row.resource_id, "type": row.resource_type}], [])
    paths = {"count": 1}
    assert posture([], graph, paths, NOW)["score"] is None
    assert posture([row], None, None, NOW)["score"] is None
    result = posture([row], graph, paths, NOW)
    assert result["score"] == 72
    assert result["grade"] == "C"
    assert result["domains"][0]["score"] == 92
    assert result["domains"][-1]["score"] is None
    assert result["domains"][-1]["status"] == "coverage_unverified"
    row.last_seen = NOW - timedelta(days=2)
    assert posture([row], graph, paths, NOW)["stale"] is True


def test_missing_logging_controls_classify_by_rule_not_anchor_resource() -> None:
    row = finding()
    row.rule_id = "cloudtrail-not-multiregion"
    row.resource_type = "AWS::EC2::VPC"
    graph = SecurityGraph([{"id": row.resource_id, "type": row.resource_type}], [])
    result = posture([row], graph, {"count": 0}, NOW)
    governance = result["domains"][-1]
    assert governance["resources_observed"] == 0
    assert governance["open_findings"] == 1
    assert governance["score"] == 92
