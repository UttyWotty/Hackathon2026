"""Provides consistent error handling and message sanitization across the manufacturing API.
Sanitizes exception messages based on environment, hiding internal details in production while exposing them in development.
Includes utility functions for API configuration such as base URL resolution from environment variables.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Get environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")


def sanitize_error_message(
    error: Exception, default_message: str = "An internal error occurred"
) -> str:
    """
    Sanitize error message based on environment.

    In production, hides internal error details.
    In development, shows full error details.

    Args:
        error: Exception object
        default_message: Default message to show in production

    Returns:
        Sanitized error message
    """
    if ENVIRONMENT == "production":
        # Include error type for debugging but hide message details
        error_type = type(error).__name__
        return f"{default_message} ({error_type})"
    else:
        # Show full error in development
        error_type = type(error).__name__
        return f"{error_type}: {error}"


def get_api_base_url() -> str:
    """
    Get API base URL from environment variable.

    Falls back to localhost:3020 if not set.

    Returns:
        API base URL string
    """
    return os.getenv("API_BASE_URL", "http://localhost:3020")
