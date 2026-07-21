"""Shared Snowflake query helpers and parameter guards for insights tool adapters.

Provides JSON-safe record fetching through the session pool and strict validation of
string/integer parameters before they are interpolated into read-only SQL text.
Keeps every insights adapter free of duplicated query plumbing.
"""

import json
import re
from typing import Any, Dict, List

from services.infrastructure.snowflake.session_pool import get_session_pool

SAFE_PARAM_PATTERN: re.Pattern = re.compile(r"^[A-Za-z0-9_\-\. ]+$")
MAX_PARAM_LENGTH: int = 100


class InvalidToolParameterError(ValueError):
    """Raised when a tool parameter fails validation before query construction."""


def safe_param(value: str, name: str) -> str:
    """Validate a string parameter for safe SQL interpolation.

    Args:
        value: Raw parameter value.
        name: Parameter name for the error message.

    Returns:
        The validated value, stripped.

    Raises:
        InvalidToolParameterError: When the value is empty, too long, or contains
            characters outside [A-Za-z0-9_-. ].
    """
    stripped = str(value).strip()
    if not stripped or len(stripped) > MAX_PARAM_LENGTH:
        raise InvalidToolParameterError("Invalid %s: empty or too long" % name)
    if not SAFE_PARAM_PATTERN.match(stripped):
        raise InvalidToolParameterError("Invalid %s: illegal characters" % name)
    return stripped


def positive_int(value: Any, name: str, maximum: int) -> int:
    """Validate an integer parameter within (0, maximum].

    Args:
        value: Raw value (int-castable).
        name: Parameter name for the error message.
        maximum: Inclusive upper bound.

    Returns:
        The validated integer.

    Raises:
        InvalidToolParameterError: When not castable or out of range.
    """
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidToolParameterError("Invalid %s: not an integer" % name) from exc
    if number <= 0 or number > maximum:
        raise InvalidToolParameterError(
            "Invalid %s: must be between 1 and %d" % (name, maximum)
        )
    return number


def query_records(query: str) -> List[Dict[str, Any]]:
    """Run a read-only query and return JSON-safe row dicts.

    Uses the pandas to_json round trip so NaN/Inf become null and timestamps are
    ISO formatted. Read-only validation is enforced by the session pool.

    Args:
        query: SQL SELECT text.

    Returns:
        List of row dicts (column name -> JSON-safe value).
    """
    pool = get_session_pool()
    df = pool.execute_query(query)
    return json.loads(df.to_json(orient="records", date_format="iso"))
