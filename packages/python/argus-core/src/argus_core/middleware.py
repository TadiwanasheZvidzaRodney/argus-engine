"""Request correlation for any ASGI app.

Pure ASGI on purpose: the API, the WebSocket gateway, and future services all
share one correlation contract without depending on Starlette internals.
"""

from __future__ import annotations

import re
from typing import Any

from argus_core.events import new_ulid
from argus_core.logging import bind_request_context, clear_request_context
from argus_core.settings import Settings
from argus_core.telemetry import current_trace_id

_REQUEST_ID_HEADER = b"x-request-id"
_TENANT_HEADER = b"x-argus-tenant"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class RequestContextMiddleware:
    """Bind request_id / trace_id / tenant_id and echo correlation headers.

    Inbound ``X-Request-Id`` values are accepted only when they look like a
    request id; anything else is replaced, so clients cannot inject log junk or
    forge another tenant's correlation trail.
    """

    def __init__(self, app: Any, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        request_id = self._request_id(headers)
        trace_id = current_trace_id()
        tenant_id = self._tenant_id(headers)

        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["trace_id"] = trace_id
        state["tenant_id"] = tenant_id
        bind_request_context(request_id=request_id, trace_id=trace_id, tenant_id=tenant_id)

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                raw = list(message.get("headers") or [])
                raw.append((b"x-request-id", request_id.encode()))
                if trace_id:
                    raw.append((b"x-trace-id", trace_id.encode()))
                message = {**message, "headers": raw}
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            clear_request_context()

    def _request_id(self, headers: dict[bytes, bytes]) -> str:
        candidate = headers.get(_REQUEST_ID_HEADER, b"").decode("latin-1").strip()
        if candidate and _SAFE_REQUEST_ID.match(candidate):
            return candidate
        return f"req_{new_ulid()}"

    def _tenant_id(self, headers: dict[bytes, bytes]) -> str | None:
        # Tenant resolution is Phase 1 auth territory; local/stub mode only.
        if not self.settings.is_local:
            return None
        candidate = headers.get(_TENANT_HEADER, b"").decode("latin-1").strip()
        return candidate or self.settings.default_tenant_id
