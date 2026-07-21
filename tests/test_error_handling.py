"""
Tests for error handling utilities.

Tests standardized error handling patterns including:
- Error sanitization
- Error decorators
- HTTP exception handling
"""

from unittest.mock import patch

import pytest  # type: ignore[import-untyped]
from fastapi import HTTPException  # type: ignore[import-untyped]

from utils.error_handling import sanitize_error_message
from utils.standardized_errors import handle_errors, handle_validation_errors


def test_sanitize_error_message_production():
    """Test error sanitization in production mode."""
    with patch("utils.error_handling.ENVIRONMENT", "production"):
        error = ValueError("Internal database error: connection failed")
        sanitized = sanitize_error_message(error, "An internal error occurred")

        # In production, should return default message with error type but hide details
        assert sanitized == "An internal error occurred (ValueError)"
        assert "database" not in sanitized.lower()
        assert "connection" not in sanitized.lower()


def test_sanitize_error_message_development():
    """Test error sanitization in development mode."""
    with patch("utils.error_handling.ENVIRONMENT", "development"):
        error = ValueError("Internal database error: connection failed")
        sanitized = sanitize_error_message(error, "An internal error occurred")

        # In development, should return full error message
        assert "database" in sanitized.lower()
        assert "connection" in sanitized.lower()


@pytest.mark.asyncio
async def test_handle_errors_decorator_success():
    """Test handle_errors decorator with successful execution."""

    @handle_errors(default_message="Operation failed")
    async def successful_function():
        return {"status": "success"}

    result = await successful_function()
    assert result == {"status": "success"}


@pytest.mark.asyncio
async def test_handle_errors_decorator_exception():
    """Test handle_errors decorator with exception."""

    @handle_errors(default_message="Operation failed", status_code=500)
    async def failing_function():
        raise ValueError("Test error")

    with pytest.raises(HTTPException) as exc_info:
        await failing_function()

    # ValueError maps to 400 via EXCEPTION_STATUS_MAP in standardized_errors
    assert exc_info.value.status_code == 400
    assert (
        "Invalid input provided" in exc_info.value.detail
        or "Test error" in exc_info.value.detail
    )


@pytest.mark.asyncio
async def test_handle_errors_decorator_http_exception():
    """Test that HTTPException is re-raised as-is."""

    @handle_errors(default_message="Operation failed")
    async def http_exception_function():
        raise HTTPException(status_code=404, detail="Not found")

    with pytest.raises(HTTPException) as exc_info:
        await http_exception_function()

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Not found"


@pytest.mark.asyncio
async def test_handle_validation_errors_decorator():
    """Test handle_validation_errors decorator."""

    @handle_validation_errors
    async def validation_function(value: int):
        if value < 0:
            raise ValueError("Value must be positive")
        return {"value": value}

    # Valid input
    result = await validation_function(5)
    assert result == {"value": 5}

    # Invalid input
    with pytest.raises(HTTPException) as exc_info:
        await validation_function(-1)

    assert exc_info.value.status_code == 400
    assert (
        "validation" in exc_info.value.detail.lower()
        or "positive" in exc_info.value.detail.lower()
    )
