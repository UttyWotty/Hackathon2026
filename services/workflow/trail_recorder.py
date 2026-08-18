"""
Persistence adapter for the autonomous agent's decision trail.

Wraps DecisionRun and DecisionStep writes behind a small recorder so the
controller never touches a session directly, and so a run's steps are numbered
consistently. The session factory is injectable, making the recorder testable
against an in-memory database.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from models.database import get_session
from models.decision_trail import (
    PHASE_Aduration,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
    DecisionRun,
    DecisionStep,
)
from services.workflow.model_text import (
    TRUNCATION_MARKER,
    truncate_keeping_tail,
)

logger = logging.getLogger(__name__)

# Result summaries are truncated before storage: analysis output can carry an
# entire DataFrame and the trail is meant to be readable, not complete.
MAX_SUMMARY_CHARS = 2000

MILLISECONDS_PER_SECOND = 1000.0

# How many past runs the history reader returns when no limit is given.
DEFAULT_RUN_LIST_LIMIT = 25


class TrailRecorderError(Exception):
    """Raised when the decision trail cannot be written."""


def _truncate(text: Optional[str]) -> Optional[str]:
    """Cut structured output down to the storage limit, keeping the head."""
    if text is None:
        return None
    if len(text) <= MAX_SUMMARY_CHARS:
        return text
    return text[:MAX_SUMMARY_CHARS] + TRUNCATION_MARKER


def _truncate_conclusion(text: Optional[str]) -> Optional[str]:
    """
    Cut a model conclusion down to the limit, keeping the END.

    A reasoning model puts its answer last, so head-truncation stores the
    deliberation and discards the conclusion. Observed live: a run's entire
    stored summary was scratchpad, with the verdict cut off.
    """
    if text is None:
        return None
    return truncate_keeping_tail(text, MAX_SUMMARY_CHARS)


class TrailRecorder:
    """Records one autonomous run and its ordered steps."""

    def __init__(
        self,
        run_id: Optional[str] = None,
        session_factory: Callable[[], Any] = get_session,
    ) -> None:
        """
        Create a recorder for a single run.

        Args:
            run_id: Identifier for the run. Defaults to a fresh UUID4 hex.
            session_factory: Callable returning a SQLAlchemy session context
                manager. Defaults to the application's get_session.
        """
        self.run_id = run_id or uuid.uuid4().hex
        self.session_factory = session_factory
        self._sequence = 0

    def start_run(
        self,
        trigger: str,
        llm_backend: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> str:
        """
        Open a run in the running state.

        Args:
            trigger: What started the run, from the TRIGGER_* constants.
            llm_backend: Backend name, so the trail records what reasoned.
            model_id: Model identifier used for reasoning.

        Returns:
            The run identifier.

        Raises:
            TrailRecorderError: If the row cannot be written.
        """
        run = DecisionRun(
            run_id=self.run_id,
            trigger=trigger,
            status=STATUS_RUNNING,
            llm_backend=llm_backend,
            model_id=model_id,
            started_at=datetime.utcnow(),
        )
        self._write(run)
        logger.info("Decision run %s started (trigger=%s)", self.run_id, trigger)
        return self.run_id

    def record_step(
        self,
        phase: str,
        status: str,
        tool_name: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        result_summary: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ) -> int:
        """
        Append a step to the trail.

        Args:
            phase: One of the PHASE_* constants.
            status: Step outcome, from the STATUS_* constants.
            tool_name: Tool invoked, when the phase is act or sense.
            payload: Tool arguments, stored as JSON.
            result_summary: Condensed result, truncated before storage.
            duration_ms: Wall clock duration of the step.

        Returns:
            The step's sequence number, starting at 1.

        Raises:
            TrailRecorderError: If the row cannot be written.
        """
        self._sequence += 1
        step = DecisionStep(
            run_id=self.run_id,
            sequence=self._sequence,
            phase=phase,
            status=status,
            tool_name=tool_name,
            payload=payload,
            result_summary=_truncate(result_summary),
            duration_ms=duration_ms,
            created_at=datetime.utcnow(),
        )
        self._write(step)
        return self._sequence

    def finish_run(
        self,
        status: str = STATUS_COMPLETED,
        summary: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Close the run, stamping completion time and duration.

        Args:
            status: Terminal status. Defaults to completed.
            summary: The agent's closing narrative.
            error: Failure detail when status is failed.

        Raises:
            TrailRecorderError: If the run row cannot be updated.
        """
        try:
            with self.session_factory() as session:
                run = (
                    session.query(DecisionRun)
                    .filter(DecisionRun.run_id == self.run_id)
                    .one_or_none()
                )
                if run is None:
                    raise TrailRecorderError(
                        f"Cannot finish unknown decision run {self.run_id}"
                    )
                completed = datetime.utcnow()
                run.status = status
                run.completed_at = completed
                run.duration_ms = (
                    completed - run.started_at
                ).total_seconds() * MILLISECONDS_PER_SECOND
                run.summary = _truncate_conclusion(summary)
                run.error = _truncate(error)
                session.commit()
        except TrailRecorderError:
            raise
        except Exception as exc:
            raise TrailRecorderError(
                f"Failed to finish run {self.run_id}: {exc}"
            ) from exc
        logger.info("Decision run %s finished (status=%s)", self.run_id, status)

    def _write(self, row: Any) -> None:
        """Persist one row, converting any driver failure to a domain error."""
        try:
            with self.session_factory() as session:
                session.add(row)
                session.commit()
        except Exception as exc:
            raise TrailRecorderError(
                f"Failed to write decision trail for run {self.run_id}: {exc}"
            ) from exc


def load_trail(
    run_id: str, session_factory: Callable[[], Any] = get_session
) -> Dict[str, Any]:
    """
    Read back a complete decision trail.

    Args:
        run_id: The run to load.
        session_factory: Session provider. Defaults to get_session.

    Returns:
        The run with its steps in sequence order, or an empty dict if absent.
    """
    with session_factory() as session:
        run = (
            session.query(DecisionRun)
            .filter(DecisionRun.run_id == run_id)
            .one_or_none()
        )
        if run is None:
            return {}
        steps: List[DecisionStep] = (
            session.query(DecisionStep)
            .filter(DecisionStep.run_id == run_id)
            .order_by(DecisionStep.sequence)
            .all()
        )
        trail = run.to_dict()
        trail["steps"] = [step.to_dict() for step in steps]
        trail["action_count"] = sum(1 for s in steps if s.phase == PHASE_ACT)
        return trail


def list_runs(
    limit: int = DEFAULT_RUN_LIST_LIMIT,
    session_factory: Callable[[], Any] = get_session,
) -> List[Dict[str, Any]]:
    """
    List recent runs, newest first, without their steps.

    Used by the demo history picker, which needs to label runs before deciding
    which trail to load in full.

    Args:
        limit: Maximum number of runs to return. Defaults to
            DEFAULT_RUN_LIST_LIMIT.
        session_factory: Session provider. Defaults to get_session.

    Returns:
        Serialised runs ordered by start time descending.
    """
    with session_factory() as session:
        runs: List[DecisionRun] = (
            session.query(DecisionRun)
            .order_by(DecisionRun.started_at.desc())
            .limit(limit)
            .all()
        )
        return [run.to_dict() for run in runs]


__all__ = [
    "TrailRecorder",
    "TrailRecorderError",
    "load_trail",
    "list_runs",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
]
