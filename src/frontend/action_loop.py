"""Autonomous action loop for the manufacturing workflow agent.

Provides work order logging, alert triggering, and equipment status updates
that write to the AUDIT_LOG table in Snowflake, completing the sense-reason-act cycle.
Includes auto-trigger logic for fully autonomous operation.
"""

import html
import json
import re
from datetime import datetime

import pandas as pd
import streamlit as st
from session_helper import get_session
from tables import TABLE_HEIGHT_COMPACT, render_table
from theme import SEVERITY_CRITICAL, SEVERITY_WARNING, severity_badge

DATABASE = "DEMO"
SCHEMA = "PUBLIC"
AUDIT_TABLE = f"{DATABASE}.{SCHEMA}.AUDIT_LOG"
SHOTS_TABLE = f"{DATABASE}.{SCHEMA}.SHOT_DATA"

ACTION_WORK_ORDER = "WORK_ORDER"
ACTION_ALERT = "ALERT"
ACTION_STATUS_CHANGE = "STATUS_CHANGE"

AUTO_TRIGGER_THRESHOLD = 10.0

# Rows pulled for the audit trail before client-side filtering.
AUDIT_TRAIL_LIMIT = 200
ALL_MACHINES_OPTION = "All machines"

MACHINE_ID_RE = re.compile(r"^[A-Z]{2}-\d{4}$")


class WebhookPayloadError(ValueError):
    """Raised when a stored webhook payload does not match the Cards v2 shape."""


def _escape_sql_str(value: str) -> str:
    """Escape a string value for safe inclusion in a Snowflake SQL literal.

    Handles both backslash and single-quote characters.
    """
    return value.replace("\\", "\\\\").replace("'", "''")


def _validate_machine_id(machine_id: str) -> str:
    """Validate and return a sanitized machine ID.

    Raises:
        ValueError: If the machine_id does not match expected format.
    """
    mid = machine_id.strip().upper()
    if not MACHINE_ID_RE.match(mid):
        raise ValueError(f"Invalid machine ID format: {machine_id!r}")
    return mid


def _parse_payload(payload) -> dict:
    """Normalise a stored webhook payload into title, source, message, fields.

    Args:
        payload: The Cards v2 payload, as a dict or a JSON string.

    Returns:
        A dict with "title", "source", "message", and "fields" keys.

    Raises:
        WebhookPayloadError: If the payload does not match the Cards v2 shape.
    """
    try:
        if isinstance(payload, str):
            payload = json.loads(payload)
        card = payload["cardsV2"][0]["card"]
        widgets = card["sections"][0]["widgets"]
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise WebhookPayloadError("Unrecognised webhook payload shape") from exc

    fields, message = [], ""
    for widget in widgets:
        if "decoratedText" in widget:
            decorated = widget["decoratedText"]
            fields.append(
                (decorated.get("topLabel", ""), decorated.get("text", ""))
            )
        elif "textParagraph" in widget:
            message = widget["textParagraph"].get("text", "")

    return {
        "title": card.get("header", {}).get("title", "Alert"),
        "source": card.get("header", {}).get("subtitle", ""),
        "message": message,
        "fields": fields,
    }


def _render_payload_card(payload):
    """Render a webhook payload as a notification card.

    Previously used `st.metric` for every field, which set text values such as a
    timestamp and a source name in the large metric display font.

    Args:
        payload: The Cards v2 payload, as a dict or a JSON string.
    """
    try:
        parsed = _parse_payload(payload)
    except WebhookPayloadError:
        st.caption("Could not parse the stored webhook payload. Raw value:")
        st.code(str(payload), language="json")
        return

    fields = "".join(
        '<div class="wh-field">'
        f'<div class="wh-flabel">{html.escape(str(label))}</div>'
        f'<div class="wh-fvalue">{html.escape(str(value))}</div>'
        "</div>"
        for label, value in parsed["fields"]
        if label or value
    )
    message = (
        f'<div class="wh-message">{html.escape(parsed["message"])}</div>'
        if parsed["message"]
        else ""
    )
    st.markdown(
        '<div class="wh-card">'
        f'<div class="wh-title">{html.escape(parsed["title"])}</div>'
        f'<div class="wh-source">{html.escape(parsed["source"])}</div>'
        f'{message}<div class="wh-fields">{fields}</div></div>',
        unsafe_allow_html=True,
    )


def _log_skill(skill_name: str, detail: str):
    """Append a skill invocation entry to the session skill log."""
    if "skill_log" not in st.session_state:
        st.session_state["skill_log"] = []
    st.session_state["skill_log"].append(
        {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "skill": skill_name,
            "detail": detail,
        }
    )


def log_work_order(machine_id: str, severity: str, description: str):
    """Insert a maintenance work order into AUDIT_LOG."""
    session = get_session()
    mid = _validate_machine_id(machine_id)
    safe_desc = _escape_sql_str(description)
    safe_severity = _escape_sql_str(severity)
    session.sql(f"""
        INSERT INTO {AUDIT_TABLE} (MACHINE_ID, ACTION_TYPE, SEVERITY, DESCRIPTION)
        VALUES ('{mid}', '{ACTION_WORK_ORDER}', '{safe_severity}', '{safe_desc}')
    """).collect()
    _log_skill(
        "$report-and-act",
        f"Work order logged for {mid} [{severity}]",
    )


def _build_webhook_payload(machine_id: str, severity: str, message: str) -> dict:
    """Construct a Google Chat Cards v2 webhook payload.

    Schema matches backend alert_sender._build_card_payload exactly.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    return {
        "cardsV2": [
            {
                "cardId": "alertCard",
                "card": {
                    "header": {
                        "title": f"Manufacturing Alert: {machine_id}",
                        "subtitle": f"{severity.upper()} | autonomous-agent",
                        "imageUrl": "",
                        "imageType": "CIRCLE",
                    },
                    "sections": [
                        {
                            "header": "Alert Details",
                            "collapsible": False,
                            "widgets": [
                                {
                                    "decoratedText": {
                                        "topLabel": "Severity",
                                        "text": severity.upper(),
                                    }
                                },
                                {
                                    "decoratedText": {
                                        "topLabel": "Source",
                                        "text": "autonomous-agent",
                                    }
                                },
                                {
                                    "decoratedText": {
                                        "topLabel": "Timestamp",
                                        "text": timestamp,
                                    }
                                },
                                {
                                    "textParagraph": {
                                        "text": message[:2000],
                                    }
                                },
                                {
                                    "decoratedText": {
                                        "topLabel": "Machine",
                                        "text": machine_id,
                                    }
                                },
                            ],
                        }
                    ],
                    "cardActions": [],
                },
            }
        ]
    }


def trigger_alert(machine_id: str, severity: str, message: str):
    """Log an alert with full webhook payload to AUDIT_LOG.

    Constructs the exact Google Chat Cards v2 JSON payload (same schema
    as backend alert_sender._build_card_payload). Stored in WEBHOOK_PAYLOAD
    column for audit proof.
    """
    session = get_session()
    mid = _validate_machine_id(machine_id)
    safe_msg = _escape_sql_str(message)
    safe_severity = _escape_sql_str(severity)
    payload = _build_webhook_payload(mid, severity, message)
    payload_json = _escape_sql_str(json.dumps(payload))
    session.sql(f"""
        INSERT INTO {AUDIT_TABLE}
            (MACHINE_ID, ACTION_TYPE, SEVERITY, DESCRIPTION, WEBHOOK_PAYLOAD)
        SELECT '{mid}', '{ACTION_ALERT}', '{safe_severity}', '{safe_msg}',
            PARSE_JSON('{payload_json}')
    """).collect()
    _log_skill(
        "$report-and-act",
        f"Alert dispatched for {mid}: {message[:50]}",
    )


def update_equipment_status(machine_id: str, new_status: str):
    """Update the operating status for a machine in SHOT_DATA."""
    session = get_session()
    mid = _validate_machine_id(machine_id)
    safe_status = _escape_sql_str(new_status)
    session.sql(f"""
        UPDATE {SHOTS_TABLE}
        SET STATUS = '{safe_status}'
        WHERE MACHINE_ID = '{mid}'
    """).collect()
    session.sql(f"""
        INSERT INTO {AUDIT_TABLE} (MACHINE_ID, ACTION_TYPE, SEVERITY, DESCRIPTION)
        VALUES ('{mid}', '{ACTION_STATUS_CHANGE}', 'INFO',
                'Status changed to {safe_status}')
    """).collect()
    _log_skill(
        "$report-and-act",
        f"Equipment status for {mid} set to {new_status}",
    )


def run_autonomous_actions(results: pd.DataFrame):
    """Auto-trigger actions for machines exceeding threshold.

    Tracks which machines have already been actioned in session state
    to avoid duplicate actions on re-sweep.
    """
    if "actioned_machines" not in st.session_state:
        st.session_state["actioned_machines"] = set()

    resolved = st.session_state.get("resolved_machines", set())
    critical = results[results["DEVIATION_PCT"] >= AUTO_TRIGGER_THRESHOLD]
    new_machines = critical[
        ~critical["MACHINE_ID"].isin(st.session_state["actioned_machines"] | resolved)
    ]
    if new_machines.empty:
        return

    _log_skill(
        "$report-and-act",
        f"AUTO-TRIGGER: {len(new_machines)} machine(s) exceed {AUTO_TRIGGER_THRESHOLD}% threshold",
    )

    for _, row in new_machines.iterrows():
        machine = row["MACHINE_ID"]
        deviation = row["DEVIATION_PCT"]
        severity = row.get("SEVERITY", SEVERITY_WARNING)

        desc = (
            f"[AUTO] Corrective maintenance required. "
            f"Duration deviation {deviation:.1f}% exceeds {AUTO_TRIGGER_THRESHOLD}% "
            f"autonomous action threshold."
        )
        log_work_order(machine, severity, desc)

        alert_msg = (
            f"[AUTO] {machine} at {deviation:.1f}% deviation. "
            f"Work order created automatically. Immediate inspection required."
        )
        trigger_alert(machine, severity, alert_msg)

        update_equipment_status(machine, "under_review")
        st.session_state["actioned_machines"].add(machine)


def render_action_buttons():
    """Show action buttons and autonomous action results."""
    if "sweep_results" not in st.session_state:
        return

    results = st.session_state["sweep_results"]
    flagged = results[results["SEVERITY"].isin([SEVERITY_CRITICAL, SEVERITY_WARNING])]

    if flagged.empty:
        return

    # Show autonomous actions that fired automatically
    critical = results[results["DEVIATION_PCT"] >= AUTO_TRIGGER_THRESHOLD]
    actioned = st.session_state.get("actioned_machines", set())

    # Only fire autonomous actions when a fresh sweep just completed (flag set by
    # render_sweep_panel), NOT on every render/rerun. This prevents duplicate DB
    # writes on browser reload.
    if st.session_state.pop("sweep_just_completed", False):
        new_to_action = critical[~critical["MACHINE_ID"].isin(actioned)]
        if not new_to_action.empty:
            run_autonomous_actions(results)

    all_actioned = critical[
        critical["MACHINE_ID"].isin(st.session_state.get("actioned_machines", set()))
    ]
    if not all_actioned.empty:
        st.subheader("Autonomous Actions (Agent-Initiated)")
        st.info(
            f"The agent automatically acted on {len(all_actioned)} machine(s) "
            f"exceeding the {AUTO_TRIGGER_THRESHOLD}% autonomous threshold. "
            "No human click required."
        )
        for _, row in all_actioned.iterrows():
            st.markdown(
                f"- **{row['MACHINE_ID']}** ({row['DEVIATION_PCT']:.1f}%): "
                "Work order created, alert dispatched, status set to UNDER_REVIEW"
            )
        st.divider()

    # Manual action buttons for machines NOT auto-actioned
    manual_machines = flagged[flagged["DEVIATION_PCT"] < AUTO_TRIGGER_THRESHOLD]
    if not manual_machines.empty:
        st.subheader("Manual Actions (Operator-Initiated)")
        st.caption(
            "These machines are below the autonomous threshold. "
            "Use buttons below to take action."
        )

    for _, row in manual_machines.iterrows():
        machine = row["MACHINE_ID"]
        severity = row["SEVERITY"]
        deviation = row["DEVIATION_PCT"]

        st.markdown(
            f"{severity_badge(severity)} &nbsp; **{machine}** &mdash; "
            f"{deviation:.1f}% deviation",
            unsafe_allow_html=True,
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button(
                "Log Work Order", key=f"wo_{machine}", use_container_width=True
            ):
                desc = (
                    f"Corrective maintenance required. "
                    f"Duration deviation {deviation:.1f}% exceeds threshold."
                )
                log_work_order(machine, severity, desc)
                st.success(f"Work order #{machine[-4:]}-WO logged")
        with col2:
            if st.button(
                "Send Alert", key=f"alert_{machine}", use_container_width=True
            ):
                msg = (
                    f"ALERT: {machine} operating at {deviation:.1f}% "
                    f"above target duration. Attention required."
                )
                trigger_alert(machine, severity, msg)
                payload = _build_webhook_payload(machine, severity, msg)
                st.success("Alert dispatched. Webhook payload stored.")
                _render_payload_card(payload)
        with col3:
            if st.button(
                "Flag for Review", key=f"status_{machine}", use_container_width=True
            ):
                update_equipment_status(machine, "under_review")
                st.success(f"{machine} status set to UNDER_REVIEW.")


def render_audit_trail():
    """Display recent AUDIT_LOG entries, with an optional machine filter."""
    session = get_session()
    audit_df = session.sql(f"""
        SELECT TIMESTAMP, MACHINE_ID, ACTION_TYPE, SEVERITY, DESCRIPTION,
               INITIATED_BY, WEBHOOK_PAYLOAD
        FROM {AUDIT_TABLE}
        ORDER BY TIMESTAMP DESC
        LIMIT {AUDIT_TRAIL_LIMIT}
    """).to_pandas()

    if audit_df.empty:
        st.caption(
            "No actions recorded yet. Run a sweep to trigger autonomous actions."
        )
        return

    machines = sorted(audit_df["MACHINE_ID"].dropna().unique().tolist())
    col_filter, _col_rest = st.columns([1, 3])
    with col_filter:
        choice = st.selectbox(
            "Machine", [ALL_MACHINES_OPTION] + machines, key="audit_machine_filter"
        )

    filtered = (
        audit_df
        if choice == ALL_MACHINES_OPTION
        else audit_df[audit_df["MACHINE_ID"] == choice]
    )
    if filtered.empty:
        st.info(f"No recorded actions for {choice}.")
        return

    display_cols = [
        "TIMESTAMP",
        "MACHINE_ID",
        "ACTION_TYPE",
        "SEVERITY",
        "DESCRIPTION",
        "INITIATED_BY",
    ]
    render_table(filtered, columns=display_cols, height=TABLE_HEIGHT_COMPACT)

    payloads = filtered[filtered["WEBHOOK_PAYLOAD"].notna()]
    if payloads.empty:
        st.caption("No alert payloads recorded for this selection.")
        return

    row = payloads.iloc[0]
    recorded = pd.to_datetime(row["TIMESTAMP"]).strftime("%d %b %Y %H:%M")
    scope = "across the fleet" if choice == ALL_MACHINES_OPTION else f"for {choice}"
    st.markdown(f"**Most recent alert payload: {row['MACHINE_ID']}**")
    st.caption(
        f"Recorded {recorded}. This is the newest alert {scope} held in the audit "
        "log, which persists between sessions. It is not tied to the machine "
        "currently selected elsewhere in the app."
    )
    _render_payload_card(row["WEBHOOK_PAYLOAD"])


def render_skill_log():
    """Display the CoCo CLI skill invocation log."""
    if "skill_log" not in st.session_state or not st.session_state["skill_log"]:
        st.caption(
            "No skill invocations yet. Run a sweep or investigation to see live activity."
        )
        return

    log_df = pd.DataFrame(reversed(st.session_state["skill_log"]))
    log_df.columns = ["Time", "Skill", "Detail"]
    render_table(log_df, height=TABLE_HEIGHT_COMPACT)
