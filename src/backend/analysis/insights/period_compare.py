"""Period-over-period metric comparison and top-mover ranking.

Computes absolute and percentage deltas between two periods of per-entity metric maps,
handling entities that appear in only one period, and ranks the largest movers.
Pure logic: callers supply already-aggregated metric maps per period.
"""

from typing import Any, Dict, List, Optional

SORT_BY_PCT: str = "pct_change"
SORT_BY_ABS: str = "absolute_change"
DEFAULT_TOP_N: int = 5


class UnknownSortKeyError(ValueError):
    """Raised when an unsupported sort key is requested for top movers."""


def compute_delta(
    current: Optional[float], previous: Optional[float]
) -> Dict[str, Optional[float]]:
    """Compute absolute and percentage change between two values.

    Args:
        current: Current-period value (None when absent).
        previous: Previous-period value (None when absent).

    Returns:
        dict with current, previous, absolute_change, pct_change. pct_change is
        None when the previous value is missing or zero.
    """
    absolute: Optional[float] = None
    pct: Optional[float] = None
    if current is not None and previous is not None:
        absolute = round(current - previous, 4)
        if previous != 0:
            pct = round((current - previous) / abs(previous) * 100.0, 2)
    return {
        "current": current,
        "previous": previous,
        "absolute_change": absolute,
        "pct_change": pct,
    }


def compare_metric_maps(
    current: Dict[str, Dict[str, float]],
    previous: Dict[str, Dict[str, float]],
) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
    """Compare per-entity metric maps between two periods.

    Args:
        current: Mapping of entity -> metric name -> value for the current period.
        previous: Same shape for the previous period.

    Returns:
        Mapping of entity -> metric name -> delta dict (see compute_delta).
        Entities and metrics present in either period are included.
    """
    result: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}
    for entity in sorted(set(current) | set(previous)):
        cur_metrics = current.get(entity, {})
        prev_metrics = previous.get(entity, {})
        result[entity] = {
            metric: compute_delta(cur_metrics.get(metric), prev_metrics.get(metric))
            for metric in sorted(set(cur_metrics) | set(prev_metrics))
        }
    return result


def rank_top_movers(
    comparison: Dict[str, Dict[str, Dict[str, Optional[float]]]],
    metric: str,
    top_n: int = DEFAULT_TOP_N,
    sort_by: str = SORT_BY_Pduration,
) -> List[Dict[str, Any]]:
    """Rank entities by the magnitude of change in one metric.

    Args:
        comparison: Output of compare_metric_maps.
        metric: Metric name to rank by.
        top_n: Number of entities to return (default: 5).
        sort_by: 'pct_change' or 'absolute_change' (default: 'pct_change').

    Returns:
        List of {entity, **delta} dicts sorted by descending absolute magnitude
        of the chosen change measure. Entities without that measure are skipped.

    Raises:
        UnknownSortKeyError: When sort_by is not a supported key.
    """
    if sort_by not in (SORT_BY_Pduration, SORT_BY_ABS):
        raise UnknownSortKeyError("Unsupported sort key: %s" % sort_by)

    movers: List[Dict[str, Any]] = []
    for entity, metrics in comparison.items():
        delta = metrics.get(metric)
        if delta is None or delta.get(sort_by) is None:
            continue
        movers.append({"entity": entity, "metric": metric, **delta})

    movers.sort(key=lambda m: abs(m[sort_by]), reverse=True)
    return movers[:top_n]
