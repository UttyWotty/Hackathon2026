"""Tests for the equipment health scoring module.

Verifies weighted scoring, weight renormalization with missing components, grade
boundaries, and worst-first ranking behavior.
Pure tests over analysis.insights.health_score.
"""

from analysis.insights.health_score import (
    GRADE_CRITICAL,
    GRADE_HEALTHY,
    GRADE_UNKNOWN,
    GRADE_WATCH,
    build_equipment_health,
    compute_health_score,
    grade_score,
    rank_by_health,
)


def test_full_components_weighted_average():
    score, missing = compute_health_score(
        {
            "run_efficiency": 100.0,
            "ct_performance": 100.0,
            "utilization": 100.0,
            "recency": 100.0,
        }
    )
    assert score == 100.0
    assert missing == []


def test_missing_components_renormalize():
    score, missing = compute_health_score(
        {
            "run_efficiency": 80.0,
            "ct_performance": None,
            "utilization": None,
            "recency": None,
        }
    )
    assert score == 80.0
    assert set(missing) == {"ct_performance", "utilization", "recency"}


def test_all_missing_returns_none():
    score, missing = compute_health_score({})
    assert score is None
    assert len(missing) == 4


def test_values_clamped_to_range():
    score, _ = compute_health_score(
        {
            "run_efficiency": 250.0,
            "ct_performance": -50.0,
            "utilization": None,
            "recency": None,
        }
    )
    assert score == round((100.0 * 0.4 + 0.0 * 0.3) / 0.7, 1)


def test_grade_boundaries():
    assert grade_score(80.0) == GRADE_HEALTHY
    assert grade_score(79.9) == GRADE_WATCH
    assert grade_score(60.0) == GRADE_WATCH
    assert grade_score(59.9) == GRADE_CRITICAL
    assert grade_score(None) == GRADE_UNKNOWN


def test_build_equipment_health_shape():
    record = build_equipment_health("6377", {"run_efficiency": 90.0})
    assert record["equipment_code"] == "6377"
    assert record["score"] == 90.0
    assert record["grade"] == GRADE_HEALTHY
    assert "ct_performance" in record["components"]


def test_rank_by_health_worst_first_unscored_last():
    records = [
        {"equipment_code": "a", "score": 90.0},
        {"equipment_code": "b", "score": 20.0},
        {"equipment_code": "c", "score": None},
        {"equipment_code": "d", "score": 55.0},
    ]
    ranked = rank_by_health(records)
    assert [r["equipment_code"] for r in ranked] == ["b", "d", "a", "c"]
