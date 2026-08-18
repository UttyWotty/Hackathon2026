"""
Tests for the autonomous agent's decision trail recorder.

Exercises run and step persistence against a real in-memory SQLite database
rather than mocks, since the behaviour under test is the SQL round trip itself.
Covers ordering, truncation, terminal states and unknown-run handling.
"""

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base
from models.decision_trail import (
    PHASE_Aduration,
    PHASE_REASON,
    PHASE_SENSE,
    STATUS_COMPLETED,
    STATUS_FAILED,
    TRIGGER_SCHEDULE,
)
from services.workflow.trail_recorder import (
    MAX_SUMMARY_CHARS,
    TrailRecorder,
    TrailRecorderError,
    load_trail,
)


@pytest.fixture
def session_factory():
    """A throwaway in-memory database with the real schema."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    maker = sessionmaker(bind=engine)

    @contextmanager
    def factory():
        session = maker()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return factory


@pytest.fixture
def recorder(session_factory):
    """A recorder with a started run."""
    rec = TrailRecorder(run_id="run-test-1", session_factory=session_factory)
    rec.start_run(TRIGGER_SCHEDULE, llm_backend="mlx", model_id="qwen3")
    return rec


class TestRunLifecycle:
    def test_start_persists_a_running_run(self, recorder, session_factory):
        trail = load_trail("run-test-1", session_factory)
        assert trail["status"] == "running"
        assert trail["trigger"] == TRIGGER_SCHEDULE

    def test_backend_and_model_are_recorded(self, recorder, session_factory):
        # A trail must never be ambiguous about what did the reasoning.
        trail = load_trail("run-test-1", session_factory)
        assert trail["llm_backend"] == "mlx"
        assert trail["model_id"] == "qwen3"

    def test_finish_sets_completion_and_duration(self, recorder, session_factory):
        recorder.finish_run(summary="all clear")
        trail = load_trail("run-test-1", session_factory)
        assert trail["status"] == STATUS_COMPLETED
        assert trail["completed_at"] is not None
        assert trail["duration_ms"] >= 0

    def test_failure_is_recorded_with_its_error(self, recorder, session_factory):
        recorder.finish_run(status=STATUS_FAILED, error="tool exploded")
        trail = load_trail("run-test-1", session_factory)
        assert trail["status"] == STATUS_FAILED
        assert "exploded" in trail["error"]

    def test_finishing_an_unknown_run_raises(self, session_factory):
        orphan = TrailRecorder(run_id="nope", session_factory=session_factory)
        with pytest.raises(TrailRecorderError):
            orphan.finish_run()

    def test_run_ids_are_unique_by_default(self, session_factory):
        first = TrailRecorder(session_factory=session_factory)
        second = TrailRecorder(session_factory=session_factory)
        assert first.run_id != second.run_id


class TestSteps:
    def test_sequence_numbers_start_at_one_and_increment(self, recorder):
        assert recorder.record_step(PHASE_SENSE, STATUS_COMPLETED) == 1
        assert recorder.record_step(PHASE_REASON, STATUS_COMPLETED) == 2
        assert recorder.record_step(PHASE_Aduration, STATUS_COMPLETED) == 3

    def test_steps_load_back_in_sequence_order(self, recorder, session_factory):
        for phase in (PHASE_SENSE, PHASE_REASON, PHASE_ACT):
            recorder.record_step(phase, STATUS_COMPLETED)
        steps = load_trail("run-test-1", session_factory)["steps"]
        assert [s["sequence"] for s in steps] == [1, 2, 3]
        assert [s["phase"] for s in steps] == [PHASE_SENSE, PHASE_REASON, PHASE_ACT]

    def test_payload_round_trips_as_json(self, recorder, session_factory):
        recorder.record_step(
            PHASE_Aduration,
            STATUS_COMPLETED,
            tool_name="run_rca_analysis",
            payload={"machine_id": "MX-7103", "depth": 2},
        )
        step = load_trail("run-test-1", session_factory)["steps"][0]
        assert step["payload"] == {"machine_id": "MX-7103", "depth": 2}
        assert step["tool_name"] == "run_rca_analysis"

    def test_long_summaries_are_truncated(self, recorder, session_factory):
        recorder.record_step(
            PHASE_SENSE, STATUS_COMPLETED, result_summary="x" * (MAX_SUMMARY_CHARS * 2)
        )
        stored = load_trail("run-test-1", session_factory)["steps"][0]["result_summary"]
        assert stored.endswith("[truncated]")
        assert len(stored) < MAX_SUMMARY_CHARS * 2

    def test_short_summaries_are_untouched(self, recorder, session_factory):
        recorder.record_step(PHASE_SENSE, STATUS_COMPLETED, result_summary="brief")
        stored = load_trail("run-test-1", session_factory)["steps"][0]["result_summary"]
        assert stored == "brief"

    def test_action_count_counts_only_act_steps(self, recorder, session_factory):
        recorder.record_step(PHASE_SENSE, STATUS_COMPLETED)
        recorder.record_step(PHASE_Aduration, STATUS_COMPLETED)
        recorder.record_step(PHASE_Aduration, STATUS_FAILED)
        assert load_trail("run-test-1", session_factory)["action_count"] == 2


class TestLoadTrail:
    def test_unknown_run_returns_empty_dict(self, session_factory):
        assert load_trail("does-not-exist", session_factory) == {}

    def test_trails_are_isolated_by_run_id(self, session_factory):
        first = TrailRecorder(run_id="run-a", session_factory=session_factory)
        first.start_run(TRIGGER_SCHEDULE)
        first.record_step(PHASE_SENSE, STATUS_COMPLETED)

        second = TrailRecorder(run_id="run-b", session_factory=session_factory)
        second.start_run(TRIGGER_SCHEDULE)

        assert len(load_trail("run-a", session_factory)["steps"]) == 1
        assert load_trail("run-b", session_factory)["steps"] == []
