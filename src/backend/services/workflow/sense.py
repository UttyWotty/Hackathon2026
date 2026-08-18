"""
Sense phase of the autonomous workflow agent.

Runs a configured set of anomaly-detection analyses and condenses their output
into short text findings the LLM can reason over, since raw analysis results
carry whole DataFrames. Summarisation is pure; only run_sense_tasks does I/O.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Status values returned by the analysis tools.
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Analyses return metrics as a list of per-equipment rows.
KEY_METRICS = "metrics"
KEY_SUMMARY = "summary"
KEY_EQUIPMENT = "machine_id"

# Per-equipment fields worth putting in front of the model.
EQUIPMENT_FIELDS = (
    "deviation_percentage",
    "deviation_category",
    "efficiency_score",
    "stability_score",
)

MAX_EQUIPMENT_ROWS = 20
NO_FINDINGS_TEXT = "no metrics returned"


@dataclass(frozen=True)
class SenseTask:
    """One analysis to run during the sense phase."""

    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SenseFinding:
    """The condensed outcome of one sense task."""

    tool_name: str
    status: str
    summary: str
    raw: Optional[Dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        """Whether the underlying analysis succeeded."""
        return self.status == STATUS_SUCCESS


# The opening sweep. Duration deviation catches drift and stability decline.
DEFAULT_SENSE_TASKS: List[SenseTask] = [
    SenseTask(tool_name="run_deviation_analysis", arguments={}),
]

DEVIATION_TOOL = "run_deviation_analysis"
KEY_DEVIATION = "deviation_percentage"


def derive_followup_tasks(findings: List[SenseFinding]) -> List[SenseTask]:
    """
    Derive follow-up tasks from the opening sweep findings.

    Currently returns empty - the duration deviation sweep is the only detector.

    Args:
        findings: Results of the opening sweep.

    Returns:
        Empty list; no follow-up tools configured.
    """
    return []


def _format_equipment_rows(rows: List[Dict[str, Any]]) -> List[str]:
    """Render per-equipment metric rows as one compact line each."""
    lines = []
    for row in rows[:MAX_EQUIPMENT_ROWS]:
        parts = [f"{row.get(KEY_EQUIPMENT, 'unknown')}"]
        for key in EQUIPMENT_FIELDS:
            if key in row and row[key] is not None:
                parts.append(f"{key}={row[key]}")
        lines.append("  " + " ".join(parts))
    if len(rows) > MAX_EQUIPMENT_ROWS:
        lines.append(f"  ... {len(rows) - MAX_EQUIPMENT_ROWS} more rows omitted")
    return lines


def summarize_sense_result(tool_name: str, result: Dict[str, Any]) -> str:
    """
    Condense one analysis result into a few lines of text.

    Args:
        tool_name: The analysis that produced the result.
        result: The tool's raw return value.

    Returns:
        A short human and model readable summary.
    """
    if not isinstance(result, dict):
        return f"{tool_name}: unexpected result type {type(result).__name__}"

    if result.get("status") == STATUS_ERROR:
        return f"{tool_name}: FAILED - {result.get('error', 'unknown error')}"

    lines = [f"{tool_name}:"]
    metrics = result.get(KEY_METRICS)

    if isinstance(metrics, list) and metrics:
        lines.extend(_format_equipment_rows(metrics))
    elif isinstance(metrics, dict) and metrics:
        lines.append(f"  {NO_FINDINGS_TEXT}")
    else:
        lines.append(f"  {NO_FINDINGS_TEXT}")

    summary = result.get(KEY_SUMMARY)
    if isinstance(summary, dict):
        distribution = summary.get("category_distribution")
        if distribution:
            lines.append(f"  category_distribution={distribution}")

    return "\n".join(lines)


def format_findings(findings: List[SenseFinding]) -> str:
    """
    Join findings into the observation block handed to the model.

    Args:
        findings: Results of the sense phase, in execution order.

    Returns:
        One text block, or a clear statement that nothing was gathered.
    """
    if not findings:
        return "No sense analyses were run."
    return "\n".join(finding.summary for finding in findings)


async def run_sense_tasks(
    tasks: List[SenseTask],
    dispatcher: Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]],
    on_step: Optional[Callable[[SenseFinding], None]] = None,
) -> List[SenseFinding]:
    """
    Execute the sense sweep, tolerating individual analysis failures.

    Args:
        tasks: Analyses to run.
        dispatcher: Awaitable tool dispatcher, injected for testability.
        on_step: Optional callback invoked per finding.

    Returns:
        One finding per task, in order.
    """
    findings: List[SenseFinding] = []
    for task in tasks:
        try:
            result = await dispatcher(task.tool_name, task.arguments)
        except Exception as exc:  # noqa: BLE001 - one bad tool must not stop the sweep
            logger.warning("Sense task %s raised: %s", task.tool_name, exc)
            result = {"status": STATUS_ERROR, "error": str(exc)}

        finding = SenseFinding(
            tool_name=task.tool_name,
            status=result.get("status", STATUS_ERROR),
            summary=summarize_sense_result(task.tool_name, result),
            raw=result,
        )
        findings.append(finding)
        if on_step is not None:
            on_step(finding)
    return findings
