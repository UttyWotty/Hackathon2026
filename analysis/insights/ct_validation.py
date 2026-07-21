"""Approved cycle time staleness validation against observed production CTs.

Compares each record's approved CT to the observed (mode) CT and classifies it as ok,
stale, missing data, or insufficient sample, suggesting an updated approved CT when stale.
Pure logic: callers supply per equipment/part records with observed statistics.
"""

from typing import Any, Dict, List, Optional

DEFAULT_STALE_THRESHOLD_PCT: float = 10.0
DEFAULT_MIN_SHOTS: int = 100

STATUS_OK: str = "ok"
STATUS_STALE: str = "stale"
STATUS_MISSING_APPROVED: str = "missing_approved_ct"
STATUS_INSUFFICIENT_DATA: str = "insufficient_data"

SUGGESTED_CT_PRECISION: int = 2


def validate_ct_record(
    approved_ct: Optional[float],
    observed_ct: Optional[float],
    shot_count: int,
    stale_threshold_pct: float = DEFAULT_STALE_THRESHOLD_PCT,
    min_shots: int = DEFAULT_MIN_SHOTS,
) -> Dict[str, Any]:
    """Classify one approved CT against its observed CT.

    Args:
        approved_ct: Approved cycle time in seconds (None when not set).
        observed_ct: Observed representative CT (e.g., mode) in seconds.
        shot_count: Number of shots backing the observation.
        stale_threshold_pct: Deviation percentage above which the approved CT is
            considered stale (default: 10.0).
        min_shots: Minimum shots required to judge (default: 100).

    Returns:
        dict with status, deviation_pct, and suggested_ct (observed CT when stale).
    """
    if approved_ct is None or approved_ct <= 0:
        return {
            "status": STATUS_MISSING_APPROVED,
            "deviation_pct": None,
            "suggested_ct": (
                round(observed_ct, SUGGESTED_CT_PRECISION) if observed_ct else None
            ),
        }
    if observed_ct is None or observed_ct <= 0 or shot_count < min_shots:
        return {
            "status": STATUS_INSUFFICIENT_DATA,
            "deviation_pct": None,
            "suggested_ct": None,
        }

    deviation_pct = round((observed_ct - approved_ct) / approved_ct * 100.0, 2)
    if abs(deviation_pct) > stale_threshold_pct:
        return {
            "status": STATUS_STALE,
            "deviation_pct": deviation_pct,
            "suggested_ct": round(observed_ct, SUGGESTED_CT_PRECISION),
        }
    return {"status": STATUS_OK, "deviation_pct": deviation_pct, "suggested_ct": None}


def validate_ct_records(
    records: List[Dict[str, Any]],
    stale_threshold_pct: float = DEFAULT_STALE_THRESHOLD_PCT,
    min_shots: int = DEFAULT_MIN_SHOTS,
) -> Dict[str, Any]:
    """Validate a batch of approved CT records.

    Args:
        records: Dicts with at least approved_ct, observed_ct, shot_count keys;
            other keys (equipment_code, part_id, ...) are passed through.
        stale_threshold_pct: See validate_ct_record.
        min_shots: See validate_ct_record.

    Returns:
        dict with per-record validations and a status-count summary, with stale
        records ordered by descending absolute deviation.
    """
    validated: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {
        STATUS_OK: 0,
        STATUS_STALE: 0,
        STATUS_MISSING_APPROVED: 0,
        STATUS_INSUFFICIENT_DATA: 0,
    }

    for record in records:
        verdict = validate_ct_record(
            record.get("approved_ct"),
            record.get("observed_ct"),
            int(record.get("shot_count", 0)),
            stale_threshold_pct,
            min_shots,
        )
        counts[verdict["status"]] += 1
        validated.append({**record, **verdict})

    stale = [v for v in validated if v["status"] == STATUS_STALE]
    stale.sort(key=lambda v: abs(v["deviation_pct"]), reverse=True)

    return {
        "records": validated,
        "stale_records": stale,
        "summary": counts,
        "total": len(validated),
    }
