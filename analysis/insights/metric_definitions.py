"""Canonical metric definitions for the manufacturing analytics platform.

Static registry of how each core metric is defined and calculated, sourced from
analysis/runrate/CALCULATION_SPEC.md and the analytics pipeline implementations.
Pure data module so every LLM answer uses identical definitions across sessions.
"""

from typing import Any, Dict, List, Optional

SPEC_PATH: str = "analysis/runrate/CALCULATION_SPEC.md"

METRIC_DEFINITIONS: Dict[str, Dict[str, str]] = {
    "production_run": {
        "definition": (
            "A contiguous block of shots on one equipment. Any gap longer than 8 "
            "hours (RUN_INTERVAL_THRESHOLD, 28800 seconds) starts a new run; the "
            "gap itself is excluded from all calculations."
        ),
        "source": SPEC_PATH,
    },
    "mode_ct": {
        "definition": (
            "Statistical mode of actual cycle times excluding the 999.9 hard-stop "
            "code, with a +/-5 percent tolerance band (MODE_CT_TOLERANCE). Baseline "
            "for stop detection and efficiency."
        ),
        "source": SPEC_PATH,
    },
    "stop_detection": {
        "definition": (
            "A shot is a stop (STOP=1) when its time gap exceeds the previous cycle "
            "time plus the 2.0 second downtime gap tolerance, or when the cycle time "
            "is the 999.9 hard-stop code."
        ),
        "source": SPEC_PATH,
    },
    "total_run_time": {
        "definition": (
            "Sum of shot intervals within each run (excluding each run's first-shot "
            "interval) plus one mode CT for the last shot, in minutes."
        ),
        "source": SPEC_PATH,
    },
    "production_time": {
        "definition": (
            "Sum of shot intervals for normal shots (STOP=0, excluding first-shot "
            "intervals), in minutes."
        ),
        "source": SPEC_PATH,
    },
    "downtime": {
        "definition": "Sum of adjusted cycle seconds for stop shots (STOP=1), in minutes.",
        "source": SPEC_PATH,
    },
    "run_efficiency": {
        "definition": "PRODUCTION_TIME divided by TOTAL_RUN_TIME, as a percentage.",
        "source": SPEC_PATH,
    },
    "mttr": {
        "definition": "Mean time to repair: total downtime divided by the number of stop events.",
        "source": SPEC_PATH,
    },
    "mtbf": {
        "definition": (
            "Mean time between failures: total production time divided by the number "
            "of stop events."
        ),
        "source": SPEC_PATH,
    },
    "approved_ct": {
        "definition": (
            "Contractually approved cycle time per part/tool. Known to drift stale; "
            "validate against observed mode CT (validate_approved_cts tool). Tool "
            "comparisons are only meaningful within the same approved CT group."
        ),
        "source": "MASTER_SHOT_TABLE.APPROVED_CT",
    },
    "ct_efficiency": {
        "definition": (
            "Share of shots within/faster/slower than the approved CT band, weighted "
            "into a single efficiency percentage (WEIGHTED_EFFICIENCY in CT_EFFICIENCY)."
        ),
        "source": "analysis/ct_efficiency",
    },
    "nctd": {
        "definition": (
            "Normalized cycle time deviation: (average CT - approved CT) relative to "
            "approved CT, as stored in CYCLE_TIME_DEVIATION.NCTD."
        ),
        "source": "analysis/ct_deviation",
    },
    "capacity_utilization": {
        "definition": (
            "Actual output versus optimal output at a target cycle time (approved, "
            "mode, or weighted-average CT scenarios in CAPACITY_DAILY/WEEKLY)."
        ),
        "source": "analysis/capacity",
    },
    "health_score": {
        "definition": (
            "Composite 0-100 equipment score: run efficiency 40 percent, CT "
            "performance 30 percent, utilization 20 percent, data recency 10 "
            "percent; weights renormalize when a component is missing. Grades: "
            "healthy >= 80, watch >= 60, critical below."
        ),
        "source": "analysis/insights/health_score.py",
    },
}


class UnknownMetricError(KeyError):
    """Raised when a metric name is not in the definitions registry."""


def list_metric_names() -> List[str]:
    """Sorted list of all defined metric names."""
    return sorted(METRIC_DEFINITIONS)


def get_definition(metric: str) -> Dict[str, str]:
    """Look up one metric definition.

    Args:
        metric: Metric name (case-insensitive).

    Returns:
        dict with definition and source.

    Raises:
        UnknownMetricError: When the metric is not defined.
    """
    key = metric.strip().lower()
    if key not in METRIC_DEFINITIONS:
        raise UnknownMetricError(metric)
    return METRIC_DEFINITIONS[key]


def get_definitions(metric: Optional[str] = None) -> Dict[str, Any]:
    """Return one definition or the full registry.

    Args:
        metric: Optional metric name filter.

    Returns:
        dict keyed by metric name. Unknown names return an empty dict.
    """
    if metric is None:
        return dict(METRIC_DEFINITIONS)
    try:
        return {metric.strip().lower(): get_definition(metric)}
    except UnknownMetricError:
        return {}
