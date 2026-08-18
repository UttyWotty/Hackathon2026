"""Mold history and maintenance impact tool adapters.

Joins MOLD, MOLD_MAINTENANCE, MOLD_LOCATION, and SHOT_DATA to expose a mold's
lifecycle and to measure production metrics before versus after maintenance events.
Impact classification is delegated to analysis.insights.maintenance_impact.
"""

import logging
from typing import Any, Dict, List, Optional

from analysis.insights.maintenance_impact import compare_before_after
from services.config.features.insights.tools.common import (
    InvalidToolParameterError,
    positive_int,
    query_records,
    safe_param,
)

logger = logging.getLogger(__name__)

MAX_WINDOW_DAYS: int = 90
DEFAULT_IMPACT_WINDOW_DAYS: int = 7
MAX_EVENTS_ANALYZED: int = 10
MAX_EVENT_ROWS: int = 100
HARD_STOP_DURATION: float = 999.0


def _find_molds(
    machine_id: Optional[str], tool_id: Optional[int]
) -> List[Dict[str, Any]]:
    """Locate mold rows by equipment code or mold id."""
    if tool_id is not None:
        where = "ID = %d" % int(tool_id)
    elif machine_id:
        where = "MACHINE_ID = '%s'" % safe_param(machine_id, "machine_id")
    else:
        raise InvalidToolParameterError("Provide machine_id or tool_id")
    return query_records("""
        SELECT ID, MACHINE_ID, SENSOR_CODE, SENSOR_ID,
               VENDOR_COMPANY_ID, LOCATION_ID, PRODUCT_ID, TYPE,
               TARGET_DURATION, TOTAL_CAVITIES, DESIGNED_SHOT,
               MAX_DAILY_OUTPUT, PRODUCTION_DAYS, SHIFTS_PER_DAY
        FROM TOOL
        WHERE %s
        """ % where)


def get_mold_history(
    machine_id: Optional[str] = None, tool_id: Optional[int] = None
) -> Dict[str, Any]:
    """Full lifecycle view of a mold: status, maintenance events, location moves.

    Args:
        machine_id: Equipment code of the mold (alternative to tool_id).
        tool_id: MOLD.ID primary key (alternative to machine_id).

    Returns:
        dict with the mold summary, maintenance events, location history, and
        shots since the last maintenance.
    """
    try:
        molds = _find_molds(machine_id, tool_id)
        if not molds:
            return {"status": "error", "error": "Mold not found"}
        mold = molds[0]
        mold_pk = int(mold["ID"])

        maintenance = query_records(f"""
            SELECT ID, STATUS, COMPLETED_AT, ORDER_TYPE
            FROM WORK_ORDER
            WHERE TOOL_ID = {mold_pk}
            ORDER BY COMPLETED_AT DESC NULLS LAST
            LIMIT {MAX_EVENT_ROWS}
            """)
        shots_since = query_records(f"""
            SELECT COUNT(*) AS SHOTS
            FROM SHOT_DATA
            WHERE TOOL_ID = {mold_pk}
              AND SHOT_TIME > (
                  SELECT COALESCE(MAX(COMPLETED_AT), '1970-01-01'::TIMESTAMP)
                  FROM WORK_ORDER WHERE TOOL_ID = {mold_pk}
              )
            """)
        return {
            "status": "success",
            "mold": mold,
            "maintenance_events": maintenance,
            "shots_since_last_maintenance": (
                int(shots_since[0]["SHOTS"]) if shots_since else None
            ),
        }
    except Exception as e:
        logger.error("get_mold_history failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


def _window_metrics_for_mold(
    mold_pk: int, event_time: str, window_days: int, before: bool
) -> Dict[str, Optional[float]]:
    """Avg CT and shots/day for a window before or after a maintenance event."""
    if before:
        time_filter = (
            "SHOT_TIME >= DATEADD(day, -%d, '%s'::TIMESTAMP) "
            "AND SHOT_TIME < '%s'::TIMESTAMP" % (window_days, event_time, event_time)
        )
    else:
        time_filter = (
            "SHOT_TIME >= '%s'::TIMESTAMP "
            "AND SHOT_TIME < DATEADD(day, %d, '%s'::TIMESTAMP)"
            % (event_time, window_days, event_time)
        )
    rows = query_records(f"""
        SELECT AVG(CASE WHEN DURATION < {HARD_STOP_DURATION} THEN DURATION END) AS AVG_DURATION,
               COUNT(*) AS SHOTS
        FROM SHOT_DATA
        WHERE TOOL_ID = {mold_pk} AND {time_filter}
        """)
    row = rows[0] if rows else {}
    shots = row.get("SHOTS") or 0
    return {
        "avg_duration": (
            round(row["AVG_DURATION"], 3) if row.get("AVG_DURATION") else None
        ),
        "shots_per_day": round(shots / window_days, 1) if shots else None,
    }


def maintenance_impact_analysis(
    machine_id: Optional[str] = None,
    tool_id: Optional[int] = None,
    window_days: int = DEFAULT_IMPACT_WINDOW_DAYS,
) -> Dict[str, Any]:
    """Measure whether maintenance events improved production metrics.

    Compares average duration and shots/day in equal windows before and after each
    completed maintenance event of the mold.

    Args:
        machine_id: Equipment code of the mold (alternative to tool_id).
        tool_id: MOLD.ID primary key (alternative to machine_id).
        window_days: Window length on each side of the event (default: 7, max: 90).

    Returns:
        dict with per-event before/after metrics and impact verdicts.
    """
    try:
        window_days = positive_int(window_days, "window_days", MAX_WINDOW_DAYS)
        molds = _find_molds(machine_id, tool_id)
        if not molds:
            return {"status": "error", "error": "Mold not found"}
        mold = molds[0]
        mold_pk = int(mold["ID"])

        events = query_records(f"""
            SELECT ID, COMPLETED_AT, STATUS, ORDER_TYPE
            FROM WORK_ORDER
            WHERE TOOL_ID = {mold_pk} AND COMPLETED_AT IS NOT NULL
            ORDER BY COMPLETED_AT DESC
            LIMIT {MAX_EVENTS_ANALYZED}
            """)
        analyzed = []
        for event in events:
            event_time = event["COMPLETED_AT"]
            before = _window_metrics_for_mold(
                mold_pk, event_time, window_days, before=True
            )
            after = _window_metrics_for_mold(
                mold_pk, event_time, window_days, before=False
            )
            analyzed.append(
                {
                    "maintenance_id": event.get("ID"),
                    "maintenanced_at": event_time,
                    "before": before,
                    "after": after,
                    **compare_before_after(before, after),
                }
            )
        return {
            "status": "success",
            "tool_id": mold_pk,
            "machine_id": mold.get("MACHINE_ID"),
            "window_days": window_days,
            "events_analyzed": len(analyzed),
            "events": analyzed,
        }
    except Exception as e:
        logger.error("maintenance_impact_analysis failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
