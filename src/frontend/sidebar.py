"""Sidebar composition for the manufacturing fleet dashboard.

Owns the grouping, ordering, and spacing of every sidebar control, so the panel
functions in `interactive_controls` stay container-agnostic and
render wherever they are placed. Sections are grouped into Run / Data /
Reference expanders because seven flat sections required multiple scrolls at
1080p. The help chat lives in its own top-level tab, not here.
"""

import streamlit as st
from action_loop import log_work_order, trigger_alert
from help_chat import render_agent_panel
from interactive_controls import (
    _clear_data_caches,
    load_machine_ids,
    render_csv_upload,
    render_rca_selector,
    render_sweep_panel,
)
from session_helper import get_session
from theme import SEVERITY_WARNING

AUDIT_TABLE = "DEMO.PUBLIC.AUDIT_LOG"
DEFAULT_MANUAL_ACTION_MACHINE = "MX-7103"

# Where sweep, investigation, and upload results render.
RESULTS_TAB_NAME = "Sweep"

# Sidebar heading for the agent panel.
ASK_PANEL_HEADING = "Manufacturing Agent"

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
    """Render the two manual write buttons used to prove the action loop.

    The target machine is chosen here rather than fixed, so a manual alert
    refers to whatever the operator is actually discussing.
    """
    machines = load_machine_ids()
    default_index = (
        machines.index(DEFAULT_MANUAL_ACTION_MACHINE)
        if DEFAULT_MANUAL_ACTION_MACHINE in machines
        else 0
    )
    machine = st.selectbox(
        "Target machine", machines, index=default_index, key="manual_action_machine"
    )

    col_alert, col_wo = st.columns(2)
    with col_alert:
        if st.button("Alert", key="manual_alert", use_container_width=True):
            trigger_alert(
                machine,
                SEVERITY_WARNING,
                f"Manual test alert dispatched from dashboard for {machine}.",
            )
            st.success(f"Alert sent for {machine}.")
    with col_wo:
        if st.button("Work Order", key="manual_wo", use_container_width=True):
            log_work_order(
                machine,
                SEVERITY_WARNING,
                f"Manual work order logged from dashboard for {machine}.",
            )
            st.success(f"Work order logged for {machine}.")


def render_sidebar() -> None:
    """Compose the full sidebar: Run, Data, Reference, and Help sections."""
    st.sidebar.title("Controls")
    st.sidebar.caption("Run the agent, manage data, or ask about the fleet.")

    # Collapsed: the sweep panel's CRITICAL/WARNING counts are no longer the
    # only place that signal appears. The fleet status banner and the Needs
    # Attention KPI both carry it on the main page, which stays visible when
    # the sidebar is closed.
    with st.sidebar.expander("Run", expanded=False):
        render_sweep_panel()
        st.divider()
        render_rca_selector()
        st.caption(f"Results appear in the {RESULTS_TAB_NAME} tab.")

    with st.sidebar.expander("Data", expanded=False):
        render_csv_upload()
        st.caption(f"The paste form opens in the {RESULTS_TAB_NAME} tab.")
        st.divider()
        _render_audit_reset()
        _render_manual_actions()

    st.sidebar.divider()
    st.sidebar.subheader(ASK_PANEL_HEADING)
    with st.sidebar.container():
        render_agent_panel()

    with st.sidebar.expander("Agent Architecture", expanded=False):
        _render_architecture()
        st.divider()
        st.caption(f"Streamlit runtime {st.__version__}")
