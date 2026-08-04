"""
Autonomous Manufacturing Workflow Agent - Fleet Anomaly Detection Demo.

Visualizes cycle time drift detection across an injection moulding fleet,
demonstrating how multi-signal reasoning catches anomalies that single-metric
monitors miss. Reads from MMS_DEMO.PUBLIC.DEMO_SHOTS in Snowflake.
"""

import streamlit as st
from snowflake.snowpark.context import get_active_session

PAGE_TITLE = "Autonomous Manufacturing Workflow Agent"
DATABASE = "MMS_DEMO"
SCHEMA = "PUBLIC"
SHOTS_TABLE = "DEMO_SHOTS"
FULL_TABLE = f"{DATABASE}.{SCHEMA}.{SHOTS_TABLE}"

DRIFT_EQUIPMENT = "MX-7103"
CRITICAL_DEVIATION_PCT = 15.0
WARNING_DEVIATION_PCT = 10.0


def get_session():
    """Get active Snowpark session."""
    return get_active_session()


@st.cache_data(ttl=600)
def load_fleet_deviation():
    """Load weekly CT deviation per equipment."""
    session = get_session()
    query = f"""
    SELECT
        EQUIPMENT_CODE,
        DATE_TRUNC('WEEK', LOCAL_SHOT_TIME) AS WEEK_START,
        AVG(CT) AS AVG_CT,
        ANY_VALUE(APPROVED_CT) AS APPROVED_CT,
        COUNT(*) AS SHOT_COUNT,
        ROUND(((AVG(CT) - ANY_VALUE(APPROVED_CT)) / NULLIF(ANY_VALUE(APPROVED_CT), 0)) * 100, 2)
            AS DEVIATION_PCT
    FROM {FULL_TABLE}
    WHERE CT < 999.9 AND VOLUME > 0 AND APPROVED_CT > 0
    GROUP BY EQUIPMENT_CODE, DATE_TRUNC('WEEK', LOCAL_SHOT_TIME)
    ORDER BY EQUIPMENT_CODE, WEEK_START
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=600)
def load_fleet_summary():
    """Load overall fleet health summary."""
    session = get_session()
    query = f"""
    SELECT
        EQUIPMENT_CODE,
        COUNT(*) AS TOTAL_SHOTS,
        ROUND(AVG(CT), 2) AS AVG_CT,
        ANY_VALUE(APPROVED_CT) AS APPROVED_CT,
        ROUND(((AVG(CT) - ANY_VALUE(APPROVED_CT)) / NULLIF(ANY_VALUE(APPROVED_CT), 0)) * 100, 2)
            AS DEVIATION_PCT,
        ROUND(STDDEV(CT) / NULLIF(AVG(CT), 0) * 100, 2) AS CV_PCT,
        MIN(LOCAL_SHOT_TIME) AS FIRST_SHOT,
        MAX(LOCAL_SHOT_TIME) AS LAST_SHOT
    FROM {FULL_TABLE}
    WHERE CT < 999.9 AND VOLUME > 0 AND APPROVED_CT > 0
    GROUP BY EQUIPMENT_CODE
    ORDER BY DEVIATION_PCT DESC
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=600)
def load_stability_trend():
    """Load weekly stability score per equipment."""
    session = get_session()
    query = f"""
    SELECT
        EQUIPMENT_CODE,
        DATE_TRUNC('WEEK', LOCAL_SHOT_TIME) AS WEEK_START,
        ROUND(100.0 - (STDDEV(CT) / NULLIF(AVG(CT), 0) * 100), 1) AS STABILITY_SCORE,
        COUNT(*) AS SHOT_COUNT
    FROM {FULL_TABLE}
    WHERE CT < 999.9 AND VOLUME > 0 AND APPROVED_CT > 0
    GROUP BY EQUIPMENT_CODE, DATE_TRUNC('WEEK', LOCAL_SHOT_TIME)
    HAVING COUNT(*) > 50
    ORDER BY EQUIPMENT_CODE, WEEK_START
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=600)
def load_daily_shots():
    """Load daily shot counts per equipment."""
    session = get_session()
    query = f"""
    SELECT
        EQUIPMENT_CODE,
        DATE_TRUNC('DAY', LOCAL_SHOT_TIME) AS DAY,
        COUNT(*) AS SHOTS,
        ROUND(AVG(CT), 2) AS AVG_CT,
        ROUND(STDDEV(CT), 2) AS STD_CT
    FROM {FULL_TABLE}
    WHERE CT < 999.9 AND VOLUME > 0
    GROUP BY EQUIPMENT_CODE, DATE_TRUNC('DAY', LOCAL_SHOT_TIME)
    ORDER BY EQUIPMENT_CODE, DAY
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=600)
def load_drift_detail():
    """Load detailed weekly progression for the drifting machine."""
    session = get_session()
    query = f"""
    SELECT
        DATE_TRUNC('WEEK', LOCAL_SHOT_TIME) AS WEEK_START,
        COUNT(*) AS SHOT_COUNT,
        ROUND(AVG(CT), 2) AS AVG_CT,
        ROUND(MIN(CT), 2) AS MIN_CT,
        ROUND(MAX(CT), 2) AS MAX_CT,
        ANY_VALUE(APPROVED_CT) AS APPROVED_CT,
        ROUND(((AVG(CT) - ANY_VALUE(APPROVED_CT)) / NULLIF(ANY_VALUE(APPROVED_CT), 0)) * 100, 2)
            AS DEVIATION_PCT,
        ROUND(STDDEV(CT), 3) AS STD_CT
    FROM {FULL_TABLE}
    WHERE EQUIPMENT_CODE = '{DRIFT_EQUIPMENT}'
        AND CT < 999.9 AND VOLUME > 0 AND APPROVED_CT > 0
    GROUP BY DATE_TRUNC('WEEK', LOCAL_SHOT_TIME)
    ORDER BY WEEK_START
    """
    return session.sql(query).to_pandas()


def render_kpi_cards(summary_df):
    """Render fleet KPI cards."""
    total_shots = summary_df["TOTAL_SHOTS"].sum()
    num_machines = len(summary_df)
    worst_deviation = summary_df["DEVIATION_PCT"].max()
    worst_machine = summary_df.iloc[0]["EQUIPMENT_CODE"]
    avg_cv = summary_df["CV_PCT"].mean()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Shots", f"{total_shots:,.0f}")
    col2.metric("Fleet Size", f"{num_machines} machines")
    col3.metric("Worst Deviation", f"{worst_deviation:.1f}%", delta=f"{worst_machine}")
    col4.metric("Avg Fleet CV", f"{avg_cv:.1f}%")


def render_drift_tab(deviation_df):
    """Render the CT drift detection tab."""
    import altair as alt

    st.subheader("Cycle Time Drift Detection")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.write(
            f"**{DRIFT_EQUIPMENT}** drifts from ~2% to ~24% above approved CT over 6 weeks "
            "while stability stays at 90%. No single-metric alert fires. "
            "The agent catches it by reasoning across deviation and stability together."
        )
    with col2:
        st.warning(
            f"**Alert:** {DRIFT_EQUIPMENT} crossed critical threshold (>{CRITICAL_DEVIATION_PCT}%) "
            "in week 6. Traditional monitors missed this progressive drift."
        )

    chart_data = deviation_df.copy()
    chart_data["IS_HEADLINE"] = chart_data["EQUIPMENT_CODE"] == DRIFT_EQUIPMENT

    highlight = alt.selection_multi(fields=["EQUIPMENT_CODE"], bind="legend")

    chart = (
        alt.Chart(chart_data)
        .mark_line(point=True)
        .encode(
            x=alt.X("WEEK_START:T", title="Week"),
            y=alt.Y("DEVIATION_PCT:Q", title="CT Deviation (%)"),
            color=alt.Color("EQUIPMENT_CODE:N", title="Equipment"),
            opacity=alt.condition(highlight, alt.value(1.0), alt.value(0.2)),
            strokeWidth=alt.condition(
                alt.datum.IS_HEADLINE, alt.value(3), alt.value(1)
            ),
        )
        .add_selection(highlight)
        .properties(height=400, title="Fleet-Wide CT Deviation Over Time")
    )

    rule_warning = (
        alt.Chart()
        .mark_rule(strokeDash=[5, 5], color="orange")
        .encode(y=alt.datum(WARNING_DEVIATION_PCT))
    )
    rule_critical = (
        alt.Chart()
        .mark_rule(strokeDash=[5, 5], color="red")
        .encode(y=alt.datum(CRITICAL_DEVIATION_PCT))
    )

    st.altair_chart(chart + rule_warning + rule_critical, use_container_width=True)

    st.caption("Orange dashed = Warning (10%) | Red dashed = Critical (15%) | Click legend to isolate")

    st.divider()
    st.subheader(f"Weekly Progression: {DRIFT_EQUIPMENT}")

    drift_detail = load_drift_detail()
    if not drift_detail.empty:
        col1, col2 = st.columns(2)

        with col1:
            bar_chart = (
                alt.Chart(drift_detail)
                .mark_bar()
                .encode(
                    x=alt.X("WEEK_START:T", title="Week"),
                    y=alt.Y("DEVIATION_PCT:Q", title="Deviation %"),
                    color=alt.Color("DEVIATION_PCT:Q", scale=alt.Scale(scheme="redyellowgreen", reverse=True)),
                )
                .properties(height=250, title="Deviation Severity by Week")
            )
            st.altair_chart(bar_chart, use_container_width=True)

        with col2:
            ct_chart = (
                alt.Chart(drift_detail)
                .mark_area(opacity=0.3, color="#ff6b6b")
                .encode(
                    x=alt.X("WEEK_START:T", title="Week"),
                    y=alt.Y("MIN_CT:Q", title="Cycle Time (s)"),
                    y2="MAX_CT:Q",
                )
                .properties(height=250, title="CT Range (min/max band)")
            )
            ct_line = (
                alt.Chart(drift_detail)
                .mark_line(color="#dc3545", point=True)
                .encode(
                    x="WEEK_START:T",
                    y="AVG_CT:Q",
                )
            )
            approved_line = (
                alt.Chart(drift_detail)
                .mark_rule(strokeDash=[4, 4], color="green")
                .encode(y="APPROVED_CT:Q")
            )
            st.altair_chart(ct_chart + ct_line + approved_line, use_container_width=True)

        st.dataframe(
            drift_detail[["WEEK_START", "SHOT_COUNT", "AVG_CT", "APPROVED_CT", "DEVIATION_PCT", "STD_CT"]],
            use_container_width=True,
        )

    st.divider()
    st.subheader("Operator Shift Notes (What the Agent Investigates)")
    st.write(
        "The agent's **$investigate-shift-notes** skill searches these operator logs "
        "to corroborate the numeric signal. Notice how operators sensed the drift "
        "before any alert fired."
    )
    session = get_session()
    notes = session.sql(f"""
        SELECT SHIFT_DATE, AUTHOR_ROLE, NOTE_TEXT
        FROM {DATABASE}.{SCHEMA}.SHIFT_NOTE
        WHERE EQUIPMENT_CODE = '{DRIFT_EQUIPMENT}'
        ORDER BY SHIFT_DATE
    """).to_pandas()
    st.dataframe(notes, use_container_width=True)


def render_stability_tab(stability_df, deviation_df):
    """Render stability trends tab."""
    import altair as alt

    st.subheader("Stability Score (Week-over-Week)")
    st.write(
        "Stability = 100% minus coefficient of variation. "
        "A declining trend is the earliest warning of degradation. "
        "Note how **MX-7103 stays stable at ~90%** despite drifting - this is why single-metric monitors fail."
    )

    highlight = alt.selection_multi(fields=["EQUIPMENT_CODE"], bind="legend")

    chart = (
        alt.Chart(stability_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("WEEK_START:T", title="Week"),
            y=alt.Y("STABILITY_SCORE:Q", title="Stability Score (%)", scale=alt.Scale(domain=[40, 100])),
            color=alt.Color("EQUIPMENT_CODE:N", title="Equipment"),
            opacity=alt.condition(highlight, alt.value(1.0), alt.value(0.2)),
        )
        .add_selection(highlight)
        .properties(height=350, title="Fleet Stability Trends")
    )

    st.altair_chart(chart, use_container_width=True)

    st.divider()
    st.subheader("Why This Matters: The Invisible Anomaly")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**What a threshold monitor sees:**")
        st.markdown(f"- {DRIFT_EQUIPMENT} stability: **90%** (HEALTHY)")
        st.markdown("- No threshold breached")
        st.markdown("- No alert fired")
        st.markdown("- Result: **Silent failure accumulates**")

    with col2:
        st.markdown("**What the autonomous agent sees:**")
        st.markdown(f"- {DRIFT_EQUIPMENT} CT deviation: **24%** (CRITICAL)")
        st.markdown(f"- {DRIFT_EQUIPMENT} stability: **90%** (looks fine)")
        st.markdown("- Contradiction = interesting signal")
        st.markdown("- Result: **Flags for investigation**")

    st.divider()
    st.subheader("Stability vs Deviation Scatter")

    merged = stability_df.groupby("EQUIPMENT_CODE").agg(
        AVG_STABILITY=("STABILITY_SCORE", "mean")
    ).reset_index()
    dev_avg = deviation_df.groupby("EQUIPMENT_CODE").agg(
        AVG_DEVIATION=("DEVIATION_PCT", "mean")
    ).reset_index()
    scatter_data = merged.merge(dev_avg, on="EQUIPMENT_CODE")

    scatter = (
        alt.Chart(scatter_data)
        .mark_circle(size=120)
        .encode(
            x=alt.X("AVG_STABILITY:Q", title="Avg Stability (%)", scale=alt.Scale(domain=[50, 100])),
            y=alt.Y("AVG_DEVIATION:Q", title="Avg CT Deviation (%)"),
            color=alt.Color("EQUIPMENT_CODE:N"),
            tooltip=["EQUIPMENT_CODE", "AVG_STABILITY", "AVG_DEVIATION"],
        )
        .properties(height=300, title="Stability vs Deviation (per machine)")
    )
    st.altair_chart(scatter, use_container_width=True)
    st.caption(f"Note: {DRIFT_EQUIPMENT} has HIGH deviation but HIGH stability - the 'invisible anomaly' pattern")


def render_fleet_tab(summary_df, daily_df):
    """Render fleet overview tab."""
    import altair as alt

    st.subheader("Fleet Health Summary")

    st.dataframe(summary_df, use_container_width=True)

    st.divider()
    st.subheader("Daily Production Volume")

    volume_chart = (
        alt.Chart(daily_df)
        .mark_bar(opacity=0.7)
        .encode(
            x=alt.X("DAY:T", title="Date"),
            y=alt.Y("SHOTS:Q", title="Shots per Day"),
            color=alt.Color("EQUIPMENT_CODE:N", title="Equipment"),
            tooltip=["EQUIPMENT_CODE", "DAY", "SHOTS", "AVG_CT"],
        )
        .properties(height=300, title="Daily Shot Count by Equipment")
    )
    st.altair_chart(volume_chart, use_container_width=True)

    st.divider()
    st.subheader("Agent Architecture")

    st.code("""
    [TRIGGER] Schedule or manual command
         |
         v
    [SENSE] CT Deviation + Stability (fleet sweep)
         |
         v
    [REASON] Snowflake Cortex LLM (Claude Sonnet)
         |   - Cross-signal reasoning across detectors
         |   - Decides which machines need investigation
         v
    [ACT] Root Cause Analysis, Save Insights
         |
         v
    [RECORD] Decision Trail + Self-grade against ground truth
    """, language=None)

    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Skill 1: $sense-equipment-anomalies**")
        st.markdown("Sweeps fleet for CT drift and stability decline. Ranks machines by severity.")
    with col2:
        st.markdown("**Skill 2: $investigate-shift-notes**")
        st.markdown("Searches operator notes to explain WHY a machine is abnormal.")
    with col3:
        st.markdown("**Skill 3: $report-and-act**")
        st.markdown("Records decision, evidence, and actions. Self-grades against ground truth.")


def main():
    """Main app layout."""
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    st.title(PAGE_TITLE)
    st.caption("Hackathon 2026 | Team: emoldinounited | Track: Intelligent Workflow Automation Agent")

    st.divider()

    summary_df = load_fleet_summary()
    render_kpi_cards(summary_df)

    st.divider()

    tab_drift, tab_stability, tab_fleet = st.tabs(
        ["CT Drift Detection", "Stability Trends", "Fleet Overview"]
    )

    with tab_drift:
        deviation_df = load_fleet_deviation()
        render_drift_tab(deviation_df)

    with tab_stability:
        stability_df = load_stability_trend()
        render_stability_tab(stability_df, deviation_df)

    with tab_fleet:
        daily_df = load_daily_shots()
        render_fleet_tab(summary_df, daily_df)

    st.divider()
    st.info(
        "This demo uses synthetic data (243K shots, 8 machines, 6 weeks) with "
        "planted anomalies. The autonomous agent sweeps the fleet, reasons across "
        "detectors, investigates anomalies, and records decisions - with zero human intervention. "
        "GitHub: github.com/UttyWotty/Hackathon2026"
    )


main()
