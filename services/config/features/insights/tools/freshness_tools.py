"""Data freshness report tool adapter.

Reads the newest record age for each analytics table plus the ETL_LATEST pipeline log
and classifies every source as fresh, stale, dead, or no_data against expected cadences.
Classification is delegated to analysis.insights.freshness.
"""

import logging
from typing import Any, Dict, List

from analysis.insights.freshness import classify_freshness
from services.config.features.insights.tools.common import query_records

logger = logging.getLogger(__name__)

HOURS_PER_DAY: float = 24.0

# Expected maximum data age per table (hours). Daily-refreshed tables get a small
# buffer over 24h; weekly aggregates get a week plus a day.
TABLE_FRESHNESS_EXPECTATIONS: Dict[str, Dict[str, Any]] = {
    "MASTER_SHOT_TABLE": {
        "time_column": "LOCAL_SHOT_TIME",
        "expected_max_age_hours": 26.0,
    },
    "ANA_SHOT_MADE_TABLE": {
        "time_column": "LOCAL_SHOT_TIME",
        "expected_max_age_hours": 26.0,
    },
    "ROI": {"time_column": "LOCAL_SHOT_TIME", "expected_max_age_hours": 26.0},
    "RUNRATE": {"time_column": "START_DATE", "expected_max_age_hours": 192.0},
    "CT_EFFICIENCY": {"time_column": "SHOT_DATE", "expected_max_age_hours": 192.0},
    "CAPACITY_DAILY": {"time_column": "START_DATE", "expected_max_age_hours": 26.0},
    "CYCLE_TIME_DEVIATION": {
        "time_column": "UPDATED_AT",
        "expected_max_age_hours": 192.0,
    },
}


def _table_entries() -> List[Dict[str, Any]]:
    """Freshness entry per analytics table from its max time column."""
    entries: List[Dict[str, Any]] = []
    for table, config in TABLE_FRESHNESS_EXPECTATIONS.items():
        column = config["time_column"]
        expected = config["expected_max_age_hours"]
        try:
            rows = query_records(f"""
                SELECT MAX({column}) AS LAST_DATA_TIME,
                       DATEDIFF('hour', MAX({column}), CURRENT_TIMESTAMP()) AS AGE_HOURS
                FROM {table}
                """)
            row = rows[0] if rows else {}
            age = row.get("AGE_HOURS")
            entries.append(
                {
                    "source": table,
                    "last_data_time": row.get("LAST_DATA_TIME"),
                    "age_hours": age,
                    "expected_max_age_hours": expected,
                    "status": classify_freshness(age, expected),
                }
            )
        except Exception as e:
            entries.append({"source": table, "status": "error", "error": str(e)})
    return entries


def _pipeline_entries() -> List[Dict[str, Any]]:
    """Pipeline status rows from the ETL_LATEST log table."""
    try:
        return query_records("""
            SELECT PIPELINE_NAME, STATUS, LAST_DATA_TIME, LAST_REFRESH_TIME,
                   ERROR_MESSAGE, UPDATED_AT
            FROM ETL_LATEST
            ORDER BY PIPELINE_NAME
            """)
    except Exception as e:
        logger.warning("ETL_LATEST not readable: %s", e)
        return []


def data_freshness_report() -> Dict[str, Any]:
    """Report how current every analytics table and pipeline is.

    Returns:
        dict with per-table freshness entries (status: fresh, stale, dead, or
        no_data), pipeline log rows, and a count of sources needing attention.
    """
    try:
        tables = _table_entries()
        attention = [
            t["source"] for t in tables if t.get("status") not in ("fresh", "error")
        ]
        return {
            "status": "success",
            "tables": tables,
            "pipelines": _pipeline_entries(),
            "sources_needing_attention": attention,
        }
    except Exception as e:
        logger.error("data_freshness_report failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
