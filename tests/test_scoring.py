"""
Tests for scoring an autonomous run against the dataset's ground truth.

Covers the distinction the scorer exists to make: what the agent actually did,
read from recorded act steps, versus what it merely claimed in prose. Pure
logic with inline fixtures; no database, no dataset on disk.
"""

from services.workflow.model_text import (
    TRUNCATION_PREFIX,
    strip_reasoning,
    truncate_keeping_tail,
)
from services.workflow.scoring import (
    ScoreReport,
    expected_defects,
    extract_investigated_equipment,
    extract_mentioned_equipment,
    negative_controls,
    score_run,
)

GROUND_TRUTH = {
    "headline_equipment": "MX-7103",
    "expected_findings": [
        {"machine_id": "MX-7101", "expected_direction": "no_finding"},
        {"machine_id": "MX-7102", "expected_direction": "no_finding"},
        {"machine_id": "MX-7103", "expected_direction": "above"},
        {"machine_id": "MX-7104", "expected_direction": "below"},
    ],
}


def _act(payload):
    return {"phase": "act", "payload": payload}


class TestGroundTruthPartition:
    def test_defects_exclude_controls(self):
        assert expected_defects(GROUND_TRUTH) == {"MX-7103", "MX-7104"}

    def test_controls_are_the_no_finding_rows(self):
        assert negative_controls(GROUND_TRUTH) == {"MX-7101", "MX-7102"}

    def test_empty_ground_truth_is_tolerated(self):
        assert expected_defects({}) == set()
        assert negative_controls({}) == set()


class TestExtraction:
    def test_reasoning_block_is_stripped(self):
        # A scratchpad naming healthy machines must not count as flagging them.
        text = "<think>MX-7101 looks fine</think> Flagged: MX-7103"
        assert extract_mentioned_equipment(text) == {"MX-7103"}

    def test_stripping_is_case_insensitive_and_multiline(self):
        text = "<THINK>\nMX-7101\n</THINK>\nMX-7103"
        assert extract_mentioned_equipment(text) == {"MX-7103"}

    def test_codes_are_found_in_prose(self):
        assert extract_mentioned_equipment("flagged MX-7103 and MX-7104") == {
            "MX-7103",
            "MX-7104",
        }

    def test_unknown_code_shape_is_still_caught(self):
        # A hallucinated machine should surface as a false positive, not vanish.
        assert "XYZ-9999" in extract_mentioned_equipment("check XYZ-9999")

    def test_empty_text_yields_nothing(self):
        assert extract_mentioned_equipment("") == set()
        assert strip_reasoning(None) == ""

    def test_investigated_reads_singular_and_plural_arguments(self):
        steps = [
            _act({"machine_id": "MX-7103"}),
            _act({"machine_ids": ["MX-7104", "MX-7105"]}),
        ]
        assert extract_investigated_equipment(steps) == {
            "MX-7103",
            "MX-7104",
            "MX-7105",
        }

    def test_non_act_steps_are_ignored(self):
        # Sense steps run automatically; they are not the agent's own choices.
        steps = [{"phase": "sense", "payload": {"machine_id": "MX-7103"}}]
        assert extract_investigated_equipment(steps) == set()

    def test_missing_payload_is_safe(self):
        assert extract_investigated_equipment([{"phase": "act"}]) == set()


class TestScoreRun:
    def test_perfect_run(self):
        report = score_run(
            GROUND_TRUTH,
            "Flagged MX-7103 and MX-7104.",
            [
                _act({"machine_id": "MX-7103"}),
                _act({"machine_id": "MX-7104"}),
            ],
        )
        assert report.recall == 1.0
        assert report.precision == 1.0
        assert report.f1 == 1.0
        assert report.claimed_only == []

    def test_flagging_a_control_is_a_false_positive(self):
        report = score_run(GROUND_TRUTH, "MX-7103 and MX-7101 are faulty.", [])
        assert report.false_positives == ["MX-7101"]
        assert report.precision == 0.5

    def test_missed_defects_are_counted(self):
        report = score_run(GROUND_TRUTH, "Only MX-7103.", [])
        assert report.false_negatives == ["MX-7104"]
        assert report.recall == 0.5

    def test_claims_without_actions_are_exposed(self):
        # The failure mode observed live: a confident summary, no work done.
        report = score_run(GROUND_TRUTH, "Investigated MX-7103 thoroughly.", [])
        assert report.claimed_only == ["MX-7103"]
        assert report.investigated == []

    def test_action_backed_claim_is_not_flagged_as_claim_only(self):
        report = score_run(
            GROUND_TRUTH, "MX-7103", [_act({"machine_id": "MX-7103"})]
        )
        assert report.claimed_only == []
        assert report.investigated == ["MX-7103"]

    def test_headline_detection(self):
        assert score_run(GROUND_TRUTH, "MX-7103", []).headline_found
        assert not score_run(GROUND_TRUTH, "MX-7104", []).headline_found

    def test_silent_run_scores_zero_recall(self):
        report = score_run(GROUND_TRUTH, "Nothing abnormal.", [])
        assert report.recall == 0.0
        assert report.f1 == 0.0
        assert len(report.false_negatives) == 2

    def test_report_serialises(self):
        report = score_run(GROUND_TRUTH, "MX-7103", [])
        assert report.to_dict()["headline_found"] is True


class TestModelText:
    def test_unterminated_scratchpad_yields_no_conclusion(self):
        # Observed live: generation cut off mid-thought, so there is no answer.
        # Returning the deliberation as a conclusion would misrepresent the run.
        assert strip_reasoning("<think>MX-7103 might be drifting") == ""

    def test_conclusion_after_scratchpad_survives(self):
        text = "<think>long deliberation</think>\nFlagged: MX-7103"
        assert "MX-7103" in strip_reasoning(text)
        assert "deliberation" not in strip_reasoning(text)

    def test_truncation_keeps_the_end(self):
        # The verdict is last; head-truncation would discard exactly it.
        text = "x" * 500 + " VERDICT: MX-7103"
        kept = truncate_keeping_tail(text, 100)
        assert "VERDICT: MX-7103" in kept
        assert kept.startswith(TRUNCATION_PREFIX)

    def test_short_text_is_untouched(self):
        assert truncate_keeping_tail("brief", 100) == "brief"

    def test_none_is_safe(self):
        assert truncate_keeping_tail(None, 10) == ""


class TestMetrics:
    def test_empty_report_does_not_divide_by_zero(self):
        report = ScoreReport()
        assert report.precision == 0.0
        assert report.recall == 0.0
        assert report.f1 == 0.0

    def test_f1_is_zero_when_either_side_is_zero(self):
        report = ScoreReport(true_positives=[], false_negatives=["a"])
        assert report.f1 == 0.0
