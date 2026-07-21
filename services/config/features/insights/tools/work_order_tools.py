"""Work order genealogy tool adapter.

Traces a work order through its linked maintenance event, mold, mounted parts, and
recent production quality records to answer end-to-end "what happened" questions.
Exposes the trace_work_order MCP tool.
"""

import logging
from typing import Any, Dict, List, Optional

from services.config.features.insights.tools.common import query_records, safe_param

logger = logging.getLogger(__name__)

MAX_PRODUCED_PART_ROWS: int = 50


def _find_work_order(work_order_id: str) -> Optional[Dict[str, Any]]:
    """Find a work order by its business key or numeric primary key."""
    key = safe_param(work_order_id, "work_order_id")
    id_clause = "WORK_ORDER_ID = '%s'" % key
    if key.isdigit():
        id_clause += " OR ID = %s" % key
    rows = query_records(f"""
        SELECT ID, WORK_ORDER_ID, ORDER_TYPE, STATUS, PRIORITY, DETAILS,
               "START", "END", STARTED_ON, COMPLETED_ON, COST_ESTIMATE,
               MOLD_MAINTENANCE_ID, REPORT_FAILURE_SHOT, START_WORK_ORDER_SHOT,
               ACCUM_SHOT_COUNT, CREATED_AT
        FROM WORK_ORDER
        WHERE {id_clause}
        """)
    return rows[0] if rows else None


def _linked_maintenance(work_order: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Maintenance events linked from either side of the relationship."""
    clauses = []
    if work_order.get("MOLD_MAINTENANCE_ID"):
        clauses.append("ID = %d" % int(work_order["MOLD_MAINTENANCE_ID"]))
    clauses.append("WORK_ORDER_ID = %d" % int(work_order["ID"]))
    return query_records("""
        SELECT ID, MOLD_ID, MAINTENANCE_STATUS, MAINTENANCED_AT, START_TIME,
               END_TIME, SHOT_COUNT, ACCUMULATED_SHOT, MAINTENANCE_BY
        FROM MOLD_MAINTENANCE
        WHERE %s
        """ % " OR ".join(clauses))


def _mold_context(mold_pk: int) -> Dict[str, Any]:
    """Mold summary, mounted parts, and recent quality rows for a mold."""
    molds = query_records(f"""
        SELECT ID, EQUIPMENT_CODE, SUPPLIER_MOLD_CODE, TOOLING_STATUS,
               OPERATING_STATUS, DESIGNED_SHOT, LAST_SHOT, TOTAL_CAVITIES
        FROM MOLD WHERE ID = {mold_pk}
        """)
    parts = query_records(f"""
        SELECT mp.MOLD_ID, mp.PART_ID, mp.CAVITY, mp.TOTAL_CAVITIES,
               p.NAME AS PART_NAME, p.PART_CODE
        FROM MOLD_PART mp
        LEFT JOIN PART p ON p.ID = mp.PART_ID
        WHERE mp.MOLD_ID = {mold_pk}
        """)
    produced = query_records(f"""
        SELECT PART_ID, DAY, TOTAL_PRODUCED_AMOUNT, TOTAL_REJECTED_AMOUNT,
               REJECTED_RATE, REJECTED_RATE_STATUS
        FROM PRODUCED_PART
        WHERE MOLD_ID = {mold_pk}
        ORDER BY CREATED_AT DESC
        LIMIT {MAX_PRODUCED_PART_ROWS}
        """)
    return {
        "mold": molds[0] if molds else None,
        "parts": parts,
        "recent_production": produced,
    }


def trace_work_order(work_order_id: str) -> Dict[str, Any]:
    """Trace a work order to its maintenance event, mold, parts, and output.

    Args:
        work_order_id: WORK_ORDER.WORK_ORDER_ID business key or numeric ID.

    Returns:
        dict with the work order, linked maintenance events, and the mold context
        (mold summary, mounted parts, recent production quality rows).
    """
    try:
        work_order = _find_work_order(work_order_id)
        if not work_order:
            return {
                "status": "error",
                "error": "Work order not found: %s" % work_order_id,
            }

        maintenance = _linked_maintenance(work_order)
        mold_context: Optional[Dict[str, Any]] = None
        mold_ids = sorted({int(m["MOLD_ID"]) for m in maintenance if m.get("MOLD_ID")})
        if mold_ids:
            mold_context = _mold_context(mold_ids[0])

        return {
            "status": "success",
            "work_order": work_order,
            "maintenance_events": maintenance,
            "mold_context": mold_context,
        }
    except Exception as e:
        logger.error("trace_work_order failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
