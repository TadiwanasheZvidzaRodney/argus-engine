"""Static-threshold and EWMA/z-score anomaly indicators."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from argus_api.telemetry.catalog import MetricDefinition

EWMA_ALPHA = 0.3
Z_SCORE_THRESHOLD = 3.0
MIN_BASELINE_POINTS = 5


@dataclass(frozen=True)
class Anomaly:
    kind: str
    severity: str
    message: str
    value: float
    threshold: float | None = None
    z_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "message": self.message,
            "value": self.value,
            "threshold": self.threshold,
            "z_score": self.z_score,
        }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def ewma(values: list[float], alpha: float = EWMA_ALPHA) -> float | None:
    if not values:
        return None
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result


def threshold_breached(metric: MetricDefinition, value: float) -> bool:
    if metric.threshold is None:
        return False
    if metric.higher_is_worse:
        return value > metric.threshold
    return value < metric.threshold


def detect_anomalies(
    points: list[tuple[int, float]],
    metric: MetricDefinition,
) -> list[Anomaly]:
    """Return threshold and statistical anomalies for a metric series."""
    if not points:
        return []
    values = [value for _, value in points]
    anomalies: list[Anomaly] = []
    latest = values[-1]
    if threshold_breached(metric, latest):
        severity = "critical" if metric.name in {"StatusCheckFailed", "5XXError"} else "warning"
        comparator = "above" if metric.higher_is_worse else "below"
        anomalies.append(
            Anomaly(
                kind="threshold",
                severity=severity,
                message=(
                    f"{metric.name} is {comparator} the configured threshold "
                    f"({latest:.2f} vs {metric.threshold:.2f})."
                ),
                value=latest,
                threshold=metric.threshold,
            )
        )

    baseline = values[:-1]
    if len(baseline) >= MIN_BASELINE_POINTS:
        mean = _mean(baseline)
        stdev = _stdev(baseline)
        if stdev > 0:
            z_score = (latest - mean) / stdev
            if abs(z_score) >= Z_SCORE_THRESHOLD:
                anomalies.append(
                    Anomaly(
                        kind="z-score",
                        severity="warning",
                        message=(
                            f"{metric.name} deviates {z_score:.1f} standard deviations "
                            "from its recent baseline."
                        ),
                        value=latest,
                        z_score=round(z_score, 3),
                    )
                )
        smoothed = ewma(baseline)
        if (
            smoothed is not None
            and metric.threshold is not None
            and metric.higher_is_worse
            and smoothed > metric.threshold * 1.1
        ):
            anomalies.append(
                Anomaly(
                    kind="ewma",
                    severity="info",
                    message=(
                        f"{metric.name} EWMA ({smoothed:.2f}) remains above the threshold band."
                    ),
                    value=round(smoothed, 3),
                    threshold=metric.threshold,
                )
            )
    return anomalies


__all__ = ["Anomaly", "detect_anomalies", "ewma", "threshold_breached"]
