"""
Standardized Error Handling for API Endpoints.

Provides consistent error handling patterns across all routers with specific
exception type mapping to appropriate HTTP status codes.
This module eliminates broad `except Exception` blocks throughout the codebase.
"""

import logging
from functools import wraps
from typing import Any, Callable, Dict, Type, TypeVar

from fastapi import HTTPException  # type: ignore[import-untyped]

from utils.error_handling import sanitize_error_message

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Exception to HTTP status code mapping
# Order matters: more specific exceptions must come before their parent classes
# In Python 3, FileNotFoundError, PermissionError, ConnectionError, TimeoutError
# are all subclasses of OSError, so they must be checked first
EXCEPTION_STATUS_MAP: Dict[Type[Exception], int] = {
    FileNotFoundError: 404,  # Not Found (subclass of OSError)
    PermissionError: 403,  # Forbidden (subclass of OSError)
    TimeoutError: 504,  # Gateway Timeout (subclass of OSError)
    ConnectionError: 503,  # Service Unavailable (subclass of OSError)
    OSError: 503,  # Service Unavailable - catch-all for other OS errors
    ValueError: 400,  # Bad Request - invalid input
    KeyError: 400,  # Bad Request - missing required field
    TypeError: 400,  # Bad Request - wrong type
}

# Exception type to user-friendly message mapping
EXCEPTION_MESSAGE_MAP: Dict[Type[Exception], str] = {
    ValueError: "Invalid input provided",
    KeyError: "Required field is missing",
    TypeError: "Invalid data type",
    FileNotFoundError: "Requested resource not found",
    PermissionError: "Access denied",
    TimeoutError: "Operation timed out",
    ConnectionError: "Service temporarily unavailable",
    OSError: "System error occurred",
}


def get_exception_status_code(exc: Exception) -> int:
    """
    Get HTTP status code for an exception type.

    Checks the exception type against the mapping, including parent classes.

    Args:
        exc: Exception instance

    Returns:
        HTTP status code (default: 500)
    """
    for exc_type, status_code in EXCEPTION_STATUS_MAP.items():
        if isinstance(exc, exc_type):
            return status_code
    return 500


def get_exception_message(exc: Exception, default_message: str) -> str:
    """
    Get user-friendly message for an exception type.

    Args:
        exc: Exception instance
        default_message: Fallback message if no mapping exists

    Returns:
        User-friendly error message
    """
    for exc_type, message in EXCEPTION_MESSAGE_MAP.items():
        if isinstance(exc, exc_type):
            return message
    return default_message


def handle_errors(
    default_message: str = "An internal error occurred",
    status_code: int = 500,
    log_error: bool = True,
):
    """
    Decorator to standardize error handling across API endpoints.

    Handles specific exception types with appropriate HTTP status codes:
    - ValueError, KeyError, TypeError -> 400 Bad Request
    - FileNotFoundError -> 404 Not Found
    - PermissionError -> 403 Forbidden
    - TimeoutError -> 504 Gateway Timeout
    - ConnectionError, OSError -> 503 Service Unavailable
    - Other exceptions -> 500 Internal Server Error (or custom status_code)

    Usage:
        @router.post("/endpoint")
        @handle_errors(default_message="Failed to process request")
        async def my_endpoint(request: RequestModel):
            # Your endpoint logic
            return result

    Args:
        default_message: Default error message for production
        status_code: Fallback HTTP status code for unknown exceptions (default: 500)
        log_error: Whether to log the error (default: True)

    Returns:
        Decorated function with standardized error handling
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # Re-raise HTTPExceptions as-is (they're already standardized)
                raise
            except Exception as e:
                # Get appropriate status code and message for this exception type
                exc_status = get_exception_status_code(e)
                exc_message = get_exception_message(e, default_message)

                # Use custom status_code only for unknown exceptions (500)
                final_status = exc_status if exc_status != 500 else status_code

                # Log with appropriate level based on status code
                if log_error:
                    _log_exception(func.__name__, e, exc_status)

                # Sanitize and raise
                error_msg = sanitize_error_message(e, exc_message)
                raise HTTPException(status_code=final_status, detail=error_msg)

        return wrapper

    return decorator


def _log_exception(func_name: str, exc: Exception, status_code: int) -> None:
    """Log exception with appropriate level based on status code."""
    if status_code < 500:
        # Client errors - warning level, no traceback
        logger.warning(f"Client error in {func_name}: {exc}")
    else:
        # Server errors - error level with traceback
        logger.error(f"Error in {func_name}: {exc}", exc_info=True)


def handle_validation_errors(func: F) -> F:
    """
    Decorator specifically for validation errors (400 status code).

    Usage:
        @router.post("/endpoint")
        @handle_validation_errors
        async def my_endpoint(request: RequestModel):
            # Your endpoint logic
            return result
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation error in {func.__name__}: {e}")
            raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            error_msg = sanitize_error_message(
                e, "Invalid request. Please check your input."
            )
            raise HTTPException(status_code=400, detail=error_msg)

    return wrapper


def handle_database_errors(func: F) -> F:
    """
    Decorator for database operations with specific error handling.

    Handles common database exceptions and maps them to appropriate HTTP codes.

    Usage:
        @router.get("/data")
        @handle_database_errors
        async def get_data():
            # Database operations
            return result
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as e:
            # Use the same mapping logic for consistency
            exc_status = get_exception_status_code(e)
            _log_exception(func.__name__, e, exc_status)

            # Map to database-specific messages
            if isinstance(e, (ConnectionError, TimeoutError)):
                raise HTTPException(
                    status_code=503, detail="Database temporarily unavailable"
                )
            if isinstance(e, PermissionError):
                raise HTTPException(status_code=403, detail="Database access denied")
            if isinstance(e, ValueError):
                raise HTTPException(status_code=400, detail=f"Invalid query: {str(e)}")

            error_msg = sanitize_error_message(e, "Database operation failed")
            raise HTTPException(status_code=500, detail=error_msg)

    return wrapper
