"""Cycle time savings simulation tool adapter.

Aggregates observed versus target cycle times per equipment/part from
MASTER_SHOT_TABLE and sizes the opportunity with analysis.insights.savings.
Targets are the approved CT or the best observed CT within the same approved CT group.
"""

import logging
from typing import Any, Dict, List, Optional

from analysis.insights.savings import simulate_savings_records
from services.config.features.insights.tools.common import (
    InvalidToolParameterError,
    positive_int,
    query_records,
    safe_param,
)

logger = logging.getLogger(__name__)

MAX_WINDOW_DAYS: int = 365
DEFAULT_WINDOW_DAYS: int = 30
DEFAULT_MIN_SHOTS: int = 100
MAX_MIN_SHOTS: int = 1000000
HARD_STOP_CT: float = 999.0

TARGET_APPROVED: str = "approved"
TARGET_GROUP_BEST: str = "group_best"
SUPPORTED_TARGETS: tuple = (TARGET_APPROVED, TARGET_GROUP_BEST)


def _fetch_aggregates(
    days: int, min_shots: int, equipment_code: Optional[str]
) -> List[Dict[str, Any]]:
    """Per equipment/part shot aggregates over the window."""
    equipment_filter = ""
    if equipment_code:
        equipment_filter = "AND EQUIPMENT_CODE = '%s'" % safe_param(
            equipment_code, "equipment_code"
        )
    return query_records(f"""
        SELECT
            EQUIPMENT_CODE,
            PART_ID,
            MAX(PART_NAME) AS PART_NAME,
            MAX(APPROVED_CT) AS APPROVED_CT,
            AVG(CASE WHEN CT < {HARD_STOP_CT} THEN CT END) AS AVG_CT,
            COUNT(CASE WHEN CT < {HARD_STOP_CT} THEN 1 END) AS SHOTS
        FROM MASTER_SHOT_TABLE
        WHERE LOCAL_SHOT_TIME >= DATEADD(day, -{days}, CURRENT_DATE())
          AND EQUIPMENT_CODE IS NOT NULL
          {equipment_filter}
        GROUP BY EQUIPMENT_CODE, PART_ID
        HAVING COUNT(CASE WHEN CT < {HARD_STOP_CT} THEN 1 END) >= {min_shots}
        """)


def _group_best_targets(rows: List[Dict[str, Any]]) -> Dict[Any, float]:
    """Best (lowest) observed average CT per approved CT group."""
    best: Dict[Any, float] = {}
    for row in rows:
        group = row.get("APPROVED_CT")
        avg_ct = row.get("AVG_CT")
        if group is None or avg_ct is None:
            continue
        if group not in best or avg_ct < best[group]:
            best[group] = avg_ct
    return best


def simulate_savings(
    days: int = DEFAULT_WINDOW_DAYS,
    target: str = TARGET_APPROVED,
    equipment_code: Optional[str] = None,
    min_shots: int = DEFAULT_MIN_SHOTS,
) -> Dict[str, Any]:
    """Size the opportunity if equipment ran at a target cycle time.

    Args:
        days: Analysis window in days (default: 30, max: 365).
        target: 'approved' compares to APPROVED_CT; 'group_best' compares to the
            best observed average CT within the same approved CT group.
        equipment_code: Optional single-equipment filter.
        min_shots: Minimum valid shots per equipment/part to include (default: 100).

    Returns:
        dict with ranked savings records (largest first) and plant totals.
    """
    try:
        if target not in SUPPORTED_TARGETS:
            raise InvalidToolParameterError(
                "Unsupported target: %s (use one of %s)"
                % (target, ", ".join(SUPPORTED_TARGETS))
            )
        days = positive_int(days, "days", MAX_WINDOW_DAYS)
        min_shots = positive_int(min_shots, "min_shots", MAX_MIN_SHOTS)

        rows = _fetch_aggregates(days, min_shots, equipment_code)
        group_best = _group_best_targets(rows) if target == TARGET_GROUP_BEST else {}

        records = []
        for row in rows:
            if target == TARGET_APPROVED:
                target_ct = row.get("APPROVED_CT")
            else:
                target_ct = group_best.get(row.get("APPROVED_CT"))
            records.append(
                {
                    "equipment_code": row.get("EQUIPMENT_CODE"),
                    "part_id": row.get("PART_ID"),
                    "part_name": row.get("PART_NAME"),
                    "shots": row.get("SHOTS") or 0,
                    "avg_ct": round(row["AVG_CT"], 3) if row.get("AVG_CT") else None,
                    "target_ct": target_ct,
                }
            )

        result = simulate_savings_records(records)
        return {
            "status": "success",
            "window_days": days,
            "target": target,
            "min_shots": min_shots,
            "total_hours_saved": result["total_hours_saved"],
            "total_extra_parts": result["total_extra_parts"],
            "opportunities": result["opportunities"],
            "records": result["records"],
            "notes": (
                "group_best compares each tool to the fastest tool sharing the same "
                "approved CT; approved compares to the approved CT itself."
            ),
        }
    except Exception as e:
        logger.error("simulate_savings failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
