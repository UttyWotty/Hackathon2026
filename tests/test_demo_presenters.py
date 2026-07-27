"""
Tests for the demo's pure display shaping.

Covers duration formatting, phase grouping including the empty-Act case the
demo exists to expose, score tiles and the unbacked-claim warning. No
Streamlit, no database and no I/O.
"""

from typing import Any, Dict, List

from demo.presenters import (
    EMPTY_LIST_LABEL,
    NO_TOOL_LABEL,
    PHASE_ACT,
    PHASE_ORDER,
    PHASE_REASON,
    PHASE_SENSE,
    UNKNOWN_DURATION,
    build_score_tiles,
    build_step_row,
    format_duration,
    format_equipment_list,
    group_steps_by_phase,
    run_label,
    unbacked_claim_warning,
)


def _step(sequence: int, phase: str, **overrides: Any) -> Dict[str, Any]:
    """Build a step dictionary in the shape DecisionStep.to_dict produces."""
    step: Dict[str, Any] = {
        "run_id": "run-1",
        "sequence": sequence,
        "phase": phase,
        "tool_name": None,
        "status": "completed",
        "payload": None,
        "result_summary": None,
        "duration_ms": 120.0,
        "created_at": "2026-07-27T08:00:00",
    }
    step.update(overrides)
    return step


def test_format_duration_uses_milliseconds_below_a_second():
    assert format_duration(120.0) == "120ms"


def test_format_duration_uses_seconds_at_and_above_a_second():
    assert format_duration(1500.0) == "1.5s"


def test_format_duration_handles_a_never_recorded_duration():
    assert format_duration(None) == UNKNOWN_DURATION


def test_build_step_row_labels_a_step_that_called_no_tool():
    row = build_step_row(_step(1, PHASE_REASON))
    assert row.tool_name == NO_TOOL_LABEL
    assert row.payload == ""
    assert row.result_summary == ""


def test_build_step_row_truncates_an_oversized_payload():
    row = build_step_row(_step(1, PHASE_ACT, payload="x" * 5000))
    assert len(row.payload) < 5000
    assert row.payload.endswith("...")


def test_group_steps_by_phase_returns_every_phase_in_loop_order():
    groups = group_steps_by_phase([_step(1, PHASE_SENSE)])
    assert [group.phase for group in groups] == list(PHASE_ORDER)


def test_group_steps_by_phase_keeps_an_empty_act_group_visible():
    """A run that reasoned but never acted must not look like it acted."""
    groups = group_steps_by_phase([_step(1, PHASE_SENSE), _step(2, PHASE_REASON)])
    act = next(group for group in groups if group.phase == PHASE_ACT)
    assert act.rows == []


def test_group_steps_by_phase_assigns_each_step_to_its_own_phase():
    groups = group_steps_by_phase(
        [
            _step(1, PHASE_SENSE, tool_name="run_ct_deviation_analysis"),
            _step(2, PHASE_ACT, tool_name="send_email"),
            _step(3, PHASE_ACT, tool_name="schedule_job"),
        ]
    )
    counts = {group.phase: len(group.rows) for group in groups}
    assert counts == {PHASE_SENSE: 1, PHASE_REASON: 0, PHASE_ACT: 2}


def test_format_equipment_list_labels_an_empty_list_explicitly():
    assert format_equipment_list([]) == EMPTY_LIST_LABEL


def test_format_equipment_list_joins_codes():
    assert format_equipment_list(["EMA-4103", "EMA-4104"]) == "EMA-4103, EMA-4104"


def test_build_score_tiles_reports_a_caught_headline():
    tiles = build_score_tiles(
        {"precision": 1.0, "recall": 0.5, "f1": 0.667, "headline_found": True}
    )
    values = {tile.label: tile.value for tile in tiles}
    assert values["Precision"] == "1.00"
    assert values["Headline defect"] == "caught"


def test_build_score_tiles_reports_a_missed_headline():
    tiles = build_score_tiles({"headline_found": False})
    values = {tile.label: tile.value for tile in tiles}
    assert values["Headline defect"] == "missed"
    assert values["Recall"] == "0.00"


def test_run_label_carries_time_status_and_backend():
    label = run_label(
        {
            "started_at": "2026-07-27T08:35:07.123456",
            "status": "completed",
            "llm_backend": "cortex",
        }
    )
    assert label == "2026-07-27T08:35:07  completed  (cortex)"


def test_unbacked_claim_warning_is_absent_when_every_claim_is_backed():
    assert unbacked_claim_warning({"claimed_only": []}) is None


def test_unbacked_claim_warning_names_the_unbacked_machines():
    warning = unbacked_claim_warning({"claimed_only": ["EMA-4107"]})
    assert warning is not None
    assert "EMA-4107" in warning


def test_group_steps_by_phase_handles_no_steps_at_all():
    groups: List[Any] = group_steps_by_phase([])
    assert len(groups) == len(PHASE_ORDER)
    assert all(not group.rows for group in groups)
