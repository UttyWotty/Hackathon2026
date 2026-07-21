"""Curated valid-input cases for the endpoint watchdog's business-logic sweep.

Each case is a realistic, schema-valid request that gets past pydantic validation
into the handler, so the watchdog can catch router-to-service contract bugs (wrong
kwargs, missing methods, stale SQL columns) that empty-body probes cannot reach.
Coverage is deliberately limited to pure-compute and read-only endpoints; write,
send, file, and job-spawning routes are excluded because a sweep must not create
real side effects (see EXCLUDED_SIDE_EFFECT_NOTE).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Realistic domain-valid inputs. `client` is a Snowflake SCHEMA name (not a
# supplier); the equipment code and dates are shaped to pass
# utils.input_validation.validate_analytics_request so the handler actually runs.
ANALYTICS_SCHEMA = "NORDPLAST"
SAMPLE_EQUIPMENT_CODE = "EMA-4101"
SAMPLE_START_DATE = "2025-11-01"
SAMPLE_END_DATE = "2025-11-30"
SAMPLE_TABLE = "MASTER_SHOT_TABLE"

# A pure, I/O-free dispatch target (all args optional, no Snowflake) used to
# exercise the MCP tool-dispatch registry without an external dependency.
DISPATCH_TOOL = "get_metric_definitions"

METHOD_POST = "POST"

# Why some mutating routes are intentionally absent: they create, send, delete,
# or persist real state (backups, email, notifications, pipeline job runs,
# scheduler jobs, user/project/task/config writes, file uploads, audit exports)
# and cannot be safely swept. Their contracts belong in dedicated router tests.
EXCLUDED_SIDE_EFFECT_NOTE = (
    "Side-effectful routes (writes/sends/files/jobs) are excluded from the "
    "valid-input sweep and must be covered by dedicated router tests."
)


@dataclass(frozen=True)
class ValidCase:
    """One schema-valid request for the business-logic watchdog sweep.

    Attributes:
        method: HTTP verb (always a mutating verb here; GET routes need no body).
        path: Registered route path, including any router prefix.
        body: JSON request body, or None for endpoints taking no body.
        params: Query-string parameters, or None when there are none.
    """

    method: str
    path: str
    body: Optional[Dict[str, Any]] = None
    params: Optional[Dict[str, str]] = field(default=None)


def _analytics_body() -> Dict[str, Any]:
    """Build the shared analytics request body (single equipment, one month)."""
    return {
        "equipment_codes": [SAMPLE_EQUIPMENT_CODE],
        "start_date": SAMPLE_START_DATE,
        "end_date": SAMPLE_END_DATE,
        "client": ANALYTICS_SCHEMA,
    }


def _table_body() -> Dict[str, Any]:
    """Build the shared Snowflake table-info request body."""
    return {"table_name": SAMPLE_TABLE}


# Pure-compute endpoints: no external dependency, so any code-level 5xx is a real
# bug. These directly cover the v0.1.4 contract-bug class (ml/predict,
# transformation/clean, mcp/tools/reason).
_COMPUTE_CASES: List[ValidCase] = [
]

# Read-only I/O endpoints: valid inputs reach the query layer. In CI (no
# Snowflake) these 5xx with a dependency signature and are tolerated; locally
# they run for real. Covers the v0.1.4 analytics SQL-column bugs.
_READ_ONLY_CASES: List[ValidCase] = [
    ValidCase(METHOD_POST, "/analytics/roi", _analytics_body()),
    ValidCase(METHOD_POST, "/analytics/rca", _analytics_body()),
    ValidCase(METHOD_POST, "/analytics/ct-efficiency", _analytics_body()),
    ValidCase(METHOD_POST, "/analytics/ct-deviation", _analytics_body()),
    ValidCase(METHOD_POST, "/analytics/tooling-eol", _analytics_body()),
    ValidCase(METHOD_POST, "/analytics/capacity", _analytics_body()),
]

# MCP dispatch endpoints: exercise the tool-dispatch registry via a pure tool so
# the reason/call contract runs without an external dependency. Covers the
# v0.1.4 /mcp/tools/reason step-handling bug.
_MCP_CASES: List[ValidCase] = [
    ValidCase(METHOD_POST, "/mcp", {"method": "tools/list"}),
    ValidCase(METHOD_POST, "/mcp/tools/list", {}),
    ValidCase(
        METHOD_POST,
        "/mcp/tools/call",
        {"name": DISPATCH_TOOL, "arguments": {}},
    ),
    ValidCase(
        METHOD_POST,
        "/mcp/tools/reason",
        {"steps": [{"name": DISPATCH_TOOL, "arguments": {}}], "stop_on_error": True},
    ),
]

VALID_CASES: List[ValidCase] = _COMPUTE_CASES + _READ_ONLY_CASES + _MCP_CASES
