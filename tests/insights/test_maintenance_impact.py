"""Tests for maintenance before/after impact classification.

Verifies direction-aware impact labels (lower duration is better, higher output is better),
the neutral threshold band, unknown handling, and overall verdict tallying.
Pure tests over analysis.insights.maintenance_impact.
"""

from analysis.insights.maintenance_impact import (
    IMPACT_DEGRADED,
    IMPACT_IMPROVED,
    IMPACT_NEUTRAL,
    IMPACT_UNKNOWN,
    classify_metric_impact,
    compare_before_after,
)


def test_lower_ct_after_maintenance_is_improvement():
    detail = classify_metric_impact("avg_duration", before=12.0, after=10.0)
    assert detail["impact"] == IMPACT_IMPROVED
    assert detail["change_pct"] == -16.67


def test_higher_ct_after_maintenance_is_degradation():
    detail = classify_metric_impact("avg_duration", before=10.0, after=12.0)
    assert detail["impact"] == IMPACT_DEGRADED


def test_higher_output_is_improvement():
    detail = classify_metric_impact("shots_per_day", before=100.0, after=120.0)
    assert detail["impact"] == IMPACT_IMPROVED


def test_small_change_is_neutral():
    detail = classify_metric_impact("avg_duration", before=100.0, after=101.0)
    assert detail["impact"] == IMPACT_NEUTRAL


def test_missing_values_are_unknown():
    assert classify_metric_impact("avg_duration", None, 10.0)["impact"] == IMPACT_UNKNOWN
    assert classify_metric_impact("avg_duration", 10.0, None)["impact"] == IMPACT_UNKNOWN
    assert classify_metric_impact("avg_duration", 0.0, 10.0)["impact"] == IMPACT_UNKNOWN


def test_overall_verdict_majority():
    result = compare_before_after(
        {"avg_duration": 12.0, "shots_per_day": 100.0, "downtime_minutes": 60.0},
        {"avg_duration": 10.0, "shots_per_day": 95.0, "downtime_minutes": 30.0},
    )
    assert result["metrics"]["avg_duration"]["impact"] == IMPACT_IMPROVED
    assert result["metrics"]["downtime_minutes"]["impact"] == IMPACT_IMPROVED
    assert result["metrics"]["shots_per_day"]["impact"] == IMPACT_DEGRADED
    assert result["overall_impact"] == IMPACT_IMPROVED
    assert result["tallies"][IMPACT_IMPROVED] == 2


def test_overall_unknown_when_no_data():
    result = compare_before_after({"avg_duration": None}, {"avg_duration": None})
    assert result["overall_impact"] == IMPACT_UNKNOWN
