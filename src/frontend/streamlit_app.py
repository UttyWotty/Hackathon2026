"""Autonomous Manufacturing Workflow Agent - Interactive Fleet Dashboard.

Visualizes duration drift detection across an injection moulding fleet,
with interactive controls for on-demand anomaly sweeps, CSV uploads,
and per-equipment root cause investigations.
"""

import streamlit as st
from action_loop import (
    render_action_buttons,
    render_audit_trail,
    render_skill_log,
)
from analysis_panels import (
    render_decision_trail_panel,
    render_efficiency_panel,
    render_five_whys_panel,
    render_insights_panel,
    render_maintenance_panel,
    render_pareto_panel,
    render_tooling_eol_panel,
)
from charts import padded_domain, threshold_rule, time_x
from evidence import render_corroboration_panel
from header import render_fleet_status, render_header, render_kpi_cards
from interactive_controls import (
    _clear_data_caches,
    classify_severity,
    load_machine_ids,
    render_rca_results,
    render_sweep_results,
    render_upload_preview,
    run_anomaly_sweep,
)
from session_helper import get_session
from sidebar import render_sidebar
from styles import inject_css
from tables import render_table
from theme import (
    ACCENT_PRIMARY,
    BAND_FILL,
    BAND_OPACITY,
    CHART_HEIGHT_HERO,
    CHART_HEIGHT_STANDARD,
    RULE_DASH,
    RULE_NEUTRAL,
    SEVERITY_COLORS,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    categorical_scale,
    severity_scale,
)

PAGE_TITLE = "Autonomous Manufacturing Workflow Agent"
DATABASE = "DEMO"
SCHEMA = "PUBLIC"
SHOTS_TABLE = "SHOT_DATA"
FULL_TABLE = f"{DATABASE}.{SCHEMA}.{SHOTS_TABLE}"

DRIFT_EQUIPMENT = "MX-7103"
CRITICAL_DEVIATION_PCT = 15.0
WARNING_DEVIATION_PCT = 10.0


@st.cache_data(ttl=600)
def load_fleet_deviation():
    """Load weekly duration deviation per equipment."""
    session = get_session()
    query = f"""
    SELECT
        MACHINE_ID,
        DATE_TRUNC('WEEK', SHOT_TIME) AS WEEK_START,
        AVG(DURATION) AS AVG_DURATION,
        ANY_VALUE(TARGET_DURATION) AS TARGET_DURATION,
        COUNT(*) AS SHOT_COUNT,
        ROUND(((AVG(DURATION) - ANY_VALUE(TARGET_DURATION))
            / NULLIF(ANY_VALUE(TARGET_DURATION), 0)) * 100, 2) AS DEVIATION_PCT
    FROM {FULL_TABLE}
    WHERE DURATION < 999.9 AND VOLUME > 0 AND TARGET_DURATION > 0
    GROUP BY MACHINE_ID, DATE_TRUNC('WEEK', SHOT_TIME)
    ORDER BY MACHINE_ID, WEEK_START
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=600)
def load_fleet_summary():
    """Load overall fleet health summary."""
    session = get_session()
    query = f"""
    SELECT
        MACHINE_ID,
        COUNT(*) AS TOTAL_SHOTS,
        ROUND(AVG(DURATION), 2) AS AVG_DURATION,
        ANY_VALUE(TARGET_DURATION) AS TARGET_DURATION,
        ROUND(((AVG(DURATION) - ANY_VALUE(TARGET_DURATION))
            / NULLIF(ANY_VALUE(TARGET_DURATION), 0)) * 100, 2) AS DEVIATION_PCT,
        ROUND(STDDEV(DURATION) / NULLIF(AVG(DURATION), 0) * 100, 2) AS CV_PCT,
        MIN(SHOT_TIME) AS FIRST_SHOT,
        MAX(SHOT_TIME) AS LAST_SHOT
    FROM {FULL_TABLE}
    WHERE DURATION < 999.9 AND VOLUME > 0 AND TARGET_DURATION > 0
    GROUP BY MACHINE_ID
    ORDER BY DEVIATION_PCT DESC
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=600)
def load_stability_trend():
    """Load weekly stability score per equipment."""
    session = get_session()
    query = f"""
    SELECT
        MACHINE_ID,
        DATE_TRUNC('WEEK', SHOT_TIME) AS WEEK_START,
        ROUND(100.0 - (STDDEV(DURATION) / NULLIF(AVG(DURATION), 0) * 100), 1)
            AS STABILITY_SCORE,
        COUNT(*) AS SHOT_COUNT
    FROM {FULL_TABLE}
    WHERE DURATION < 999.9 AND VOLUME > 0 AND TARGET_DURATION > 0
    GROUP BY MACHINE_ID, DATE_TRUNC('WEEK', SHOT_TIME)
    HAVING COUNT(*) > 50
    ORDER BY MACHINE_ID, WEEK_START
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=600)
def load_drift_detail(machine: str):
    """Load detailed weekly progression for one machine.

    Args:
        machine: The MACHINE_ID to profile.
    """
    session = get_session()
    query = f"""
    SELECT
        DATE_TRUNC('WEEK', SHOT_TIME) AS WEEK_START,
        COUNT(*) AS SHOT_COUNT,
        ROUND(AVG(DURATION), 2) AS AVG_DURATION,
        ROUND(MIN(DURATION), 2) AS MIN_DURATION,
        ROUND(MAX(DURATION), 2) AS MAX_DURATION,
        ANY_VALUE(TARGET_DURATION) AS TARGET_DURATION,
        ROUND(((AVG(DURATION) - ANY_VALUE(TARGET_DURATION))
            / NULLIF(ANY_VALUE(TARGET_DURATION), 0)) * 100, 2) AS DEVIATION_PCT,
        ROUND(STDDEV(DURATION), 3) AS STD_DURATION
    FROM {FULL_TABLE}
    WHERE MACHINE_ID = '{machine}'
        AND DURATION < 999.9 AND VOLUME > 0 AND TARGET_DURATION > 0
    GROUP BY DATE_TRUNC('WEEK', SHOT_TIME)
    ORDER BY WEEK_START
    """
    return session.sql(query).to_pandas()


def render_drift_tab(deviation_df):
    """Render the duration drift detection tab."""
    import altair as alt

    st.subheader("Duration Drift Detection")

    if deviation_df.empty:
        st.info("No deviation data available for the selected period.")
        return

    max_dev = deviation_df["DEVIATION_PCT"].max()
    max_machine = deviation_df.loc[
        deviation_df["DEVIATION_PCT"].idxmax(), "MACHINE_ID"
    ]
    if max_dev > WARNING_DEVIATION_PCT:
        st.warning(
            f"**{max_machine}** shows {max_dev:.1f}% peak deviation "
            f"(threshold: {WARNING_DEVIATION_PCT}%)"
        )

    chart_data = deviation_df.copy()
    chart_data["IS_HEADLINE"] = chart_data["MACHINE_ID"] == DRIFT_EQUIPMENT

    highlight = alt.selection_multi(fields=["MACHINE_ID"], bind="legend")

    chart = (
        alt.Chart(chart_data)
        .mark_line(point=True)
        .encode(
            x=time_x("WEEK_START", "Week"),
            y=alt.Y("DEVIATION_PCT:Q", title="Duration Deviation (%)"),
            color=alt.Color(
                "MACHINE_ID:N", title="Equipment", scale=categorical_scale()
            ),
            opacity=alt.condition(highlight, alt.value(1.0), alt.value(0.2)),
            strokeWidth=alt.condition(
                alt.datum.IS_HEADLINE, alt.value(3), alt.value(1)
            ),
            tooltip=[
                alt.Tooltip("MACHINE_ID:N", title="Machine"),
                alt.Tooltip("WEEK_START:T", title="Week", format="%b %d"),
                alt.Tooltip("DEVIATION_PCT:Q", title="Deviation %", format=".1f"),
                alt.Tooltip("SHOT_COUNT:Q", title="Shots", format=","),
            ],
        )
        .add_selection(highlight)
        .properties(height=CHART_HEIGHT_HERO)
    )

    rule_warning = threshold_rule(
        WARNING_DEVIATION_PCT,
        f"Warning ({WARNING_DEVIATION_PCT:.0f}%)",
        SEVERITY_COLORS[SEVERITY_WARNING],
    )
    rule_critical = threshold_rule(
        CRITICAL_DEVIATION_PCT,
        f"Critical ({CRITICAL_DEVIATION_PCT:.0f}%)",
        SEVERITY_COLORS[SEVERITY_CRITICAL],
    )

    st.altair_chart(chart + rule_warning + rule_critical, use_container_width=True)
    st.caption(
        "Each line is one machine's duration deviation from target over time. "
        "Machines that drift steadily while holding high stability are the "
        "'invisible anomalies' single-metric alerts miss. "
        "Click a legend entry to isolate a machine."
    )

    st.divider()

    machines = load_machine_ids()
    default_index = (
        machines.index(DRIFT_EQUIPMENT) if DRIFT_EQUIPMENT in machines else 0
    )
    col_pick, _col_rest = st.columns([1, 3])
    with col_pick:
        machine = st.selectbox(
            "Machine", machines, index=default_index, key="drift_machine"
        )

    st.subheader(f"Weekly Progression: {machine}")

    drift_detail = load_drift_detail(machine)
    if not drift_detail.empty:
        drift_detail["SEVERITY"] = drift_detail["DEVIATION_PCT"].apply(
            classify_severity
        )
        col1, col2 = st.columns(2)
        with col1:
            bar_chart = (
                alt.Chart(drift_detail)
                .mark_bar()
                .encode(
                    x=alt.X("WEEK_START:T", title="Week"),
                    y=alt.Y("DEVIATION_PCT:Q", title="Deviation %"),
                    color=alt.Color(
                        "SEVERITY:N", scale=severity_scale(), legend=None
                    ),
                )
                .properties(height=CHART_HEIGHT_STANDARD, title="Deviation Severity by Week")
            )
            st.altair_chart(bar_chart, use_container_width=True)

        with col2:
            area = (
                alt.Chart(drift_detail)
                .mark_area(opacity=BAND_OPACITY, color=BAND_FILL)
                .encode(
                    x=alt.X("WEEK_START:T", title="Week"),
                    y=alt.Y("MIN_DURATION:Q", title="Duration (s)"),
                    y2="MAX_DURATION:Q",
                )
                .properties(height=CHART_HEIGHT_STANDARD, title="Duration Range (min/max band)")
            )
            line = (
                alt.Chart(drift_detail)
                .mark_line(color=ACCENT_PRIMARY, point=True)
                .encode(x="WEEK_START:T", y="AVG_DURATION:Q")
            )
            target_line = (
                alt.Chart(drift_detail)
                .mark_rule(strokeDash=RULE_DASH, color=RULE_NEUTRAL)
                .encode(y="TARGET_DURATION:Q")
            )
            st.altair_chart(area + line + target_line, use_container_width=True)

        render_table(
            drift_detail,
            columns=[
                "WEEK_START",
                "SHOT_COUNT",
                "AVG_DURATION",
                "TARGET_DURATION",
                "DEVIATION_PCT",
                "STD_DURATION",
            ],
        )

    st.divider()
    with st.expander(
        "Corroborating Evidence: Telemetry and Operator Notes", expanded=False
    ):
        st.caption(
            f"Numeric drift for {machine} matched against unstructured "
            "operator shift notes. Operators described this failure in their own "
            "words before the deviation crossed the critical threshold."
        )

        session = get_session()
        notes = session.sql(f"""
            SELECT SHIFT_DATE, AUTHOR_ROLE, NOTE_TEXT
            FROM {DATABASE}.{SCHEMA}.SHIFT_NOTE
            WHERE MACHINE_ID = '{machine}'
            ORDER BY SHIFT_DATE
        """).to_pandas()

        render_corroboration_panel(notes, drift_detail, machine)

        st.divider()
        st.markdown(
            "**How this works:** the agent scans operator notes for wear-related "
            "language and matches each hit to the nearest weekly deviation figure. "
            "Where operators describe a machine slowing down before the numbers "
            "cross a threshold, the unstructured and quantitative signals "
            "corroborate each other."
        )


def render_stability_tab(stability_df, deviation_df):
    """Render stability trends tab."""
    import altair as alt

    st.subheader("Stability Score (Week-over-Week)")
    st.write(
        "Stability = 100% minus coefficient of variation. "
        f"Note how **{DRIFT_EQUIPMENT} stays stable at ~90%** despite drifting - "
        "this is why single-metric monitors fail."
    )

    highlight = alt.selection_multi(fields=["MACHINE_ID"], bind="legend")
    chart = (
        alt.Chart(stability_df)
        .mark_line(point=True)
        .encode(
            x=time_x("WEEK_START", "Week"),
            y=alt.Y(
                "STABILITY_SCORE:Q",
                title="Stability Score (%)",
                scale=alt.Scale(
                    domain=list(padded_domain(stability_df["STABILITY_SCORE"]))
                ),
            ),
            color=alt.Color(
                "MACHINE_ID:N", title="Equipment", scale=categorical_scale()
            ),
            opacity=alt.condition(highlight, alt.value(1.0), alt.value(0.2)),
            tooltip=[
                alt.Tooltip("MACHINE_ID:N", title="Machine"),
                alt.Tooltip("WEEK_START:T", title="Week", format="%b %d"),
                alt.Tooltip("STABILITY_SCORE:Q", title="Stability %", format=".1f"),
                alt.Tooltip("SHOT_COUNT:Q", title="Shots", format=","),
            ],
        )
        .add_selection(highlight)
        .properties(height=CHART_HEIGHT_HERO)
    )
    st.altair_chart(chart, use_container_width=True)

    st.divider()
    st.subheader("Stability vs Deviation Scatter")

    merged = (
        stability_df.groupby("MACHINE_ID")
        .agg(AVG_STABILITY=("STABILITY_SCORE", "mean"))
        .reset_index()
    )
    dev_avg = (
        deviation_df.groupby("MACHINE_ID")
        .agg(AVG_DEVIATION=("DEVIATION_PCT", "mean"))
        .reset_index()
    )
    scatter_data = merged.merge(dev_avg, on="MACHINE_ID")

    scatter = (
        alt.Chart(scatter_data)
        .mark_circle(size=120)
        .encode(
            x=alt.X(
                "AVG_STABILITY:Q",
                title="Avg Stability (%)",
                scale=alt.Scale(
                    domain=list(padded_domain(scatter_data["AVG_STABILITY"]))
                ),
            ),
            y=alt.Y("AVG_DEVIATION:Q", title="Avg Duration Deviation (%)"),
            color=alt.Color("MACHINE_ID:N", scale=categorical_scale()),
            tooltip=[
                alt.Tooltip("MACHINE_ID:N", title="Machine"),
                alt.Tooltip("AVG_STABILITY:Q", title="Avg Stability %", format=".1f"),
                alt.Tooltip("AVG_DEVIATION:Q", title="Avg Deviation %", format=".1f"),
            ],
        )
        .properties(height=CHART_HEIGHT_STANDARD)
    )
    st.altair_chart(scatter, use_container_width=True)
    st.caption(
        f"{DRIFT_EQUIPMENT} has HIGH deviation but HIGH stability - "
        "the 'invisible anomaly' pattern"
    )


def render_fleet_tab(summary_df):
    """Render fleet overview tab."""
    st.subheader("Fleet Health Summary")
    if summary_df.empty:
        st.info("No fleet data available.")
        return
    render_table(summary_df)


SWEEP_TAB_BASE_LABEL = "Sweep"


def _sweep_tab_label() -> str:
    """Build the sweep tab label, carrying a flagged count when one exists.

    `st.tabs` offers no way to select a tab programmatically, so a sweep cannot
    focus its own tab. Surfacing the count in the label is what makes a fresh
    result noticeable from whichever tab the operator is on.

    Returns:
        Either "Sweep" or "Sweep (N flagged)".
    """
    results = st.session_state.get("sweep_results")
    if results is None or results.empty:
        return SWEEP_TAB_BASE_LABEL
    flagged = results[
        results["SEVERITY"].isin([SEVERITY_CRITICAL, SEVERITY_WARNING])
    ]
    if flagged.empty:
        return SWEEP_TAB_BASE_LABEL
    return f"{SWEEP_TAB_BASE_LABEL} ({len(flagged)} flagged)"


def render_sweep_tab() -> None:
    """Render everything triggered from the sidebar Run and Data controls.

    Sweep results, agent and operator actions, investigation output, and the CSV
    paste form all land here so that none of them can push the KPI row or the
    charts down the page.
    """
    has_sweep = "sweep_results" in st.session_state
    has_rca = "rca_machine" in st.session_state
    has_upload = bool(st.session_state.get("show_csv_paste"))

    if not (has_sweep or has_rca or has_upload):
        st.info(
            "Nothing to show yet. Open **Controls > Run** in the sidebar and "
            "choose **Run Fleet Sweep** to scan the fleet for anomalies."
        )
        return

    render_sweep_results()
    render_action_buttons()

    if has_rca and has_sweep:
        st.divider()
    render_rca_results()

    if has_upload and (has_sweep or has_rca):
        st.divider()
    render_upload_preview()


def main():
    """Main app layout with interactive sidebar."""
    st.set_page_config(
        page_title=PAGE_TITLE,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.set_option("client.showErrorDetails", False)
    inject_css()

    render_sidebar()

    # Main area
    render_header()

    # Post-ingest: auto-sweep BEFORE rendering results
    if st.session_state.pop("ingest_trigger_sweep", False):
        results = run_anomaly_sweep()
        results["SEVERITY"] = results["DEVIATION_PCT"].apply(classify_severity)
        st.session_state["sweep_results"] = results
        st.session_state["sweep_just_completed"] = True
        _clear_data_caches()

    if st.session_state.pop("ingest_success", None):
        st.success("Telemetry ingested. Fleet sweep re-run with new data.")

    # Fleet KPIs sit directly under the title and never move: everything that
    # used to render above them (sweep results, action buttons, activity logs)
    # now lives in a tab.
    summary_df = load_fleet_summary()
    render_fleet_status(summary_df)
    render_kpi_cards(summary_df)

    st.divider()

    (
        tab_sweep,
        tab_drift,
        tab_root_cause,
        tab_health,
        tab_actions,
        tab_fleet,
    ) = st.tabs(
        [
            _sweep_tab_label(),
            "Drift Detection",
            "Root Cause",
            "Health",
            "Actions",
            "Fleet",
        ]
    )

    with tab_sweep:
        render_sweep_tab()

    with tab_drift:
        render_drift_tab(load_fleet_deviation())

    with tab_root_cause:
        sub_pareto, sub_whys = st.tabs(["Pareto", "5 Whys"])
        with sub_pareto:
            render_pareto_panel()
        with sub_whys:
            render_five_whys_panel()

    with tab_health:
        sub_efficiency, sub_stability, sub_eol = st.tabs(
            ["Efficiency", "Stability", "Tooling Life"]
        )
        with sub_efficiency:
            render_efficiency_panel()
        with sub_stability:
            render_stability_tab(load_stability_trend(), load_fleet_deviation())
        with sub_eol:
            render_tooling_eol_panel()

    with tab_actions:
        sub_maint, sub_trail, sub_activity, sub_audit = st.tabs(
            ["Maintenance", "Decision Trail", "Activity Log", "Audit Trail"]
        )
        with sub_maint:
            render_maintenance_panel()
        with sub_trail:
            render_decision_trail_panel()
        with sub_activity:
            st.subheader("Agent Activity Log")
            st.caption("Skill invocations recorded during this session.")
            render_skill_log()
        with sub_audit:
            st.subheader("Audit Trail")
            st.caption("Work orders, alerts, and status changes written to AUDIT_LOG.")
            render_audit_trail()

    with tab_fleet:
        sub_overview, sub_insights = st.tabs(["Overview", "Insights"])
        with sub_overview:
            render_fleet_tab(summary_df)
        with sub_insights:
            render_insights_panel()

    st.divider()
    st.caption(
        "Agent sweeps fleet, reasons over anomalies, investigates root causes, "
        "and records decisions autonomously."
    )
    st.caption(
        "Hackathon 2026 | Team: emoldinounited | "
        "Track: Intelligent Workflow Automation Agent"
    )


main()
