"""Tests for data freshness classification.

Verifies age computation, fresh/stale/dead boundaries with the dead multiplier,
no-data handling, and the full freshness entry shape.
Pure tests over analysis.insights.freshness.
"""

from datetime import datetime, timedelta

from analysis.insights.freshness import (
    STATUS_DEAD,
    STATUS_FRESH,
    STATUS_NO_DATA,
    STATUS_STALE,
    age_hours,
    build_freshness_entry,
    classify_freshness,
)

NOW = datetime(2026, 6, 11, 12, 0, 0)


def test_age_hours():
    assert age_hours(NOW - timedelta(hours=5), NOW) == 5.0
    assert age_hours(None, NOW) is None


def test_classification_boundaries():
    assert classify_freshness(10.0, expected_max_age_hours=24.0) == STATUS_FRESH
    assert classify_freshness(24.0, expected_max_age_hours=24.0) == STATUS_FRESH
    assert classify_freshness(25.0, expected_max_age_hours=24.0) == STATUS_STALE
    assert classify_freshness(72.0, expected_max_age_hours=24.0) == STATUS_STALE
    assert classify_freshness(72.1, expected_max_age_hours=24.0) == STATUS_DEAD
    assert classify_freshness(None, expected_max_age_hours=24.0) == STATUS_NO_DATA


def test_build_entry_shape():
    entry = build_freshness_entry(
        "SHOT_DATA", NOW - timedelta(hours=30), NOW, expected_max_age_hours=24.0
    )
    assert entry["source"] == "SHOT_DATA"
    assert entry["age_hours"] == 30.0
    assert entry["status"] == STATUS_STALE
    assert entry["last_data_time"].startswith("2026-06-10")


def test_build_entry_no_data():
    entry = build_freshness_entry("EMPTY_TABLE", None, NOW, expected_max_age_hours=24.0)
    assert entry["status"] == STATUS_NO_DATA
    assert entry["last_data_time"] is None
