"""
Decision trail database models for the autonomous workflow agent.

Records every autonomous run and each sense, reason and act step within it, so
the agent's behaviour can be replayed and audited rather than taken on trust.
One DecisionRun owns an ordered sequence of DecisionStep rows.
"""

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (  # type: ignore[import-untyped]
    JSON,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)

from .database import Base

# What started a run.
TRIGGER_SCHEDULE = "schedule"
TRIGGER_MANUAL = "manual"
TRIGGER_ANOMALY = "anomaly_event"

# Run and step lifecycle states.
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# The three phases of the autonomous loop. Logged per step so the trail can be
# grouped into what the agent observed, concluded, and then did about it.
PHASE_SENSE = "sense"
PHASE_REASON = "reason"
PHASE_ACT = "act"

# Column widths, named so the models and any validation agree.
LEN_RUN_ID = 64
LEN_SHORT = 50
LEN_MODEL_ID = 120


class DecisionRun(Base):
    """One autonomous execution of the sense-reason-act loop."""

    __tablename__ = "decision_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(LEN_RUN_ID), unique=True, nullable=False, index=True)

    trigger = Column(String(LEN_SHORT), nullable=False, index=True)
    status = Column(String(LEN_SHORT), nullable=False, index=True)

    # Which backend produced the reasoning, so a trail is never ambiguous about
    # whether it came from Cortex or a local development model.
    llm_backend = Column(String(LEN_SHORT), nullable=True)
    model_id = Column(String(LEN_MODEL_ID), nullable=True)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)

    summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the run for API responses and the demo trail view."""
        return {
            "run_id": self.run_id,
            "trigger": self.trigger,
            "status": self.status,
            "llm_backend": self.llm_backend,
            "model_id": self.model_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_ms": self.duration_ms,
            "summary": self.summary,
            "error": self.error,
        }


class DecisionStep(Base):
    """A single sense, reason or act step belonging to a DecisionRun."""

    __tablename__ = "decision_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(LEN_RUN_ID), nullable=False, index=True)

    # Ordering is explicit rather than inferred from the timestamp, because
    # steps can share a timestamp at this resolution.
    sequence = Column(Integer, nullable=False)

    phase = Column(String(LEN_SHORT), nullable=False, index=True)
    tool_name = Column(String(LEN_MODEL_ID), nullable=True, index=True)
    status = Column(String(LEN_SHORT), nullable=False)

    # Tool arguments and a condensed result. The full result is deliberately not
    # stored: analysis output includes whole DataFrames.
    payload = Column(JSON, nullable=True)
    result_summary = Column(Text, nullable=True)

    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the step for API responses and the demo trail view."""
        return {
            "run_id": self.run_id,
            "sequence": self.sequence,
            "phase": self.phase,
            "tool_name": self.tool_name,
            "status": self.status,
            "payload": self.payload,
            "result_summary": self.result_summary,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
