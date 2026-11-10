"""Shared runtime primitives for Argus Engine services.

Only framework-agnostic building blocks live here: settings, structured
logging, RFC 9457 problem details, opaque cursors, idempotency, telemetry,
and the event/audit contract models. HTTP framework wiring belongs to the
services so that `argus_core` stays importable from workers and CLIs.
"""

from argus_core.events import AuditEvent, EventEnvelope
from argus_core.settings import Environment, Settings, get_settings

__all__ = [
    "AuditEvent",
    "Environment",
    "EventEnvelope",
    "Settings",
    "get_settings",
]

__version__ = "0.1.0"
