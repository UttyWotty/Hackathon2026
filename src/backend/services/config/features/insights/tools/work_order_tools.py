"""Work order trace tool adapter.

Traces a work order through its linked tool and production data to answer
end-to-end 'what happened' questions. Uses WORK_ORDER and TOOL tables.
"""

import logging
from typing import Any, Dict, Optional

from services.config.features.insights.tools.common import query_records, safe_param

logger = logging.getLogger(__name__)


def _find_work_order(work_order_id: str) -> Optional[Dict[str, Any]]:
    """Find a work order by numeric ID."""
    key = safe_param(work_order_id, "work_order_id")
    id_clause = "ID = %s" % key if key.isdigit() else "1=0"
    rows = query_records(f"""
        SELECT ID, TOOL_ID, STATUS, COMPLETED_AT, ORDER_TYPE
        FROM WORK_ORDER
        WHERE {id_clause}
        """)
    return rows[0] if rows else None


def _tool_context(tool_id: int) -> Dict[str, Any]:
    """Tool summary for a given tool ID."""
    tools = query_records(f"""
        SELECT ID, MACHINE_ID, TYPE, TARGET_DURATION,
               TOTAL_CAVITIES, DESIGNED_SHOT, MAX_DAILY_OUTPUT
        FROM TOOL WHERE ID = {tool_id}
        """)
    return {"tool": tools[0] if tools else None}


def trace_work_order(work_order_id: str) -> Dict[str, Any]:
    """Trace a work order to its linked tool and context.

    Args:
        work_order_id: WORK_ORDER.ID numeric key.

    Returns:
        dict with the work order and tool context.
    """
    try:
        work_order = _find_work_order(work_order_id)
        if not work_order:
            return {
                "status": "error",
                "error": "Work order not found: %s" % work_order_id,
            }

        tool_context: Optional[Dict[str, Any]] = None
        if work_order.get("TOOL_ID"):
            tool_context = _tool_context(int(work_order["TOOL_ID"]))

        return {
            "status": "success",
            "work_order": work_order,
            "tool_context": tool_context,
        }
    except Exception as e:
        logger.error("trace_work_order failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
