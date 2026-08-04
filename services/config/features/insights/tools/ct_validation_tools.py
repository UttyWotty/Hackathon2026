"""Approved CT validation tool adapter.

Fetches approved CT versus observed mode CT per equipment/part from DEMO_TABLE
and delegates staleness classification to analysis.insights.ct_validation.
Exposes the validate_approved_cts MCP tool.
"""

import logging
from typing import Any, Dict, Optional

from analysis.insights.ct_validation import (
    DEFAULT_MIN_SHOTS,
    DEFAULT_STALE_THRESHOLD_PCT,
    validate_ct_records,
)
from services.config.features.insights.tools.common import (
    positive_int,
    query_records,
    safe_param,
)

logger = logging.getLogger(__name__)

MAX_WINDOW_DAYS: int = 365
DEFAULT_WINDOW_DAYS: int = 30
HARD_STOP_CT: float = 999.0
MAX_THRESHOLD_PCT: float = 100.0


def validate_approved_cts(
    days: int = DEFAULT_WINDOW_DAYS,
    stale_threshold_pct: float = DEFAULT_STALE_THRESHOLD_PCT,
    min_shots: int = DEFAULT_MIN_SHOTS,
    equipment_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Flag approved CTs that have drifted from observed production CTs.

    Compares APPROVED_CT to the statistical mode of recent actual CTs per
    equipment/part and proposes updated values for stale entries.

    Args:
        days: Observation window in days (default: 30, max: 365).
        stale_threshold_pct: Deviation percentage that marks an approved CT stale
            (default: 10.0).
        min_shots: Minimum shots required to judge a record (default: 100).
        equipment_code: Optional single-equipment filter.

    Returns:
        dict with stale records (largest deviation first), full validations, and
        a status summary.
    """
    try:
        days = positive_int(days, "days", MAX_WINDOW_DAYS)
        threshold = min(abs(float(stale_threshold_pct)), MAX_THRESHOLD_PCT)
        equipment_filter = ""
        if equipment_code:
            equipment_filter = "AND EQUIPMENT_CODE = '%s'" % safe_param(
                equipment_code, "equipment_code"
            )

        rows = query_records(f"""
            SELECT
                EQUIPMENT_CODE,
                PART_ID,
                MAX(PART_NAME) AS PART_NAME,
                MAX(APPROVED_CT) AS APPROVED_CT,
                MODE(CASE WHEN CT < {HARD_STOP_CT} THEN CT END) AS OBSERVED_CT,
                COUNT(CASE WHEN CT < {HARD_STOP_CT} THEN 1 END) AS SHOT_COUNT
            FROM DEMO_TABLE
            WHERE LOCAL_SHOT_TIME >= DATEADD(day, -{days}, CURRENT_DATE())
              AND EQUIPMENT_CODE IS NOT NULL
              {equipment_filter}
            GROUP BY EQUIPMENT_CODE, PART_ID
            """)
        records = [
            {
                "equipment_code": r.get("EQUIPMENT_CODE"),
                "part_id": r.get("PART_ID"),
                "part_name": r.get("PART_NAME"),
                "approved_ct": r.get("APPROVED_CT"),
                "observed_ct": r.get("OBSERVED_CT"),
                "shot_count": r.get("SHOT_COUNT") or 0,
            }
            for r in rows
        ]
        result = validate_ct_records(records, threshold, min_shots)
        return {
            "status": "success",
            "window_days": days,
            "stale_threshold_pct": threshold,
            "min_shots": min_shots,
            "summary": result["summary"],
            "stale_records": result["stale_records"],
            "records": result["records"],
            "notes": (
                "Observed CT is the statistical mode of actual CTs excluding the "
                "999.9 hard-stop code. Tool comparisons are only meaningful within "
                "the same approved CT group."
            ),
        }
    except Exception as e:
        logger.error("validate_approved_cts failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
