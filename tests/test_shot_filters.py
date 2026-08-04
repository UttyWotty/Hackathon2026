"""
Tests for the pure MASTER_SHOT_TABLE filter predicates.

Asserts that the local CSV path applies the same validity bounds, date windows
and membership rules as the analysis SQL, since any divergence would make local
results silently disagree with Snowflake. Pure logic: no I/O and no fixtures on
disk.
"""

import pandas as pd
import pytest

from analysis.shared.shot_filters import (
    MAX_VALID_CT,
    START_OF_DAY,
    apply_date_filter,
    apply_membership_filter,
    apply_validity_filter,
    filter_shots,
)


@pytest.fixture
def shots() -> pd.DataFrame:
    """Eight rows spanning three days, two machines and two suppliers."""
    return pd.DataFrame(
        {
            "CT": [10.0, 12.0, 11.0, 0.0, None, 1000.0, 9.0, 13.0],
            "APPROVED_CT": [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 0.0, 10.0],
            "LOCAL_SHOT_TIME": pd.to_datetime(
                [
                    "2026-06-08 06:00",
                    "2026-06-09 06:00",
                    "2026-06-10 23:59",
                    "2026-06-08 07:00",
                    "2026-06-08 08:00",
                    "2026-06-08 09:00",
                    "2026-06-08 10:00",
                    "2026-06-10 06:00",
                ]
            ),
            "EQUIPMENT_CODE": [
                "MX-7101",
                "MX-7103",
                "MX-7101",
                "MX-7101",
                "MX-7101",
                "MX-7101",
                "MX-7101",
                "MX-7103",
            ],
            "SUPPLIER_NAME": ["A", "B", "A", "A", "A", "A", "A", "B"],
        }
    )


class TestValidityFilter:
    def test_drops_null_and_non_positive_and_sentinel_rows(self, shots):
        kept = apply_validity_filter(shots)
        # Rows dropped: CT=0, CT=None, CT=1000 (>= 999.9), APPROVED_CT=0.
        assert len(kept) == 4
        assert kept["CT"].tolist() == [10.0, 12.0, 11.0, 13.0]

    def test_boundary_ct_is_excluded(self):
        frame = pd.DataFrame({"CT": [MAX_VALID_CT], "APPROVED_CT": [10.0]})
        assert apply_validity_filter(frame).empty

    def test_just_below_boundary_is_kept(self):
        frame = pd.DataFrame({"CT": [MAX_VALID_CT - 0.1], "APPROVED_CT": [10.0]})
        assert len(apply_validity_filter(frame)) == 1


class TestDateFilter:
    def test_end_date_includes_the_whole_day(self, shots):
        # A row at 23:59 on the end date must survive; a naive <= on the date
        # literal would drop it.
        kept = apply_date_filter(shots, end_date="2026-06-10")
        assert (kept["LOCAL_SHOT_TIME"].dt.day == 10).sum() == 2

    def test_start_date_is_inclusive(self, shots):
        kept = apply_date_filter(shots, start_date="2026-06-09")
        assert kept["LOCAL_SHOT_TIME"].min() == pd.Timestamp("2026-06-09 06:00")

    def test_window_bounds_both_ends(self, shots):
        kept = apply_date_filter(shots, "2026-06-09", "2026-06-09")
        assert len(kept) == 1

    def test_no_bounds_returns_everything(self, shots):
        assert len(apply_date_filter(shots)) == len(shots)


class TestMembershipFilter:
    def test_equipment_subset(self, shots):
        kept = apply_membership_filter(shots, equipment_codes=["MX-7103"])
        assert set(kept["EQUIPMENT_CODE"]) == {"MX-7103"}

    def test_wildcard_means_all_equipment(self, shots):
        # The sense tools pass ["*"] for "every machine".
        assert len(apply_membership_filter(shots, equipment_codes=["*"])) == len(shots)

    def test_supplier_subset(self, shots):
        kept = apply_membership_filter(shots, supplier_names=["B"])
        assert set(kept["SUPPLIER_NAME"]) == {"B"}

    def test_none_means_no_filtering(self, shots):
        assert len(apply_membership_filter(shots)) == len(shots)


class TestFilterShots:
    def test_result_is_ordered_by_shot_time(self, shots):
        out = filter_shots(shots)
        assert out["LOCAL_SHOT_TIME"].is_monotonic_increasing

    def test_index_is_reset(self, shots):
        # Downstream analysis assumes positional integrity after ORDER BY.
        assert filter_shots(shots).index.tolist() == list(range(4))

    def test_predicates_compose(self, shots):
        out = filter_shots(shots, start_date="2026-06-09", equipment_codes=["MX-7103"])
        assert len(out) == 2
        assert set(out["EQUIPMENT_CODE"]) == {"MX-7103"}

    def test_validity_can_be_disabled(self, shots):
        assert len(filter_shots(shots, validity=False)) == len(shots)


class TestEndBoundDivergence:
    """The three analyses use three different end-date conventions."""

    @pytest.fixture
    def late(self) -> pd.DataFrame:
        """One shot at the very end of the day, one at midday."""
        return pd.DataFrame(
            {
                "CT": [10.0, 10.0],
                "APPROVED_CT": [10.0, 10.0],
                "LOCAL_SHOT_TIME": pd.to_datetime(
                    ["2026-06-10 12:00:00.000", "2026-06-10 23:59:59.500"],
                    format="ISO8601",
                ),
                "EQUIPMENT_CODE": ["MX-7101", "MX-7101"],
                "SUPPLIER_NAME": ["A", "A"],
            }
        )

    def test_ct_deviation_bound_excludes_sub_second_tail(self, late):
        # SQL says `<= '2026-06-10 23:59:59'`, so 23:59:59.5 is OUT. Writing
        # this as `< the next day` would wrongly include it.
        kept = apply_date_filter(late, end_date="2026-06-10")
        assert len(kept) == 1
        assert kept["LOCAL_SHOT_TIME"].iloc[0].hour == 12

    def test_ct_efficiency_bound_is_midnight(self, late):
        # `<= '2026-06-10'` is midnight, so the whole day is excluded.
        kept = apply_date_filter(late, end_date="2026-06-10", end_time=START_OF_DAY)
        assert kept.empty
