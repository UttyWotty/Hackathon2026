"""
Streamlit rendering of the demo's panels.

Draws the configuration header, the decision trail, the score card and the
drift chart from structures the pure presenters already shaped, so nothing
here decides anything. Every function takes plain data and returns None.
"""

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from demo.presenters import (
    PhaseGroup,
    Tile,
    build_score_tiles,
    format_duration,
    format_equipment_list,
    group_steps_by_phase,
    unbacked_claim_warning,
)
from demo.runner import DemoConfig
from demo.story import to_chart_frame

# Column proportions for the step table: sequence, tool, status, duration.
STEP_COLUMNS = (1, 6, 2, 2)

CHART_Y_LABEL = "Mean duration deviation vs approved (%)"
CHART_X_LABEL = "Production week"

STATUS_FAILED = "failed"

KEY_TRUE_POSITIVES = "true_positives"
KEY_FALSE_NEGATIVES = "false_negatives"
KEY_FALSE_POSITIVES = "false_positives"
KEY_INVESTIGATED = "investigated"

BACKEND_MLX = "mlx"


def render_config(config: DemoConfig) -> None:
    """
    Draw the header describing what this demo is pointed at.

    Args:
        config: The environment description from runner.read_config.
    """
    columns = st.columns(3)
    columns[0].metric("LLM backend", config.llm_backend)
    columns[1].metric("Data source", config.data_source)
    columns[2].metric("Iteration cap", str(config.max_iterations))

    if config.llm_backend == BACKEND_MLX:
        st.warning(
            "Running on the local MLX backend. This is a development path, "
            "not the submission path. Set LLM_BACKEND=cortex for the demo."
        )
    if not config.ground_truth_available:
        st.info(
            "No ground truth is loaded, so runs cannot be graded. Point "
            "LOCAL_DATA_DIR at the generator's output to enable scoring."
        )


def render_summary(trail: Dict[str, Any]) -> None:
    """
    Draw a run's headline outcome and the model's own conclusion.

    Args:
        trail: A trail as returned by runner.read_trail.
    """
    columns = st.columns(4)
    columns[0].metric("Status", trail.get("status", "-"))
    columns[1].metric("Actions taken", str(trail.get("action_count", 0)))
    columns[2].metric("Duration", format_duration(trail.get("duration_ms")))
    columns[3].metric("Model", trail.get("model_id") or "-")

    if trail.get("error"):
        st.error(trail["error"])

    st.markdown("**The agent's conclusion**")
    st.write(trail.get("summary") or "No summary was recorded.")


def _render_phase(group: PhaseGroup) -> None:
    """Draw one phase group, including when it is empty."""
    st.markdown(f"**{group.title}**")
    if not group.rows:
        st.caption("No steps in this phase.")
        return
    for row in group.rows:
        columns = st.columns(STEP_COLUMNS)
        columns[0].write(str(row.sequence))
        columns[1].write(row.tool_name)
        columns[2].write(row.status)
        columns[3].write(row.duration)
        if row.payload or row.result_summary:
            with st.expander(f"Step {row.sequence} detail", expanded=False):
                if row.payload:
                    st.caption("Arguments")
                    st.code(row.payload)
                if row.result_summary:
                    st.caption("Result")
                    st.text(row.result_summary)


def render_trail(trail: Dict[str, Any]) -> None:
    """
    Draw the full decision trail, grouped into sense, reason and act.

    Args:
        trail: A trail as returned by runner.read_trail.
    """
    steps: List[Dict[str, Any]] = trail.get("steps", [])
    if not steps:
        st.info("This run recorded no steps.")
        return
    for group in group_steps_by_phase(steps):
        _render_phase(group)
        st.divider()


def _render_tiles(tiles: List[Tile]) -> None:
    """Draw the headline score tiles in a row."""
    columns = st.columns(len(tiles))
    for column, tile in zip(columns, tiles):
        column.metric(tile.label, tile.value, help=tile.help_text)


def render_score(report: Optional[Dict[str, Any]]) -> None:
    """
    Draw the grade of a run against the planted defects.

    Args:
        report: A serialised ScoreReport, or None when grading is unavailable.
    """
    if report is None:
        st.info(
            "Grading needs the generated dataset's ground_truth.json. "
            "Set LOCAL_DATA_DIR to enable it."
        )
        return

    _render_tiles(build_score_tiles(report))

    warning = unbacked_claim_warning(report)
    if warning:
        st.error(warning)

    st.markdown(
        f"- Caught: `{format_equipment_list(report.get(KEY_TRUE_POSITIVES, []))}`\n"
        f"- Missed: `{format_equipment_list(report.get(KEY_FALSE_NEGATIVES, []))}`\n"
        f"- False positives: "
        f"`{format_equipment_list(report.get(KEY_FALSE_POSITIVES, []))}`\n"
        f"- Investigated with a tool call: "
        f"`{format_equipment_list(report.get(KEY_INVESTIGATED, []))}`"
    )
    st.caption(
        "Scored from the act-step payloads in the trail, not from the "
        "summary text. A machine the agent only wrote about does not count "
        "as investigated."
    )


def render_drift_chart(weekly: pd.DataFrame, headline: Optional[str]) -> None:
    """
    Draw fleet-wide weekly duration deviation, which is where the defect shows.

    Args:
        weekly: The long frame from story.weekly_deviation.
        headline: The equipment code carrying the planted drift, if known.
    """
    chart_frame = to_chart_frame(weekly)
    if chart_frame.empty:
        st.info("No shot data available to chart.")
        return

    st.line_chart(chart_frame, x_label=CHART_X_LABEL, y_label=CHART_Y_LABEL)
    if headline:
        st.caption(
            f"{headline} climbs week over week while the fleet stays flat. "
            "Its stability score stays healthy throughout, which is why a "
            "single-metric threshold never fires on it."
        )


__all__ = [
    "render_config",
    "render_summary",
    "render_trail",
    "render_score",
    "render_drift_chart",
]
