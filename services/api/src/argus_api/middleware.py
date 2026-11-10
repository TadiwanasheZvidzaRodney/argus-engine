"""Edge middleware: request size limits, idempotency, and security headers."""

from __future__ import annotations

import json
import re
from typing import Any

from argus_core.errors import PROBLEM_CONTENT_TYPE
from argus_core.idempotency import (
    BeginOutcome,
    IdempotencyStore,
    StoredResponse,
    fingerprint_request,
)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_JSON_CONTENT_TYPE = "application/json"


def _headers(scope: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers") or []
    }
    return headers


def _problem_body(status: int, code: str, title: str, detail: str, request_id: str | None) -> bytes:
    return json.dumps(
        {
            "type": f"https://errors.argus.example.com/{code}",
            "title": title,
            "status": status,
            "detail": detail,
            "request_id": request_id,
        },
        separators=(",", ":"),
    ).encode("utf-8")


class IdempotencyMiddleware:
    """Enforce the Idempotency-Key contract for every mutating API request.

    Applied at the edge so no handler can forget it. The request body is read
    once, hashed into a fingerprint, and replayed to the application.
    """

    def __init__(
        self,
        app: Any,
        store: IdempotencyStore,
        *,
        ttl_seconds: int = 86_400,
        lock_seconds: int = 30,
        max_body_bytes: int = 10 * 1024 * 1024,
        protected_prefix: str = "/api/v1/",
    ) -> None:
        self.app = app
        self.store = store
        self.ttl_seconds = ttl_seconds
        self.lock_seconds = lock_seconds
        self.max_body_bytes = max_body_bytes
        self.protected_prefix = protected_prefix

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["method"] in SAFE_METHODS or not scope["path"].startswith(self.protected_prefix):
            await self.app(scope, receive, send)
            return

        headers = _headers(scope)
        request_id = (scope.get("state") or {}).get("request_id")

        key = headers.get("idempotency-key", "").strip()
        if not key:
            await self._problem(
                send,
                400,
                "idempotency-key-required",
                "Idempotency-Key Required",
                "Every mutating request must include an Idempotency-Key header.",
                request_id,
            )
            return
        if not IDEMPOTENCY_KEY_PATTERN.match(key):
            await self._problem(
                send,
                400,
                "idempotency-key-invalid",
                "Invalid Idempotency Key",
                "Idempotency-Key must be 8-128 characters of [A-Za-z0-9._:-].",
                request_id,
            )
            return

        body = b""
        async for chunk in self._read_body(receive):
            body += chunk
            if len(body) > self.max_body_bytes:
                await self._problem(
                    send,
                    413,
                    "payload-too-large",
                    "Payload Too Large",
                    "Request body exceeds the configured limit.",
                    request_id,
                )
                return

        fingerprint = fingerprint_request(scope["method"], scope["path"], body)
        result = await self.store.begin(
            key, fingerprint, ttl_seconds=self.ttl_seconds, lock_seconds=self.lock_seconds
        )

        if result.outcome is BeginOutcome.REPLAY and result.stored is not None:
            await self._replay(send, result.stored)
            return
        if result.outcome is BeginOutcome.IN_FLIGHT:
            await self._problem(
                send,
                409,
                "idempotency-request-in-flight",
                "Request Already In Progress",
                "A request with this Idempotency-Key is still being processed.",
                request_id,
                extra_headers={"Retry-After": "1"},
            )
            return
        if result.outcome is BeginOutcome.FINGERPRINT_MISMATCH:
            await self._problem(
                send,
                409,
                "idempotency-key-reuse",
                "Idempotency Key Reused",
                "This Idempotency-Key was already used with a different request payload.",
                request_id,
            )
            return

        replay_receive = _replay_receive(body, receive)
        captured: dict[str, Any] = {"status": 500, "headers": [], "body": b""}

        async def capture_send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                captured["status"] = message["status"]
                captured["headers"] = list(message.get("headers") or [])
            elif message["type"] == "http.response.body":
                captured["body"] += message.get("body", b"")
            await send(message)

        try:
            await self.app(scope, replay_receive, capture_send)
        except BaseException:
            await self.store.release(key)
            raise

        await self._store_response(key, fingerprint, captured)

    async def _read_body(self, receive: Any) -> Any:
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return
            yield message.get("body", b"")
            if not message.get("more_body", False):
                return

    async def _store_response(self, key: str, fingerprint: str, captured: dict[str, Any]) -> None:
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in captured["headers"]}
        content_type = headers.get("content-type", "")
        status = int(captured["status"])
        if status >= 500 or _JSON_CONTENT_TYPE not in content_type:
            await self.store.release(key)
            return
        try:
            body = json.loads(captured["body"] or b"{}")
        except json.JSONDecodeError:
            await self.store.release(key)
            return
        if not isinstance(body, dict):
            await self.store.release(key)
            return
        await self.store.complete(
            key,
            StoredResponse(status_code=status, body=body, fingerprint=fingerprint),
            ttl_seconds=self.ttl_seconds,
        )

    async def _replay(self, send: Any, stored: StoredResponse) -> None:
        payload = json.dumps(stored.body, separators=(",", ":")).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": stored.status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                    (b"x-idempotent-replay", b"true"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})

    async def _problem(
        self,
        send: Any,
        status: int,
        code: str,
        title: str,
        detail: str,
        request_id: str | None,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        payload = _problem_body(status, code, title, detail, request_id)
        raw_headers = [
            (b"content-type", PROBLEM_CONTENT_TYPE.encode()),
            (b"content-length", str(len(payload)).encode()),
        ]
        for name, value in (extra_headers or {}).items():
            raw_headers.append((name.encode(), value.encode()))
        await send({"type": "http.response.start", "status": status, "headers": raw_headers})
        await send({"type": "http.response.body", "body": payload})


def _replay_receive(body: bytes, original_receive: Any) -> Any:
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        message: dict[str, Any] = await original_receive()
        return message

    return receive


class SecurityHeadersMiddleware:
    """Conservative browser hardening for every JSON response."""

    DEFAULT_HEADERS: tuple[tuple[bytes, bytes], ...] = (
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
        (b"cross-origin-resource-policy", b"same-site"),
    )

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                raw = list(message.get("headers") or [])
                existing = {name.lower() for name, _ in raw}
                raw.extend((n, v) for n, v in self.DEFAULT_HEADERS if n not in existing)
                message = {**message, "headers": raw}
            await send(message)

        await self.app(scope, receive, send_with_headers)
