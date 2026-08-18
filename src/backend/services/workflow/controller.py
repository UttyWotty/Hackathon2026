"""
Headless sense-reason-act controller for the autonomous workflow agent.

Runs an anomaly sweep, hands the findings to the LLM, lets it chain tool calls
through the existing dispatcher, and records every step to the decision trail.
Triggered by a schedule or an event rather than a human chat turn.
"""

import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from core.cortex_wire import (
    extract_assistant_message,
    extract_text_from_response,
    extract_tool_uses,
    format_tool_result,
    get_stop_reason,
)
from core.tools_config import get_tools_for_llm
from models.decision_trail import (
    PHASE_Aduration,
    PHASE_REASON,
    PHASE_SENSE,
    STATUS_COMPLETED,
    STATUS_FAILED,
    TRIGGER_SCHEDULE,
)
from services.infrastructure.scheduler.tool_dispatcher import dispatch_tool_direct
from services.workflow.agent_prompt import build_agent_prompt, build_failure_note
from services.workflow.model_text import strip_reasoning
from services.workflow.sense import (
    DEFAULT_SENSE_TASKS,
    SenseFinding,
    SenseTask,
    derive_followup_tasks,
    format_findings,
    run_sense_tasks,
)
from services.workflow.trail_recorder import TrailRecorder

logger = logging.getLogger(__name__)

# Bound on the reason-act loop. The chat surface uses 5; an unattended run is
# given more room to chain investigation and reporting, but still terminates.
MAX_ITERATIONS = 8

STOP_REASON_TOOL_USE = "tool_use"
MILLISECONDS_PER_SECOND = 1000.0

# Trail summaries are truncated by the recorder; this bounds what we build.
MAX_RESULT_CHARS = 800


class WorkflowControllerError(Exception):
    """Raised when an autonomous run cannot be completed."""


def _summarize_tool_result(result: Any) -> str:
    """Render a tool result compactly enough to store in the trail."""
    try:
        text = json.dumps(result, default=str)
    except (TypeError, ValueError):
        text = str(result)
    return text[:MAX_RESULT_CHARS]


class WorkflowController:
    """Runs one autonomous sense-reason-act cycle and records its trail."""

    def __init__(
        self,
        llm_client: Any,
        recorder: Optional[TrailRecorder] = None,
        dispatcher: Optional[
            Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]
        ] = None,
        sense_tasks: Optional[List[SenseTask]] = None,
        max_iterations: int = MAX_ITERATIONS,
        tools_provider: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    ) -> None:
        """
        Build a controller.

        Args:
            llm_client: Any client exposing get_response, from llm_backend.
            recorder: Decision trail recorder. Defaults to a fresh TrailRecorder.
            dispatcher: Awaitable tool dispatcher. Defaults to
                dispatch_tool_direct; injectable for testing.
            sense_tasks: Analyses for the sweep. Defaults to DEFAULT_SENSE_TASKS.
            max_iterations: Cap on reason-act turns. Defaults to 8.
            tools_provider: Returns the tool schema offered to the model.
                Defaults to get_tools_for_llm. Injectable so a caller can trim
                the schema, which matters on local models where all 35 tools
                are roughly 7,000 tokens of prefill per turn.
        """
        self.llm_client = llm_client
        self.recorder = recorder or TrailRecorder()
        self.dispatcher = dispatcher or dispatch_tool_direct
        self.sense_tasks = (
            sense_tasks if sense_tasks is not None else DEFAULT_SENSE_TASKS
        )
        self.max_iterations = max_iterations
        self.tools_provider = tools_provider or get_tools_for_llm

    async def run(self, trigger: str = TRIGGER_SCHEDULE) -> Dict[str, Any]:
        """
        Execute one autonomous cycle.

        Args:
            trigger: What started this run, from the TRIGGER_* constants.

        Returns:
            A dict with run_id, status, summary, actions taken and findings.

        Raises:
            WorkflowControllerError: If the reasoning phase cannot start.
        """
        self.recorder.start_run(
            trigger=trigger,
            llm_backend=getattr(self.llm_client, "backend_name", None),
            model_id=getattr(self.llm_client, "model", None),
        )

        try:
            findings = await self._sense()
            summary, actions = await self._reason_and_act(findings)
        except Exception as exc:
            self.recorder.finish_run(status=STATUS_FAILED, error=str(exc))
            raise WorkflowControllerError(f"Autonomous run failed: {exc}") from exc

        self.recorder.finish_run(status=STATUS_COMPLETED, summary=summary)
        return {
            "run_id": self.recorder.run_id,
            "status": STATUS_COMPLETED,
            "summary": summary,
            "actions": actions,
            "findings": [f.summary for f in findings],
        }

    async def _sense(self) -> List[SenseFinding]:
        """
        Run the anomaly sweep across the fleet.

        The follow-up pass derives additional tasks from the opening sweep findings.
        """

        def record(finding: SenseFinding) -> None:
            self.recorder.record_step(
                phase=PHASE_SENSE,
                status=STATUS_COMPLETED if finding.ok else STATUS_FAILED,
                tool_name=finding.tool_name,
                result_summary=finding.summary,
            )

        findings = await run_sense_tasks(
            self.sense_tasks, self.dispatcher, on_step=record
        )
        followups = derive_followup_tasks(findings)
        if followups:
            findings.extend(
                await run_sense_tasks(followups, self.dispatcher, on_step=record)
            )
        return findings

    def _build_prompt(self, findings: List[SenseFinding]) -> str:
        """Compose the observation prompt, flagging any missing signal."""
        text = format_findings(findings)
        note = build_failure_note([f.tool_name for f in findings if not f.ok])
        return build_agent_prompt(text if not note else f"{text}\n\n{note}")

    async def _reason_and_act(
        self, findings: List[SenseFinding]
    ) -> tuple[str, List[str]]:
        """
        Drive the LLM loop until it stops calling tools.

        Returns:
            The closing summary text and the list of tools actually invoked.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": self._build_prompt(findings)}
        ]
        tools = self.tools_provider()
        actions: List[str] = []

        for iteration in range(self.max_iterations):
            response = self.llm_client.get_response(
                messages=messages, tools=tools, session_id=self.recorder.run_id
            )
            if response is None:
                raise WorkflowControllerError(
                    f"LLM returned no response on iteration {iteration + 1}"
                )

            if get_stop_reason(response) != STOP_REASON_TOOL_USE:
                # Store the conclusion, not the scratchpad: head-truncation
                # would otherwise keep the deliberation and drop the answer.
                text = strip_reasoning(extract_text_from_response(response))
                self.recorder.record_step(
                    phase=PHASE_REASON, status=STATUS_COMPLETED, result_summary=text
                )
                return text, actions

            messages.append(extract_assistant_message(response))
            await self._execute_tools(response, messages, actions)

        logger.warning("Autonomous run hit the %d iteration cap", self.max_iterations)
        return (
            f"Stopped after {self.max_iterations} iterations without a final summary.",
            actions,
        )

    async def _execute_tools(
        self,
        response: Dict[str, Any],
        messages: List[Dict[str, Any]],
        actions: List[str],
    ) -> None:
        """Run every tool the model requested and append results to messages."""
        for tool_use in extract_tool_uses(response):
            name = tool_use["name"]
            arguments = tool_use.get("input") or {}
            started = time.perf_counter()

            try:
                result = await self.dispatcher(name, arguments)
                failed = False
            except Exception as exc:  # noqa: BLE001 - reported back to the model
                result = {"status": "error", "error": str(exc)}
                failed = True

            elapsed = (time.perf_counter() - started) * MILLISECONDS_PER_SECOND
            actions.append(name)
            self.recorder.record_step(
                phase=PHASE_Aduration,
                status=STATUS_FAILED if failed else STATUS_COMPLETED,
                tool_name=name,
                payload=arguments,
                result_summary=_summarize_tool_result(result),
                duration_ms=elapsed,
            )
            messages.append(
                format_tool_result(tool_use["toolUseId"], result, is_error=failed)
            )
