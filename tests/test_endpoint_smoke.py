"""Endpoint watchdog: exercise every registered route and flag code-level 5xx.

Enumerates all routes from the live FastAPI app, calls each in-process (GET
directly, mutating routes with an empty body, destructive routes skipped), and
fails only on 5xx responses whose body reveals an application bug -- so it stays
green when Snowflake, Redis, or the MLX server are absent (as in CI) while still
catching regressions of the error-handling classes fixed in v0.1.1. A second
sweep drives a curated set of schema-valid requests (tests.endpoint_smoke_cases)
past validation into the handlers, catching the router-to-service contract bugs
fixed in v0.1.4 that empty-body probes cannot reach.
"""

from typing import Iterator, List, Optional, Tuple

import pytest  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
from httpx import Response

from tests.endpoint_smoke_cases import VALID_CASES, ValidCase

# Routes that create/send/delete real state; never called by the watchdog.
DESTRUCTIVE_DENYLIST = {
    "/backup/create",
    "/backup/restore",
    "/backup/delete/{backup_id}",
    "/cache/clear",
    "/documents/upload",
    "/email/send",
    "/email/send-template",
    "/email/analytics-result",
    "/notifications/webhook",
    "/pipelines/ana-shot-made/run",
    "/pipelines/master-shot-table/run",
    "/pipelines/roi/run",
    "/pipelines/run-all",
    "/pipelines/run-rate/run",
    "/analytics/runrate",
    "/visualization/create",
}

STATIC_PREFIXES = ("/static",)
PATH_PARAM_VALUE = "1"
RATE_LIMITER_CLASS = "RateLimitMiddleware"
MAX_MIDDLEWARE_DEPTH = 50

# Tokens in a 5xx body that indicate an uncaught application error (a real bug),
# not an unavailable external dependency.
CODE_ERROR_SIGNATURES = (
    "valueerror",
    "keyerror",
    "attributeerror",
    "typeerror",
    "nameerror",
    "indexerror",
    "unboundlocalerror",
    "no such column",
    "traceback (most recent call last)",
    "is not subscriptable",
    "object is not iterable",
    "unhashable",
    "positional argument",
    "unexpected keyword argument",
)

# Tokens that mark a 5xx as an unavailable dependency, which is tolerated because
# CI runs without Snowflake, Redis, or the local LLM server.
DEPENDENCY_SIGNATURES = (
    "snowflake",
    "snowpark",
    "250001",
    "errno 61",
    "connection refused",
    "could not connect",
    "redis",
    "mlx",
    "8081",
    "private key",
    "failed to get llm",
    "plotly",
    "kaleido",
)


def _enumerate_routes(app: object) -> List[Tuple[str, str]]:
    """Return (method, path) for every non-static API route on the app."""
    routes: List[Tuple[str, str]] = []
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if not path or not methods or path.startswith(STATIC_PREFIXES):
            continue
        for method in methods:
            if method not in ("HEAD", "OPTIONS"):
                routes.append((method, path))
    return sorted(set(routes))


def _fill_path(path: str) -> str:
    """Substitute a dummy value for every path parameter placeholder."""
    parts = []
    for segment in path.split("/"):
        parts.append(PATH_PARAM_VALUE if segment.startswith("{") else segment)
    return "/".join(parts)


def _find_rate_limiter(app: object) -> Optional[object]:
    """Locate the live RateLimitMiddleware instance in the built ASGI stack."""
    if getattr(app, "middleware_stack", None) is None:
        app.middleware_stack = app.build_middleware_stack()  # type: ignore[attr-defined]
    node = app.middleware_stack  # type: ignore[attr-defined]
    for _ in range(MAX_MIDDLEWARE_DEPTH):
        if node.__class__.__name__ == RATE_LIMITER_CLASS:
            return node
        node = getattr(node, "app", None)
        if node is None:
            break
    return None


def _is_code_level_failure(status: int, body: str) -> bool:
    """True only for a 5xx whose body reveals a bug, not a missing dependency."""
    if status < 500:
        return False
    lowered = body.lower()
    if any(token in lowered for token in DEPENDENCY_SIGNATURES):
        return False
    return any(token in lowered for token in CODE_ERROR_SIGNATURES)


def _call(client: TestClient, method: str, url: str) -> Response:
    """Issue one request; mutating verbs get an empty JSON body."""
    if method == "GET":
        return client.get(url)
    return client.request(method, url, json={})


def _call_case(client: TestClient, case: ValidCase) -> Response:
    """Issue one curated valid-input request with its body and query params."""
    return client.request(
        case.method,
        _fill_path(case.path),
        json=case.body,
        params=case.params,
    )


@pytest.fixture()
def smoke_client() -> Iterator[TestClient]:
    """TestClient with rate limiting off so a full sweep is not throttled.

    Toggles the live middleware instance rather than the env so the change is
    scoped to this fixture, and returns 5xx as responses (not raised) so every
    route can be classified.
    """
    from main import app

    limiter = _find_rate_limiter(app)
    previous = getattr(limiter, "enabled", None)
    if limiter is not None:
        limiter.enabled = False
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()
        if limiter is not None and previous is not None:
            limiter.enabled = previous


def test_no_endpoint_returns_code_level_5xx(smoke_client: TestClient) -> None:
    """Every route responds without an uncaught application error."""
    failures: List[str] = []
    for method, path in _enumerate_routes(smoke_client.app):
        if path in DESTRUCTIVE_DENYLIST:
            continue
        response = _call(smoke_client, method, _fill_path(path))
        if _is_code_level_failure(response.status_code, response.text):
            failures.append(
                "%s %s -> %d: %s"
                % (method, path, response.status_code, response.text[:160])
            )
    assert not failures, "Endpoints raised code-level 5xx:\n" + "\n".join(failures)


@pytest.mark.parametrize(
    "case", VALID_CASES, ids=[f"{c.method} {c.path}" for c in VALID_CASES]
)
def test_valid_input_reaches_handler_without_code_5xx(
    smoke_client: TestClient, case: ValidCase
) -> None:
    """Schema-valid input runs the handler without an uncaught application error.

    Unlike the empty-body sweep (which 422s before mutating handlers run), each
    case passes validation and exercises the router-to-service call. A dependency
    5xx (Snowflake/Plotly absent in CI) is tolerated; only a code-level 5xx --
    the v0.1.4 contract-bug class -- fails the test.
    """
    response = _call_case(smoke_client, case)
    assert not _is_code_level_failure(
        response.status_code, response.text
    ), "%s %s -> %d: %s" % (
        case.method,
        case.path,
        response.status_code,
        response.text[:200],
    )


@pytest.mark.parametrize("term", ["run-rate", "ct-deviation", "tooling-eol"])
@pytest.mark.parametrize("endpoint", ["/notes/search", "/documents/search"])
def test_search_survives_hyphenated_terms(
    smoke_client: TestClient, endpoint: str, term: str
) -> None:
    """FTS search must not crash on hyphenated domain terms (v0.1.1 regression)."""
    response = smoke_client.get(endpoint, params={"q": term})
    assert response.status_code == 200, response.text


def test_note_is_searchable_after_create(smoke_client: TestClient) -> None:
    """A created note is found via search, proving the FTS sync trigger works."""
    token = "zzql-uniquetoken-smoke"
    created = smoke_client.post(
        "/notes/",
        json={"title": "Smoke Test Note", "content": "contains %s here" % token},
    )
    assert created.status_code == 200, created.text
    found = smoke_client.get("/notes/search", params={"q": token})
    assert found.status_code == 200, found.text
    assert found.json()["count"] >= 1, found.text


def test_audit_export_rejects_invalid_date_with_400(smoke_client: TestClient) -> None:
    """A malformed date is client error (400), not a server crash (500)."""
    response = smoke_client.post(
        "/audit/export",
        json={
            "start_date": "not-a-date",
            "end_date": "not-a-date",
            "format": "csv",
            "output_path": "output/smoke_audit_export.csv",
        },
    )
    assert response.status_code == 400, response.text


def test_chart_rejects_unknown_column_with_400(smoke_client: TestClient) -> None:
    """An axis that is not a data column is client error (400), not a 500."""
    response = smoke_client.post(
        "/visualization/bar-chart",
        json={
            "data": [{"month": "Jan", "sales": 10}],
            "x_column": "nonexistent",
            "y_column": "sales",
            "title": "Smoke",
        },
    )
    assert response.status_code == 400, response.text
