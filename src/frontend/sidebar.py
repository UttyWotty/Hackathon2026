"""Sidebar composition for the manufacturing fleet dashboard.

Owns the grouping, ordering, and spacing of every sidebar control, so the panel
functions in `interactive_controls` and `help_chat` stay container-agnostic and
render wherever they are placed. Sections are grouped into Run / Data / Help
expanders because seven flat sections required multiple scrolls at 1080p.
"""

import streamlit as st
from action_loop import log_work_order, trigger_alert
from help_chat import render_help_chat
from interactive_controls import (
    _clear_data_caches,
    render_csv_upload,
    render_rca_selector,
    render_sweep_panel,
)
from session_helper import get_session
from theme import SEVERITY_WARNING

AUDIT_TABLE = "DEMO.PUBLIC.AUDIT_LOG"
MANUAL_ACTION_MACHINE = "MX-7103"

_ARCHITECTURE_DIAGRAM = (
    "[TRIGGER] Schedule / command / button\n"
    "     |\n"
    "     v\n"
    "[SENSE] Multi-signal fleet sweep\n"
    "  - Duration deviation from target\n"
    "  - Week-over-week stability decline\n"
    "  - Efficiency degradation\n"
    "  - Tooling wear (shot accumulation)\n"
    "     |\n"
    "     v\n"
    "[REASON] Snowflake Cortex LLM\n"
    "  - Cross-signal correlation\n"
    "  - Prioritize by severity\n"
    "  - Decide investigation targets\n"
    "     |\n"
    "     v\n"
    "[ACT] Investigate + Respond\n"
    "  - Temporal root cause breakdown\n"
    "  - Corroborate with operator notes\n"
    "  - Log work orders / send alerts\n"
    "  - Update equipment status\n"
    "     |\n"
    "     v\n"
    "[RECORD] Audit + Self-evaluate\n"
    "  - Full decision trail to AUDIT_LOG\n"
    "  - Evidence + severity recorded\n"
    "  - Self-grade against ground truth"
)

_SKILLS = (
    ("$sense-equipment-anomalies", "Sweeps fleet for duration drift and stability decline."),
    ("$investigate-shift-notes", "Searches operator notes to explain WHY a machine is abnormal."),
    ("$report-and-act", "Records decision, evidence, and actions to audit trail."),
)


def _render_architecture() -> None:
    """Render the sense-reason-act diagram and the skill reference."""
    st.code(_ARCHITECTURE_DIAGRAM, language=None)
    for skill_name, description in _SKILLS:
        st.markdown(f"**{skill_name}**")
        st.caption(description)


def _render_audit_reset() -> None:
    """Render the guarded audit-log reset control.

    Truncating AUDIT_LOG is irreversible and destroys the decision trail the
    demo depends on, so the button stays disabled until explicitly confirmed.
    """
    confirm_reset = st.checkbox(
        "Confirm audit log reset", key="confirm_reset_audit", value=False
    )
    if st.button(
        "Reset Audit Log",
        key="reset_audit_log",
        use_container_width=True,
        disabled=not confirm_reset,
    ):
        session = get_session()
        session.sql(f"TRUNCATE TABLE {AUDIT_TABLE}").collect()
        _clear_data_caches()
        st.success("Audit log cleared.")


def _render_manual_actions() -> None:
    """Render the two manual write buttons used to prove the action loop."""
    col_alert, col_wo = st.columns(2)
    with col_alert:
        if st.button("Alert", key="manual_alert", use_container_width=True):
            trigger_alert(
                MANUAL_ACTION_MACHINE,
                SEVERITY_WARNING,
                "Manual test alert dispatched from dashboard.",
            )
            st.success("Alert sent.")
    with col_wo:
        if st.button("Work Order", key="manual_wo", use_container_width=True):
            log_work_order(
                MANUAL_ACTION_MACHINE,
                SEVERITY_WARNING,
                "Manual work order logged from dashboard.",
            )
            st.success("Work order logged.")


def render_sidebar() -> None:
    """Compose the full sidebar: Run, Data, Reference, and Help sections."""
    st.sidebar.title("Controls")
    st.sidebar.caption("Interact with the fleet in real-time")

    # Expanded by default: the sweep panel surfaces CRITICAL/WARNING counts, and
    # those must never be hidden behind a collapsed section.
    with st.sidebar.expander("Run", expanded=True):
        render_sweep_panel()
        st.divider()
        render_rca_selector()

    with st.sidebar.expander("Data", expanded=False):
        render_csv_upload()
        st.divider()
        _render_audit_reset()
        _render_manual_actions()

    with st.sidebar.expander("Agent Architecture", expanded=False):
        _render_architecture()

    with st.sidebar.expander("Help Chat", expanded=False):
        render_help_chat()
