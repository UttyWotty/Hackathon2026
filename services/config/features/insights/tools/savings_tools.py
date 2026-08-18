"""Duration savings simulation tool adapter.

Aggregates observed versus target durations per equipment/part from
SHOT_DATA and sizes the opportunity with analysis.insights.savings.
Targets are the approved duration or the best observed duration within the same approved duration group.
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
HARD_STOP_DURATION: float = 999.0

TARGET_APPROVED: str = "approved"
TARGET_GROUP_BEST: str = "group_best"
SUPPORTED_TARGETS: tuple = (TARGET_APPROVED, TARGET_GROUP_BEST)


def _fetch_aggregates(
    days: int, min_shots: int, machine_id: Optional[str]
) -> List[Dict[str, Any]]:
    """Per equipment/part shot aggregates over the window."""
    equipment_filter = ""
    if machine_id:
        equipment_filter = "AND MACHINE_ID = '%s'" % safe_param(
            machine_id, "machine_id"
        )
    return query_records(f"""
        SELECT
            MACHINE_ID,
            PRODUCT_ID,
            MAX(PRODUCT_NAME) AS PRODUCT_NAME,
            MAX(TARGET_DURATION) AS TARGET_DURATION,
            AVG(CASE WHEN CT < {HARD_STOP_DURATION} THEN CT END) AS AVG_DURATION,
            COUNT(CASE WHEN CT < {HARD_STOP_DURATION} THEN 1 END) AS SHOTS
        FROM SHOT_DATA
        WHERE SHOT_TIME >= DATEADD(day, -{days}, CURRENT_DATE())
          AND MACHINE_ID IS NOT NULL
          {equipment_filter}
        GROUP BY MACHINE_ID, PRODUCT_ID
        HAVING COUNT(CASE WHEN CT < {HARD_STOP_DURATION} THEN 1 END) >= {min_shots}
        """)


def _group_best_targets(rows: List[Dict[str, Any]]) -> Dict[Any, float]:
    """Best (lowest) observed average duration per approved duration group."""
    best: Dict[Any, float] = {}
    for row in rows:
        group = row.get("TARGET_DURATION")
        avg_duration = row.get("AVG_DURATION")
        if group is None or avg_duration is None:
            continue
        if group not in best or avg_duration < best[group]:
            best[group] = avg_duration
    return best


def simulate_savings(
    days: int = DEFAULT_WINDOW_DAYS,
    target: str = TARGET_APPROVED,
    machine_id: Optional[str] = None,
    min_shots: int = DEFAULT_MIN_SHOTS,
) -> Dict[str, Any]:
    """Size the opportunity if equipment ran at a target duration.

    Args:
        days: Analysis window in days (default: 30, max: 365).
        target: 'approved' compares to TARGET_DURATION; 'group_best' compares to the
            best observed average duration within the same approved duration group.
        machine_id: Optional single-equipment filter.
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

        rows = _fetch_aggregates(days, min_shots, machine_id)
        group_best = _group_best_targets(rows) if target == TARGET_GROUP_BEST else {}

        records = []
        for row in rows:
            if target == TARGET_APPROVED:
                target_duration = row.get("TARGET_DURATION")
            else:
                target_duration = group_best.get(row.get("TARGET_DURATION"))
            records.append(
                {
                    "machine_id": row.get("MACHINE_ID"),
                    "product_id": row.get("PRODUCT_ID"),
                    "product_name": row.get("PRODUCT_NAME"),
                    "shots": row.get("SHOTS") or 0,
                    "avg_duration": round(row["AVG_DURATION"], 3) if row.get("AVG_DURATION") else None,
                    "target_duration": target_duration,
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
                "approved duration; approved compares to the approved duration itself."
            ),
        }
    except Exception as e:
        logger.error("simulate_savings failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
