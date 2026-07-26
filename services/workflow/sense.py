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

# Analyses return metrics in two different shapes: CT deviation gives a list of
# per-equipment rows, run rate gives a single dict of aggregates. Both are
# handled rather than assumed.
KEY_METRICS = "metrics"
KEY_SUMMARY = "summary"
KEY_EQUIPMENT = "equipment_code"

# Per-equipment fields worth putting in front of the model. Anything else is
# noise at this stage and costs prompt tokens.
EQUIPMENT_FIELDS = (
    "deviation_percentage",
    "deviation_category",
    "efficiency_score",
    "stability_score",
    # Risk Tower fields: the only signal that sees week-over-week decline.
    "risk_score",
    "rag_status",
    "is_declining",
    "primary_risk_factor",
    "mttr_minutes",
    "mtbf_minutes",
    "mttr_vs_peers",
    "mtbf_vs_peers",
    "high_mttr",
    "frequent_stops",
)

# Aggregate fields from a dict-shaped metrics block.
AGGREGATE_FIELDS = (
    "efficiency_percentage",
    "total_stops",
    "total_sessions",
    "downtime_minutes",
    "average_stop_duration_minutes",
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


# The opening sweep. Cycle time deviation catches drift; Risk Tower catches
# week-over-week decline, frequent stops and long repairs, which a single-period
# average hides. Run rate is not here because it requires explicit equipment
# codes - there is no wildcard - so it follows up once suspects are named.
DEFAULT_SENSE_TASKS: List[SenseTask] = [
    SenseTask(tool_name="run_ct_deviation_analysis", arguments={}),
    SenseTask(tool_name="run_risk_tower_analysis", arguments={}),
]

CT_DEVIATION_TOOL = "run_ct_deviation_analysis"
RUNRATE_TOOL = "run_runrate_analysis"
KEY_DEVIATION = "deviation_percentage"

# How many of the worst machines get a run rate follow-up. Catching the seeded
# drift needs both signals: run rate alone cannot see it, and the contradiction
# between the two is the thing worth reasoning about.
FOLLOWUP_EQUIPMENT_COUNT = 3


def derive_followup_tasks(findings: List[SenseFinding]) -> List[SenseTask]:
    """
    Build run rate follow-ups for the worst machines the deviation pass found.

    Run rate takes explicit equipment codes, so the targets have to come from
    somewhere. Ranking by deviation focuses the second signal on the machines
    most likely to be interesting, without hard-coding any machine name.

    Args:
        findings: Results of the opening sweep.

    Returns:
        One run rate task per suspect equipment code, worst first. Empty when
        the deviation pass produced nothing usable.
    """
    rows: List[Dict[str, Any]] = []
    for finding in findings:
        if finding.tool_name != CT_DEVIATION_TOOL or not finding.ok:
            continue
        metrics = (finding.raw or {}).get(KEY_METRICS)
        if isinstance(metrics, list):
            rows.extend(row for row in metrics if isinstance(row, dict))

    ranked = sorted(
        (row for row in rows if row.get(KEY_EQUIPMENT)),
        key=lambda row: row.get(KEY_DEVIATION) or 0,
        reverse=True,
    )
    return [
        SenseTask(
            tool_name=RUNRATE_TOOL,
            arguments={"equipment_codes": [row[KEY_EQUIPMENT]]},
        )
        for row in ranked[:FOLLOWUP_EQUIPMENT_COUNT]
    ]


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


def _format_aggregates(metrics: Dict[str, Any]) -> List[str]:
    """Render a dict-shaped metrics block, keeping only the useful fields."""
    return [
        f"  {key}={metrics[key]}"
        for key in AGGREGATE_FIELDS
        if key in metrics and metrics[key] is not None
    ]


def summarize_sense_result(tool_name: str, result: Dict[str, Any]) -> str:
    """
    Condense one analysis result into a few lines of text.

    Handles both metric shapes the analyses return, and reports failures as
    findings rather than hiding them, so the model can decide what a missing
    signal means.

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
        lines.extend(_format_aggregates(metrics))
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

    A failed analysis becomes a finding rather than aborting the run: the agent
    should still reason over whatever signal it did gather.

    Args:
        tasks: Analyses to run.
        dispatcher: Awaitable tool dispatcher, injected for testability.
        on_step: Optional callback invoked per finding, used to record the
            decision trail. Defaults to None.

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
