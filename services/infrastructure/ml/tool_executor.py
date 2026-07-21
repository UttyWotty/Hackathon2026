"""
Chat-integrated tool executor for running real manufacturing analyses.

Extracts parameters from natural language messages and dispatches to actual
analysis tools (Snowflake-connected) via the tool dispatcher.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Analysis tool mapping: keyword -> tool name
ANALYSIS_TOOLS = {
    "runrate": "run_runrate_analysis",
    "run_rate": "run_runrate_analysis",
    "run rate": "run_runrate_analysis",
    "roi": "run_roi_analysis",
    "return on investment": "run_roi_analysis",
    "rca": "run_rca_analysis",
    "root cause": "run_rca_analysis",
    "ct efficiency": "run_ct_efficiency_analysis",
    "cycle time efficiency": "run_ct_efficiency_analysis",
    "ct deviation": "run_ct_deviation_analysis",
    "cycle time deviation": "run_ct_deviation_analysis",
    "tooling eol": "run_tooling_eol_analysis",
    "end of life": "run_tooling_eol_analysis",
    "tool life": "run_tooling_eol_analysis",
    "capacity": "run_capacity_analysis",
    "oee": "run_capacity_analysis",
}

# Keywords that signal "run the actual analysis" vs "tell me about it"
RUN_KEYWORDS = [
    "run",
    "execute",
    "perform",
    "start",
    "do",
    "launch",
    "calculate",
    "compute",
    "generate",
    "create",
    "pull",
    "get me",
    "show me the",
    "can you run",
    "please run",
    "analyze",
    "analyse",
]

# Common equipment code patterns (e.g., EMA-4104, EMA-4102)
EQUIPMENT_PATTERN = re.compile(
    r"\b(\d{4}-\d{2}|\d[A-Z]{2}\d{2}-\d{4,5}|[A-Z]{2,4}-?\d{3,6})\b",
    re.IGNORECASE,
)

# Date patterns
MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# Client/schema keywords
CLIENT_KEYWORDS = {
    "vantis": "VANTIS",
    "vantis industries": "VANTIS",
    "nordplast": "NORDPLAST",
    "nordplast": "NORDPLAST",
    "aurelia": "AURELIA",
    "meridian": "MERIDIAN",
    "arcweld": "ARCWELD",
    "caldera": "CALDERA",
}


def is_analysis_request(message: str) -> bool:
    """Check if message is requesting to run a real analysis."""
    msg_lower = message.lower()

    # Must mention an analysis type
    has_analysis_type = any(kw in msg_lower for kw in ANALYSIS_TOOLS)
    if not has_analysis_type:
        return False

    # Must have a run keyword OR specific parameters (equipment, dates)
    has_run_keyword = any(kw in msg_lower for kw in RUN_KEYWORDS)
    has_equipment = bool(EQUIPMENT_PATTERN.search(message))
    has_date = _extract_date_range(message) != (None, None)

    return has_run_keyword or has_equipment or has_date


def detect_analysis_type(message: str) -> Optional[str]:
    """Detect which analysis tool to run from the message."""
    msg_lower = message.lower()

    # Check longest keywords first to avoid partial matches
    sorted_keywords = sorted(ANALYSIS_TOOLS.keys(), key=len, reverse=True)
    for keyword in sorted_keywords:
        if keyword in msg_lower:
            return ANALYSIS_TOOLS[keyword]

    return None


def extract_equipment_codes(message: str) -> List[str]:
    """Extract equipment codes from message."""
    matches = EQUIPMENT_PATTERN.findall(message)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for m in matches:
        if m.upper() not in seen:
            seen.add(m.upper())
            result.append(m.upper())
    return result


def _extract_date_range(message: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract date range from natural language message."""
    msg_lower = message.lower()

    # Pattern: "for january 2026" or "in january 2026"
    month_year = re.search(
        r"(?:for|in|during|of)\s+(\w+)\s+(\d{4})",
        msg_lower,
    )
    if month_year:
        month_name = month_year.group(1)
        year = int(month_year.group(2))
        month_num = MONTH_NAMES.get(month_name)
        if month_num:
            start = f"{year}-{month_num:02d}-01"
            # Last day of month
            if month_num == 12:
                end = f"{year}-12-31"
            else:
                next_month = datetime(year, month_num + 1, 1)
                last_day = next_month - timedelta(days=1)
                end = last_day.strftime("%Y-%m-%d")
            return start, end

    # Pattern: "from 2026-01-01 to 2026-01-31"
    explicit = re.search(
        r"from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})",
        msg_lower,
    )
    if explicit:
        return explicit.group(1), explicit.group(2)

    # Pattern: "last 30 days" or "past week"
    relative = re.search(r"(?:last|past)\s+(\d+)\s+(day|week|month)", msg_lower)
    if relative:
        count = int(relative.group(1))
        unit = relative.group(2)
        end = datetime.now()
        if unit == "day":
            start = end - timedelta(days=count)
        elif unit == "week":
            start = end - timedelta(weeks=count)
        elif unit == "month":
            start = end - timedelta(days=count * 30)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    return None, None


def extract_client(message: str) -> Optional[str]:
    """Extract client/schema from message."""
    msg_lower = message.lower()
    sorted_keys = sorted(CLIENT_KEYWORDS.keys(), key=len, reverse=True)
    for keyword in sorted_keys:
        if keyword in msg_lower:
            return CLIENT_KEYWORDS[keyword]
    return None


def extract_parameters(message: str, tool_name: str) -> Dict[str, Any]:
    """Extract all parameters for a given tool from the message."""
    params: Dict[str, Any] = {}

    equipment = extract_equipment_codes(message)
    start_date, end_date = _extract_date_range(message)
    client = extract_client(message)

    if equipment:
        params["equipment_codes"] = equipment
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    # Only pass client/schema to tools that support it
    tools_with_client = {
        "run_runrate_analysis",
        "run_roi_analysis",
        "run_capacity_analysis",
    }
    tools_with_schema = {
        "run_rca_analysis",
    }

    if client:
        if tool_name in tools_with_client:
            params["client"] = client
        elif tool_name in tools_with_schema:
            params["snowflake_schema"] = client

    return params


async def execute_analysis(
    tool_name: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute an analysis tool and return results."""
    from services.infrastructure.scheduler.tool_dispatcher import dispatch_tool_direct

    logger.info(
        "Executing analysis: tool=%s, params=%s",
        tool_name,
        json.dumps(params, default=str),
    )

    try:
        result = await dispatch_tool_direct(tool_name, params)
        logger.info(
            "Analysis complete: tool=%s, status=%s",
            tool_name,
            result.get("status", "unknown"),
        )
        return result
    except Exception as e:
        logger.error("Analysis execution failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


def format_result_for_llm(result: Dict[str, Any], tool_name: str) -> str:
    """Format analysis results into a concise string for LLM summarization."""
    if result.get("status") == "error":
        return f"Analysis failed with error: {result.get('error', 'Unknown error')}"

    # Extract key sections, skip raw data arrays
    summary = {}
    skip_keys = {"raw_data", "session_data", "daily_data", "shot_data"}

    for key, value in result.items():
        if key in skip_keys:
            continue
        if isinstance(value, dict) and len(str(value)) > 5000:
            # Truncate very large nested dicts
            summary[key] = {k: v for k, v in list(value.items())[:20]}
        elif isinstance(value, list) and len(value) > 20:
            summary[key] = value[:20]
            summary[f"{key}_total_count"] = len(value)
        else:
            summary[key] = value

    return json.dumps(summary, indent=2, default=str)


def get_missing_params_message(
    tool_name: str,
    params: Dict[str, Any],
) -> Optional[str]:
    """Check for missing required parameters and return a help message."""
    missing = []

    # Tools that require equipment codes
    equipment_required = [
        "run_runrate_analysis",
        "run_capacity_analysis",
    ]
    if tool_name in equipment_required and not params.get("equipment_codes"):
        missing.append("equipment code(s)")

    # Tools that require date ranges
    date_required = [
        "run_runrate_analysis",
        "run_roi_analysis",
        "run_capacity_analysis",
    ]
    if tool_name in date_required:
        if not params.get("start_date") or not params.get("end_date"):
            missing.append("date range (e.g., 'for January 2026')")

    if not missing:
        return None

    tool_display = tool_name.replace("run_", "").replace("_", " ").title()
    items = " and ".join(missing)
    return (
        f"To run the **{tool_display}**, I need the following:\n"
        f"- {items}\n\n"
        f"Example: *Run {tool_display.lower()} for EMA-4104 for January 2026*"
    )
