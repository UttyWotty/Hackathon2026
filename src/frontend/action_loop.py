"""Autonomous action loop for the manufacturing workflow agent.

Provides work order logging, alert triggering, and equipment status updates
that write to the AUDIT_LOG table in Snowflake, completing the sense-reason-act cycle.
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
    """Log an alert event to AUDIT_LOG (simulates webhook to plant engineers)."""
    session = get_active_session()
    safe_msg = message.replace("'", "''")
    session.sql(f"""
        INSERT INTO {AUDIT_TABLE} (MACHINE_ID, ACTION_TYPE, SEVERITY, DESCRIPTION)
        VALUES ('{machine_id}', '{ACTION_ALERT}', '{severity}', '{safe_msg}')
    """).collect()
    _log_skill(
        "$report-and-act",
        f"Alert triggered for {machine_id}: {message[:50]}",
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
        f"Status updated for {machine_id} -> {new_status}",
    )


def render_action_buttons():
    """Show action buttons when sweep finds flagged machines."""
    if "sweep_results" not in st.session_state:
        return

    results = st.session_state["sweep_results"]
    flagged = results[results["SEVERITY"].isin(["CRITICAL", "WARNING"])]

    if flagged.empty:
        return

    st.subheader("Autonomous Actions")
    st.caption("Take action on flagged machines - actions are logged to the audit trail")

    for _, row in flagged.iterrows():
        machine = row["MACHINE_ID"]
        severity = row["SEVERITY"]
        deviation = row["DEVIATION_PCT"]

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"**{machine}** - {deviation:.1f}% [{severity}]")
        with col2:
            if st.button(f"Log Work Order", key=f"wo_{machine}"):
                desc = (
                    f"Corrective maintenance required. "
                    f"Duration deviation {deviation:.1f}% exceeds threshold."
                )
                log_work_order(machine, severity, desc)
                st.success(f"Work order #{machine[-4:]}-WO logged for {machine}")
                st.caption("Maintenance team notified. Scheduled for next available window.")
        with col3:
            if st.button(f"Send Alert", key=f"alert_{machine}"):
                msg = (
                    f"ALERT: {machine} operating at {deviation:.1f}% "
                    f"above target duration. Immediate attention required."
                )
                trigger_alert(machine, severity, msg)
                st.success(f"Webhook dispatched for {machine}")
                st.caption(
                    "POST -> plant-engineers@webhook.site/alerts | "
                    "CC: shift-lead@plant.local, maintenance@plant.local"
                )


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
        st.caption("No actions recorded yet. Run a sweep and take action on flagged machines.")
        return

    st.dataframe(audit_df, use_container_width=True)


def render_skill_log():
    """Display the CoCo CLI skill invocation log."""
    if "skill_log" not in st.session_state or not st.session_state["skill_log"]:
        st.caption("No skill invocations yet. Run a sweep or investigation.")
        return

    for entry in reversed(st.session_state["skill_log"]):
        st.text(f"[{entry['timestamp']}] {entry['skill']} -- {entry['detail']}")
