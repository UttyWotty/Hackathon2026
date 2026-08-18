"""Approved duration staleness validation against observed production CTs.

Compares each record's approved duration to the observed (mode) duration and classifies it as ok,
stale, missing data, or insufficient sample, suggesting an updated approved duration when stale.
Pure logic: callers supply per equipment/part records with observed statistics.
"""

from typing import Any, Dict, List, Optional

DEFAULT_STALE_THRESHOLD_PCT: float = 10.0
DEFAULT_MIN_SHOTS: int = 100

STATUS_OK: str = "ok"
STATUS_STALE: str = "stale"
STATUS_MISSING_APPROVED: str = "missing_target_duration"
STATUS_INSUFFICIENT_DATA: str = "insufficient_data"

SUGGESTED_CT_PRECISION: int = 2


def validate_ct_record(
    target_duration: Optional[float],
    observed_duration: Optional[float],
    shot_count: int,
    stale_threshold_pct: float = DEFAULT_STALE_THRESHOLD_PCT,
    min_shots: int = DEFAULT_MIN_SHOTS,
) -> Dict[str, Any]:
    """Classify one approved duration against its observed duration.

    Args:
        target_duration: Approved duration in seconds (None when not set).
        observed_duration: Observed representative duration (e.g., mode) in seconds.
        shot_count: Number of shots backing the observation.
        stale_threshold_pct: Deviation percentage above which the approved duration is
            considered stale (default: 10.0).
        min_shots: Minimum shots required to judge (default: 100).

    Returns:
        dict with status, deviation_pct, and suggested_duration (observed duration when stale).
    """
    if target_duration is None or target_duration <= 0:
        return {
            "status": STATUS_MISSING_APPROVED,
            "deviation_pct": None,
            "suggested_duration": (
                round(observed_duration, SUGGESTED_CT_PRECISION) if observed_duration else None
            ),
        }
    if observed_duration is None or observed_duration <= 0 or shot_count < min_shots:
        return {
            "status": STATUS_INSUFFICIENT_DATA,
            "deviation_pct": None,
            "suggested_duration": None,
        }

    deviation_pct = round((observed_duration - target_duration) / target_duration * 100.0, 2)
    if abs(deviation_pct) > stale_threshold_pct:
        return {
            "status": STATUS_STALE,
            "deviation_pct": deviation_pct,
            "suggested_duration": round(observed_duration, SUGGESTED_CT_PRECISION),
        }
    return {"status": STATUS_OK, "deviation_pct": deviation_pct, "suggested_duration": None}


def validate_ct_records(
    records: List[Dict[str, Any]],
    stale_threshold_pct: float = DEFAULT_STALE_THRESHOLD_PCT,
    min_shots: int = DEFAULT_MIN_SHOTS,
) -> Dict[str, Any]:
    """Validate a batch of approved duration records.

    Args:
        records: Dicts with at least target_duration, observed_duration, shot_count keys;
            other keys (machine_id, product_id, ...) are passed through.
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
            record.get("target_duration"),
            record.get("observed_duration"),
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
