"""Tests for the KPI computation in src/frontend/header.py.

build_kpis is pure: it takes the fleet summary frame and returns display text,
so the figures shown at the top of the dashboard can be asserted directly.
"""

import sys
from pathlib import Path

import pandas as pd

FRONTEND = Path(__file__).resolve().parents[1] / "src" / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

import header  # noqa: E402


def _fleet(**overrides):
    """Build a three-machine fleet summary frame."""
    data = {
        "MACHINE_ID": ["MX-7101", "MX-7507", "MX-9201"],
        "TOTAL_SHOTS": [100000, 120000, 25719],
        "DEVIATION_PCT": [1.2, 21.3, 8.0],
        "CV_PCT": [5.0, 9.0, 14.6],
        "LAST_SHOT": pd.to_datetime(["2026-08-19", "2026-08-20", "2026-08-18"]),
    }
    data.update(overrides)
    return pd.DataFrame(data)


def _by_label(kpis, label):
    return next(k for k in kpis if k[0] == label)


class TestBuildKpis:
    """Tests for header.build_kpis."""

    def test_empty_frame_yields_no_cards(self):
        assert header.build_kpis(pd.DataFrame()) == []

    def test_returns_five_cards(self):
        assert len(header.build_kpis(_fleet())) == 5

    def test_every_card_has_label_value_and_note(self):
        for label, value, note in header.build_kpis(_fleet()):
            assert label and value and note

    def test_fleet_card_counts_machines_and_shots(self):
        _, value, note = _by_label(header.build_kpis(_fleet()), "Fleet")
        assert value == "3 machines"
        assert "245,719" in note

    def test_attention_counts_machines_at_or_above_threshold(self):
        _, value, _ = _by_label(header.build_kpis(_fleet()), "Needs Attention")
        assert value == "1"

    def test_attention_threshold_is_inclusive(self):
        fleet = _fleet(DEVIATION_PCT=[10.0, 1.0, 1.0])
        _, value, _ = _by_label(header.build_kpis(fleet), "Needs Attention")
        assert value == "1"

    def test_worst_deviation_reports_the_right_machine(self):
        _, value, note = _by_label(header.build_kpis(_fleet()), "Worst Deviation")
        assert value == "21.3%"
        assert "MX-7507" in note

    def test_worst_deviation_uses_absolute_value(self):
        fleet = _fleet(DEVIATION_PCT=[-30.0, 21.3, 8.0])
        _, value, note = _by_label(header.build_kpis(fleet), "Worst Deviation")
        assert "MX-7101" in note
        assert value == "-30.0%"

    def test_lowest_stability_reports_the_right_machine(self):
        _, value, note = _by_label(header.build_kpis(_fleet()), "Lowest Stability")
        assert value == "85.4%"
        assert "MX-9201" in note

    def test_latest_reading_takes_the_maximum_timestamp(self):
        _, value, _ = _by_label(header.build_kpis(_fleet()), "Latest Reading")
        assert value == "20 Aug 2026"

    def test_missing_last_shot_column_is_tolerated(self):
        fleet = _fleet().drop(columns=["LAST_SHOT"])
        _, value, _ = _by_label(header.build_kpis(fleet), "Latest Reading")
        assert value == "unknown"

    def test_null_last_shot_is_tolerated(self):
        fleet = _fleet(LAST_SHOT=[pd.NaT, pd.NaT, pd.NaT])
        _, value, _ = _by_label(header.build_kpis(fleet), "Latest Reading")
        assert value == "unknown"

    def test_single_machine_fleet_works(self):
        fleet = _fleet().head(1)
        assert len(header.build_kpis(fleet)) == 5

    def test_nominal_fleet_reports_zero_needing_attention(self):
        fleet = _fleet(DEVIATION_PCT=[1.0, 2.0, 3.0])
        _, value, _ = _by_label(header.build_kpis(fleet), "Needs Attention")
        assert value == "0"


class TestKpiCardMarkup:
    """Tests that machine identifiers cannot inject markup into a card."""

    def test_machine_name_is_escaped(self):
        card = header._kpi("Label", "Value", "<script>alert(1)</script>")
        assert "<script>" not in card
        assert "&lt;script&gt;" in card

    def test_note_is_optional(self):
        assert "kpi-note" not in header._kpi("Label", "Value")


class TestRankableFiltering:
    """Tests that statistically meaningless machines are held out of rankings.

    A machine with a single shot produced a 21.3% deviation figure and was
    reported as the fleet's worst, contradicting the agent's own analysis.
    """

    @staticmethod
    def _with_singleton():
        return pd.DataFrame(
            {
                "MACHINE_ID": ["MX-7507", "MX-9201", "MX-7103"],
                "TOTAL_SHOTS": [1, 6000, 26364],
                "DEVIATION_PCT": [21.3, 15.0, 12.6],
                "CV_PCT": [0.0, 14.6, 9.8],
                "LAST_SHOT": pd.to_datetime(["2026-08-01"] * 3),
            }
        )

    def test_low_shot_machine_is_excluded_from_rankable(self):
        eligible = header.rankable(self._with_singleton())
        assert "MX-7507" not in set(eligible["MACHINE_ID"])

    def test_excluded_count_reports_the_holdout(self):
        assert header.excluded_count(self._with_singleton()) == 1

    def test_worst_deviation_skips_the_low_shot_machine(self):
        _, value, note = _by_label(
            header.build_kpis(self._with_singleton()), "Worst Deviation"
        )
        assert "MX-9201" in note
        assert value == "15.0%"

    def test_attention_count_skips_the_low_shot_machine(self):
        _, value, _ = _by_label(
            header.build_kpis(self._with_singleton()), "Needs Attention"
        )
        assert value == "2"

    def test_attention_note_discloses_the_holdout(self):
        _, _, note = _by_label(
            header.build_kpis(self._with_singleton()), "Needs Attention"
        )
        assert "held out" in note

    def test_fleet_card_still_counts_every_machine(self):
        _, value, _ = _by_label(header.build_kpis(self._with_singleton()), "Fleet")
        assert value == "3 machines"

    def test_no_exclusion_note_when_all_machines_qualify(self):
        _, _, note = _by_label(header.build_kpis(_fleet()), "Needs Attention")
        assert "held out" not in note

    def test_falls_back_to_full_frame_when_nothing_qualifies(self):
        sparse = self._with_singleton().assign(TOTAL_SHOTS=[1, 2, 3])
        assert len(header.rankable(sparse)) == 3

    def test_excluded_count_is_zero_for_an_empty_frame(self):
        assert header.excluded_count(pd.DataFrame()) == 0

    def test_missing_shot_column_does_not_raise(self):
        frame = _fleet().drop(columns=["TOTAL_SHOTS"])
        assert len(header.rankable(frame)) == 3


class TestCopyHygiene:
    """Tests that user-facing copy does not leak internal identifiers."""

    def test_notes_do_not_name_database_tables(self):
        notes = " ".join(note or "" for _, _, note in header.build_kpis(_fleet()))
        for table in ["SHOT_DATA", "AUDIT_LOG", "SHIFT_NOTE", "DEMO.PUBLIC"]:
            assert table not in notes

    def test_subtitle_explains_the_problem(self):
        assert "drift" in header.APP_SUBTITLE.lower()
