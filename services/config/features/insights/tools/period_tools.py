"""Period-over-period comparison and top-mover tool adapters.

Aggregates per-equipment metrics for two adjacent windows from MASTER_SHOT_TABLE and
delegates delta math and ranking to analysis.insights.period_compare.
Exposes the compare_periods and find_top_movers MCP tools.
"""

import logging
from typing import Any, Dict, Optional

from analysis.insights.period_compare import (
    DEFAULT_TOP_N,
    compare_metric_maps,
    rank_top_movers,
)
from services.config.features.insights.tools.common import (
    InvalidToolParameterError,
    positive_int,
    query_records,
    safe_param,
)

logger = logging.getLogger(__name__)

MAX_PERIOD_DAYS: int = 180
DEFAULT_PERIOD_DAYS: int = 7
MAX_TOP_N: int = 50
HARD_STOP_CT: float = 999.0

SUPPORTED_METRICS: tuple = ("shots", "avg_ct", "active_days")


def _window_metrics(
    start_offset_days: int, end_offset_days: int, equipment_code: Optional[str]
) -> Dict[str, Dict[str, float]]:
    """Per-equipment metrics for a window [now-start_offset, now-end_offset)."""
    equipment_filter = ""
    if equipment_code:
        equipment_filter = "AND EQUIPMENT_CODE = '%s'" % safe_param(
            equipment_code, "equipment_code"
        )
    rows = query_records(f"""
        SELECT
            EQUIPMENT_CODE,
            COUNT(*) AS SHOTS,
            AVG(CASE WHEN CT < {HARD_STOP_CT} THEN CT END) AS AVG_CT,
            COUNT(DISTINCT DATE(LOCAL_SHOT_TIME)) AS ACTIVE_DAYS
        FROM MASTER_SHOT_TABLE
        WHERE LOCAL_SHOT_TIME >= DATEADD(day, -{start_offset_days}, CURRENT_DATE())
          AND LOCAL_SHOT_TIME < DATEADD(day, -{end_offset_days}, CURRENT_DATE())
          AND EQUIPMENT_CODE IS NOT NULL
          {equipment_filter}
        GROUP BY EQUIPMENT_CODE
        """)
    return {
        r["EQUIPMENT_CODE"]: {
            "shots": r.get("SHOTS"),
            "avg_ct": round(r["AVG_CT"], 2) if r.get("AVG_CT") else None,
            "active_days": r.get("ACTIVE_DAYS"),
        }
        for r in rows
    }


def compare_periods(
    period_days: int = DEFAULT_PERIOD_DAYS, equipment_code: Optional[str] = None
) -> Dict[str, Any]:
    """Compare the last period against the one before it, per equipment.

    Args:
        period_days: Window length in days (default: 7, max: 180).
        equipment_code: Optional single-equipment filter.

    Returns:
        dict with per-equipment metric deltas (shots, avg_ct, active_days) and
        plant-level totals for both windows.
    """
    try:
        period_days = positive_int(period_days, "period_days", MAX_PERIOD_DAYS)
        current = _window_metrics(period_days, 0, equipment_code)
        previous = _window_metrics(period_days * 2, period_days, equipment_code)
        comparison = compare_metric_maps(current, previous)

        totals = {
            "current_shots": sum(m.get("shots") or 0 for m in current.values()),
            "previous_shots": sum(m.get("shots") or 0 for m in previous.values()),
            "current_equipment": len(current),
            "previous_equipment": len(previous),
        }
        return {
            "status": "success",
            "period_days": period_days,
            "totals": totals,
            "comparison": comparison,
        }
    except Exception as e:
        logger.error("compare_periods failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


def find_top_movers(
    metric: str = "shots",
    period_days: int = DEFAULT_PERIOD_DAYS,
    top_n: int = DEFAULT_TOP_N,
) -> Dict[str, Any]:
    """Rank equipment by the largest change in one metric between periods.

    Args:
        metric: One of shots, avg_ct, active_days (default: shots).
        period_days: Window length in days (default: 7, max: 180).
        top_n: Number of movers to return (default: 5, max: 50).

    Returns:
        dict with the ranked movers (largest percentage change magnitude first).
    """
    try:
        if metric not in SUPPORTED_METRICS:
            raise InvalidToolParameterError(
                "Unsupported metric: %s (use one of %s)"
                % (metric, ", ".join(SUPPORTED_METRICS))
            )
        period_days = positive_int(period_days, "period_days", MAX_PERIOD_DAYS)
        top_n = positive_int(top_n, "top_n", MAX_TOP_N)

        current = _window_metrics(period_days, 0, None)
        previous = _window_metrics(period_days * 2, period_days, None)
        movers = rank_top_movers(
            compare_metric_maps(current, previous), metric, top_n=top_n
        )
        return {
            "status": "success",
            "metric": metric,
            "period_days": period_days,
            "movers": movers,
        }
    except Exception as e:
        logger.error("find_top_movers failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
