"""Tests for the savings simulation module.

Verifies hours-saved arithmetic, cavity multiplication, non-applicable cases (already
at target, missing data), and batch aggregation ordering and totals.
Pure tests over analysis.insights.savings.
"""

from analysis.insights.savings import compute_record_savings, simulate_savings_records


def test_basic_savings():
    result = compute_record_savings(shots=3600, avg_duration=11.0, target_duration=10.0)
    assert result["applicable"] is True
    assert result["hours_saved"] == 1.0
    assert result["extra_parts_possible"] == 360


def test_cavities_multiply_extra_parts():
    result = compute_record_savings(
        shots=3600, avg_duration=11.0, target_duration=10.0, cavities=4
    )
    assert result["extra_parts_possible"] == 1440


def test_already_at_target_not_applicable():
    result = compute_record_savings(shots=1000, avg_duration=9.5, target_duration=10.0)
    assert result["applicable"] is False
    assert result["hours_saved"] == 0.0


def test_missing_data_not_applicable():
    assert compute_record_savings(0, 11.0, 10.0)["applicable"] is False
    assert compute_record_savings(100, None, 10.0)["applicable"] is False
    assert compute_record_savings(100, 11.0, None)["applicable"] is False
    assert compute_record_savings(100, 11.0, 0.0)["applicable"] is False


def test_batch_totals_and_ordering():
    records = [
        {
            "machine_id": "small",
            "shots": 3600,
            "avg_duration": 10.5,
            "target_duration": 10.0,
        },
        {
            "machine_id": "big",
            "shots": 7200,
            "avg_duration": 12.0,
            "target_duration": 10.0,
        },
        {
            "machine_id": "fine",
            "shots": 1000,
            "avg_duration": 10.0,
            "target_duration": 10.0,
        },
    ]
    result = simulate_savings_records(records)
    assert result["opportunities"] == 2
    assert result["records"][0]["machine_id"] == "big"
    assert result["total_hours_saved"] == 4.5
    assert result["total_extra_parts"] == 180 + 1440
