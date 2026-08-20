"""Autonomous Manufacturing Workflow Agent - Interactive Fleet Dashboard.

Visualizes duration drift detection across an injection moulding fleet,
with interactive controls for on-demand anomaly sweeps, CSV uploads,
and per-equipment root cause investigations.
"""

import pandas as pd
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
from interactive_controls import (
    classify_severity,
    render_rca_results,
    render_sweep_results,
    render_upload_preview,
)
from session_helper import get_session
from sidebar import render_sidebar
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
    inject_css,
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
def load_drift_detail():
    """Load detailed weekly progression for the drifting machine."""
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
    WHERE MACHINE_ID = '{DRIFT_EQUIPMENT}'
        AND DURATION < 999.9 AND VOLUME > 0 AND TARGET_DURATION > 0
    GROUP BY DATE_TRUNC('WEEK', SHOT_TIME)
    ORDER BY WEEK_START
    """
    return session.sql(query).to_pandas()


def render_kpi_cards(summary_df):
    """Render fleet KPI cards."""
    if summary_df.empty:
        st.info("No fleet data available yet.")
        return

    total_shots = summary_df["TOTAL_SHOTS"].sum()
    num_machines = len(summary_df)
    worst_deviation = summary_df["DEVIATION_PCT"].max()
    worst_machine = summary_df.loc[summary_df["DEVIATION_PCT"].idxmax(), "MACHINE_ID"]

    stability_col = 100.0 - summary_df["CV_PCT"]
    worst_stability_idx = stability_col.idxmin()
    worst_stability = stability_col.loc[worst_stability_idx]
    worst_stability_machine = summary_df.loc[worst_stability_idx, "MACHINE_ID"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Shots", f"{total_shots:,.0f}")
    col2.metric("Fleet Size", f"{num_machines} machines")
    # delta_color="off" suppresses the up/down arrow and green/red tint: these
    # deltas carry a machine name, not a change, and rendered as improvements.
    col3.metric(
        "Worst Deviation",
        f"{worst_deviation:.1f}%",
        delta=worst_machine,
        delta_color="off",
    )
    col4.metric(
        "Lowest Stability",
        f"{worst_stability:.1f}%",
        delta=worst_stability_machine,
        delta_color="off",
    )


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
    st.subheader(f"Weekly Progression: {DRIFT_EQUIPMENT}")

    drift_detail = load_drift_detail()
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
    st.subheader("Corroborating Evidence: Telemetry + Operator Notes")
    st.caption(
        f"Numeric drift for {DRIFT_EQUIPMENT} matched against unstructured operator "
        "shift notes. Highlighted notes directly corroborate the statistical anomaly."
    )

    session = get_session()
    notes = session.sql(f"""
        SELECT SHIFT_DATE, AUTHOR_ROLE, NOTE_TEXT
        FROM {DATABASE}.{SCHEMA}.SHIFT_NOTE
        WHERE MACHINE_ID = '{DRIFT_EQUIPMENT}'
        ORDER BY SHIFT_DATE
    """).to_pandas()

    if not notes.empty and not drift_detail.empty:
        # The deviation trend chart is deliberately not repeated here -- the same
        # chart is already rendered above in this tab.
        st.markdown("**Corroborating Operator Notes**")
        corroboration_keywords = [
            "drift",
            "creep",
            "slow",
            "over standard",
            "compensation",
            "sluggish",
            "cooling",
            "ejection",
            "drag",
            "recommend pulling",
            "significantly long",
            "well over",
        ]

        week_starts = pd.to_datetime(drift_detail["WEEK_START"])
        deviations = drift_detail["DEVIATION_PCT"].values

        for _, note_row in notes.iterrows():
            note_text = str(note_row["NOTE_TEXT"]).lower()
            is_corroborating = any(kw in note_text for kw in corroboration_keywords)
            if is_corroborating:
                note_date = pd.to_datetime(note_row["SHIFT_DATE"])
                diffs = abs(week_starts - note_date)
                nearest_idx = diffs.argmin()
                matched_week = week_starts.iloc[nearest_idx].strftime("%Y-%m-%d")
                matched_dev = deviations[nearest_idx]
                st.warning(
                    f"**{note_row['SHIFT_DATE']}** | {note_row['AUTHOR_ROLE']}\n\n"
                    f"{note_row['NOTE_TEXT']}\n\n"
                    f"--- Corroborates **{matched_dev:.1f}% deviation spike** "
                    f"(week of {matched_week})"
                )
            else:
                st.text(f"[{note_row['SHIFT_DATE']}] {note_row['NOTE_TEXT']}")

        st.markdown("---")
        st.markdown(
            "**Key insight:** Operators noted 'cycle drifting further from standard' "
            "and 'ejection sluggish on the B half' weeks before the deviation crossed "
            "the critical 10% threshold. The agent correlates these unstructured signals "
            "with the quantitative drift to build a complete picture."
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


def main():
    """Main app layout with interactive sidebar."""
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    st.set_option("client.showErrorDetails", False)
    inject_css()

    render_sidebar()

    # Main area
    st.title(PAGE_TITLE)

    # Post-ingest: auto-sweep BEFORE rendering results
    if st.session_state.pop("ingest_trigger_sweep", False):
        from interactive_controls import classify_severity, run_anomaly_sweep

        results = run_anomaly_sweep()
        results["SEVERITY"] = results["DEVIATION_PCT"].apply(classify_severity)
        st.session_state["sweep_results"] = results
        st.session_state["sweep_just_completed"] = True
        from interactive_controls import _clear_data_caches

        _clear_data_caches()

    if st.session_state.pop("ingest_success", None):
        st.success("Telemetry ingested. Fleet sweep re-run with new data.")

    # Show interactive results if triggered
    render_sweep_results()
    render_action_buttons()
    render_rca_results()
    render_upload_preview()

    # Agent Activity Log (collapsed by default to reduce clutter)
    with st.expander("Agent Activity Log (CoCo Skill Invocations)", expanded=False):
        render_skill_log()

    # Audit Trail (collapsed by default)
    with st.expander("Audit Trail (Work Orders and Alerts)", expanded=False):
        render_audit_trail()

    st.divider()

    # Fleet KPIs
    summary_df = load_fleet_summary()
    render_kpi_cards(summary_df)

    st.divider()

    # Tabbed views -- only visible tab queries Snowflake (caching handles repeated loads)
    # Ten flat tabs overflowed the tab bar at 1080p. Grouped into five, with
    # sub-tabs inside each. Drift Detection stays first and standalone: it is
    # the headline finding.
    (
        tab_drift,
        tab_root_cause,
        tab_health,
        tab_actions,
        tab_fleet,
    ) = st.tabs(
        [
            "Drift Detection",
            "Root Cause",
            "Health",
            "Actions",
            "Fleet",
        ]
    )

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
        sub_maint, sub_trail = st.tabs(["Maintenance", "Decision Trail"])
        with sub_maint:
            render_maintenance_panel()
        with sub_trail:
            render_decision_trail_panel()

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
