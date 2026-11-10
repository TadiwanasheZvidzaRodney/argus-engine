"""OpenTelemetry wiring shared by API, WebSocket gateway, and workers."""

from __future__ import annotations

import atexit
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from argus_core.settings import Settings

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

_provider: TracerProvider | None = None


def build_resource(settings: Settings) -> Resource:
    return Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "service.instance.id": settings.commit_sha,
            "deployment.environment": settings.env.value,
        }
    )


def configure_telemetry(settings: Settings) -> TracerProvider | None:
    """Install a global tracer provider.

    Returns ``None`` when tracing is disabled, which keeps unit tests and local
    smoke runs free of background exporter threads.
    """
    global _provider
    if not settings.otel_enabled:
        return None
    if _provider is not None:
        return _provider

    provider = TracerProvider(
        resource=build_resource(settings),
        sampler=ParentBased(TraceIdRatioBased(settings.otel_sample_ratio)),
    )
    if settings.otel_exporter_otlp_endpoint:
        exporter = OTLPSpanExporter(
            endpoint=f"{settings.otel_exporter_otlp_endpoint.rstrip('/')}/v1/traces"
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _provider = provider
    atexit.register(shutdown_telemetry)
    return provider


def shutdown_telemetry() -> None:
    global _provider
    if _provider is not None:
        _provider.shutdown()
        _provider = None


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x")


def traced_span(
    name: str, attributes: dict[str, str | int | bool] | None = None, *, tracer: str = "argus"
) -> AbstractContextManager[Span]:
    """Context manager that records exceptions and sets span status."""
    return get_tracer(tracer).start_as_current_span(name, attributes=attributes or {})


def record_error(span: Span, error: BaseException) -> None:
    span.record_exception(error)
    span.set_status(Status(StatusCode.ERROR, str(error)))


def inject_trace_headers(headers: dict[str, str]) -> dict[str, str]:
    TraceContextTextMapPropagator().inject(headers)
    return headers


__all__ = [
    "build_resource",
    "configure_telemetry",
    "current_trace_id",
    "get_tracer",
    "inject_trace_headers",
    "record_error",
    "shutdown_telemetry",
    "traced_span",
]
