"""Mold history and maintenance impact tool adapters.

Joins MOLD, MOLD_MAINTENANCE, MOLD_LOCATION, and MASTER_SHOT_TABLE to expose a mold's
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
HARD_STOP_CT: float = 999.0


def _find_molds(
    equipment_code: Optional[str], mold_id: Optional[int]
) -> List[Dict[str, Any]]:
    """Locate mold rows by equipment code or mold id."""
    if mold_id is not None:
        where = "ID = %d" % int(mold_id)
    elif equipment_code:
        where = "EQUIPMENT_CODE = '%s'" % safe_param(equipment_code, "equipment_code")
    else:
        raise InvalidToolParameterError("Provide equipment_code or mold_id")
    return query_records("""
        SELECT ID, EQUIPMENT_CODE, SUPPLIER_MOLD_CODE, TOOLING_STATUS,
               OPERATING_STATUS, DESIGNED_SHOT, LAST_SHOT, COUNTER_SHOT_COUNT,
               MAINTENANCE_COUNT, LAST_MAINTENANCE_DATE, LAST_SHOT_AT,
               CONTRACTED_CYCLE_TIME, WEIGHTED_AVERAGE_CYCLE_TIME, TOTAL_CAVITIES,
               UTILIZATION_RATE
        FROM MOLD
        WHERE %s
        """ % where)


def get_mold_history(
    equipment_code: Optional[str] = None, mold_id: Optional[int] = None
) -> Dict[str, Any]:
    """Full lifecycle view of a mold: status, maintenance events, location moves.

    Args:
        equipment_code: Equipment code of the mold (alternative to mold_id).
        mold_id: MOLD.ID primary key (alternative to equipment_code).

    Returns:
        dict with the mold summary, maintenance events, location history, and
        shots since the last maintenance.
    """
    try:
        molds = _find_molds(equipment_code, mold_id)
        if not molds:
            return {"status": "error", "error": "Mold not found"}
        mold = molds[0]
        mold_pk = int(mold["ID"])

        maintenance = query_records(f"""
            SELECT ID, MAINTENANCE_STATUS, MAINTENANCED_AT, START_TIME, END_TIME,
                   SHOT_COUNT, ACCUMULATED_SHOT, WORK_ORDER_ID, MAINTENANCE_BY
            FROM MOLD_MAINTENANCE
            WHERE MOLD_ID = {mold_pk}
            ORDER BY MAINTENANCED_AT DESC NULLS LAST
            LIMIT {MAX_EVENT_ROWS}
            """)
        locations = query_records(f"""
            SELECT RELOCATION_TYPE, LOCATION_ID, PREVIOUS_LOCATION_ID,
                   MOLD_LOCATION_STATUS, CONFIRMED_AT, CREATED_AT, LATEST
            FROM MOLD_LOCATION
            WHERE MOLD_ID = {mold_pk}
            ORDER BY CREATED_AT DESC
            LIMIT {MAX_EVENT_ROWS}
            """)
        shots_since = query_records(f"""
            SELECT COUNT(*) AS SHOTS
            FROM MASTER_SHOT_TABLE
            WHERE MOLD_ID = {mold_pk}
              AND LOCAL_SHOT_TIME > (
                  SELECT COALESCE(MAX(MAINTENANCED_AT), '1970-01-01'::TIMESTAMP)
                  FROM MOLD_MAINTENANCE WHERE MOLD_ID = {mold_pk}
              )
            """)
        return {
            "status": "success",
            "mold": mold,
            "maintenance_events": maintenance,
            "location_history": locations,
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
            "LOCAL_SHOT_TIME >= DATEADD(day, -%d, '%s'::TIMESTAMP) "
            "AND LOCAL_SHOT_TIME < '%s'::TIMESTAMP"
            % (window_days, event_time, event_time)
        )
    else:
        time_filter = (
            "LOCAL_SHOT_TIME >= '%s'::TIMESTAMP "
            "AND LOCAL_SHOT_TIME < DATEADD(day, %d, '%s'::TIMESTAMP)"
            % (event_time, window_days, event_time)
        )
    rows = query_records(f"""
        SELECT AVG(CASE WHEN CT < {HARD_STOP_CT} THEN CT END) AS AVG_CT,
               COUNT(*) AS SHOTS
        FROM MASTER_SHOT_TABLE
        WHERE MOLD_ID = {mold_pk} AND {time_filter}
        """)
    row = rows[0] if rows else {}
    shots = row.get("SHOTS") or 0
    return {
        "avg_ct": round(row["AVG_CT"], 3) if row.get("AVG_CT") else None,
        "shots_per_day": round(shots / window_days, 1) if shots else None,
    }


def maintenance_impact_analysis(
    equipment_code: Optional[str] = None,
    mold_id: Optional[int] = None,
    window_days: int = DEFAULT_IMPACT_WINDOW_DAYS,
) -> Dict[str, Any]:
    """Measure whether maintenance events improved production metrics.

    Compares average CT and shots/day in equal windows before and after each
    completed maintenance event of the mold.

    Args:
        equipment_code: Equipment code of the mold (alternative to mold_id).
        mold_id: MOLD.ID primary key (alternative to equipment_code).
        window_days: Window length on each side of the event (default: 7, max: 90).

    Returns:
        dict with per-event before/after metrics and impact verdicts.
    """
    try:
        window_days = positive_int(window_days, "window_days", MAX_WINDOW_DAYS)
        molds = _find_molds(equipment_code, mold_id)
        if not molds:
            return {"status": "error", "error": "Mold not found"}
        mold = molds[0]
        mold_pk = int(mold["ID"])

        events = query_records(f"""
            SELECT ID, MAINTENANCED_AT, MAINTENANCE_STATUS, SHOT_COUNT
            FROM MOLD_MAINTENANCE
            WHERE MOLD_ID = {mold_pk} AND MAINTENANCED_AT IS NOT NULL
            ORDER BY MAINTENANCED_AT DESC
            LIMIT {MAX_EVENTS_ANALYZED}
            """)
        analyzed = []
        for event in events:
            event_time = event["MAINTENANCED_AT"]
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
            "mold_id": mold_pk,
            "equipment_code": mold.get("EQUIPMENT_CODE"),
            "window_days": window_days,
            "events_analyzed": len(analyzed),
            "events": analyzed,
        }
    except Exception as e:
        logger.error("maintenance_impact_analysis failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
