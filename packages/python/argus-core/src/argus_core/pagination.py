"""Opaque, tamper-evident cursors and page envelopes.

Cursors are HMAC-signed so clients cannot forge offsets, widen a page, or point
a query at another tenant. They are intentionally opaque: the payload is an
implementation detail that may change without a version bump.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from typing import Any

from pydantic import BaseModel, Field

MAX_CURSOR_BYTES = 4096
_SIGNATURE_BYTES = 16


class CursorError(ValueError):
    """Raised when a cursor is malformed, oversized, or fails verification."""


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload: bytes, secret: str) -> bytes:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return digest[:_SIGNATURE_BYTES]


def encode_cursor(payload: dict[str, Any], *, secret: str) -> str:
    """Serialize and sign a cursor payload.

    Raises ``CursorError`` when the payload exceeds the cursor size budget,
    which keeps cursors bounded when they carry free-form sort keys.
    """
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(raw) > MAX_CURSOR_BYTES:
        raise CursorError("cursor payload too large")
    return f"{_b64encode(raw)}.{_b64encode(_sign(raw, secret))}"


def decode_cursor(cursor: str, *, secret: str) -> dict[str, Any]:
    if len(cursor) > MAX_CURSOR_BYTES * 2:
        raise CursorError("cursor too large")
    try:
        payload_b64, signature_b64 = cursor.split(".", 1)
        raw = _b64decode(payload_b64)
        signature = _b64decode(signature_b64)
    except (ValueError, binascii.Error) as exc:  # pragma: no cover - defensive
        raise CursorError("cursor is malformed") from exc

    if not hmac.compare_digest(signature, _sign(raw, secret)):
        raise CursorError("cursor signature is invalid")

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CursorError("cursor payload is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise CursorError("cursor payload must be an object")
    return decoded


class Page[T](BaseModel):
    """Cursor-paginated collection envelope used by every list endpoint."""

    items: list[T] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False

    @classmethod
    def build(
        cls,
        items: list[T],
        *,
        limit: int,
        next_payload: dict[str, Any] | None,
        secret: str,
    ) -> Page[T]:
        return cls(
            items=items,
            next_cursor=encode_cursor(next_payload, secret=secret) if next_payload else None,
            has_more=next_payload is not None,
        )
