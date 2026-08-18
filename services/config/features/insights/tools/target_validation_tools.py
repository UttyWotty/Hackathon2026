"""Approved Duration validation tool adapter.

Fetches approved duration versus observed mode duration per equipment/part from SHOT_DATA
and delegates staleness classification to analysis.insights.target_validation.
Exposes the validate_targets MCP tool.
"""

import logging
from typing import Any, Dict, Optional

from analysis.insights.target_validation import (
    DEFAULT_MIN_SHOTS,
    DEFAULT_STALE_THRESHOLD_Pduration,
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
HARD_STOP_DURATION: float = 999.0
MAX_THRESHOLD_PCT: float = 100.0


def validate_targets(
    days: int = DEFAULT_WINDOW_DAYS,
    stale_threshold_pct: float = DEFAULT_STALE_THRESHOLD_Pduration,
    min_shots: int = DEFAULT_MIN_SHOTS,
    machine_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Flag approved durations that have drifted from observed production CTs.

    Compares TARGET_DURATION to the statistical mode of recent actual durations per
    equipment/part and proposes updated values for stale entries.

    Args:
        days: Observation window in days (default: 30, max: 365).
        stale_threshold_pct: Deviation percentage that marks an approved duration stale
            (default: 10.0).
        min_shots: Minimum shots required to judge a record (default: 100).
        machine_id: Optional single-equipment filter.

    Returns:
        dict with stale records (largest deviation first), full validations, and
        a status summary.
    """
    try:
        days = positive_int(days, "days", MAX_WINDOW_DAYS)
        threshold = min(abs(float(stale_threshold_pct)), MAX_THRESHOLD_PCT)
        equipment_filter = ""
        if machine_id:
            equipment_filter = "AND MACHINE_ID = '%s'" % safe_param(
                machine_id, "machine_id"
            )

        rows = query_records(f"""
            SELECT
                MACHINE_ID,
                PRODUCT_ID,
                MAX(PRODUCT_NAME) AS PRODUCT_NAME,
                MAX(TARGET_DURATION) AS TARGET_DURATION,
                MODE(CASE WHEN CT < {HARD_STOP_DURATION} THEN CT END) AS OBSERVED_duration,
                COUNT(CASE WHEN CT < {HARD_STOP_DURATION} THEN 1 END) AS SHOT_COUNT
            FROM SHOT_DATA
            WHERE SHOT_TIME >= DATEADD(day, -{days}, CURRENT_DATE())
              AND MACHINE_ID IS NOT NULL
              {equipment_filter}
            GROUP BY MACHINE_ID, PRODUCT_ID
            """)
        records = [
            {
                "machine_id": r.get("MACHINE_ID"),
                "product_id": r.get("PRODUCT_ID"),
                "product_name": r.get("PRODUCT_NAME"),
                "target_duration": r.get("TARGET_DURATION"),
                "observed_duration": r.get("OBSERVED_CT"),
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
                "Observed CT is the statistical mode of actual durations excluding the "
                "999.9 hard-stop code. Tool comparisons are only meaningful within "
                "the same approved duration group."
            ),
        }
    except Exception as e:
        logger.error("validate_targets failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
