"""Autonomous action loop for the manufacturing workflow agent.

Provides work order logging, alert triggering, and equipment status updates
that write to the AUDIT_LOG table in Snowflake, completing the sense-reason-act cycle.
Includes auto-trigger logic for fully autonomous operation.
"""

from datetime import datetime

import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session

DATABASE = "DEMO"
SCHEMA = "PUBLIC"
AUDIT_TABLE = f"{DATABASE}.{SCHEMA}.AUDIT_LOG"
SHOTS_TABLE = f"{DATABASE}.{SCHEMA}.SHOT_DATA"

ACTION_WORK_ORDER = "WORK_ORDER"
ACTION_ALERT = "ALERT"
ACTION_STATUS_CHANGE = "STATUS_CHANGE"

AUTO_TRIGGER_THRESHOLD = 15.0


def _log_skill(skill_name: str, detail: str):
    """Append a skill invocation entry to the session skill log."""
    if "skill_log" not in st.session_state:
        st.session_state["skill_log"] = []
    st.session_state["skill_log"].append({
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "skill": skill_name,
        "detail": detail,
    })


def log_work_order(machine_id: str, severity: str, description: str):
    """Insert a maintenance work order into AUDIT_LOG."""
    session = get_active_session()
    safe_desc = description.replace("'", "''")
    session.sql(f"""
        INSERT INTO {AUDIT_TABLE} (MACHINE_ID, ACTION_TYPE, SEVERITY, DESCRIPTION)
        VALUES ('{machine_id}', '{ACTION_WORK_ORDER}', '{severity}', '{safe_desc}')
    """).collect()
    _log_skill(
        "$report-and-act",
        f"Work order logged for {machine_id} [{severity}]",
    )


def trigger_alert(machine_id: str, severity: str, message: str):
    """Log an alert event to AUDIT_LOG and record delivery metadata."""
    session = get_active_session()
    safe_msg = message.replace("'", "''")
    session.sql(f"""
        INSERT INTO {AUDIT_TABLE} (MACHINE_ID, ACTION_TYPE, SEVERITY, DESCRIPTION)
        VALUES ('{machine_id}', '{ACTION_ALERT}', '{severity}', '{safe_msg}')
    """).collect()
    _log_skill(
        "$report-and-act",
        f"Alert dispatched for {machine_id}: {message[:50]}",
    )


def update_equipment_status(machine_id: str, new_status: str):
    """Update the operating status for a machine in SHOT_DATA."""
    session = get_active_session()
    session.sql(f"""
        UPDATE {SHOTS_TABLE}
        SET STATUS = '{new_status}'
        WHERE MACHINE_ID = '{machine_id}'
    """).collect()
    session.sql(f"""
        INSERT INTO {AUDIT_TABLE} (MACHINE_ID, ACTION_TYPE, SEVERITY, DESCRIPTION)
        VALUES ('{machine_id}', '{ACTION_STATUS_CHANGE}', 'INFO',
                'Status changed to {new_status}')
    """).collect()
    _log_skill(
        "$report-and-act",
        f"Equipment status: {machine_id} -> {new_status}",
    )


def run_autonomous_actions(results: pd.DataFrame):
    """Auto-trigger actions for CRITICAL machines without human intervention.

    This is the autonomous part: when deviation exceeds the threshold,
    the agent acts on its own decision.
    """
    critical = results[results["DEVIATION_PCT"] >= AUTO_TRIGGER_THRESHOLD]
    if critical.empty:
        return

    _log_skill(
        "$report-and-act",
        f"AUTO-TRIGGER: {len(critical)} machine(s) exceed {AUTO_TRIGGER_THRESHOLD}% threshold",
    )

    for _, row in critical.iterrows():
        machine = row["MACHINE_ID"]
        deviation = row["DEVIATION_PCT"]

        desc = (
            f"[AUTO] Corrective maintenance required. "
            f"Duration deviation {deviation:.1f}% exceeds {AUTO_TRIGGER_THRESHOLD}% "
            f"autonomous action threshold."
        )
        log_work_order(machine, "CRITICAL", desc)

        alert_msg = (
            f"[AUTO] {machine} at {deviation:.1f}% deviation. "
            f"Work order created automatically. Immediate inspection required."
        )
        trigger_alert(machine, "CRITICAL", alert_msg)

        update_equipment_status(machine, "under_review")


def render_action_buttons():
    """Show action buttons and autonomous action results."""
    if "sweep_results" not in st.session_state:
        return

    results = st.session_state["sweep_results"]
    flagged = results[results["SEVERITY"].isin(["CRITICAL", "WARNING"])]

    if flagged.empty:
        return

    # Show autonomous actions that fired automatically
    critical = results[results["DEVIATION_PCT"] >= AUTO_TRIGGER_THRESHOLD]
    if not critical.empty and not st.session_state.get("auto_actions_fired"):
        st.subheader("Autonomous Actions (Agent-Initiated)")
        st.info(
            f"The agent automatically acted on {len(critical)} machine(s) "
            f"exceeding the {AUTO_TRIGGER_THRESHOLD}% autonomous threshold -- "
            "no human click required."
        )
        run_autonomous_actions(results)
        st.session_state["auto_actions_fired"] = True

        for _, row in critical.iterrows():
            st.markdown(
                f"- **{row['MACHINE_ID']}** ({row['DEVIATION_PCT']:.1f}%): "
                "Work order created, alert dispatched, status set to UNDER_REVIEW"
            )
        st.divider()

    # Manual action buttons for WARNING-level machines
    warning_only = flagged[flagged["SEVERITY"] == "WARNING"]
    if not warning_only.empty:
        st.subheader("Manual Actions (Operator-Initiated)")
        st.caption(
            "WARNING-level machines require human judgment. "
            "Use buttons below to take action."
        )

    for _, row in flagged.iterrows():
        machine = row["MACHINE_ID"]
        severity = row["SEVERITY"]
        deviation = row["DEVIATION_PCT"]

        if severity == "CRITICAL" and st.session_state.get("auto_actions_fired"):
            continue

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"**{machine}** - {deviation:.1f}% [{severity}]")
        with col2:
            if st.button("Log Work Order", key=f"wo_{machine}"):
                desc = (
                    f"Corrective maintenance required. "
                    f"Duration deviation {deviation:.1f}% exceeds threshold."
                )
                log_work_order(machine, severity, desc)
                st.success(f"Work order #{machine[-4:]}-WO logged")
        with col3:
            if st.button("Send Alert", key=f"alert_{machine}"):
                msg = (
                    f"ALERT: {machine} operating at {deviation:.1f}% "
                    f"above target duration. Attention required."
                )
                trigger_alert(machine, severity, msg)
                st.success("Alert dispatched")
        with col4:
            if st.button("Flag for Review", key=f"status_{machine}"):
                update_equipment_status(machine, "under_review")
                st.success(f"{machine} -> UNDER_REVIEW")


def render_audit_trail():
    """Display recent entries from the AUDIT_LOG table."""
    session = get_active_session()
    audit_df = session.sql(f"""
        SELECT TIMESTAMP, MACHINE_ID, ACTION_TYPE, SEVERITY, DESCRIPTION, INITIATED_BY
        FROM {AUDIT_TABLE}
        ORDER BY TIMESTAMP DESC
        LIMIT 20
    """).to_pandas()

    if audit_df.empty:
        st.caption("No actions recorded yet. Run a sweep to trigger autonomous actions.")
        return

    st.dataframe(audit_df, use_container_width=True)


def render_skill_log():
    """Display the CoCo CLI skill invocation log."""
    if "skill_log" not in st.session_state or not st.session_state["skill_log"]:
        st.caption("No skill invocations yet. Run a sweep or investigation to see live activity.")
        return

    for entry in reversed(st.session_state["skill_log"]):
        st.code(f"[{entry['timestamp']}] {entry['skill']} -- {entry['detail']}", language=None)
