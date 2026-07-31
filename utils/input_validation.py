"""
Input Validation & Sanitization Utilities

Provides secure input validation and sanitization to prevent SQL injection
and other security vulnerabilities.

Author: Manufacturing Analytics Team
Date: 2025-11-24
"""

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)


class InputValidationError(ValueError):
    """Raised when input validation fails."""

    pass


def sanitize_sql_string(
    value: str, max_length: int = 200, allow_special: bool = False
) -> str:
    """
    Sanitize string input to prevent SQL injection.

    Args:
        value: Input string to sanitize
        max_length: Maximum allowed length
        allow_special: If True, allows some special characters (for supplier names, etc.)

    Returns:
        Sanitized string

    Raises:
        InputValidationError: If input contains dangerous characters or is too long
    """
    if not isinstance(value, str):
        raise InputValidationError(f"Expected string, got {type(value).__name__}")

    value = value.strip()

    # Check length
    if len(value) > max_length:
        raise InputValidationError(
            f"Input too long (max {max_length} chars, got {len(value)})"
        )

    # Check for empty after strip
    if not value:
        raise InputValidationError("Input cannot be empty")

    # SQL injection dangerous patterns
    dangerous_patterns = [
        r"['\";]",  # Single quote, double quote, semicolon
        r"--",  # SQL comment
        r"/\*",  # SQL comment start
        r"\*/",  # SQL comment end
        r"(?i)(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE)",  # SQL commands
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, value):
            raise InputValidationError(
                f"Input contains potentially dangerous characters: {pattern}"
            )

    # If allow_special is False, only allow alphanumeric, spaces, hyphens, underscores, dots
    if not allow_special:
        if not re.match(r"^[a-zA-Z0-9\s\-_.]+$", value):
            raise InputValidationError(
                "Input contains invalid characters. Only letters, numbers, spaces, hyphens, underscores, and dots are allowed."
            )

    return value


def validate_equipment_code(code: str) -> str:
    """
    Validate and sanitize equipment code.

    Equipment codes can be any format (varchar), but we sanitize to prevent SQL injection.
    No format restrictions - just security validation.

    Args:
        code: Equipment code to validate

    Returns:
        Sanitized equipment code

    Raises:
        InputValidationError: If input contains dangerous characters
    """
    # Sanitize for SQL injection (allow alphanumeric, hyphens, underscores, dots)
    # Increased max_length to 50 to accommodate various formats like "MX-7101"
    code = sanitize_sql_string(code, max_length=50, allow_special=False)

    return code


def validate_date_string(date_str: str) -> str:
    """
    Validate date string format.

    Expected format: YYYY-MM-DD

    Args:
        date_str: Date string to validate

    Returns:
        Validated date string

    Raises:
        InputValidationError: If format is invalid
    """
    date_str = sanitize_sql_string(date_str, max_length=10, allow_special=False)

    # Date format: YYYY-MM-DD
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise InputValidationError(
            f"Invalid date format: {date_str}. Expected format: YYYY-MM-DD"
        )

    # Validate date components
    try:
        year, month, day = map(int, date_str.split("-"))
        if year < 2000 or year > 2100:
            raise InputValidationError(f"Year out of valid range: {year}")
        if month < 1 or month > 12:
            raise InputValidationError(f"Month out of valid range: {month}")
        if day < 1 or day > 31:
            raise InputValidationError(f"Day out of valid range: {day}")
    except ValueError as e:
        raise InputValidationError(f"Invalid date components: {e}")

    return date_str


def validate_supplier_name(supplier: str) -> str:
    """
    Validate supplier name.

    Allows more characters than equipment codes (for company names).

    Args:
        supplier: Supplier name to validate

    Returns:
        Validated supplier name

    Raises:
        InputValidationError: If input is invalid
    """
    # Allow "All" as special case
    if supplier == "All":
        return supplier

    return sanitize_sql_string(supplier, max_length=100, allow_special=True)


def sanitize_list(values: List[str], validator_func, max_items: int = 100) -> List[str]:
    """
    Sanitize a list of string values.

    Args:
        values: List of values to sanitize
        validator_func: Function to validate each value
        max_items: Maximum number of items allowed

    Returns:
        List of sanitized values

    Raises:
        InputValidationError: If validation fails
    """
    if not isinstance(values, list):
        raise InputValidationError(f"Expected list, got {type(values).__name__}")

    if len(values) > max_items:
        raise InputValidationError(
            f"Too many items (max {max_items}, got {len(values)})"
        )

    return [validator_func(value) for value in values]


def validate_analytics_request(
    equipment_codes: Optional[List[str]] = None,
    supplier_names: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """
    Validate common analytics request parameters.

    Args:
        equipment_codes: List of equipment codes
        supplier_names: List of supplier names (optional)
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)

    Returns:
        Dictionary with validated values

    Raises:
        InputValidationError: If validation fails
    """
    validated = {}

    if equipment_codes:
        validated["equipment_codes"] = sanitize_list(
            equipment_codes, validate_equipment_code, max_items=50
        )

    if supplier_names:
        validated["supplier_names"] = sanitize_list(
            supplier_names, validate_supplier_name, max_items=50
        )

    if start_date:
        validated["start_date"] = validate_date_string(start_date)

    if end_date:
        validated["end_date"] = validate_date_string(end_date)

    # Validate date range
    if "start_date" in validated and "end_date" in validated:
        if validated["start_date"] > validated["end_date"]:
            raise InputValidationError(
                f"Start date ({validated['start_date']}) must be before end date ({validated['end_date']})"
            )

    return validated
