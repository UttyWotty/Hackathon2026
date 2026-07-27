"""
Pure shaping of decision trails and score reports into display rows.

Turns the dictionaries returned by load_trail, list_runs and ScoreReport into
flat, labelled structures a view can render without further reasoning, so the
Streamlit layer stays a thin renderer. Contains no Streamlit import and no I/O.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

# Phases in the order the loop performs them, so a grouped trail always reads
# sense, then reason, then act, even if a phase is empty.
PHASE_SENSE = "sense"
PHASE_REASON = "reason"
PHASE_ACT = "act"
PHASE_ORDER = (PHASE_SENSE, PHASE_REASON, PHASE_ACT)

PHASE_TITLES = {
    PHASE_SENSE: "Sense: what the agent observed",
    PHASE_REASON: "Reason: what it concluded",
    PHASE_ACT: "Act: what it actually did",
}

STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# Shown when a step carries no tool, which is every reason step.
NO_TOOL_LABEL = "-"

MILLISECONDS_PER_SECOND = 1000.0
# Below this, milliseconds read better than a fractional second.
SUB_SECOND_MS = 1000.0
UNKNOWN_DURATION = "-"

# Payloads are rendered in an expander; this bounds what is put on screen.
MAX_PAYLOAD_CHARS = 1200
TRUNCATION_SUFFIX = "..."

RUN_LABEL_UNKNOWN_TIME = "unknown time"
# Length of an ISO timestamp trimmed to seconds, "2026-07-27T08:35:07".
ISO_SECONDS_LENGTH = 19

EMPTY_LIST_LABEL = "none"


@dataclass(frozen=True)
class StepRow:
    """One decision-trail step, flattened for display."""

    sequence: int
    phase: str
    status: str
    tool_name: str
    duration: str
    payload: str
    result_summary: str


@dataclass(frozen=True)
class PhaseGroup:
    """The steps belonging to one phase, with its display title."""

    phase: str
    title: str
    rows: List[StepRow]


@dataclass(frozen=True)
class Tile:
    """A single headline number with its caption."""

    label: str
    value: str
    help_text: str


def format_duration(duration_ms: Optional[float]) -> str:
    """
    Render a millisecond duration for display.

    Args:
        duration_ms: Duration in milliseconds, or None if never recorded.

    Returns:
        A short human-readable duration, or UNKNOWN_DURATION when absent.
    """
    if duration_ms is None:
        return UNKNOWN_DURATION
    if duration_ms < SUB_SECOND_MS:
        return f"{duration_ms:.0f}ms"
    return f"{duration_ms / MILLISECONDS_PER_SECOND:.1f}s"


def _render_payload(payload: Any) -> str:
    """Render a step payload compactly, bounded to MAX_PAYLOAD_CHARS."""
    if payload is None:
        return ""
    text = str(payload)
    if len(text) <= MAX_PAYLOAD_CHARS:
        return text
    return text[:MAX_PAYLOAD_CHARS] + TRUNCATION_SUFFIX


def build_step_row(step: Dict[str, Any]) -> StepRow:
    """
    Flatten one persisted step into a display row.

    Args:
        step: A step dictionary as produced by DecisionStep.to_dict.

    Returns:
        The step with every field present and rendered as a string.
    """
    return StepRow(
        sequence=step.get("sequence", 0),
        phase=step.get("phase", ""),
        status=step.get("status", ""),
        tool_name=step.get("tool_name") or NO_TOOL_LABEL,
        duration=format_duration(step.get("duration_ms")),
        payload=_render_payload(step.get("payload")),
        result_summary=step.get("result_summary") or "",
    )


def group_steps_by_phase(steps: Sequence[Dict[str, Any]]) -> List[PhaseGroup]:
    """
    Group trail steps into sense, reason and act, in loop order.

    Phases with no steps are returned as empty groups rather than omitted: a
    run that reasoned but never acted is the failure mode this demo exists to
    make visible, and hiding the empty Act group would conceal it.

    Args:
        steps: Step dictionaries in sequence order.

    Returns:
        One PhaseGroup per phase, always three, in PHASE_ORDER.
    """
    rows = [build_step_row(step) for step in steps]
    return [
        PhaseGroup(
            phase=phase,
            title=PHASE_TITLES[phase],
            rows=[row for row in rows if row.phase == phase],
        )
        for phase in PHASE_ORDER
    ]


def format_equipment_list(codes: Sequence[str]) -> str:
    """
    Render a list of equipment codes, or an explicit label when empty.

    Args:
        codes: Equipment codes.

    Returns:
        A comma-separated list, or EMPTY_LIST_LABEL.
    """
    return ", ".join(codes) if codes else EMPTY_LIST_LABEL


def build_score_tiles(report: Dict[str, Any]) -> List[Tile]:
    """
    Build the headline score tiles from a serialised ScoreReport.

    Args:
        report: The dictionary from ScoreReport.to_dict.

    Returns:
        Four tiles: precision, recall, F1 and whether the headline was caught.
    """
    headline = report.get("headline_found", False)
    return [
        Tile(
            label="Precision",
            value=f"{report.get('precision', 0.0):.2f}",
            help_text="Share of flagged machines that carry a planted defect.",
        ),
        Tile(
            label="Recall",
            value=f"{report.get('recall', 0.0):.2f}",
            help_text="Share of planted defects the agent flagged.",
        ),
        Tile(
            label="F1",
            value=f"{report.get('f1', 0.0):.2f}",
            help_text="Harmonic mean of precision and recall.",
        ),
        Tile(
            label="Headline defect",
            value="caught" if headline else "missed",
            help_text=(
                "The drifting machine a single-metric monitor cannot see. "
                "This is the run that matters."
            ),
        ),
    ]


def run_label(run: Dict[str, Any]) -> str:
    """
    Build a one-line label for a past run, for the history picker.

    Args:
        run: A run dictionary as produced by DecisionRun.to_dict.

    Returns:
        A label carrying start time, status and backend.
    """
    started = run.get("started_at") or ""
    stamp = started[:ISO_SECONDS_LENGTH] if started else RUN_LABEL_UNKNOWN_TIME
    backend = run.get("llm_backend") or "unknown backend"
    status = run.get("status", "")
    return f"{stamp}  {status}  ({backend})"


def unbacked_claim_warning(report: Dict[str, Any]) -> Optional[str]:
    """
    Build the warning shown when the summary claimed unrecorded work.

    Models narrate work they did not do. The trail is the record and the
    summary is only a claim, so a mismatch is surfaced rather than smoothed
    over.

    Args:
        report: The dictionary from ScoreReport.to_dict.

    Returns:
        A warning string, or None when every claim is backed by a step.
    """
    claimed = report.get("claimed_only") or []
    if not claimed:
        return None
    return (
        f"The summary named {', '.join(claimed)} but the trail has no act step "
        "for them. These claims are unbacked."
    )


__all__ = [
    "StepRow",
    "PhaseGroup",
    "Tile",
    "format_duration",
    "build_step_row",
    "group_steps_by_phase",
    "format_equipment_list",
    "build_score_tiles",
    "run_label",
    "unbacked_claim_warning",
    "PHASE_ORDER",
]
