"""Tests for the explicit FLAGGED verdict line used when scoring a run.

Naming a machine in prose cannot distinguish flagging it from clearing it. The
agent's summaries list healthy machines by name, which scored every negative
control as a false positive. The verdict line removes that ambiguity; the prose
heuristic remains as a fallback for summaries written without one.
"""

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.workflow.scoring import (  # noqa: E402
    extract_flagged_equipment,
    extract_mentioned_equipment,
    extract_verdict_equipment,
)

REAL_SUMMARY = """## Autonomous Sweep Summary

### Equipment Flagged: MX-7103 - CRITICAL

MX-7101, MX-7102, MX-7104, MX-7105, MX-7106, MX-7107, MX-7108 - all healthy.

FLAGGED: MX-7103
"""


class TestVerdictExtraction:
    """Tests for extract_verdict_equipment."""

    def test_absent_verdict_returns_none(self):
        assert extract_verdict_equipment("MX-7103 looks bad.") is None

    def test_single_machine(self):
        assert extract_verdict_equipment("FLAGGED: MX-7103") == {"MX-7103"}

    def test_several_machines(self):
        assert extract_verdict_equipment("FLAGGED: MX-7103, MX-7106") == {
            "MX-7103",
            "MX-7106",
        }

    def test_none_verdict_is_an_empty_set_not_none(self):
        result = extract_verdict_equipment("FLAGGED: NONE")
        assert result == set()
        assert result is not None

    def test_whitespace_is_tolerated(self):
        assert extract_verdict_equipment("   FLAGGED :   MX-7103  ") == {"MX-7103"}

    def test_lowercase_none_is_accepted(self):
        assert extract_verdict_equipment("FLAGGED: none") == set()

    def test_verdict_is_found_at_the_end_of_a_long_summary(self):
        assert extract_verdict_equipment(REAL_SUMMARY) == {"MX-7103"}


class TestFlaggedEquipment:
    """Tests for extract_flagged_equipment, the function scoring uses."""

    def test_verdict_excludes_machines_cleared_in_prose(self):
        assert extract_flagged_equipment(REAL_SUMMARY) == {"MX-7103"}

    def test_prose_heuristic_would_have_counted_all_eight(self):
        # Documents why the verdict line was needed.
        assert len(extract_mentioned_equipment(REAL_SUMMARY)) == 8

    def test_falls_back_to_prose_without_a_verdict(self):
        text = "MX-7103 is drifting. MX-7101 is healthy."
        assert extract_flagged_equipment(text) == {"MX-7101", "MX-7103"}

    def test_none_verdict_flags_nothing(self):
        text = "All machines healthy: MX-7101, MX-7102.\nFLAGGED: NONE"
        assert extract_flagged_equipment(text) == set()

    def test_empty_text_flags_nothing(self):
        assert extract_flagged_equipment("") == set()

    @pytest.mark.parametrize("code", ["MX-7103", "ML-9201", "AB-123", "ABCD-12345"])
    def test_equipment_code_shapes_are_recognised(self, code):
        assert extract_flagged_equipment(f"FLAGGED: {code}") == {code}


class TestScopeFiltering:
    """Tests that out-of-scope planted defects are excluded from scoring.

    The generator plants defects for mean time between failures, mean time to
    repair, and a stability decline carried by hard-stop rate. Those signal
    families were trimmed from the project, so the analysis layer computes none
    of them.
    """

    @staticmethod
    def _contract():
        return {
            "expected_findings": [
                {
                    "machine_id": "MX-7103",
                    "metric": "deviation_pct",
                    "expected_direction": "above",
                },
                {
                    "machine_id": "MX-7104",
                    "metric": "mtbf_minutes",
                    "expected_direction": "below",
                },
                {
                    "machine_id": "MX-7105",
                    "metric": "mttr_minutes",
                    "expected_direction": "above",
                },
                {
                    "machine_id": "MX-7106",
                    "metric": "stability_decline_pct",
                    "expected_direction": "above",
                },
                {
                    "machine_id": "MX-7101",
                    "metric": "none",
                    "expected_direction": "no_finding",
                },
            ]
        }

    def test_only_in_scope_defects_are_expected(self):
        from services.workflow.scoring import expected_defects

        assert expected_defects(self._contract()) == {"MX-7103"}

    def test_out_of_scope_defects_are_reported_separately(self):
        from services.workflow.scoring import out_of_scope_defects

        assert out_of_scope_defects(self._contract()) == {
            "MX-7104",
            "MX-7105",
            "MX-7106",
        }

    def test_negative_controls_are_unaffected(self):
        from services.workflow.scoring import negative_controls

        assert negative_controls(self._contract()) == {"MX-7101"}

    def test_missing_an_out_of_scope_defect_is_not_a_false_negative(self):
        from services.workflow.scoring import score_run

        report = score_run(self._contract(), "FLAGGED: MX-7103", [])
        assert report.false_negatives == []
        assert report.recall == 1.0

    def test_naming_an_out_of_scope_machine_is_not_a_false_positive(self):
        from services.workflow.scoring import score_run

        report = score_run(self._contract(), "FLAGGED: MX-7103, MX-7104", [])
        assert report.false_positives == []

    def test_flagging_a_control_is_still_a_false_positive(self):
        from services.workflow.scoring import score_run

        report = score_run(self._contract(), "FLAGGED: MX-7103, MX-7101", [])
        assert report.false_positives == ["MX-7101"]
