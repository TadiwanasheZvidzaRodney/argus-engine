"""Deterministic synthetic AWS Cost Explorer adapter.

Enables realistic cost ingestion, 12-month historical backfill, and reconciliation
without live AWS credentials.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

SERVICES_AND_USAGE: list[tuple[str, str, float]] = [
    ("Amazon EC2", "BoxUsage:m5.xlarge", 45.0),
    ("Amazon EC2", "VolumeUsage.gp3", 12.0),
    ("Amazon RDS", "RDS:Multi-AZ-Usage", 38.0),
    ("Amazon RDS", "RDS:StorageUsage", 8.0),
    ("Amazon S3", "TimedStorage-ByteHrs", 24.0),
    ("Elastic Load Balancing", "LoadBalancerUsage", 18.0),
    ("AWS Lambda", "Lambda-GB-Second", 6.0),
    ("Amazon VPC", "NatGateway-Hours", 15.0),
    ("Amazon CloudWatch", "MetricData", 4.0),
]

TAG_ALLOCATIONS: list[tuple[str, str, float]] = [
    ("Environment", "production", 0.65),
    ("Environment", "staging", 0.25),
    ("Team", "platform", 0.40),
    ("Team", "payments", 0.50),
]


@dataclass(frozen=True)
class DailyCostRecord:
    account_id: str
    region: str
    service: str
    usage_type: str
    tag_key: str | None
    tag_value: str | None
    amount: float
    currency: str
    period_date: date


def _hash_seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def generate_daily_costs(
    account_id: str,
    region: str = "us-east-1",
    days: int = 30,
    end_date: date | None = None,
) -> list[DailyCostRecord]:
    """Generate deterministic daily cost records ending on end_date."""
    end = end_date or datetime.now(tz=UTC).date()
    records: list[DailyCostRecord] = []
    base_seed = _hash_seed(f"{account_id}:{region}")

    for day_offset in range(days - 1, -1, -1):
        period_date = end - timedelta(days=day_offset)
        day_seed = base_seed + day_offset

        for service, usage_type, base_amount in SERVICES_AND_USAGE:
            # Deterministic variation with subtle day-of-week and monthly seasonality
            wobble = math.sin((day_seed % 30) / 30.0 * math.tau) * 0.15
            amount = round(base_amount * (1.0 + wobble), 4)

            # Untagged baseline row for service total
            records.append(
                DailyCostRecord(
                    account_id=account_id,
                    region=region,
                    service=service,
                    usage_type=usage_type,
                    tag_key=None,
                    tag_value=None,
                    amount=amount,
                    currency="USD",
                    period_date=period_date,
                )
            )

            # Tagged allocation splits (for tag breakdown)
            for tag_key, tag_value, ratio in TAG_ALLOCATIONS:
                tagged_amount = round(amount * ratio, 4)
                records.append(
                    DailyCostRecord(
                        account_id=account_id,
                        region=region,
                        service=service,
                        usage_type=usage_type,
                        tag_key=tag_key,
                        tag_value=tag_value,
                        amount=tagged_amount,
                        currency="USD",
                        period_date=period_date,
                    )
                )

    return records
