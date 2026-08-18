"""What-if savings simulation for duration improvements.

Computes the production time saved and the extra parts attainable if equipment ran at a
target duration (approved duration or best performer in its approved duration group) instead of
its observed average. Pure arithmetic: callers supply per equipment/part aggregates.
"""

from typing import Any, Dict, List, Optional

SECONDS_PER_HOUR: float = 3600.0
HOURS_PRECISION: int = 2
DEFAULT_CAVITIES: int = 1


def compute_record_savings(
    shots: int,
    avg_duration: Optional[float],
    target_duration: Optional[float],
    cavities: int = DEFAULT_CAVITIES,
) -> Dict[str, Any]:
    """Compute potential savings for one equipment/part aggregate.

    Args:
        shots: Shots produced in the analyzed window.
        avg_duration: Observed average duration in seconds.
        target_duration: Duration to simulate (approved or group-best), in seconds.
        cavities: Parts produced per shot (default: 1).

    Returns:
        dict with applicable flag, hours_saved, and extra_parts_possible. When the
        equipment already meets or beats the target (or data is missing), savings
        are zero and applicable is False.
    """
    if not shots or avg_duration is None or target_duration is None or target_duration <= 0:
        return {"applicable": False, "hours_saved": 0.0, "extra_parts_possible": 0}

    ct_gap = avg_duration - target_duration
    if ct_gap <= 0:
        return {"applicable": False, "hours_saved": 0.0, "extra_parts_possible": 0}

    seconds_saved = shots * ct_gap
    extra_parts = int(seconds_saved / target_duration) * max(cavities, DEFAULT_CAVITIES)
    return {
        "applicable": True,
        "hours_saved": round(seconds_saved / SECONDS_PER_HOUR, HOURS_PRECISION),
        "extra_parts_possible": extra_parts,
    }


def simulate_savings_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Simulate savings across a batch of aggregates.

    Args:
        records: Dicts with shots, avg_duration, target_duration, and optional cavities keys;
            identifying keys (machine_id, product_id, ...) are passed through.

    Returns:
        dict with per-record results (largest savings first) and totals.
    """
    results: List[Dict[str, Any]] = []
    total_hours = 0.0
    total_parts = 0

    for record in records:
        savings = compute_record_savings(
            int(record.get("shots", 0)),
            record.get("avg_duration"),
            record.get("target_duration"),
            int(record.get("cavities") or DEFAULT_CAVITIES),
        )
        total_hours += savings["hours_saved"]
        total_parts += savings["extra_parts_possible"]
        results.append({**record, **savings})

    results.sort(key=lambda r: r["hours_saved"], reverse=True)
    return {
        "records": results,
        "total_hours_saved": round(total_hours, HOURS_PRECISION),
        "total_extra_parts": total_parts,
        "opportunities": sum(1 for r in results if r["applicable"]),
    }
