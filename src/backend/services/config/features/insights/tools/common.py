"""Shared Snowflake query helpers and parameter guards for insights tool adapters.

Provides JSON-safe record fetching through the session pool (or local CSV fallback)
and strict validation of string/integer parameters before they are interpolated into
read-only SQL text. Keeps every insights adapter free of duplicated query plumbing.
"""

import json
import re
import sqlite3
from collections import Counter
from typing import Any, Dict, List

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


def _translate_snowflake_sql(sql: str) -> str:
    """Translate Snowflake-specific SQL functions to SQLite equivalents.

    Handles DATEDIFF, DATEADD, CURRENT_TIMESTAMP(), CURRENT_DATE(), and ILIKE.

    Args:
        sql: Snowflake SQL text.

    Returns:
        SQLite-compatible SQL text.
    """
    translated = sql

    # CURRENT_TIMESTAMP() -> datetime('now')
    translated = re.sub(
        r"CURRENT_TIMESTAMP\(\)", "datetime('now')", translated, flags=re.IGNORECASE
    )
    # CURRENT_DATE() -> date('now')
    translated = re.sub(
        r"CURRENT_DATE\(\)", "date('now')", translated, flags=re.IGNORECASE
    )

    # DATEDIFF('hour', col, datetime('now')) -> (julianday(datetime('now')) - julianday(col)) * 24
    translated = re.sub(
        r"DATEDIFF\(\s*'hour'\s*,\s*(.+?)\s*,\s*(.+?)\s*\)",
        r"((julianday(\2) - julianday(\1)) * 24)",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"DATEDIFF\(\s*'day'\s*,\s*(.+?)\s*,\s*(.+?)\s*\)",
        r"(julianday(\2) - julianday(\1))",
        translated,
        flags=re.IGNORECASE,
    )

    # DATEADD(day, -N, datetime('now')) -> datetime('now', '-N days')
    translated = re.sub(
        r"DATEADD\(\s*day\s*,\s*(-?\d+)\s*,\s*(.+?)\s*\)",
        lambda m: f"datetime({m.group(2)}, '{m.group(1)} days')",
        translated,
        flags=re.IGNORECASE,
    )

    # ILIKE -> LIKE (SQLite LIKE is case-insensitive for ASCII)
    translated = re.sub(r"\bILIKE\b", "LIKE", translated, flags=re.IGNORECASE)

    # ::TIMESTAMP / ::DATE / ::VARCHAR casts -> remove (SQLite has no cast syntax)
    translated = re.sub(
        r"::(TIMESTAMP|DATE|VARCHAR|STRING|NUMBER|INT)",
        "",
        translated,
        flags=re.IGNORECASE,
    )

    # NULLS LAST / NULLS FIRST -> remove (SQLite default is NULLS LAST)
    translated = re.sub(
        r"\bNULLS\s+(LAST|FIRST)\b", "", translated, flags=re.IGNORECASE
    )

    return translated


class _ModeAggregate:
    """SQLite custom aggregate implementing Snowflake MODE (statistical mode)."""

    def __init__(self) -> None:
        self.values: List[Any] = []

    def step(self, value: Any) -> None:
        if value is not None:
            self.values.append(value)

    def finalize(self) -> Any:
        if not self.values:
            return None
        counter = Counter(self.values)
        return counter.most_common(1)[0][0]


def _register_mode_aggregate(conn: sqlite3.Connection) -> None:
    """Register the MODE aggregate function on a SQLite connection."""
    conn.create_aggregate("MODE", 1, _ModeAggregate)


def _query_records_local(query: str) -> List[Dict[str, Any]]:
    """Run a read-only query against the local CSV via in-memory SQLite.

    Loads SHOT_DATA (and MOLD/WORK_ORDER if referenced) into SQLite,
    translates Snowflake SQL to SQLite, and returns JSON-safe row dicts.

    Args:
        query: SQL SELECT text (Snowflake dialect).

    Returns:
        List of row dicts (column name -> JSON-safe value).
    """
    from analysis.shared.local_source import (
        load_mold_csv,
        load_shot_data,
        load_work_order_csv,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _register_mode_aggregate(conn)

    # Load tables referenced in the query
    query_upper = query.upper()
    if "SHOT_DATA" in query_upper:
        df = load_shot_data()
        df.to_sql("SHOT_DATA", conn, if_exists="replace", index=False)
    if "MOLD_MAINTENANCE" in query_upper:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS MOLD_MAINTENANCE ("
            "ID INTEGER, TOOL_ID INTEGER, MAINTENANCE_STATUS TEXT, "
            "MAINTENANCED_AT TEXT, START_TIME TEXT, END_TIME TEXT, "
            "SHOT_COUNT INTEGER, ACCUMULATED_SHOT INTEGER, "
            "WORK_ORDER_ID INTEGER, MAINTENANCE_BY TEXT)"
        )
    if "MOLD_LOCATION" in query_upper:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS MOLD_LOCATION ("
            "TOOL_ID INTEGER, RELOCATION_TYPE TEXT, LOCATION_ID INTEGER, "
            "PREVIOUS_LOCATION_ID INTEGER, MOLD_LOCATION_STATUS TEXT, "
            "CONFIRMED_AT TEXT, CREATED_AT TEXT, LATEST INTEGER)"
        )
    if (
        "TOOL" in query_upper
        and "MOLD_MAINTENANCE" not in query_upper
        and "MOLD_LOCATION" not in query_upper
    ):
        mold = load_mold_csv()
        mold.to_sql("TOOL", conn, if_exists="replace", index=False)
    elif re.search(r"\bFROM\s+MOLD\b", query_upper) or re.search(
        r"\bJOIN\s+MOLD\b", query_upper
    ):
        mold = load_mold_csv()
        mold.to_sql("TOOL", conn, if_exists="replace", index=False)
    if "WORK_ORDER" in query_upper:
        wo = load_work_order_csv()
        wo.to_sql("WORK_ORDER", conn, if_exists="replace", index=False)

    # Translate and execute
    translated = _translate_snowflake_sql(query)
    try:
        cursor = conn.execute(translated)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()

    return rows


def query_records(query: str) -> List[Dict[str, Any]]:
    """Run a read-only query and return JSON-safe row dicts.

    Uses the Snowflake session pool in production, or an in-memory SQLite
    fallback when LOCAL_DATA_DIR is set.

    Args:
        query: SQL SELECT text.

    Returns:
        List of row dicts (column name -> JSON-safe value).
    """
    from analysis.shared.local_source import is_local_data_enabled

    if is_local_data_enabled():
        return _query_records_local(query)

    from services.infrastructure.snowflake.session_pool import get_session_pool

    pool = get_session_pool()
    df = pool.execute_query(query)
    return json.loads(df.to_json(orient="records", date_format="iso"))
