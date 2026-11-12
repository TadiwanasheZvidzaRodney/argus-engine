"""CloudWatch-compatible metric catalog for canvas overlays."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    unit: str
    default_statistic: str = "Average"
    threshold: float | None = None
    higher_is_worse: bool = True
    description: str = ""


@dataclass(frozen=True)
class ResourceMetrics:
    resource_type: str
    metrics: tuple[MetricDefinition, ...]


_EC2 = ResourceMetrics(
    "AWS::EC2::Instance",
    (
        MetricDefinition("CPUUtilization", "Percent", threshold=80.0),
        MetricDefinition("NetworkIn", "Bytes", "Sum"),
        MetricDefinition("NetworkOut", "Bytes", "Sum"),
        MetricDefinition("DiskReadOps", "Count", "Sum"),
        MetricDefinition("DiskWriteOps", "Count", "Sum"),
        MetricDefinition("StatusCheckFailed", "Count", "Maximum", threshold=0.0),
    ),
)

_RDS = ResourceMetrics(
    "AWS::RDS::DBInstance",
    (
        MetricDefinition("CPUUtilization", "Percent", threshold=80.0),
        MetricDefinition("DatabaseConnections", "Count", threshold=200.0),
        MetricDefinition("FreeableMemory", "Bytes", threshold=536870912.0, higher_is_worse=False),
        MetricDefinition("ReadIOPS", "Count/Second"),
        MetricDefinition("WriteIOPS", "Count/Second"),
        MetricDefinition("Latency", "Seconds", threshold=0.5),
    ),
)

_ALB = ResourceMetrics(
    "AWS::ElasticLoadBalancingV2::LoadBalancer",
    (
        MetricDefinition("RequestCount", "Count", "Sum"),
        MetricDefinition("TargetResponseTime", "Seconds", threshold=1.0),
        MetricDefinition("HTTPCode_ELB_5XX", "Count", "Sum", threshold=5.0),
        MetricDefinition("HealthyHostCount", "Count", threshold=1.0, higher_is_worse=False),
    ),
)

_LAMBDA = ResourceMetrics(
    "AWS::Lambda::Function",
    (
        MetricDefinition("Invocations", "Count", "Sum"),
        MetricDefinition("Errors", "Count", "Sum", threshold=1.0),
        MetricDefinition("Throttles", "Count", "Sum", threshold=0.0),
        MetricDefinition("Duration", "Milliseconds", threshold=3000.0),
        MetricDefinition("ConcurrentExecutions", "Count"),
    ),
)

_SQS = ResourceMetrics(
    "AWS::SQS::Queue",
    (
        MetricDefinition("ApproximateNumberOfMessagesVisible", "Count", threshold=1000.0),
        MetricDefinition("AgeOfOldestMessage", "Seconds", threshold=300.0),
    ),
)

_SNS = ResourceMetrics(
    "AWS::SNS::Topic",
    (
        MetricDefinition("NumberOfMessagesPublished", "Count", "Sum"),
        MetricDefinition("NumberOfNotificationsFailed", "Count", "Sum", threshold=0.0),
    ),
)

_DYNAMO = ResourceMetrics(
    "AWS::DynamoDB::Table",
    (
        MetricDefinition("ConsumedReadCapacityUnits", "Count", "Sum"),
        MetricDefinition("ConsumedWriteCapacityUnits", "Count", "Sum"),
        MetricDefinition("ThrottledRequests", "Count", "Sum", threshold=0.0),
    ),
)

_ECS = ResourceMetrics(
    "AWS::ECS::Service",
    (
        MetricDefinition("CPUUtilization", "Percent", threshold=80.0),
        MetricDefinition("MemoryUtilization", "Percent", threshold=85.0),
        MetricDefinition("RunningTaskCount", "Count", threshold=1.0, higher_is_worse=False),
    ),
)

_S3 = ResourceMetrics(
    "AWS::S3::Bucket",
    (
        MetricDefinition("BucketSizeBytes", "Bytes", "Average"),
        MetricDefinition("NumberOfObjects", "Count", "Average"),
    ),
)

_APIGW = ResourceMetrics(
    "AWS::ApiGateway::RestApi",
    (
        MetricDefinition("Count", "Count", "Sum"),
        MetricDefinition("4XXError", "Count", "Sum", threshold=10.0),
        MetricDefinition("5XXError", "Count", "Sum", threshold=1.0),
        MetricDefinition("Latency", "Milliseconds", threshold=1000.0),
    ),
)

_CLOUDFRONT = ResourceMetrics(
    "AWS::CloudFront::Distribution",
    (
        MetricDefinition("Requests", "Count", "Sum"),
        MetricDefinition("BytesDownloaded", "Bytes", "Sum"),
        MetricDefinition("4xxErrorRate", "Percent", threshold=5.0),
        MetricDefinition("5xxErrorRate", "Percent", threshold=1.0),
    ),
)

CATALOG: dict[str, ResourceMetrics] = {
    entry.resource_type: entry
    for entry in (_EC2, _RDS, _ALB, _LAMBDA, _SQS, _SNS, _DYNAMO, _ECS, _S3, _APIGW, _CLOUDFRONT)
}

# Layout icons / node badges use the first metric as the primary health signal.
PRIMARY_METRIC = {
    "AWS::EC2::Instance": "CPUUtilization",
    "AWS::RDS::DBInstance": "CPUUtilization",
    "AWS::ElasticLoadBalancingV2::LoadBalancer": "TargetResponseTime",
    "AWS::Lambda::Function": "Errors",
    "AWS::ECS::Service": "CPUUtilization",
    "AWS::ApiGateway::RestApi": "5XXError",
}

_DEFAULT = ResourceMetrics(
    "default",
    (MetricDefinition("HealthCheck", "Count", threshold=0.0),),
)


def metrics_for_type(resource_type: str) -> list[MetricDefinition]:
    return list(CATALOG.get(resource_type, _DEFAULT).metrics)


def metric_names_for_type(resource_type: str) -> list[str]:
    return [metric.name for metric in metrics_for_type(resource_type)]


def find_metric(resource_type: str, name: str) -> MetricDefinition | None:
    for metric in metrics_for_type(resource_type):
        if metric.name == name:
            return metric
    return None


def catalog_payload() -> list[dict[str, object]]:
    return [
        {
            "resource_type": resource_type,
            "metrics": [
                {
                    "name": metric.name,
                    "unit": metric.unit,
                    "default_statistic": metric.default_statistic,
                    "threshold": metric.threshold,
                    "higher_is_worse": metric.higher_is_worse,
                    "description": metric.description,
                }
                for metric in entry.metrics
            ],
        }
        for resource_type, entry in CATALOG.items()
    ]


__all__ = [
    "CATALOG",
    "PRIMARY_METRIC",
    "MetricDefinition",
    "catalog_payload",
    "find_metric",
    "metric_names_for_type",
    "metrics_for_type",
]
