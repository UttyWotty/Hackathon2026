"""Plant-wide equipment health snapshot tool adapter.

Aggregates shot activity, DURATION performance, run efficiency, and capacity utilization per
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
HARD_STOP_DURATION: float = 999.0
CT_WITHIN_TOLERANCE: float = 1.10
RECENCY_FULL_SCORE_HOURS: float = 24.0
RECENCY_ZERO_SCORE_HOURS: float = 168.0


def _master_metrics(days: int) -> Dict[str, Dict[str, Any]]:
    """Per-equipment shot metrics from SHOT_DATA over the window."""
    rows = query_records(f"""
        SELECT
            MACHINE_ID,
            COUNT(*) AS SHOTS,
            AVG(CASE WHEN DURATION < {HARD_STOP_DURATION} THEN DURATION END) AS AVG_DURATION,
            MAX(TARGET_DURATION) AS TARGET_DURATION,
            AVG(CASE WHEN DURATION < {HARD_STOP_DURATION} AND TARGET_DURATION > 0
                     AND DURATION <= TARGET_DURATION * {CT_WITHIN_TOLERANCE}
                     THEN 100.0 WHEN DURATION < {HARD_STOP_DURATION} AND TARGET_DURATION > 0
                     THEN 0.0 END) AS DURATION_PERFORMANCE,
            DATEDIFF('hour', MAX(SHOT_TIME), CURRENT_TIMESTAMP()) AS HOURS_SINCE_LAST_SHOT
        FROM SHOT_DATA
        WHERE SHOT_TIME >= DATEADD(day, -{days}, CURRENT_DATE())
          AND MACHINE_ID IS NOT NULL
        GROUP BY MACHINE_ID
        """)
    return {r["MACHINE_ID"]: r for r in rows}


def _production_efficiency(days: int) -> Dict[str, float]:
    """Per-equipment run efficiency percentage. Returns empty if table unavailable."""
    try:
        rows = query_records(f"""
            SELECT MACHINE_ID,
                   SUM(PRODUCTION_TIME_SEC) / NULLIF(SUM(RUN_TIME_SEC), 0) * 100 AS RUN_EFFICIENCY
            FROM PRODUCTION_METRICS
            WHERE START_DATE >= DATEADD(day, -{days}, CURRENT_DATE())
            GROUP BY MACHINE_ID
            """)
        return {
            r["MACHINE_ID"]: r["RUN_EFFICIENCY"]
            for r in rows
            if r.get("RUN_EFFICIENCY") is not None
        }
    except Exception:
        return {}


def _capacity_utilization(days: int) -> Dict[str, float]:
    """Per-equipment utilization percentage. Returns empty if table unavailable."""
    try:
        rows = query_records(f"""
            SELECT MACHINE_ID,
                   SUM(ACTUAL_OUTPUT) / NULLIF(SUM(OPTIMAL_OUTPUT), 0) * 100 AS UTILIZATION
            FROM CAPACITY_DAILY
            WHERE START_DATE >= DATEADD(day, -{days}, CURRENT_DATE())
            GROUP BY MACHINE_ID
            """)
        return {
            r["MACHINE_ID"]: r["UTILIZATION"]
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
                    "duration_performance": m.get("DURATION_PERFORMANCE"),
                    "utilization": utilization.get(code),
                    "recency": _recency_score(m.get("HOURS_SINCE_LAST_SHOT")),
                },
            )
            health["shots_in_window"] = m.get("SHOTS")
            health["avg_duration"] = round(m["AVG_DURATION"], 2) if m.get("AVG_DURATION") else None
            health["target_duration"] = m.get("TARGET_DURATION")
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
