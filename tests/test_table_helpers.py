"""Tests for the shared table-rendering helpers in src/frontend/tables.py.

Covers label mapping, the fallback for columns with no explicit label, and the
number formats selected per column kind. Rendering itself is not exercised;
these tests cover the pure mapping logic only.
"""

import sys
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "src" / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

import tables  # noqa: E402


def _format_of(columns, column):
    """Return the number format the pure spec assigns to a column.

    Deliberately targets `tables.column_specs` rather than
    `tables.build_column_config`: another test in this suite replaces the
    `streamlit` module with a MagicMock, so anything reaching through
    `st.column_config` yields mocks and cannot be asserted on.
    """
    return tables.column_specs(columns)[column].number_format


class TestLabelFor:
    """Tests for tables.label_for."""

    @pytest.mark.parametrize(
        "column,expected",
        [
            ("MACHINE_ID", "Machine"),
            ("DEVIATION_PCT", "Deviation"),
            ("STABILITY_SCORE", "Stability"),
            ("NOTE_TEXT", "Note"),
            ("RESULT_SUMMARY", "Result"),
        ],
    )
    def test_maps_known_columns(self, column, expected):
        assert tables.label_for(column) == expected

    def test_unknown_column_falls_back_to_title_case(self):
        assert tables.label_for("SOME_NEW_COLUMN") == "Some New Column"

    def test_fallback_never_returns_a_raw_sql_name(self):
        assert "_" not in tables.label_for("ANOTHER_UNMAPPED_COL")

    def test_no_label_is_empty(self):
        for column in tables._LABELS:
            assert tables.label_for(column).strip()


class TestColumnConfig:
    """Tests for tables.build_column_config."""

    def test_percent_columns_get_a_percent_format(self):
        cols = ["DEVIATION_PCT", "LIFE_USED_PCT"]
        assert _format_of(cols, "DEVIATION_PCT") == "%.1f%%"
        assert _format_of(cols, "LIFE_USED_PCT") == "%.1f%%"

    def test_stability_score_is_treated_as_a_percentage(self):
        assert _format_of(["STABILITY_SCORE"], "STABILITY_SCORE") == "%.1f%%"

    def test_count_columns_get_an_integer_format(self):
        assert _format_of(["SHOT_COUNT"], "SHOT_COUNT") == "%d"

    def test_duration_columns_get_two_decimals(self):
        assert _format_of(["AVG_DURATION"], "AVG_DURATION") == "%.2f"

    def test_text_columns_get_no_number_format(self):
        assert _format_of(["DESCRIPTION"], "DESCRIPTION") is None

    def test_every_column_is_configured(self):
        cols = ["MACHINE_ID", "DEVIATION_PCT", "UNMAPPED"]
        assert set(tables.column_specs(cols)) == set(cols)

    def test_arbitrary_uploaded_columns_do_not_raise(self):
        cols = ["a b", "", "123"]
        assert set(tables.column_specs(cols)) == set(cols)

    def test_every_spec_carries_a_non_empty_label(self):
        cols = ["MACHINE_ID", "UNMAPPED_THING", "DEVIATION_PCT"]
        for spec in tables.column_specs(cols).values():
            assert spec.label.strip()


class TestLabelConsistency:
    """Tests that guard against a column being labelled two different ways."""

    def test_shot_count_aliases_share_one_label(self):
        assert (
            tables.label_for("SHOT_COUNT")
            == tables.label_for("SHOTS")
            == tables.label_for("TOTAL_SHOTS")
        )

    def test_count_columns_are_all_labelled(self):
        for column in tables._COUNT_COLUMNS:
            assert tables.label_for(column).strip()

    def test_duration_columns_are_all_labelled(self):
        for column in tables._DURATION_COLUMNS:
            assert tables.label_for(column).strip()

    def test_duration_columns_declare_their_unit(self):
        for column in tables._DURATION_COLUMNS:
            assert "(s)" in tables.label_for(column)
