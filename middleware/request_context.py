"""
Request context middleware with per-request context variables.
Stores request_id, method, path, and user_id in contextvars so logs can
be correlated across the codebase. Adds X-Request-ID response header.
This is intentionally lightweight and safe to run in all environments.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware  # type: ignore[import-untyped]
from starlette.requests import Request  # type: ignore[import-untyped]
from starlette.responses import Response  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Per-request context variables (formerly in app/request_context.py)
# ---------------------------------------------------------------------------
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
request_method_var: ContextVar[str] = ContextVar("request_method", default="-")
request_path_var: ContextVar[str] = ContextVar("request_path", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")


def set_request_context(
    *,
    request_id: str,
    method: str,
    path: str,
    user_id: Optional[str] = None,
) -> None:
    """
    Set the request context for the current execution context.

    Args:
        request_id: Request id (UUID string).
        method: HTTP method.
        path: Request path.
        user_id: Optional user identifier.
    """
    request_id_var.set(request_id or "-")
    request_method_var.set(method or "-")
    request_path_var.set(path or "-")
    user_id_var.set(user_id or "-")


def clear_request_context() -> None:
    """Reset request context variables to defaults."""
    request_id_var.set("-")
    request_method_var.set("-")
    request_path_var.set("-")
    user_id_var.set("-")


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request context (request_id, path, method, user_id) to contextvars."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        user_id: Optional[str] = request.headers.get("X-User-Id")

        set_request_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            user_id=user_id,
        )

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            clear_request_context()
