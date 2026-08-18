"""
SQL Query Validation Utilities

Provides validation and sanitization for SQL queries to prevent SQL injection
and ensure queries are safe to execute.

Author: Manufacturing Analytics Team
Date: 2025-11-24
"""

import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)


class SQLValidationError(ValueError):
    """Raised when SQL validation fails."""

    pass


def validate_sql_query(query: str, max_length: int = 10000) -> Tuple[str, bool]:
    """
    Validate and sanitize SQL query.

    Args:
        query: SQL query string to validate
        max_length: Maximum allowed query length

    Returns:
        Tuple of (sanitized_query, is_read_only)

    Raises:
        SQLValidationError: If query is invalid or dangerous
    """
    if not isinstance(query, str):
        raise SQLValidationError("Query must be a string")

    query = query.strip()

    # Check length
    if len(query) > max_length:
        raise SQLValidationError(
            f"Query too long (max {max_length} chars, got {len(query)})"
        )

    if not query:
        raise SQLValidationError("Query cannot be empty")

    # Convert to uppercase for validation (preserve original)
    query_upper = query.upper()

    # Check for dangerous SQL keywords (write operations)
    dangerous_keywords = [
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "EXEC",
        "EXECUTE",
        "GRANT",
        "REVOKE",
        "MERGE",
        "CALL",
        "COPY",
        "UNLOAD",
    ]

    for keyword in dangerous_keywords:
        # Use word boundary to avoid false positives
        pattern = r"\b" + keyword + r"\b"
        if re.search(pattern, query_upper):
            raise SQLValidationError(
                f"Query contains dangerous keyword: {keyword}. Only SELECT queries are allowed."
            )

    # Check for SQL injection patterns
    injection_patterns = [
        r"';",  # SQL injection attempt
        r'";',  # SQL injection attempt
        r"--",  # SQL comment
        r"/\*",  # SQL comment start
        r"\*/",  # SQL comment end
        r"xp_",  # Extended stored procedures (SQL Server)
        r"sp_",  # Stored procedures
        r"EXEC\s*\(",  # Execute function
    ]

    for pattern in injection_patterns:
        if re.search(pattern, query_upper, re.IGNORECASE):
            raise SQLValidationError(
                f"Query contains potentially dangerous pattern: {pattern}"
            )

    # Check if query starts with SELECT or WITH (read-only)
    query_start = query_upper.strip()
    is_read_only = (
        query_start.startswith("SELECT")
        or query_start.startswith("WITH")
        or query_start.startswith("SHOW")
        or query_start.startswith("DESCRIBE")
        or query_start.startswith("DESC")
    )

    if not is_read_only:
        raise SQLValidationError(
            "Query must start with SELEduration, WITH, SHOW, or DESCRIBE. Only read-only queries are allowed."
        )

    # Additional safety: Check for semicolons (potential query chaining)
    if query.count(";") > 1:
        raise SQLValidationError(
            "Query contains multiple semicolons. Query chaining is not allowed."
        )

    return query, is_read_only


def sanitize_sql_identifier(identifier: str) -> str:
    """
    Sanitize SQL identifier (table name, column name, schema name).

    Args:
        identifier: Identifier to sanitize

    Returns:
        Sanitized identifier

    Raises:
        SQLValidationError: If identifier is invalid
    """
    if not isinstance(identifier, str):
        raise SQLValidationError("Identifier must be a string")

    identifier = identifier.strip()

    if not identifier:
        raise SQLValidationError("Identifier cannot be empty")

    if len(identifier) > 128:
        raise SQLValidationError("Identifier too long (max 128 chars)")

    # Only allow alphanumeric, underscores, dots, and hyphens
    if not re.match(r"^[a-zA-Z0-9_.-]+$", identifier):
        raise SQLValidationError(
            "Identifier contains invalid characters. Only letters, numbers, underscores, dots, and hyphens are allowed."
        )

    # Check for SQL keywords that shouldn't be used as identifiers
    sql_keywords = [
        "SELECT",
        "FROM",
        "WHERE",
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "ALTER",
        "CREATE",
        "TABLE",
        "DATABASE",
        "SCHEMA",
    ]

    if identifier.upper() in sql_keywords:
        raise SQLValidationError(f"Cannot use SQL keyword as identifier: {identifier}")

    return identifier


def validate_date_param(value: str) -> str:
    """Validate a date string is strictly YYYY-MM-DD before SQL interpolation.

    Prevents SQL injection in Snowpark queries where bind parameters
    are not supported. After validation, the value is safe to interpolate.

    Args:
        value: Date string to validate.

    Returns:
        The validated date string, unchanged.

    Raises:
        SQLValidationError: If the string is not a valid YYYY-MM-DD date.
    """
    if not isinstance(value, str):
        raise SQLValidationError("Date parameter must be a string")

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise SQLValidationError(
            "Invalid date format: %s. Expected YYYY-MM-DD." % value
        )

    from datetime import datetime as _dt

    try:
        _dt.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise SQLValidationError("Invalid calendar date: %s" % value)

    return value
