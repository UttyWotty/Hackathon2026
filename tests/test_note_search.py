"""Tests for the lexical shift-note ranking used when Cortex Search is unavailable.

This fallback exists so the investigation skill works offline, and its limits matter: it
matches shared terms, so the tests pin both what it finds and what it provably cannot.
Pure logic, inline fixtures, no dataset on disk.
"""

from services.workflow.note_search import (
    rank_notes,
    score_note,
    tokenize,
)


def _note(code, date, text, role="Operator"):
    return {
        "MACHINE_ID": code,
        "SHIFT_DATE": date,
        "AUTHOR_ROLE": role,
        "NOTE_TEXT": text,
    }


NOTES = [
    _note(
        "MX-7103",
        "2026-06-15",
        "Parts releasing slower from the cavity. Added cooling.",
    ),
    _note("MX-7103", "2026-06-22", "Duration creeping up again this week."),
    _note("MX-7103", "2026-06-08", "Shift ran clean. Continuous production."),
    _note(
        "MX-7104", "2026-06-15", "Three short stoppages today. Each restarted cleanly."
    ),
]


class TestTokenize:
    def test_lowercases_and_splits(self):
        assert "cycle" in tokenize("Duration")

    def test_drops_stop_words(self):
        # "the", "is", "shift" carry no signal in a corpus of shift notes.
        assert tokenize("the shift is running") == ["running"]

    def test_keeps_hyphenated_machine_ids(self):
        assert "mx-7103" in tokenize("MX-7103 is drifting")

    def test_empty_input_is_safe(self):
        assert tokenize("") == []
        assert tokenize(None) == []


class TestScoreNote:
    def test_scores_by_query_coverage_not_term_count(self):
        # A note repeating one term must not outrank one covering both.
        both = score_note("cycle cooling", ["cycle", "cooling"])
        repeated = score_note("cycle cycle cycle", ["cycle", "cooling"])
        assert both > repeated

    def test_full_coverage_scores_one(self):
        assert score_note("cycle cooling issue", ["cycle", "cooling"]) == 1.0

    def test_no_overlap_scores_zero(self):
        assert score_note("everything nominal", ["hydraulic"]) == 0.0

    def test_empty_query_scores_zero(self):
        assert score_note("anything", []) == 0.0


class TestRankNotes:
    def test_filters_by_equipment(self):
        results = rank_notes(NOTES, "", "MX-7104")
        assert len(results) == 1
        assert results[0].machine_id == "MX-7104"

    def test_empty_query_returns_history_in_date_order(self):
        results = rank_notes(NOTES, "", "MX-7103")
        assert [r.shift_date for r in results] == [
            "2026-06-08",
            "2026-06-15",
            "2026-06-22",
        ]

    def test_query_ranks_by_relevance(self):
        results = rank_notes(NOTES, "cooling cavity", "MX-7103")
        assert results[0].shift_date == "2026-06-15"

    def test_zero_scoring_notes_are_dropped(self):
        # Returning every note for the machine would bury what was asked for.
        results = rank_notes(NOTES, "hydraulic", "MX-7103")
        assert results == []

    def test_limit_is_respected(self):
        assert len(rank_notes(NOTES, "", None, limit=2)) == 2

    def test_paraphrase_is_missed(self):
        """The documented limitation, asserted so nobody mistakes this for semantic search.

        A human searching for "running long" means the same thing as "creeping up", but
        they share no terms, so this ranker cannot connect them. Cortex Search can.
        """
        assert rank_notes(NOTES, "running long", "MX-7103") == []

    def test_results_carry_the_date_for_attribution(self):
        results = rank_notes(NOTES, "cooling", "MX-7103")
        assert results[0].to_dict()["shift_date"] == "2026-06-15"
