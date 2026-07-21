"""Tests for the metric definitions registry.

Verifies lookups (including case-insensitivity), the unknown-metric error, and that
every definition carries both a definition text and a source reference.
Pure tests over analysis.insights.metric_definitions.
"""

import pytest

from analysis.insights.metric_definitions import (
    METRIC_DEFINITIONS,
    UnknownMetricError,
    get_definition,
    get_definitions,
    list_metric_names,
)


def test_all_definitions_have_text_and_source():
    for name, entry in METRIC_DEFINITIONS.items():
        assert entry["definition"], name
        assert entry["source"], name


def test_lookup_case_insensitive():
    assert get_definition("MTTR") == METRIC_DEFINITIONS["mttr"]
    assert get_definition(" run_efficiency ") == METRIC_DEFINITIONS["run_efficiency"]


def test_unknown_metric_raises():
    with pytest.raises(UnknownMetricError):
        get_definition("nonexistent_metric")


def test_get_definitions_full_registry():
    assert get_definitions() == METRIC_DEFINITIONS


def test_get_definitions_filter_and_unknown():
    assert "mtbf" in get_definitions("mtbf")
    assert get_definitions("nonexistent_metric") == {}


def test_list_metric_names_sorted():
    names = list_metric_names()
    assert names == sorted(names)
    assert "health_score" in names
