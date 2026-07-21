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
    ValidCase(
        METHOD_POST,
        "/ml/detect-anomalies",
        {
            "data": [
                {"cycle_time": 10.1},
                {"cycle_time": 10.3},
                {"cycle_time": 98.7},
                {"cycle_time": 10.0},
            ],
            "columns": ["cycle_time"],
            "method": "zscore",
            "threshold": 3.0,
        },
    ),
    ValidCase(
        METHOD_POST,
        "/ml/forecast",
        {
            "data": [
                {"production": 100},
                {"production": 110},
                {"production": 105},
                {"production": 120},
                {"production": 115},
                {"production": 130},
            ],
            "target_column": "production",
            "periods": 7,
            "frequency": "D",
        },
    ),
    ValidCase(
        METHOD_POST,
        "/ml/predict",
        {
            "data": [
                {"temp": 80, "pressure": 30, "downtime": 0},
                {"temp": 95, "pressure": 45, "downtime": 1},
                {"temp": 85, "pressure": 33, "downtime": 0},
                {"temp": 99, "pressure": 50, "downtime": 1},
            ],
            "target": "downtime",
            "features": ["temp", "pressure"],
        },
    ),
    ValidCase(
        METHOD_POST,
        "/transformation/clean",
        {
            "data": [{"a": 1, "b": 2}, {"a": 1, "b": 2}, {"a": 3, "b": None}],
            "remove_duplicates": True,
            "handle_nulls": "drop",
            "detect_outliers": True,
            "outlier_method": "iqr",
        },
    ),
    ValidCase(
        METHOD_POST,
        "/transformation/validate",
        {
            "data": [{"id": 1, "name": "x"}, {"id": 2, "name": "y"}],
            "required_columns": ["id", "name"],
            "check_nulls": True,
            "check_duplicates": True,
        },
    ),
    ValidCase(
        METHOD_POST,
        "/transformation/transform",
        {
            "data": [
                {"region": "A", "value": 10},
                {"region": "A", "value": 20},
                {"region": "B", "value": 30},
            ],
            "operations": [{"type": "normalize", "params": {"columns": ["value"]}}],
        },
    ),
    ValidCase(
        METHOD_POST,
        "/transformation/pipeline",
        {"data": [{"a": 1}], "pipeline_name": "manufacturing_etl", "config": {}},
    ),
    ValidCase(
        METHOD_POST,
        "/transformation/pipeline",
        {
            "data": [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
            "pipeline_name": "manufacturing_etl",
            "config": {
                "steps": [
                    {
                        "step_type": "transformation",
                        "operation": "select_columns",
                        "parameters": {"columns": ["a"]},
                    }
                ]
            },
        },
    ),
    ValidCase(
        METHOD_POST,
        "/transformation/pipeline",
        {
            "data": [{"a": 1}],
            "pipeline_name": "manufacturing_etl",
            "config": {"steps": [{"step_type": "transformation"}]},
        },
    ),
    ValidCase(
        METHOD_POST,
        "/visualization/bar-chart",
        {
            "data": [{"machine": "A", "output": 120}, {"machine": "B", "output": 95}],
            "x_column": "machine",
            "y_column": "output",
            "title": "Output by Machine",
            "orientation": "v",
        },
    ),
    ValidCase(
        METHOD_POST,
        "/visualization/line-chart",
        {
            "data": [{"t": 1, "v": 10}, {"t": 2, "v": 15}],
            "x_column": "t",
            "y_column": "v",
            "title": "Trend",
        },
    ),
    ValidCase(
        METHOD_POST,
        "/visualization/scatter-plot",
        {
            "data": [{"x": 1, "y": 2}, {"x": 3, "y": 4}],
            "x_column": "x",
            "y_column": "y",
            "title": "Scatter",
        },
    ),
    ValidCase(
        METHOD_POST,
        "/visualization/pie-chart",
        {
            "data": [{"label": "A", "val": 30}, {"label": "B", "val": 70}],
            "labels_column": "label",
            "values_column": "val",
            "title": "Share",
        },
    ),
    ValidCase(
        METHOD_POST,
        "/visualization/dashboard",
        {
            "charts": [
                {
                    "title": "C1",
                    "chart_type": "line",
                    "data": [{"x": 1, "y": 2}],
                    "x_column": "x",
                    "y_column": "y",
                }
            ],
            "layout": "grid",
            "title": "Dashboard",
        },
    ),
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
    ValidCase(METHOD_POST, "/database/query", {"query": "SELECT 1"}),
    ValidCase(METHOD_POST, "/database/tables", {}),
    ValidCase(METHOD_POST, "/database/describe", _table_body()),
    ValidCase(METHOD_POST, "/database/sample", _table_body()),
    ValidCase(METHOD_POST, "/database/stats", _table_body()),
    ValidCase(METHOD_POST, "/audit/query", {}),
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
