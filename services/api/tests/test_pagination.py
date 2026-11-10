from __future__ import annotations

from fastapi.testclient import TestClient


def test_pagination_returns_page_and_cursor(client: TestClient) -> None:
    response = client.get("/api/v1/demo/resources", params={"limit": 10})
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 10
    assert body["has_more"] is True
    assert body["next_cursor"]


def test_cursor_walks_all_pages_without_duplicates(client: TestClient) -> None:
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict[str, object] = {"limit": 25}
        if cursor:
            params["cursor"] = cursor
        body = client.get("/api/v1/demo/resources", params=params).json()
        seen.extend(item["id"] for item in body["items"])
        pages += 1
        cursor = body["next_cursor"]
        if not cursor:
            break
        assert pages < 10

    assert len(seen) == 75
    assert len(set(seen)) == 75
    assert pages == 3


def test_last_page_has_no_cursor(client: TestClient) -> None:
    body = client.get("/api/v1/demo/resources", params={"limit": 100}).json()
    assert len(body["items"]) == 75
    assert body["has_more"] is False
    assert body["next_cursor"] is None


def test_tampered_cursor_is_rejected(client: TestClient) -> None:
    body = client.get("/api/v1/demo/resources", params={"limit": 10}).json()
    cursor = body["next_cursor"]
    forged = cursor[:-2] + ("AA" if not cursor.endswith("AA") else "BB")
    response = client.get("/api/v1/demo/resources", params={"cursor": forged})
    assert response.status_code == 422
    assert response.json()["type"].endswith("/validation-failed")


def test_page_size_limits_are_enforced(client: TestClient) -> None:
    assert client.get("/api/v1/demo/resources", params={"limit": 101}).status_code == 422
    assert client.get("/api/v1/demo/resources", params={"limit": 0}).status_code == 422
