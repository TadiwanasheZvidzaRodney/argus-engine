"""Deterministic synthetic CloudWatch collector with cache and downsampling.

The Phase 7 implementation ships a deterministic collector so the API, SSE
gateway, overlays, quotas, and anomaly pipeline can be exercised without live
AWS credentials. The adapter boundary is intentionally narrow: replacing
``generate_series`` with a batched CloudWatch ``GetMetricData`` call does not
change the rest of the pipeline.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from argus_api.telemetry.anomaly import detect_anomalies
from argus_api.telemetry.catalog import find_metric, metric_names_for_type


@dataclass(frozen=True)
class Series:
    resource_id: str
    metric: str
    unit: str
    resolution: int
    points: list[tuple[int, float]]
    anomalies: list[dict[str, Any]]

    def to_dict(self, subscription_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "resource_id": self.resource_id,
            "metric": self.metric,
            "unit": self.unit,
            "points": [[timestamp, value] for timestamp, value in self.points],
            "resolution": self.resolution,
            "anomalies": self.anomalies,
        }
        if subscription_id is not None:
            payload["subscription_id"] = subscription_id
        return payload


def _seed(resource_id: str, metric: str) -> int:
    digest = hashlib.sha256(f"{resource_id}:{metric}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _round(value: float, unit: str) -> float:
    if unit == "Bytes":
        return round(value, 0)
    if unit in {"Count", "Count/Second"}:
        return round(value, 2)
    return round(value, 3)


def _base_value(metric: str, unit: str, phase: float, index: int) -> float:
    wobble = math.sin(phase + index / 6.0)
    jitter = math.sin(phase * 3.7 + index * 1.93) * 0.5
    if metric == "CPUUtilization":
        return 38 + 14 * wobble + 3 * jitter
    if metric == "MemoryUtilization":
        return 55 + 10 * wobble + 2 * jitter
    if metric == "TargetResponseTime":
        return 0.22 + 0.08 * wobble + 0.02 * jitter
    if metric == "Latency":
        return 120 + 40 * wobble + 10 * jitter
    if metric == "FreeableMemory":
        return 2_147_483_648 + 268_435_456 * wobble
    if metric == "StatusCheckFailed":
        return 1.0 if (index + int(phase * 10)) % 97 == 0 else 0.0
    if metric in {"Errors", "Throttles", "NumberOfNotificationsFailed", "ThrottledRequests"}:
        return 1.0 if (index + int(phase * 10)) % 53 == 0 else 0.0
    if metric in {"HTTPCode_ELB_5XX", "5XXError", "5xxErrorRate"}:
        return max(0.0, 0.4 + 0.6 * wobble + 0.2 * jitter)
    if metric in {"4XXError", "4xxErrorRate"}:
        return max(0.0, 1.5 + 1.2 * wobble + 0.3 * jitter)
    if metric == "HealthyHostCount":
        return 2.0 if (index + int(phase * 10)) % 89 != 0 else 0.0
    if metric == "DatabaseConnections":
        return 40 + 25 * wobble + 4 * jitter
    if unit == "Bytes":
        return 1_000_000 + 250_000 * wobble + 20_000 * jitter
    if metric in {"RequestCount", "Invocations", "Count", "NumberOfMessagesPublished"}:
        return 600 + 220 * wobble + 40 * jitter
    if unit == "Percent":
        return max(0.0, 15 + 6 * wobble + jitter)
    return max(0.0, 10 + 4 * wobble + jitter)


def generate_series(
    *,
    resource_id: str,
    resource_type: str,
    metric: str,
    resolution: int = 60,
    periods: int = 30,
    now: datetime | None = None,
) -> Series:
    """Generate a deterministic series ending at the current aligned bucket."""
    definition = find_metric(resource_type, metric)
    if definition is None:
        supported = metric_names_for_type(resource_type)
        definition_name = supported[0] if supported else "HealthCheck"
        definition = find_metric(resource_type, definition_name)
        metric = definition_name
    unit = definition.unit if definition else "Count"
    resolution = max(1, resolution)
    now = now or datetime.now(tz=UTC)
    end_bucket = int(now.timestamp()) // resolution * resolution
    seed = _seed(resource_id, metric)
    phase = (seed % 3600) / 3600 * math.tau
    points: list[tuple[int, float]] = []
    for index in range(periods):
        timestamp = end_bucket - (periods - 1 - index) * resolution
        value = _base_value(metric, unit, phase, index)
        # Deterministic rare spike so the UI has an anomaly to display.
        if (seed + index * 7) % 149 == 0:
            multiplier = 2.5 if definition and definition.higher_is_worse else 0.5
            value *= multiplier
        if definition and definition.threshold is not None and definition.higher_is_worse:
            value = min(value, definition.threshold * 3 + 1)
        points.append((timestamp * 1000, _round(value, unit)))
    anomalies = []
    if definition is not None:
        anomalies = [item.to_dict() for item in detect_anomalies(points, definition)]
    return Series(
        resource_id=resource_id,
        metric=metric,
        unit=unit,
        resolution=resolution,
        points=points,
        anomalies=anomalies,
    )


def downsample(
    points: list[tuple[int, float]], resolution: int, target_resolution: int
) -> list[tuple[int, float]]:
    if target_resolution <= resolution or not points:
        return points
    step_ms = target_resolution * 1000
    buckets: dict[int, list[float]] = {}
    for timestamp, value in points:
        bucket = timestamp // step_ms * step_ms
        buckets.setdefault(bucket, []).append(value)
    return [
        (timestamp, round(sum(values) / len(values), 3))
        for timestamp, values in sorted(buckets.items())
    ]


class TelemetryCache:
    """Redis-backed cache with an in-memory fallback for local tests."""

    def __init__(self, redis: Redis | None = None, ttl_seconds: int = 60) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds
        self._memory: dict[str, tuple[float, str]] = {}

    def _key(self, tenant: str, resource_id: str, metric: str, resolution: int) -> str:
        return f"telemetry:cache:{tenant}:{resource_id}:{metric}:{resolution}"

    async def get(
        self, tenant: str, resource_id: str, metric: str, resolution: int
    ) -> Series | None:
        key = self._key(tenant, resource_id, metric, resolution)
        raw: str | None = None
        if self.redis is not None:
            try:
                fetched = await self.redis.get(key)
                if isinstance(fetched, bytes):
                    raw = fetched.decode("utf-8")
                elif isinstance(fetched, str):
                    raw = fetched
            except Exception:
                raw = None
        if raw is None:
            cached = self._memory.get(key)
            if cached and cached[0] > time.monotonic():
                raw = cached[1]
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            return Series(
                resource_id=payload["resource_id"],
                metric=payload["metric"],
                unit=payload["unit"],
                resolution=payload["resolution"],
                points=[(int(item[0]), float(item[1])) for item in payload["points"]],
                anomalies=list(payload.get("anomalies", [])),
            )
        except (ValueError, KeyError, TypeError):
            return None

    async def set(self, tenant: str, series: Series) -> None:
        key = self._key(tenant, series.resource_id, series.metric, series.resolution)
        payload = json.dumps(
            {
                "resource_id": series.resource_id,
                "metric": series.metric,
                "unit": series.unit,
                "resolution": series.resolution,
                "points": series.points,
                "anomalies": series.anomalies,
            }
        )
        if self.redis is not None:
            with contextlib.suppress(Exception):
                await self.redis.set(key, payload, ex=self.ttl_seconds)
                return
        self._memory[key] = (time.monotonic() + self.ttl_seconds, payload)

    def clear(self) -> None:
        self._memory.clear()


class MetricCollector:
    def __init__(self, cache: TelemetryCache) -> None:
        self.cache = cache

    async def collect(
        self,
        *,
        tenant: str,
        resources: list[dict[str, Any]],
        metrics: list[str],
        resolution: int,
        periods: int = 30,
        subscription_id: str | None = None,
    ) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        for resource in resources:
            resource_id = str(resource.get("id"))
            resource_type = str(resource.get("type", ""))
            allowed = metric_names_for_type(resource_type)
            selected = [metric for metric in metrics if metric in allowed] or allowed[:1]
            for metric in selected:
                cached = await self.cache.get(tenant, resource_id, metric, resolution)
                if cached is not None:
                    series = cached
                else:
                    series = generate_series(
                        resource_id=resource_id,
                        resource_type=resource_type,
                        metric=metric,
                        resolution=resolution,
                        periods=periods,
                    )
                    await self.cache.set(tenant, series)
                samples.append(series.to_dict(subscription_id))
        return samples


__all__ = [
    "MetricCollector",
    "Series",
    "TelemetryCache",
    "downsample",
    "generate_series",
]
