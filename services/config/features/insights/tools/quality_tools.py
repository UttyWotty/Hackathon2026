"""Data quality audit tool adapter for the master shot data.

Runs integrity checks over a MASTER_SHOT_TABLE window: null keys, invalid cycle times,
missing approved CTs, future timestamps, and duplicate shots, with rate-based verdicts.
Exposes the data_quality_audit MCP tool.
"""

import logging
from typing import Any, Dict, List, Optional

from services.config.features.insights.tools.common import positive_int, query_records

logger = logging.getLogger(__name__)

MAX_WINDOW_DAYS: int = 365
DEFAULT_WINDOW_DAYS: int = 30
HARD_STOP_CT: float = 999.0
FUTURE_GRACE_HOURS: int = 24
WARN_RATE_PCT: float = 1.0
FAIL_RATE_PCT: float = 5.0

CHECK_PASS: str = "pass"
CHECK_WARN: str = "warn"
CHECK_FAIL: str = "fail"


def _verdict(count: int, total: int) -> Dict[str, Any]:
    """Rate-based verdict for one check."""
    rate = round(count / total * 100.0, 2) if total else 0.0
    if rate >= FAIL_RATE_PCT:
        status = CHECK_FAIL
    elif rate >= WARN_RATE_PCT or (count > 0 and total == 0):
        status = CHECK_WARN
    elif count > 0:
        status = CHECK_WARN
    else:
        status = CHECK_PASS
    return {"count": count, "rate_pct": rate, "status": status}


def _base_counts(days: int) -> Optional[Dict[str, Any]]:
    """Single-pass integrity counters over the window."""
    rows = query_records(f"""
        SELECT
            COUNT(*) AS TOTAL_SHOTS,
            COUNT(CASE WHEN EQUIPMENT_CODE IS NULL THEN 1 END) AS NULL_EQUIPMENT,
            COUNT(CASE WHEN CT IS NULL OR CT <= 0 THEN 1 END) AS INVALID_CT,
            COUNT(CASE WHEN CT >= {HARD_STOP_CT} THEN 1 END) AS HARD_STOP_SHOTS,
            COUNT(CASE WHEN APPROVED_CT IS NULL OR APPROVED_CT <= 0 THEN 1 END)
                AS MISSING_APPROVED_CT,
            COUNT(CASE WHEN LOCAL_SHOT_TIME >
                  DATEADD(hour, {FUTURE_GRACE_HOURS}, CURRENT_TIMESTAMP()) THEN 1 END)
                AS FUTURE_TIMESTAMPS
        FROM MASTER_SHOT_TABLE
        WHERE LOCAL_SHOT_TIME >= DATEADD(day, -{days}, CURRENT_DATE())
        """)
    return rows[0] if rows else None


def _duplicate_count(days: int) -> int:
    """Count of extra rows sharing (equipment, shot time) within the window."""
    rows = query_records(f"""
        SELECT COALESCE(SUM(DUP_COUNT - 1), 0) AS EXTRA_ROWS
        FROM (
            SELECT EQUIPMENT_CODE, LOCAL_SHOT_TIME, COUNT(*) AS DUP_COUNT
            FROM MASTER_SHOT_TABLE
            WHERE LOCAL_SHOT_TIME >= DATEADD(day, -{days}, CURRENT_DATE())
              AND EQUIPMENT_CODE IS NOT NULL
            GROUP BY EQUIPMENT_CODE, LOCAL_SHOT_TIME
            HAVING COUNT(*) > 1
        )
        """)
    return int(rows[0]["EXTRA_ROWS"]) if rows else 0


def data_quality_audit(days: int = DEFAULT_WINDOW_DAYS) -> Dict[str, Any]:
    """Audit MASTER_SHOT_TABLE integrity over a recent window.

    Args:
        days: Audit window in days (default: 30, max: 365).

    Returns:
        dict with per-check counts, rates, and pass/warn/fail verdicts, plus an
        overall worst-status rollup.
    """
    try:
        days = positive_int(days, "days", MAX_WINDOW_DAYS)
        base = _base_counts(days)
        if not base:
            return {"status": "error", "error": "No audit data returned"}

        total = int(base.get("TOTAL_SHOTS") or 0)
        checks: Dict[str, Dict[str, Any]] = {
            "null_equipment_code": _verdict(
                int(base.get("NULL_EQUIPMENT") or 0), total
            ),
            "invalid_ct": _verdict(int(base.get("INVALID_CT") or 0), total),
            "hard_stop_shots": _verdict(int(base.get("HARD_STOP_SHOTS") or 0), total),
            "missing_approved_ct": _verdict(
                int(base.get("MISSING_APPROVED_CT") or 0), total
            ),
            "future_timestamps": _verdict(
                int(base.get("FUTURE_TIMESTAMPS") or 0), total
            ),
            "duplicate_shots": _verdict(_duplicate_count(days), total),
        }

        statuses: List[str] = [c["status"] for c in checks.values()]
        if CHECK_FAIL in statuses:
            overall = CHECK_FAIL
        elif CHECK_WARN in statuses:
            overall = CHECK_WARN
        else:
            overall = CHECK_PASS

        return {
            "status": "success",
            "window_days": days,
            "total_shots": total,
            "overall": overall,
            "checks": checks,
            "notes": (
                "hard_stop_shots counts the CT=999.9 stop code; these are expected "
                "in normal operation and flagged only for visibility."
            ),
        }
    except Exception as e:
        logger.error("data_quality_audit failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
