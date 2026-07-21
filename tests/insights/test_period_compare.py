"""Tests for period comparison and top-mover ranking.

Verifies delta math (including zero/missing previous values), union behavior across
periods and metrics, magnitude-based ranking, and the unknown sort key error.
Pure tests over analysis.insights.period_compare.
"""

import pytest

from analysis.insights.period_compare import (
    UnknownSortKeyError,
    compare_metric_maps,
    compute_delta,
    rank_top_movers,
)


def test_compute_delta_basic():
    delta = compute_delta(120.0, 100.0)
    assert delta["absolute_change"] == 20.0
    assert delta["pct_change"] == 20.0


def test_compute_delta_zero_previous_has_no_pct():
    delta = compute_delta(50.0, 0.0)
    assert delta["absolute_change"] == 50.0
    assert delta["pct_change"] is None


def test_compute_delta_missing_values():
    delta = compute_delta(None, 10.0)
    assert delta["absolute_change"] is None
    assert delta["pct_change"] is None


def test_compare_metric_maps_union_of_entities():
    comparison = compare_metric_maps(
        {"eq1": {"shots": 100.0}},
        {"eq2": {"shots": 50.0}},
    )
    assert set(comparison) == {"eq1", "eq2"}
    assert comparison["eq1"]["shots"]["previous"] is None
    assert comparison["eq2"]["shots"]["current"] is None


def test_rank_top_movers_by_pct_magnitude():
    comparison = compare_metric_maps(
        {"a": {"shots": 110.0}, "b": {"shots": 30.0}, "c": {"shots": 100.0}},
        {"a": {"shots": 100.0}, "b": {"shots": 100.0}, "c": {"shots": 100.0}},
    )
    movers = rank_top_movers(comparison, "shots", top_n=2)
    assert [m["entity"] for m in movers] == ["b", "a"]
    assert movers[0]["pct_change"] == -70.0


def test_rank_top_movers_skips_entities_without_pct():
    comparison = compare_metric_maps({"a": {"shots": 10.0}}, {"b": {"shots": 5.0}})
    assert rank_top_movers(comparison, "shots") == []


def test_rank_top_movers_unknown_sort_key():
    with pytest.raises(UnknownSortKeyError):
        rank_top_movers({}, "shots", sort_by="bogus")
