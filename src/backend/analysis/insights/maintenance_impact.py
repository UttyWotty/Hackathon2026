"""Before/after metric comparison around maintenance events.

Compares production metrics from windows before and after a maintenance event and
classifies the impact per metric, honoring metric direction (lower duration is better,
higher output is better). Pure logic: callers supply pre-aggregated window metrics.
"""

from typing import Any, Dict, Optional

LOWER_IS_BETTER: frozenset = frozenset({"avg_duration", "downtime_minutes", "stop_rate"})
NEUTRAL_THRESHOLD_PCT: float = 2.0

IMPACT_IMPROVED: str = "improved"
IMPACT_DEGRADED: str = "degraded"
IMPACT_NEUTRAL: str = "neutral"
IMPACT_UNKNOWN: str = "unknown"


def classify_metric_impact(
    metric: str,
    before: Optional[float],
    after: Optional[float],
    neutral_threshold_pct: float = NEUTRAL_THRESHOLD_PCT,
) -> Dict[str, Any]:
    """Classify the impact of a maintenance event on one metric.

    Args:
        metric: Metric name (direction looked up in LOWER_IS_BETTER).
        before: Metric value in the window before maintenance.
        after: Metric value in the window after maintenance.
        neutral_threshold_pct: Absolute change percentage below which the impact
            is considered neutral (default: 2.0).

    Returns:
        dict with before, after, change_pct, and impact label.
    """
    if before is None or after is None or before == 0:
        return {
            "before": before,
            "after": after,
            "change_pct": None,
            "impact": IMPACT_UNKNOWN,
        }

    change_pct = round((after - before) / abs(before) * 100.0, 2)
    if abs(change_pct) <= neutral_threshold_pct:
        impact = IMPACT_NEUTRAL
    elif (change_pct < 0) == (metric in LOWER_IS_BETTER):
        impact = IMPACT_IMPROVED
    else:
        impact = IMPACT_DEGRADED

    return {
        "before": before,
        "after": after,
        "change_pct": change_pct,
        "impact": impact,
    }


def compare_before_after(
    before_metrics: Dict[str, Optional[float]],
    after_metrics: Dict[str, Optional[float]],
    neutral_threshold_pct: float = NEUTRAL_THRESHOLD_PCT,
) -> Dict[str, Any]:
    """Compare all metrics across maintenance windows and summarize the verdict.

    Args:
        before_metrics: Metric name -> value for the window before maintenance.
        after_metrics: Same shape for the window after.
        neutral_threshold_pct: See classify_metric_impact.

    Returns:
        dict with per-metric impact details and an overall verdict based on the
        majority of non-unknown metric impacts.
    """
    metrics: Dict[str, Dict[str, Any]] = {}
    tallies = {IMPACT_IMPROVED: 0, IMPACT_DEGRADED: 0, IMPACT_NEUTRAL: 0}

    for metric in sorted(set(before_metrics) | set(after_metrics)):
        detail = classify_metric_impact(
            metric,
            before_metrics.get(metric),
            after_metrics.get(metric),
            neutral_threshold_pct,
        )
        metrics[metric] = detail
        if detail["impact"] in tallies:
            tallies[detail["impact"]] += 1

    if tallies[IMPACT_IMPROVED] > tallies[IMPACT_DEGRADED]:
        overall = IMPACT_IMPROVED
    elif tallies[IMPACT_DEGRADED] > tallies[IMPACT_IMPROVED]:
        overall = IMPACT_DEGRADED
    elif tallies[IMPACT_NEUTRAL] > 0:
        overall = IMPACT_NEUTRAL
    else:
        overall = IMPACT_UNKNOWN

    return {"metrics": metrics, "overall_impact": overall, "tallies": tallies}
