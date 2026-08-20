"""Interactive control functions for the manufacturing fleet dashboard.

Provides on-demand anomaly sweep, CSV telemetry upload, and per-equipment
root cause investigation triggers for the Streamlit-in-Snowflake app.
"""

import pandas as pd
import streamlit as st
from action_loop import _log_skill
from session_helper import get_session

DATABASE = "DEMO"
SCHEMA = "PUBLIC"
SHOTS_TABLE = "SHOT_DATA"
FULL_TABLE = f"{DATABASE}.{SCHEMA}.{SHOTS_TABLE}"
SHIFT_NOTE_TABLE = f"{DATABASE}.{SCHEMA}.SHIFT_NOTE"

SEVERITY_CRITICAL = 15.0
SEVERITY_WARNING = 10.0
SEVERITY_MINOR = 5.0


def run_anomaly_sweep() -> pd.DataFrame:
    """Execute an on-demand anomaly sweep across the fleet.

    Returns:
        DataFrame with per-machine deviation and stability metrics.
    """
    session = get_session()
    query = f"""
    SELECT
        MACHINE_ID,
        COUNT(*) AS SHOT_COUNT,
        ROUND(AVG(DURATION), 2) AS AVG_DURATION,
        ANY_VALUE(TARGET_DURATION) AS TARGET_DURATION,
        ROUND(((AVG(DURATION) - ANY_VALUE(TARGET_DURATION))
            / NULLIF(ANY_VALUE(TARGET_DURATION), 0)) * 100, 2) AS DEVIATION_PCT,
        ROUND(100.0 - (STDDEV(DURATION)
            / NULLIF(AVG(DURATION), 0) * 100), 1) AS STABILITY_SCORE
    FROM {FULL_TABLE}
    WHERE DURATION < 999.9 AND VOLUME > 0 AND TARGET_DURATION > 0
    GROUP BY MACHINE_ID
    ORDER BY DEVIATION_PCT DESC
    """
    return session.sql(query).to_pandas()


def classify_severity(deviation_pct: float) -> str:
    """Classify deviation into severity category."""
    if abs(deviation_pct) >= SEVERITY_CRITICAL:
        return "CRITICAL"
    if abs(deviation_pct) >= SEVERITY_WARNING:
        return "WARNING"
    if abs(deviation_pct) >= SEVERITY_MINOR:
        return "MINOR"
    return "NOMINAL"


def render_sweep_panel():
    """Render the on-demand anomaly sweep panel in the sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("Anomaly Sweep")

    if st.sidebar.button("Run Fleet Sweep", type="primary", use_container_width=True):
        with st.spinner("Sweeping fleet for anomalies..."):
            _log_skill("$sense-equipment-anomalies", "Fleet sweep initiated")
            results = run_anomaly_sweep()
            results["SEVERITY"] = results["DEVIATION_PCT"].apply(classify_severity)
            st.session_state["sweep_results"] = results
            critical = len(results[results["SEVERITY"] == "CRITICAL"])
            _log_skill(
                "$sense-equipment-anomalies",
                f"Sweep complete: {len(results)} machines, {critical} critical",
            )
            st.cache_data.clear()

    if "sweep_results" in st.session_state:
        results = st.session_state["sweep_results"]
        critical_count = len(results[results["SEVERITY"] == "CRITICAL"])
        warning_count = len(results[results["SEVERITY"] == "WARNING"])

        if critical_count > 0:
            st.sidebar.error(f"{critical_count} machine(s) CRITICAL")
        if warning_count > 0:
            st.sidebar.warning(f"{warning_count} machine(s) WARNING")
        if critical_count == 0 and warning_count == 0:
            st.sidebar.success("Fleet nominal")


def render_sweep_results():
    """Render full sweep results in the main area when available."""
    if "sweep_results" not in st.session_state:
        return

    results = st.session_state["sweep_results"]

    st.subheader("On-Demand Sweep Results")

    st.dataframe(
        results[
            [
                "MACHINE_ID",
                "SHOT_COUNT",
                "AVG_DURATION",
                "TARGET_DURATION",
                "DEVIATION_PCT",
                "STABILITY_SCORE",
                "SEVERITY",
            ]
        ],
        use_container_width=True,
    )

    flagged = results[results["SEVERITY"].isin(["CRITICAL", "WARNING"])]
    if not flagged.empty:
        st.markdown("**Flagged machines requiring investigation:**")
        for _, row in flagged.iterrows():
            severity_icon = "!!!" if row["SEVERITY"] == "CRITICAL" else "!!"
            st.markdown(
                f"- {severity_icon} **{row['MACHINE_ID']}**: "
                f"{row['DEVIATION_PCT']:.1f}% deviation, "
                f"stability {row['STABILITY_SCORE']:.1f}% [{row['SEVERITY']}]"
            )
    else:
        st.success("All machines within nominal range.")


def render_csv_upload():
    """Render CSV upload control for fresh telemetry data.

    SiS runtime runs Streamlit 1.22 which lacks st.file_uploader.
    Uses text_area paste approach as the supported alternative.
    """
    st.sidebar.markdown("---")
    st.sidebar.subheader("Upload Telemetry")
    st.sidebar.caption("Paste CSV content below to ingest new data")

    if st.sidebar.button("Open CSV Paste Dialog", use_container_width=True):
        st.session_state["show_csv_paste"] = True


def _ingest_csv(df: pd.DataFrame):
    """Write uploaded DataFrame into SHOT_DATA table."""
    session = get_session()
    try:
        session.write_pandas(
            df,
            table_name=SHOTS_TABLE,
            database=DATABASE,
            schema=SCHEMA,
            auto_create_table=False,
            overwrite=False,
        )
        st.cache_data.clear()
        st.session_state["ingest_success"] = len(df)
        st.session_state["ingest_trigger_sweep"] = True
        if "uploaded_preview" in st.session_state:
            del st.session_state["uploaded_preview"]
    except Exception as exc:
        st.sidebar.error(f"Upload failed: {exc}")


def render_upload_preview():
    """Show CSV paste area and handle ingestion when triggered."""
    if not st.session_state.get("show_csv_paste"):
        return

    st.subheader("Upload Telemetry Data")
    st.caption(
        "Paste CSV data with at minimum these columns: "
        "MACHINE_ID, DURATION, TARGET_DURATION, SHOT_TIME, VOLUME"
    )

    SAMPLE_CSV = (
        "MACHINE_ID,DURATION,TARGET_DURATION,SHOT_TIME,VOLUME,VENDOR_NAME,"
        "SENSOR_CODE,PRODUCT_NAME,TYPE,STATUS,"
        "SENSOR_ID,TOOL_ID,VENDOR_ID,PRODUCT_ID,UPLOAD_TIME,PROCESSING_DATE\n"
        "MX-7101,28.9,28.4,2026-08-01 08:00:00,1,NORDPLAST INDUSTRIES,"
        "CNT-88200,Door Handle Carrier,Injection Molding,active,"
        "88200,4100,700,1,2026-08-01 09:00:00,2026-08-01\n"
        "MX-7101,29.1,28.4,2026-08-01 08:00:29,1,NORDPLAST INDUSTRIES,"
        "CNT-88200,Door Handle Carrier,Injection Molding,active,"
        "88200,4100,700,1,2026-08-01 09:00:00,2026-08-01\n"
        "MX-7103,32.5,26.8,2026-08-01 08:01:00,1,MERIDIAN TOOLING,"
        "CNT-88202,Coolant Reservoir Cap,Injection Molding,active,"
        "88202,4102,702,4,2026-08-01 09:00:00,2026-08-01\n"
    )

    col_sample, col_demo, col_clear = st.columns(3)
    with col_sample:
        if st.button("Load Sample (3 rows)"):
            st.session_state["csv_text_input"] = SAMPLE_CSV
    with col_demo:
        if st.button("Load MX-9201 (3K rows)"):
            import os

            csv_path = os.path.join(
                os.path.dirname(__file__), "sample_telemetry_MX9201.csv"
            )
            with open(csv_path, "r") as f:
                st.session_state["csv_text_input"] = f.read()
    with col_clear:
        if st.button("Cancel Upload"):
            st.session_state["show_csv_paste"] = False
            if "csv_text_input" in st.session_state:
                del st.session_state["csv_text_input"]
            return

    csv_text = st.text_area(
        "CSV Content",
        value=st.session_state.get("csv_text_input", ""),
        height=200,
    )

    if csv_text:
        import io

        try:
            df = pd.read_csv(io.StringIO(csv_text))
            st.dataframe(df, use_container_width=True)
            st.caption(f"{len(df)} rows parsed, {len(df.columns)} columns")

            if st.button("Ingest to Snowflake", type="primary"):
                _ingest_csv(df)
                st.session_state["show_csv_paste"] = False
                if "csv_text_input" in st.session_state:
                    del st.session_state["csv_text_input"]
        except Exception as exc:
            st.error(f"Failed to parse CSV: {exc}")


def render_rca_selector():
    """Render machine selector for root cause investigation."""
    st.sidebar.subheader("Investigate Machine")
    st.sidebar.caption("Drill into a single machine after sweeping the fleet")

    session = get_session()
    machines = (
        session.sql(f"SELECT DISTINCT MACHINE_ID FROM {FULL_TABLE} ORDER BY MACHINE_ID")
        .to_pandas()["MACHINE_ID"]
        .tolist()
    )

    selected = st.sidebar.selectbox("Machine", [""] + machines, index=0, key="rca_select")
    if selected == "":
        selected = None

    if selected and st.sidebar.button("Run Investigation", use_container_width=True):
        st.session_state["rca_machine"] = selected
        _log_skill("$investigate-shift-notes", f"Investigation started for {selected}")


def render_rca_results():
    """Render RCA investigation results for selected equipment."""
    if "rca_machine" not in st.session_state:
        return

    machine = st.session_state["rca_machine"]
    session = get_session()

    st.subheader(f"Investigation: {machine}")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Duration Trend (Weekly)**")
        trend = session.sql(f"""
            SELECT
                DATE_TRUNC('WEEK', SHOT_TIME) AS WEEK_START,
                ROUND(AVG(DURATION), 2) AS AVG_DURATION,
                ANY_VALUE(TARGET_DURATION) AS TARGET_DURATION,
                ROUND(((AVG(DURATION) - ANY_VALUE(TARGET_DURATION))
                    / NULLIF(ANY_VALUE(TARGET_DURATION), 0)) * 100, 2) AS DEVIATION_PCT,
                COUNT(*) AS SHOTS
            FROM {FULL_TABLE}
            WHERE MACHINE_ID = '{machine}'
                AND DURATION < 999.9 AND VOLUME > 0 AND TARGET_DURATION > 0
            GROUP BY DATE_TRUNC('WEEK', SHOT_TIME)
            ORDER BY WEEK_START
        """).to_pandas()
        st.dataframe(trend, use_container_width=True)

    with col2:
        st.markdown("**Operator Shift Notes**")
        notes = session.sql(f"""
            SELECT SHIFT_DATE, AUTHOR_ROLE, NOTE_TEXT
            FROM {SHIFT_NOTE_TABLE}
            WHERE MACHINE_ID = '{machine}'
            ORDER BY SHIFT_DATE DESC
            LIMIT 20
        """).to_pandas()

        if notes.empty:
            st.info("No shift notes found for this machine.")
        else:
            st.dataframe(notes, use_container_width=True)

    col_clear, col_resolve = st.columns(2)
    with col_clear:
        if st.button(f"Close panel", key=f"close_{machine}"):
            del st.session_state["rca_machine"]
            st.experimental_rerun()
    with col_resolve:
        if st.button(
            f"Mark {machine} resolved", key=f"resolve_{machine}", type="primary"
        ):
            from action_loop import update_equipment_status, _log_skill

            update_equipment_status(machine, "active")
            _log_skill(
                "$investigate-shift-notes",
                f"Investigation complete: {machine} marked resolved",
            )
            del st.session_state["rca_machine"]
            if "resolved_machines" not in st.session_state:
                st.session_state["resolved_machines"] = set()
            st.session_state["resolved_machines"].add(machine)
            st.experimental_rerun()
