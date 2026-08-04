"""Plant-wide equipment health snapshot tool adapter.

Aggregates shot activity, CT performance, run efficiency, and capacity utilization per
equipment from Snowflake and blends them into ranked health scores (worst first).
Computation is delegated to analysis.insights.health_score.
"""

import logging
from typing import Any, Dict, Optional

from analysis.insights.health_score import build_equipment_health, rank_by_health
from services.config.features.insights.tools.common import positive_int, query_records

logger = logging.getLogger(__name__)

MAX_WINDOW_DAYS: int = 365
DEFAULT_WINDOW_DAYS: int = 14
HARD_STOP_CT: float = 999.0
CT_WITHIN_TOLERANCE: float = 1.10
RECENCY_FULL_SCORE_HOURS: float = 24.0
RECENCY_ZERO_SCORE_HOURS: float = 168.0


def _master_metrics(days: int) -> Dict[str, Dict[str, Any]]:
    """Per-equipment shot metrics from DEMO_TABLE over the window."""
    rows = query_records(f"""
        SELECT
            EQUIPMENT_CODE,
            COUNT(*) AS SHOTS,
            AVG(CASE WHEN CT < {HARD_STOP_CT} THEN CT END) AS AVG_CT,
            MAX(APPROVED_CT) AS APPROVED_CT,
            AVG(CASE WHEN CT < {HARD_STOP_CT} AND APPROVED_CT > 0
                     AND CT <= APPROVED_CT * {CT_WITHIN_TOLERANCE}
                     THEN 100.0 WHEN CT < {HARD_STOP_CT} AND APPROVED_CT > 0
                     THEN 0.0 END) AS CT_PERFORMANCE,
            DATEDIFF('hour', MAX(LOCAL_SHOT_TIME), CURRENT_TIMESTAMP()) AS HOURS_SINCE_LAST_SHOT
        FROM DEMO_TABLE
        WHERE LOCAL_SHOT_TIME >= DATEADD(day, -{days}, CURRENT_DATE())
          AND EQUIPMENT_CODE IS NOT NULL
        GROUP BY EQUIPMENT_CODE
        """)
    return {r["EQUIPMENT_CODE"]: r for r in rows}


def _production_efficiency(days: int) -> Dict[str, float]:
    """Per-equipment run efficiency percentage. Returns empty if table unavailable."""
    try:
        rows = query_records(f"""
            SELECT EQUIPMENT_CODE,
                   SUM(PRODUCTION_TIME_SEC) / NULLIF(SUM(RUN_TIME_SEC), 0) * 100 AS RUN_EFFICIENCY
            FROM PRODUCTION_METRICS
            WHERE START_DATE >= DATEADD(day, -{days}, CURRENT_DATE())
            GROUP BY EQUIPMENT_CODE
            """)
        return {
            r["EQUIPMENT_CODE"]: r["RUN_EFFICIENCY"]
            for r in rows
            if r.get("RUN_EFFICIENCY") is not None
        }
    except Exception:
        return {}


def _capacity_utilization(days: int) -> Dict[str, float]:
    """Per-equipment utilization percentage. Returns empty if table unavailable."""
    try:
        rows = query_records(f"""
            SELECT EQUIPMENT_CODE,
                   SUM(ACTUAL_OUTPUT) / NULLIF(SUM(OPTIMAL_OUTPUT), 0) * 100 AS UTILIZATION
            FROM CAPACITY_DAILY
            WHERE START_DATE >= DATEADD(day, -{days}, CURRENT_DATE())
            GROUP BY EQUIPMENT_CODE
            """)
        return {
            r["EQUIPMENT_CODE"]: r["UTILIZATION"]
            for r in rows
            if r.get("UTILIZATION") is not None
        }
    except Exception:
        return {}


def _recency_score(hours_since_last_shot: Optional[float]) -> Optional[float]:
    """Linear 100-to-0 recency score between 24h and 168h since the last shot."""
    if hours_since_last_shot is None:
        return None
    if hours_since_last_shot <= RECENCY_FULL_SCORE_HOURS:
        return 100.0
    if hours_since_last_shot >= RECENCY_ZERO_SCORE_HOURS:
        return 0.0
    span = RECENCY_ZERO_SCORE_HOURS - RECENCY_FULL_SCORE_HOURS
    return round(
        100.0 * (1 - (hours_since_last_shot - RECENCY_FULL_SCORE_HOURS) / span), 1
    )


def get_plant_health_snapshot(days: int = DEFAULT_WINDOW_DAYS) -> Dict[str, Any]:
    """Build a ranked health snapshot for every active equipment.

    Args:
        days: Analysis window in days (default: 14, max: 365).

    Returns:
        dict with ranked equipment health records (worst first), grade counts,
        and the metric sources used.
    """
    try:
        days = positive_int(days, "days", MAX_WINDOW_DAYS)
        master = _master_metrics(days)
        efficiency = _production_efficiency(days)
        utilization = _capacity_utilization(days)

        records = []
        for code, m in master.items():
            health = build_equipment_health(
                code,
                {
                    "run_efficiency": efficiency.get(code),
                    "ct_performance": m.get("CT_PERFORMANCE"),
                    "utilization": utilization.get(code),
                    "recency": _recency_score(m.get("HOURS_SINCE_LAST_SHOT")),
                },
            )
            health["shots_in_window"] = m.get("SHOTS")
            health["avg_ct"] = round(m["AVG_CT"], 2) if m.get("AVG_CT") else None
            health["approved_ct"] = m.get("APPROVED_CT")
            health["hours_since_last_shot"] = m.get("HOURS_SINCE_LAST_SHOT")
            records.append(health)

        ranked = rank_by_health(records)
        grades: Dict[str, int] = {}
        for r in ranked:
            grades[r["grade"]] = grades.get(r["grade"], 0) + 1

        return {
            "status": "success",
            "window_days": days,
            "equipment_count": len(ranked),
            "grade_counts": grades,
            "equipment": ranked,
            "notes": (
                "Run efficiency from PRODUCTION_METRICS, utilization from CAPACITY_DAILY; "
                "missing components renormalize the score weights."
            ),
        }
    except Exception as e:
        logger.error("get_plant_health_snapshot failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
