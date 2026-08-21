"""Tests for the note-corroboration logic in src/frontend/evidence.py.

Covers keyword matching, nearest-week selection, and HTML escaping of note
bodies, which matters because notes come from the database and are rendered
with unsafe_allow_html. Pure functions only; no Streamlit runtime involved.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "src" / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

import evidence  # noqa: E402


class TestIsCorroborating:
    """Tests for evidence.is_corroborating."""

    @pytest.mark.parametrize(
        "note",
        [
            "Cycle drifting further from standard",
            "Ejection sluggish on the B half",
            "Cooling looks off this shift",
            "Operator applied compensation again",
            "Recommend pulling the tool",
        ],
    )
    def test_detects_wear_language(self, note):
        assert evidence.is_corroborating(note) is True

    @pytest.mark.parametrize(
        "note",
        [
            "Routine changeover completed",
            "Shift handover normal",
            "Material lot changed",
        ],
    )
    def test_ignores_unrelated_notes(self, note):
        assert evidence.is_corroborating(note) is False

    def test_is_case_insensitive(self):
        assert evidence.is_corroborating("CYCLE DRIFTING FROM STANDARD") is True

    def test_matches_keyword_inside_a_longer_word(self):
        assert evidence.is_corroborating("cooling channel blocked") is True

    def test_none_is_not_corroborating(self):
        assert evidence.is_corroborating(None) is False

    def test_empty_string_is_not_corroborating(self):
        assert evidence.is_corroborating("") is False

    def test_non_string_values_do_not_raise(self):
        assert evidence.is_corroborating(12345) is False

    def test_every_keyword_matches_itself(self):
        for keyword in evidence.CORROBORATION_KEYWORDS:
            assert evidence.is_corroborating(keyword) is True


class TestNearestWeekIndex:
    """Tests for evidence.nearest_week_index."""

    @staticmethod
    def _weeks():
        return pd.to_datetime(pd.Series(["2026-07-06", "2026-07-13", "2026-07-20"]))

    def test_picks_the_closest_week(self):
        assert evidence.nearest_week_index("2026-07-14", self._weeks()) == 1

    def test_exact_match_selects_that_week(self):
        assert evidence.nearest_week_index("2026-07-20", self._weeks()) == 2

    def test_date_before_all_weeks_selects_the_first(self):
        assert evidence.nearest_week_index("2026-01-01", self._weeks()) == 0

    def test_date_after_all_weeks_selects_the_last(self):
        assert evidence.nearest_week_index("2026-12-31", self._weeks()) == 2

    def test_empty_weeks_returns_none(self):
        empty = pd.Series([], dtype="datetime64[ns]")
        assert evidence.nearest_week_index("2026-07-14", empty) is None

    def test_returns_a_plain_int(self):
        assert isinstance(evidence.nearest_week_index("2026-07-14", self._weeks()), int)


class TestNoteCardEscaping:
    """Tests that database-sourced note text cannot inject markup."""

    def test_script_tag_in_body_is_escaped(self):
        card = evidence._note_card("meta", "<script>alert(1)</script>", None, False)
        assert "<script>" not in card
        assert "&lt;script&gt;" in card

    def test_markup_in_meta_is_escaped(self):
        card = evidence._note_card("<b>x</b>", "body", None, False)
        assert "<b>x</b>" not in card

    def test_markup_in_match_line_is_escaped(self):
        card = evidence._note_card("meta", "body", "<i>match</i>", False)
        assert "<i>match</i>" not in card

    def test_quotes_in_body_cannot_break_the_attribute(self):
        card = evidence._note_card("meta", '" onmouseover="evil()', None, False)
        assert 'onmouseover="evil()' not in card

    def test_muted_flag_sets_the_muted_class(self):
        assert "note-muted" in evidence._note_card("m", "b", None, True)

    def test_unmuted_card_has_no_muted_class(self):
        assert "note-muted" not in evidence._note_card("m", "b", None, False)

    def test_match_line_is_omitted_when_absent(self):
        assert "note-match" not in evidence._note_card("m", "b", None, False)

    def test_match_line_is_present_when_supplied(self):
        assert "note-match" in evidence._note_card("m", "b", "matched", False)
