"""Composite equipment health scoring from normalized component metrics.

Blends run efficiency, duration performance, utilization, and data recency into a
single 0-100 health score per equipment, renormalizing weights when components are missing.
Pure logic: callers supply already-normalized component values in the 0-100 range.
"""

from typing import Any, Dict, List, Optional, Tuple

HEALTH_WEIGHTS: Dict[str, float] = {
    "run_efficiency": 0.40,
    "duration_performance": 0.30,
    "utilization": 0.20,
    "recency": 0.10,
}

GRADE_HEALTHY_MIN: float = 80.0
GRADE_WATCH_MIN: float = 60.0

GRADE_HEALTHY: str = "healthy"
GRADE_WATCH: str = "watch"
GRADE_CRITICAL: str = "critical"
GRADE_UNKNOWN: str = "unknown"

COMPONENT_MIN: float = 0.0
COMPONENT_MAX: float = 100.0


class InvalidComponentError(ValueError):
    """Raised when a health component value is outside the 0-100 range."""


def clamp_component(value: float) -> float:
    """Clamp a component value into the 0-100 range."""
    return max(COMPONENT_MIN, min(COMPONENT_MAX, value))


def compute_health_score(
    components: Dict[str, Optional[float]],
) -> Tuple[Optional[float], List[str]]:
    """Compute the weighted health score from component values.

    Args:
        components: Mapping of component name to a 0-100 value, or None when the
            component has no data. Unknown component names are ignored.

    Returns:
        Tuple of (score or None when no component has data, list of missing
        component names).
    """
    weighted_sum = 0.0
    weight_total = 0.0
    missing: List[str] = []

    for name, weight in HEALTH_WEIGHTS.items():
        value = components.get(name)
        if value is None:
            missing.append(name)
            continue
        weighted_sum += clamp_component(float(value)) * weight
        weight_total += weight

    if weight_total == 0.0:
        return None, missing

    return round(weighted_sum / weight_total, 1), missing


def grade_score(score: Optional[float]) -> str:
    """Map a health score to a grade label."""
    if score is None:
        return GRADE_UNKNOWN
    if score >= GRADE_HEALTHY_MIN:
        return GRADE_HEALTHY
    if score >= GRADE_WATCH_MIN:
        return GRADE_WATCH
    return GRADE_CRITICAL


def build_equipment_health(
    machine_id: str, components: Dict[str, Optional[float]]
) -> Dict[str, Any]:
    """Build the full health record for one equipment.

    Args:
        machine_id: Equipment identifier.
        components: Component values in the 0-100 range (None when missing).

    Returns:
        dict with machine_id, score, grade, components, and missing_components.
    """
    score, missing = compute_health_score(components)
    return {
        "machine_id": machine_id,
        "score": score,
        "grade": grade_score(score),
        "components": {k: components.get(k) for k in HEALTH_WEIGHTS},
        "missing_components": missing,
    }


def rank_by_health(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort health records worst-first; records without a score go last."""
    scored = [r for r in records if r.get("score") is not None]
    unscored = [r for r in records if r.get("score") is None]
    return sorted(scored, key=lambda r: r["score"]) + unscored
