"""Structured JSON logging with mandatory redaction.

Every log line carries the service identity, and — when bound by the request
context middleware — ``request_id``, ``trace_id`` and ``tenant_id`` so that
logs can be pivoted from a trace or a tenant without grepping free text.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from argus_core.settings import Settings

#: Substrings that trigger redaction. Matched case-insensitively against keys.
REDACT_KEYS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "authorization",
    "cookie",
    "credential",
    "private_key",
    "access_key",
    "session_id",
    "api_key",
)

REDACTED = "[REDACTED]"


def _redact(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    for key in list(event_dict.keys()):
        lowered = key.lower()
        if any(marker in lowered for marker in REDACT_KEYS):
            event_dict[key] = REDACTED
    return event_dict


def _add_service_context(settings: Settings) -> Processor:
    def processor(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("service", settings.service_name)
        event_dict.setdefault("service_version", settings.service_version)
        event_dict.setdefault("env", settings.env.value)
        return event_dict

    return processor


def configure_logging(settings: Settings, *, stream: Any | None = None) -> None:
    """Configure structlog + stdlib logging once per process."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact,
        _add_service_context(settings),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn duplicates access logs; keep its loggers on the same pipeline.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)


def bind_request_context(
    *, request_id: str, trace_id: str | None = None, tenant_id: str | None = None
) -> None:
    context: MutableMapping[str, Any] = {"request_id": request_id}
    if trace_id:
        context["trace_id"] = trace_id
    if tenant_id:
        context["tenant_id"] = tenant_id
    structlog.contextvars.bind_contextvars(**context)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()
