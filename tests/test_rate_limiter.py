"""Regression tests for the rate-limiting middleware.

Builds a minimal app around RateLimitMiddleware and asserts the v0.1.1 contract:
an over-limit write returns a real 429 with a Retry-After header (never a 500
from raising inside the middleware), read-only requests are never throttled, and
the limiter is a no-op when disabled.
"""

from typing import Iterator

import pytest  # type: ignore[import-untyped]
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.rate_limiter import RateLimitMiddleware

WRITE_LIMIT = "3/minute"


def _build_client(limit: str) -> Iterator[TestClient]:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, default_limit=limit)

    @app.get("/read")
    def read() -> dict:
        return {"ok": True}

    @app.post("/write")
    def write() -> dict:
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_write_over_limit_returns_429_not_500(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    client = next(_build_client(WRITE_LIMIT))
    codes = [client.post("/write").status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429

    throttled = client.post("/write")
    assert throttled.status_code == 429
    assert "retry-after" in {key.lower() for key in throttled.headers}
    assert throttled.json()["error"] == "Rate limit exceeded"


def test_reads_are_never_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    client = next(_build_client(WRITE_LIMIT))
    codes = [client.get("/read").status_code for _ in range(10)]
    assert codes == [200] * 10


def test_disabled_limiter_allows_all_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    client = next(_build_client("1/minute"))
    codes = [client.post("/write").status_code for _ in range(5)]
    assert codes == [200] * 5
