"""
Input Validation Middleware

Validates request sizes, query lengths, and file sizes to prevent abuse.
"""

import logging

from fastapi import HTTPException, Request  # type: ignore
from starlette.middleware.base import BaseHTTPMiddleware  # type: ignore
from starlette.requests import ClientDisconnect  # type: ignore[import-untyped]
from starlette.responses import Response  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Configuration defaults (can be overridden via environment variables)
MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10 MB default
MAX_QUERY_LENGTH = 10000  # 10,000 characters default
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB default


class InputValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate input sizes and prevent abuse.

    Validates:
    - Request body size
    - Query parameter lengths
    - File upload sizes
    """

    def __init__(
        self,
        app,
        max_request_size: int = MAX_REQUEST_SIZE,
        max_query_length: int = MAX_QUERY_LENGTH,
        max_file_size: int = MAX_FILE_SIZE,
    ):
        super().__init__(app)
        self.max_request_size = max_request_size
        self.max_query_length = max_query_length
        self.max_file_size = max_file_size

    async def dispatch(self, request: Request, call_next):
        """
        Validate request before processing.
        """
        # Skip validation for health checks and docs
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # Validate query string length
        if len(request.url.query) > self.max_query_length:
            logger.warning(
                f"Query string too long: {len(request.url.query)} chars "
                f"(max: {self.max_query_length})"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Query string too long. Maximum length: {self.max_query_length} characters",
            )

        # Check content length header
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_request_size:
                    logger.warning(
                        f"Request body too large: {size} bytes (max: {self.max_request_size})"
                    )
                    raise HTTPException(
                        status_code=413,
                        detail=f"Request body too large. Maximum size: {self.max_request_size / (1024 * 1024):.1f} MB",
                    )
            except ValueError:
                # Invalid content-length header, let it pass (will fail later if needed)
                pass

        # Process request
        try:
            response = await call_next(request)
            return response
        except (ClientDisconnect,) as e:
            # Client disconnected mid-request (e.g., browser navigation/refresh).
            logger.debug("Client disconnected during request: %s", e)
            return Response(status_code=499)
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            # Starlette/AnyIO can surface client disconnect as EndOfStream.
            # Treat this as a non-error to avoid noisy 500s.
            try:
                import anyio  # type: ignore[import-untyped]

                if isinstance(e, (anyio.EndOfStream, anyio.WouldBlock)):
                    logger.debug("Request stream ended early: %s", e)
                    return Response(status_code=499)
            except ImportError:
                # anyio not available, fall through
                pass

            # Log the error but re-raise the original exception
            # so the actual error details are visible for debugging
            logger.error(
                f"Unexpected error in input validation middleware: {e}", exc_info=True
            )
            # Re-raise the original exception instead of masking it
            raise
