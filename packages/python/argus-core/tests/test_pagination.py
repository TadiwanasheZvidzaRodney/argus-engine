from __future__ import annotations

import pytest
from argus_core.pagination import (
    MAX_CURSOR_BYTES,
    CursorError,
    Page,
    decode_cursor,
    encode_cursor,
)

SECRET = "unit-test-secret"


def test_cursor_round_trip() -> None:
    cursor = encode_cursor({"after": "2026-11-10T12:00:00Z", "id": "abc"}, secret=SECRET)
    assert decode_cursor(cursor, secret=SECRET) == {"after": "2026-11-10T12:00:00Z", "id": "abc"}


def test_cursor_is_opaque_base64() -> None:
    cursor = encode_cursor({"tenant": "tnt_x"}, secret=SECRET)
    assert "." in cursor
    assert "tnt_" not in cursor
    assert cursor.isascii()
    assert "=" not in cursor


def test_tampered_cursor_is_rejected() -> None:
    cursor = encode_cursor({"after": "a"}, secret=SECRET)
    payload, signature = cursor.split(".", 1)
    forged = encode_cursor({"after": "b"}, secret=SECRET).split(".", 1)[0]
    with pytest.raises(CursorError, match="signature"):
        decode_cursor(f"{forged}.{signature}", secret=SECRET)
    with pytest.raises(CursorError):
        decode_cursor(payload, secret=SECRET)


def test_cursor_signed_with_other_secret_is_rejected() -> None:
    cursor = encode_cursor({"after": "a"}, secret="one-secret")
    with pytest.raises(CursorError, match="signature"):
        decode_cursor(cursor, secret="another-secret")


def test_malformed_cursor_is_rejected() -> None:
    with pytest.raises(CursorError):
        decode_cursor("not-a-cursor", secret=SECRET)
    with pytest.raises(CursorError):
        decode_cursor("a.b", secret=SECRET)


def test_oversized_payload_is_rejected() -> None:
    with pytest.raises(CursorError, match="too large"):
        encode_cursor({"blob": "x" * (MAX_CURSOR_BYTES + 64)}, secret=SECRET)


def test_page_build_omits_cursor_on_last_page() -> None:
    last = Page[int].build([1, 2], limit=2, next_payload=None, secret=SECRET)
    assert last.next_cursor is None
    assert last.has_more is False

    more = Page[int].build([1, 2], limit=2, next_payload={"after": 2}, secret=SECRET)
    assert more.next_cursor is not None
    assert more.has_more is True
    assert decode_cursor(more.next_cursor, secret=SECRET) == {"after": 2}
