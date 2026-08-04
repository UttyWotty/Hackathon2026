"""
Tests for the autonomous sense-reason-act controller and its sense summariser.

Drives the loop with a scripted LLM client and a fake dispatcher, so the control
flow, the trail it writes, and its failure handling are all asserted without a
model, a network or Snowflake.
"""

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base
from models.decision_trail import PHASE_ACT, PHASE_REASON, PHASE_SENSE
from services.workflow.controller import (
    WorkflowController,
    WorkflowControllerError,
)
from services.workflow.sense import (
    DEFAULT_SENSE_TASKS,
    SenseFinding,
    SenseTask,
    derive_followup_tasks,
    format_findings,
    run_sense_tasks,
    summarize_sense_result,
)
from services.workflow.trail_recorder import TrailRecorder, load_trail

CT_RESULT = {
    "status": "success",
    "metrics": [
        {
            "equipment_code": "MX-7103",
            "deviation_percentage": 12.68,
            "deviation_category": "Acceptable (10-15% deviation)",
            "efficiency_score": 87.3,
            "stability_score": 90.1,
        },
        {
            "equipment_code": "MX-7101",
            "deviation_percentage": 2.16,
            "deviation_category": "Excellent",
            "efficiency_score": 97.8,
            "stability_score": 86.0,
        },
    ],
    "summary": {"category_distribution": {"Excellent": 7, "Acceptable": 1}},
}

ERROR_RESULT = {"status": "error", "error": "Snowflake unreachable"}


def _text_response(text):
    """An assistant turn that ends the loop."""
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


def _tool_response(name, arguments, use_id="call_1"):
    """An assistant turn requesting one tool call."""
    return {
        "stop_reason": "tool_use",
        "content": [
            {"type": "tool_use", "id": use_id, "name": name, "input": arguments}
        ],
    }


class ScriptedClient:
    """Returns queued responses in order and records what it was sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.model = "test-model"

    def get_response(self, messages, tools=None, **kwargs):
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self.responses:
            return _text_response("done")
        return self.responses.pop(0)


class FakeDispatcher:
    """Async tool dispatcher returning canned results by tool name."""

    def __init__(self, results=None, raises=None):
        self.results = results or {}
        self.raises = raises or set()
        self.calls = []

    async def __call__(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if tool_name in self.raises:
            raise RuntimeError(f"{tool_name} exploded")
        return self.results.get(tool_name, {"status": "success"})


@pytest.fixture
def session_factory():
    """Throwaway in-memory database with the real schema."""
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
    return TrailRecorder(run_id="run-ctrl", session_factory=session_factory)


@pytest.fixture
def dispatcher():
    return FakeDispatcher({"run_ct_deviation_analysis": CT_RESULT})


def _controller(client, recorder, dispatcher, **kwargs):
    return WorkflowController(
        llm_client=client, recorder=recorder, dispatcher=dispatcher, **kwargs
    )


class TestSummarize:
    def test_list_metrics_render_per_equipment(self):
        text = summarize_sense_result("run_ct_deviation_analysis", CT_RESULT)
        assert "MX-7103" in text
        assert "deviation_percentage=12.68" in text

    def test_dict_metrics_render_as_no_findings(self):
        # Dict-shaped metrics (non-list) now report no findings.
        dict_result = {"status": "success", "metrics": {"some_key": 42}}
        text = summarize_sense_result("some_tool", dict_result)
        assert "no metrics" in text

    def test_failures_are_surfaced_not_hidden(self):
        text = summarize_sense_result("run_ct_deviation_analysis", ERROR_RESULT)
        assert "FAILED" in text
        assert "Snowflake unreachable" in text

    def test_category_distribution_is_included(self):
        assert "category_distribution" in summarize_sense_result("t", CT_RESULT)

    def test_empty_metrics_say_so(self):
        text = summarize_sense_result("t", {"status": "success", "metrics": []})
        assert "no metrics" in text

    def test_non_dict_result_does_not_raise(self):
        assert "unexpected result type" in summarize_sense_result("t", ["oops"])

    def test_format_findings_with_none(self):
        assert "No sense analyses" in format_findings([])


class TestRunSenseTasks:
    @pytest.mark.asyncio
    async def test_dispatcher_exception_becomes_a_finding(self):
        # One broken analysis must not abort the sweep.
        dispatcher = FakeDispatcher(raises={"run_ct_deviation_analysis"})
        findings = await run_sense_tasks(
            [
                SenseTask("run_ct_deviation_analysis"),
                SenseTask("run_ct_deviation_analysis"),
            ],
            dispatcher,
        )
        assert len(findings) == 2
        assert not findings[0].ok
        assert not findings[1].ok

    @pytest.mark.asyncio
    async def test_on_step_callback_fires_per_task(self):
        seen = []
        await run_sense_tasks(
            [SenseTask("run_ct_deviation_analysis")],
            FakeDispatcher({"run_ct_deviation_analysis": CT_RESULT}),
            on_step=seen.append,
        )
        assert len(seen) == 1
        assert isinstance(seen[0], SenseFinding)


class TestDeriveFollowups:
    def test_returns_empty_list(self):
        tasks = derive_followup_tasks(
            [SenseFinding("run_ct_deviation_analysis", "success", "", CT_RESULT)]
        )
        assert tasks == []

    def test_failed_sweep_yields_no_followups(self):
        finding = SenseFinding("run_ct_deviation_analysis", "error", "", ERROR_RESULT)
        assert derive_followup_tasks([finding]) == []


class TestControllerLoop:
    @pytest.mark.asyncio
    async def test_sense_findings_reach_the_prompt(self, recorder, dispatcher):
        client = ScriptedClient([_text_response("nothing abnormal")])
        await _controller(client, recorder, dispatcher).run()
        prompt = client.calls[0]["messages"][0]["content"]
        assert "MX-7103" in prompt
        assert "autonomous" in prompt.lower()

    @pytest.mark.asyncio
    async def test_text_response_ends_the_run(self, recorder, dispatcher):
        client = ScriptedClient([_text_response("all healthy")])
        result = await _controller(client, recorder, dispatcher).run()
        assert result["status"] == "completed"
        assert result["summary"] == "all healthy"
        assert result["actions"] == []

    @pytest.mark.asyncio
    async def test_tool_calls_are_executed_and_returned(self, recorder, dispatcher):
        client = ScriptedClient(
            [
                _tool_response("run_rca_analysis", {"equipment_code": "MX-7103"}),
                _text_response("flagged MX-7103"),
            ]
        )
        result = await _controller(client, recorder, dispatcher).run()
        assert result["actions"] == ["run_rca_analysis"]
        assert ("run_rca_analysis", {"equipment_code": "MX-7103"}) in dispatcher.calls

    @pytest.mark.asyncio
    async def test_tool_failure_is_reported_back_to_the_model(self, recorder):
        # The model must learn the tool failed, not silently continue.
        dispatcher = FakeDispatcher(raises={"run_rca_analysis"})
        client = ScriptedClient(
            [_tool_response("run_rca_analysis", {}), _text_response("could not verify")]
        )
        result = await _controller(client, recorder, dispatcher).run()
        assert result["status"] == "completed"
        tool_turn = client.calls[1]["messages"][-1]
        assert tool_turn["content"][0]["is_error"] is True

    @pytest.mark.asyncio
    async def test_iteration_cap_terminates_a_looping_model(self, recorder, dispatcher):
        # A model that never stops calling tools must not run forever.
        client = ScriptedClient([_tool_response("run_rca_analysis", {})] * 20)
        result = await _controller(client, recorder, dispatcher, max_iterations=3).run()
        assert "Stopped after 3 iterations" in result["summary"]
        assert len(result["actions"]) == 3

    @pytest.mark.asyncio
    async def test_none_response_fails_the_run(self, recorder, dispatcher):
        class DeadClient:
            model = "dead"

            def get_response(self, **kwargs):
                return None

        with pytest.raises(WorkflowControllerError):
            await _controller(DeadClient(), recorder, dispatcher).run()


class TestControllerTrail:
    @pytest.mark.asyncio
    async def test_every_phase_is_recorded(self, recorder, dispatcher, session_factory):
        client = ScriptedClient(
            [_tool_response("run_rca_analysis", {}), _text_response("done")]
        )
        await _controller(client, recorder, dispatcher).run()

        trail = load_trail("run-ctrl", session_factory)
        phases = [s["phase"] for s in trail["steps"]]
        # The opening sweep runs CT deviation only (no follow-ups).
        assert phases.count(PHASE_SENSE) == len(DEFAULT_SENSE_TASKS)
        assert PHASE_ACT in phases
        assert phases[-1] == PHASE_REASON
        assert trail["status"] == "completed"
        assert trail["action_count"] == 1

    @pytest.mark.asyncio
    async def test_model_id_is_stamped_on_the_run(
        self, recorder, dispatcher, session_factory
    ):
        client = ScriptedClient([_text_response("done")])
        await _controller(client, recorder, dispatcher).run()
        assert load_trail("run-ctrl", session_factory)["model_id"] == "test-model"

    @pytest.mark.asyncio
    async def test_failed_run_is_marked_failed(
        self, recorder, dispatcher, session_factory
    ):
        class DeadClient:
            model = "dead"

            def get_response(self, **kwargs):
                return None

        with pytest.raises(WorkflowControllerError):
            await _controller(DeadClient(), recorder, dispatcher).run()
        trail = load_trail("run-ctrl", session_factory)
        assert trail["status"] == "failed"
        assert trail["error"]
