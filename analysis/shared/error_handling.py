"""
Error Handling Utilities
========================

Provides consistent error handling patterns across all analysis modules.
Includes custom exceptions, retry logic, and error reporting.

Author: Utku Gulbardak
Date: 2025-10-28
"""

import logging
import time
import traceback
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type


# Custom Exception Classes
class AnalysisError(Exception):
    """Base exception for all analysis errors."""


class DataValidationError(AnalysisError):
    """Raised when data validation fails."""


class DataNotFoundError(AnalysisError):
    """Raised when required data is not found."""


class ConfigurationError(AnalysisError):
    """Raised when configuration is invalid or missing."""


class ProcessingError(AnalysisError):
    """Raised during data processing operations."""


class ReportGenerationError(AnalysisError):
    """Raised when report generation fails."""


def retry_on_failure(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    logger: Optional[logging.Logger] = None,
):
    """
    Decorator to retry a function on failure with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        delay: Initial delay between retries in seconds (default: 1.0)
        backoff: Multiplier for delay after each attempt (default: 2.0)
        exceptions: Tuple of exceptions to catch (default: all exceptions)
        logger: Optional logger instance

    Example:
        >>> @retry_on_failure(max_attempts=5, delay=2.0)
        ... def fetch_data():
        ...     return api.get_data()
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            nonlocal logger
            if logger is None:
                logger = logging.getLogger(func.__module__)

            last_exception = None
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(
                            f"❌ {func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise

                    logger.warning(
                        f"⚠️  {func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )

                    time.sleep(current_delay)
                    current_delay *= backoff

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def handle_analysis_error(
    error: Exception,
    context: str,
    logger: Optional[logging.Logger] = None,
    raise_error: bool = True,
) -> dict:
    """
    Standardized error handler for analysis operations.

    Args:
        error: The exception that occurred
        context: Description of what was being attempted
        logger: Optional logger instance
        raise_error: Whether to re-raise the error (default: True)

    Returns:
        dict: Error information dictionary

    Example:
        >>> try:
        ...     process_data()
        ... except Exception as e:
        ...     handle_analysis_error(e, "processing equipment data")
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    error_info = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context,
        "traceback": traceback.format_exc(),
    }

    logger.error(
        f"❌ Error in {context}: {error_info['error_type']} - {error_info['error_message']}"
    )
    logger.debug(f"Traceback:\n{error_info['traceback']}")

    if raise_error:
        raise

    return error_info


def safe_execute(
    func: Callable,
    default_return: Any = None,
    error_message: str = "Operation failed",
    logger: Optional[logging.Logger] = None,
) -> Any:
    """
    Safely execute a function and return a default value on error.

    Args:
        func: Function to execute
        default_return: Value to return on error (default: None)
        error_message: Custom error message
        logger: Optional logger instance

    Returns:
        Function result or default_return on error

    Example:
        >>> result = safe_execute(
        ...     lambda: risky_operation(),
        ...     default_return=[],
        ...     error_message="Failed to fetch data"
        ... )
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        return func()
    except Exception as e:
        logger.error(f"❌ {error_message}: {e}")
        return default_return


def validate_or_raise(
    condition: bool,
    error_message: str,
    error_class: Type[AnalysisError] = AnalysisError,
    logger: Optional[logging.Logger] = None,
):
    """
    Validate a condition and raise an error if it fails.

    Args:
        condition: Condition to validate
        error_message: Error message to display
        error_class: Exception class to raise (default: AnalysisError)
        logger: Optional logger instance

    Raises:
        error_class: If condition is False

    Example:
        >>> validate_or_raise(
        ...     len(df) > 0,
        ...     "DataFrame is empty",
        ...     DataValidationError
        ... )
    """
    if not condition:
        if logger:
            logger.error(f"❌ Validation failed: {error_message}")
        raise error_class(error_message)


def log_and_raise(
    error_class: Type[Exception],
    message: str,
    logger: Optional[logging.Logger] = None,
):
    """
    Log an error message and raise an exception.

    Args:
        error_class: Exception class to raise
        message: Error message
        logger: Optional logger instance

    Raises:
        error_class: Always raises the specified exception

    Example:
        >>> if not valid_config:
        ...     log_and_raise(ConfigurationError, "Invalid configuration")
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    logger.error(f"❌ {message}")
    raise error_class(message)


def graceful_degradation(
    fallback_func: Callable,
    logger: Optional[logging.Logger] = None,
):
    """
    Decorator for graceful degradation - execute fallback on failure.

    Args:
        fallback_func: Function to call if main function fails
        logger: Optional logger instance

    Example:
        >>> def fallback():
        ...     return cached_data()
        >>>
        >>> @graceful_degradation(fallback)
        ... def fetch_fresh_data():
        ...     return api.get_data()
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            nonlocal logger
            if logger is None:
                logger = logging.getLogger(func.__module__)

            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(
                    f"⚠️  {func.__name__} failed: {e}. Using fallback function."
                )
                try:
                    return fallback_func(*args, **kwargs)
                except Exception as fallback_error:
                    logger.error(f"❌ Fallback also failed: {fallback_error}")
                    raise

        return wrapper

    return decorator


# Module metadata
__version__ = "1.0.0"
__author__ = "Utku Gulbardak"
__all__ = [
    # Custom Exceptions
    "AnalysisError",
    "DataValidationError",
    "DataNotFoundError",
    "ConfigurationError",
    "ProcessingError",
    "ReportGenerationError",
    # Error Handling Functions
    "retry_on_failure",
    "handle_analysis_error",
    "safe_execute",
    "validate_or_raise",
    "log_and_raise",
    "graceful_degradation",
]
