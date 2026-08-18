"""Tests for approved target staleness validation.

Verifies status classification (ok, stale, missing approved, insufficient data),
deviation math, suggested duration proposals, and batch summary ordering.
Pure tests over analysis.insights.target_validation.
"""

from analysis.insights.target_validation import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_MISSING_APPROVED,
    STATUS_OK,
    STATUS_STALE,
    validate_ct_record,
    validate_ct_records,
)


def test_ok_within_threshold():
    verdict = validate_ct_record(30.0, 32.0, shot_count=500)
    assert verdict["status"] == STATUS_OK
    assert verdict["deviation_pct"] == 6.67
    assert verdict["suggested_duration"] is None


def test_stale_above_threshold_suggests_observed():
    verdict = validate_ct_record(30.0, 36.0, shot_count=500)
    assert verdict["status"] == STATUS_STALE
    assert verdict["deviation_pct"] == 20.0
    assert verdict["suggested_duration"] == 36.0


def test_stale_when_observed_much_faster():
    verdict = validate_ct_record(30.0, 24.0, shot_count=500)
    assert verdict["status"] == STATUS_STALE
    assert verdict["deviation_pct"] == -20.0


def test_missing_target_duration():
    verdict = validate_ct_record(None, 25.0, shot_count=500)
    assert verdict["status"] == STATUS_MISSING_APPROVED
    assert verdict["suggested_duration"] == 25.0


def test_insufficient_shots():
    verdict = validate_ct_record(30.0, 40.0, shot_count=10)
    assert verdict["status"] == STATUS_INSUFFICIENT_DATA


def test_custom_threshold():
    verdict = validate_ct_record(30.0, 32.0, shot_count=500, stale_threshold_pct=5.0)
    assert verdict["status"] == STATUS_STALE


def test_batch_summary_and_ordering():
    records = [
        {
            "machine_id": "a",
            "target_duration": 30.0,
            "observed_duration": 33.5,
            "shot_count": 500,
        },
        {
            "machine_id": "b",
            "target_duration": 30.0,
            "observed_duration": 45.0,
            "shot_count": 500,
        },
        {
            "machine_id": "c",
            "target_duration": None,
            "observed_duration": 20.0,
            "shot_count": 500,
        },
        {
            "machine_id": "d",
            "target_duration": 30.0,
            "observed_duration": 30.5,
            "shot_count": 500,
        },
    ]
    result = validate_ct_records(records)
    assert result["total"] == 4
    assert result["summary"][STATUS_STALE] == 2
    assert result["summary"][STATUS_MISSING_APPROVED] == 1
    assert result["summary"][STATUS_OK] == 1
    assert [r["machine_id"] for r in result["stale_records"]] == ["b", "a"]
