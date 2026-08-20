"""Analysis visualization panels for the Streamlit dashboard.

Provides SQL-driven Pareto, 5 Whys, efficiency, tooling EOL, maintenance impact,
decision trail, and insights panels that render directly from Snowflake queries.
"""

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st
from session_helper import get_session

DATABASE = "DEMO"
SCHEMA = "PUBLIC"
FULL_TABLE = f"{DATABASE}.{SCHEMA}.SHOT_DATA"
TOOL_TABLE = f"{DATABASE}.{SCHEMA}.TOOL"
WORK_ORDER_TABLE = f"{DATABASE}.{SCHEMA}.WORK_ORDER"
AUDIT_TABLE = f"{DATABASE}.{SCHEMA}.AUDIT_LOG"
SHIFT_NOTE_TABLE = f"{DATABASE}.{SCHEMA}.SHIFT_NOTE"

HARD_STOP = 999.9
DEFAULT_LOOKBACK_DAYS = 42
DEVIATION_THRESHOLD = 3.0

GRANULARITY_MAP = {
    "Daily": "DAY",
    "Weekly": "WEEK",
    "Monthly": "MONTH",
}


def _render_date_range(key_prefix: str) -> tuple:
    """Render date range picker and return (start_date, end_date) strings."""
    col_start, col_end = st.columns(2)
    default_end = date(2026, 8, 18)
    default_start = default_end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    with col_start:
        start = st.date_input("From", value=default_start, key=f"{key_prefix}_start")
    with col_end:
        end = st.date_input("To", value=default_end, key=f"{key_prefix}_end")
    return str(start), str(end)


def _date_filter(start: str, end: str) -> str:
    """Return SQL WHERE clause fragment for SHOT_TIME date range."""
    return f"SHOT_TIME >= '{start}' AND SHOT_TIME <= '{end} 23:59:59'"


def render_pareto_panel():
    """Pareto analysis: which machines contribute most to total deviation."""
    session = get_session()

    st.subheader("Pareto Analysis - Deviation Contribution")
    st.caption(
        "Which machines contribute the most to total fleet deviation from target?"
    )

    start, end = _render_date_range("pareto")
    date_clause = _date_filter(start, end)

    df = session.sql(f"""
        SELECT
            MACHINE_ID,
            COUNT(*) AS SHOT_COUNT,
            SUM(ABS(DURATION - TARGET_DURATION)) AS TOTAL_DEVIATION_SEC,
            ROUND(AVG(ABS(DURATION - TARGET_DURATION)), 2) AS AVG_ABS_DEVIATION
        FROM {FULL_TABLE}
        WHERE DURATION < {HARD_STOP} AND VOLUME > 0 AND TARGET_DURATION > 0
          AND {date_clause}
        GROUP BY MACHINE_ID
        ORDER BY TOTAL_DEVIATION_SEC DESC
    """).to_pandas()

    if df.empty:
        st.warning("No data available.")
        return

    total = df["TOTAL_DEVIATION_SEC"].sum()
    df["CONTRIBUTION_PCT"] = (df["TOTAL_DEVIATION_SEC"] / total * 100).round(1)
    df["CUMULATIVE_PCT"] = df["CONTRIBUTION_PCT"].cumsum()

    base = alt.Chart(df).encode(
        x=alt.X("MACHINE_ID:N", sort="-y", title="Machine"),
    )
    bars = base.mark_bar(color="#dc3545").encode(
        y=alt.Y("CONTRIBUTION_PCT:Q", title="Contribution (%)"),
        tooltip=["MACHINE_ID", "CONTRIBUTION_PCT", "SHOT_COUNT", "AVG_ABS_DEVIATION"],
    )
    line = base.mark_line(color="#00d4ff", point=True, strokeWidth=3).encode(
        y=alt.Y("CUMULATIVE_PCT:Q", title="Cumulative (%)"),
    )
    chart = alt.layer(bars, line).resolve_scale(y="independent").properties(height=320)
    st.altair_chart(chart, use_container_width=True)

    st.markdown(
        f"**Top contributor:** {df.iloc[0]['MACHINE_ID']} accounts for "
        f"{df.iloc[0]['CONTRIBUTION_PCT']:.1f}% of total deviation"
    )

    st.divider()
    render_dimensional_drilldown()


def render_dimensional_drilldown():
    """Dimensional drill-down: break deviation by time, shift, and product."""
    session = get_session()

    st.subheader("Dimensional Drill-Down")
    st.caption("Break down deviation by time pattern, shift, and product for a single machine")

    machines = (
        session.sql(f"SELECT DISTINCT MACHINE_ID FROM {FULL_TABLE} ORDER BY MACHINE_ID")
        .to_pandas()["MACHINE_ID"]
        .tolist()
    )

    ctrl1, ctrl2 = st.columns([2, 1])
    with ctrl1:
        selected = st.selectbox("Machine", machines, index=2, key="5whys_machine")
    with ctrl2:
        granularity = st.selectbox(
            "Time Granularity", list(GRANULARITY_MAP.keys()), key="5whys_gran"
        )

    start, end = _render_date_range("5whys")
    date_clause = _date_filter(start, end)
    trunc_unit = GRANULARITY_MAP[granularity]
    base_where = f"MACHINE_ID = '{selected}' AND DURATION < {HARD_STOP} AND VOLUME > 0 AND {date_clause}"

    st.markdown(f"**Time Trend ({granularity})**")
    trend = session.sql(f"""
        SELECT DATE_TRUNC('{trunc_unit}', SHOT_TIME) AS PERIOD,
               ROUND(AVG(DURATION) - AVG(TARGET_DURATION), 2) AS AVG_DEVIATION,
               COUNT(*) AS SHOTS
        FROM {FULL_TABLE}
        WHERE {base_where}
        GROUP BY 1 ORDER BY 1
    """).to_pandas()
    if not trend.empty:
        trend["STATUS"] = trend["AVG_DEVIATION"].apply(
            lambda v: "High" if v > DEVIATION_THRESHOLD else "Normal"
        )
        chart = (
            alt.Chart(trend)
            .mark_bar()
            .encode(
                x="PERIOD:T",
                y="AVG_DEVIATION:Q",
                color=alt.Color(
                    "STATUS:N",
                    scale=alt.Scale(
                        domain=["High", "Normal"], range=["#dc3545", "#28a745"]
                    ),
                    legend=None,
                ),
                tooltip=["PERIOD:T", "AVG_DEVIATION", "SHOTS"],
            )
            .properties(height=180)
        )
        st.altair_chart(chart, use_container_width=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Hour of Day**")
        hourly = session.sql(f"""
            SELECT HOUR(SHOT_TIME) AS HOUR_OF_DAY,
                   ROUND(AVG(DURATION) - AVG(TARGET_DURATION), 2) AS AVG_DEVIATION
            FROM {FULL_TABLE}
            WHERE {base_where}
            GROUP BY 1 ORDER BY 1
        """).to_pandas()
        if not hourly.empty:
            hourly["STATUS"] = hourly["AVG_DEVIATION"].apply(
                lambda v: "High" if v > DEVIATION_THRESHOLD else "Normal"
            )
            chart = (
                alt.Chart(hourly)
                .mark_bar()
                .encode(
                    x="HOUR_OF_DAY:O",
                    y="AVG_DEVIATION:Q",
                    color=alt.Color(
                        "STATUS:N",
                        scale=alt.Scale(
                            domain=["High", "Normal"], range=["#dc3545", "#28a745"]
                        ),
                        legend=None,
                    ),
                    tooltip=["HOUR_OF_DAY", "AVG_DEVIATION"],
                )
                .properties(height=180)
            )
            st.altair_chart(chart, use_container_width=True)

    with col2:
        st.markdown("**Day of Week**")
        dow = session.sql(f"""
            SELECT DAYOFWEEK(SHOT_TIME) AS DOW,
                   ROUND(AVG(DURATION) - AVG(TARGET_DURATION), 2) AS AVG_DEVIATION,
                   COUNT(*) AS SHOTS
            FROM {FULL_TABLE}
            WHERE {base_where}
            GROUP BY 1 ORDER BY 1
        """).to_pandas()
        if not dow.empty:
            dow["STATUS"] = dow["AVG_DEVIATION"].apply(
                lambda v: "High" if v > DEVIATION_THRESHOLD else "Normal"
            )
            chart = (
                alt.Chart(dow)
                .mark_bar()
                .encode(
                    x=alt.X("DOW:O", title="Day of Week (0=Mon)"),
                    y="AVG_DEVIATION:Q",
                    color=alt.Color(
                        "STATUS:N",
                        scale=alt.Scale(
                            domain=["High", "Normal"], range=["#dc3545", "#28a745"]
                        ),
                        legend=None,
                    ),
                    tooltip=["DOW", "AVG_DEVIATION", "SHOTS"],
                )
                .properties(height=180)
            )
            st.altair_chart(chart, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        st.markdown("**By Shift**")
        shift = session.sql(f"""
            SELECT
                CASE
                    WHEN HOUR(SHOT_TIME) BETWEEN 6 AND 13 THEN 'Morning (06-14)'
                    WHEN HOUR(SHOT_TIME) BETWEEN 14 AND 21 THEN 'Afternoon (14-22)'
                    ELSE 'Night (22-06)'
                END AS SHIFT,
                ROUND(AVG(DURATION) - AVG(TARGET_DURATION), 2) AS AVG_DEVIATION,
                COUNT(*) AS SHOTS
            FROM {FULL_TABLE}
            WHERE {base_where}
            GROUP BY 1 ORDER BY AVG_DEVIATION DESC
        """).to_pandas()
        if not shift.empty:
            shift["STATUS"] = shift["AVG_DEVIATION"].apply(
                lambda v: "High" if v > DEVIATION_THRESHOLD else "Normal"
            )
            chart = (
                alt.Chart(shift)
                .mark_bar()
                .encode(
                    x=alt.X("SHIFT:N", title="Shift"),
                    y="AVG_DEVIATION:Q",
                    color=alt.Color(
                        "STATUS:N",
                        scale=alt.Scale(
                            domain=["High", "Normal"], range=["#dc3545", "#28a745"]
                        ),
                        legend=None,
                    ),
                    tooltip=["SHIFT", "AVG_DEVIATION", "SHOTS"],
                )
                .properties(height=180)
            )
            st.altair_chart(chart, use_container_width=True)

    with col4:
        st.markdown("**By Product**")
        product = session.sql(f"""
            SELECT PRODUCT_NAME,
                   ROUND(AVG(DURATION) - AVG(TARGET_DURATION), 2) AS AVG_DEVIATION,
                   COUNT(*) AS SHOTS
            FROM {FULL_TABLE}
            WHERE {base_where}
            GROUP BY 1 ORDER BY AVG_DEVIATION DESC
        """).to_pandas()
        if not product.empty:
            product["STATUS"] = product["AVG_DEVIATION"].apply(
                lambda v: "High" if v > DEVIATION_THRESHOLD else "Normal"
            )
            chart = (
                alt.Chart(product)
                .mark_bar()
                .encode(
                    x=alt.X("PRODUCT_NAME:N", sort="-y", title="Product"),
                    y="AVG_DEVIATION:Q",
                    color=alt.Color(
                        "STATUS:N",
                        scale=alt.Scale(
                            domain=["High", "Normal"], range=["#dc3545", "#28a745"]
                        ),
                        legend=None,
                    ),
                    tooltip=["PRODUCT_NAME", "AVG_DEVIATION", "SHOTS"],
                )
                .properties(height=180)
            )
            st.altair_chart(chart, use_container_width=True)


FIVE_WHYS_MODEL = "mistral-large2"
FIVE_WHYS_SESSION_KEY = "five_whys_result"


def _gather_machine_context(session, machine_id: str, date_clause: str) -> str:
    """Gather data context for a machine to feed the 5 Whys LLM prompt."""
    base_where = (
        f"MACHINE_ID = '{machine_id}' AND DURATION < {HARD_STOP} "
        f"AND VOLUME > 0 AND {date_clause}"
    )

    overview = session.sql(f"""
        SELECT
            ROUND(AVG(DURATION), 2) AS AVG_DURATION,
            ROUND(AVG(TARGET_DURATION), 2) AS AVG_TARGET,
            ROUND(((AVG(DURATION) - AVG(TARGET_DURATION))
                / NULLIF(AVG(TARGET_DURATION), 0)) * 100, 2) AS DEVIATION_PCT,
            ROUND(STDDEV(DURATION), 3) AS STD_DURATION,
            COUNT(*) AS TOTAL_SHOTS
        FROM {FULL_TABLE}
        WHERE {base_where}
    """).to_pandas()

    shift_data = session.sql(f"""
        SELECT
            CASE
                WHEN HOUR(SHOT_TIME) BETWEEN 6 AND 13 THEN 'Morning'
                WHEN HOUR(SHOT_TIME) BETWEEN 14 AND 21 THEN 'Afternoon'
                ELSE 'Night'
            END AS SHIFT,
            ROUND(AVG(DURATION) - AVG(TARGET_DURATION), 2) AS AVG_DEVIATION,
            COUNT(*) AS SHOTS
        FROM {FULL_TABLE}
        WHERE {base_where}
        GROUP BY 1 ORDER BY AVG_DEVIATION DESC
    """).to_pandas()

    product_data = session.sql(f"""
        SELECT PRODUCT_NAME,
               ROUND(AVG(DURATION) - AVG(TARGET_DURATION), 2) AS AVG_DEVIATION,
               COUNT(*) AS SHOTS
        FROM {FULL_TABLE}
        WHERE {base_where}
        GROUP BY 1 ORDER BY AVG_DEVIATION DESC
        LIMIT 5
    """).to_pandas()

    weekly_trend = session.sql(f"""
        SELECT DATE_TRUNC('WEEK', SHOT_TIME) AS WEEK,
               ROUND(AVG(DURATION) - AVG(TARGET_DURATION), 2) AS AVG_DEVIATION
        FROM {FULL_TABLE}
        WHERE {base_where}
        GROUP BY 1 ORDER BY 1
    """).to_pandas()

    context_parts = [
        f"Machine: {machine_id}",
        f"Overall: avg_duration={overview.iloc[0]['AVG_DURATION']}s, "
        f"target={overview.iloc[0]['AVG_TARGET']}s, "
        f"deviation={overview.iloc[0]['DEVIATION_PCT']}%, "
        f"std_dev={overview.iloc[0]['STD_DURATION']}s, "
        f"total_shots={overview.iloc[0]['TOTAL_SHOTS']}",
        "",
        "Weekly trend (deviation from target):",
        weekly_trend.to_string(index=False) if not weekly_trend.empty else "No data",
        "",
        "Deviation by shift:",
        shift_data.to_string(index=False) if not shift_data.empty else "No data",
        "",
        "Top products by deviation:",
        product_data.to_string(index=False) if not product_data.empty else "No data",
    ]
    return "\n".join(context_parts)


def _run_five_whys_llm(session, machine_id: str, context: str) -> str:
    """Call Cortex Complete to generate a 5 Whys causal chain."""
    prompt = f"""You are a manufacturing root cause analysis expert. Perform a 5 Whys analysis
for the machine below. Each "Why" must dig deeper into the previous answer, forming a causal
chain from symptom to root cause.

DATA CONTEXT:
{context}

INSTRUCTIONS:
- Start with the observed problem (duration deviation from target)
- Each Why should be a specific question about WHY the previous answer is happening
- Each answer should reference the data provided where possible
- The 5th Why should identify the most likely root cause
- Be specific and data-driven, not generic
- Format exactly as shown below

FORMAT:
Problem: [State the observed problem in one sentence]

Why 1: [Question about why the problem exists]
Answer: [Data-driven answer]

Why 2: [Deeper question based on Answer 1]
Answer: [Data-driven answer]

Why 3: [Deeper question based on Answer 2]
Answer: [Data-driven answer]

Why 4: [Deeper question based on Answer 3]
Answer: [Data-driven answer]

Why 5: [Deepest question - gets to root cause]
Answer: [Root cause conclusion]

Root Cause: [One-sentence summary of the root cause]
Recommended Action: [One concrete action to address it]
"""
    escaped = prompt.replace("\\", "\\\\").replace("'", "\\'")
    result = session.sql(
        f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{FIVE_WHYS_MODEL}', '{escaped}') AS RESPONSE"
    ).collect()
    if result and len(result) > 0:
        return str(result[0]["RESPONSE"]).strip()
    return "Unable to generate analysis. Please try again."


def render_five_whys_panel():
    """LLM-driven iterative 5 Whys root cause analysis."""
    session = get_session()

    st.subheader("5 Whys - Root Cause Analysis")
    st.caption(
        "Select a machine and run an AI-driven 5 Whys analysis that iteratively "
        "drills from symptom to root cause"
    )

    machines = (
        session.sql(f"SELECT DISTINCT MACHINE_ID FROM {FULL_TABLE} ORDER BY MACHINE_ID")
        .to_pandas()["MACHINE_ID"]
        .tolist()
    )

    col_machine, col_btn = st.columns([2, 1])
    with col_machine:
        selected = st.selectbox(
            "Machine", machines, index=2, key="5whys_llm_machine"
        )
    with col_btn:
        st.write("")
        run_clicked = st.button(
            "Run 5 Whys", key="5whys_run", use_container_width=True
        )

    start, end = _render_date_range("5whys_llm")
    date_clause = _date_filter(start, end)

    if run_clicked:
        with st.spinner("Running 5 Whys analysis with Cortex AI..."):
            context = _gather_machine_context(session, selected, date_clause)
            result = _run_five_whys_llm(session, selected, context)
            st.session_state[FIVE_WHYS_SESSION_KEY] = {
                "machine": selected,
                "result": result,
            }

    stored = st.session_state.get(FIVE_WHYS_SESSION_KEY)
    if stored:
        st.markdown(f"**Analysis for {stored['machine']}:**")
        st.markdown("---")
        st.markdown(stored["result"])


def render_efficiency_panel():
    """Fleet efficiency: TARGET_DURATION / DURATION ratio per machine."""
    session = get_session()

    st.subheader("Duration Efficiency - Fleet Comparison")
    st.caption(
        "How efficiently each machine runs relative to its target (100% = perfect)"
    )

    start, end = _render_date_range("efficiency")
    date_clause = _date_filter(start, end)

    df = session.sql(f"""
        SELECT
            MACHINE_ID,
            ROUND(AVG(TARGET_DURATION / NULLIF(DURATION, 0)) * 100, 1) AS EFFICIENCY_PCT,
            COUNT(*) AS SHOTS,
            ROUND(STDDEV(DURATION) / NULLIF(AVG(DURATION), 0) * 100, 1) AS CV_PCT
        FROM {FULL_TABLE}
        WHERE DURATION < {HARD_STOP} AND DURATION > 0 AND VOLUME > 0 AND TARGET_DURATION > 0
          AND {date_clause}
        GROUP BY MACHINE_ID
        ORDER BY EFFICIENCY_PCT
    """).to_pandas()

    if df.empty:
        st.warning("No data.")
        return

    df["STATUS"] = df["EFFICIENCY_PCT"].apply(
        lambda v: "Critical" if v < 90 else ("Warning" if v < 98 else "Normal")
    )
    color_scale = alt.Scale(
        domain=["Critical", "Warning", "Normal"],
        range=["#dc3545", "#ffc107", "#28a745"],
    )
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            y=alt.Y("MACHINE_ID:N", sort="x", title="Machine"),
            x=alt.X(
                "EFFICIENCY_PCT:Q",
                title="Efficiency %",
                scale=alt.Scale(domain=[0, 105]),
            ),
            color=alt.Color(
                "STATUS:N", scale=color_scale, legend=alt.Legend(title="Status")
            ),
            tooltip=["MACHINE_ID", "EFFICIENCY_PCT", "SHOTS", "CV_PCT"],
        )
        .properties(height=300)
    )

    rule = (
        alt.Chart(pd.DataFrame({"x": [100]}))
        .mark_rule(strokeDash=[4, 4], color="black")
        .encode(x="x:Q")
    )

    st.altair_chart(chart + rule, use_container_width=True)


def render_tooling_eol_panel():
    """Tooling end-of-life: shots used vs designed life."""
    session = get_session()

    st.subheader("Tooling End-of-Life Prediction")
    st.caption("Remaining tool life based on accumulated shots vs designed shot limit")

    df = session.sql(f"""
        SELECT
            t.MACHINE_ID,
            t.DESIGNED_SHOT,
            t.TYPE,
            COUNT(s.DURATION) AS ACCUMULATED_SHOTS,
            ROUND(COUNT(s.DURATION) / NULLIF(t.DESIGNED_SHOT, 0) * 100, 1) AS LIFE_USED_PCT
        FROM {TOOL_TABLE} t
        LEFT JOIN {FULL_TABLE} s ON t.MACHINE_ID = s.MACHINE_ID
        GROUP BY t.MACHINE_ID, t.DESIGNED_SHOT, t.TYPE
        ORDER BY LIFE_USED_PCT DESC
    """).to_pandas()

    if df.empty:
        st.warning("No tooling data.")
        return

    df["REMAINING_PCT"] = (100 - df["LIFE_USED_PCT"]).clip(lower=0)
    df["STATUS"] = df["LIFE_USED_PCT"].apply(
        lambda v: "Critical" if v > 80 else ("Warning" if v > 50 else "Normal")
    )
    color_scale = alt.Scale(
        domain=["Critical", "Warning", "Normal"],
        range=["#dc3545", "#ffc107", "#28a745"],
    )
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            y=alt.Y("MACHINE_ID:N", sort="-x", title="Machine"),
            x=alt.X(
                "LIFE_USED_PCT:Q",
                title="Tool Life Used (%)",
                scale=alt.Scale(domain=[0, 100]),
            ),
            color=alt.Color(
                "STATUS:N", scale=color_scale, legend=alt.Legend(title="Status")
            ),
            tooltip=[
                "MACHINE_ID",
                "TYPE",
                "ACCUMULATED_SHOTS",
                "DESIGNED_SHOT",
                "LIFE_USED_PCT",
            ],
        )
        .properties(height=300)
    )
    st.altair_chart(chart, use_container_width=True)

    st.dataframe(
        df[
            [
                "MACHINE_ID",
                "TYPE",
                "ACCUMULATED_SHOTS",
                "DESIGNED_SHOT",
                "LIFE_USED_PCT",
                "REMAINING_PCT",
            ]
        ],
        use_container_width=True,
    )


def render_maintenance_panel():
    """Before/after maintenance comparison."""
    session = get_session()

    st.subheader("Maintenance Impact Analysis")
    st.caption(
        "Did maintenance actually help? Compare duration before vs after each work order."
    )

    df = session.sql(f"""
        WITH wo AS (
            SELECT TOOL_ID, COMPLETED_AT, ORDER_TYPE
            FROM {WORK_ORDER_TABLE}
            WHERE COMPLETED_AT IS NOT NULL
        )
        SELECT
            t.MACHINE_ID,
            wo.ORDER_TYPE,
            wo.COMPLETED_AT,
            ROUND(AVG(CASE WHEN s.SHOT_TIME < wo.COMPLETED_AT
                            AND s.SHOT_TIME >= DATEADD(day, -7, wo.COMPLETED_AT)
                       THEN s.DURATION END), 2) AS AVG_BEFORE,
            ROUND(AVG(CASE WHEN s.SHOT_TIME >= wo.COMPLETED_AT
                            AND s.SHOT_TIME < DATEADD(day, 7, wo.COMPLETED_AT)
                       THEN s.DURATION END), 2) AS AVG_AFTER
        FROM wo
        JOIN {TOOL_TABLE} t ON t.ID = wo.TOOL_ID
        JOIN {FULL_TABLE} s ON s.MACHINE_ID = t.MACHINE_ID
            AND s.DURATION < {HARD_STOP} AND s.VOLUME > 0
        GROUP BY t.MACHINE_ID, wo.ORDER_TYPE, wo.COMPLETED_AT
        HAVING AVG_BEFORE IS NOT NULL AND AVG_AFTER IS NOT NULL
        ORDER BY wo.COMPLETED_AT DESC
    """).to_pandas()

    if df.empty:
        st.info("No before/after data available for completed work orders.")
        return

    df["CHANGE_PCT"] = (
        (df["AVG_AFTER"] - df["AVG_BEFORE"]) / df["AVG_BEFORE"] * 100
    ).round(1)
    df["IMPROVED"] = df["CHANGE_PCT"] < 0

    st.dataframe(
        df[
            [
                "MACHINE_ID",
                "ORDER_TYPE",
                "COMPLETED_AT",
                "AVG_BEFORE",
                "AVG_AFTER",
                "CHANGE_PCT",
            ]
        ],
        use_container_width=True,
    )

    improved_count = df["IMPROVED"].sum()
    total = len(df)
    st.markdown(
        f"**Result:** {improved_count}/{total} maintenance events showed improvement. "
        f"{total - improved_count} showed no effect or degradation."
    )


TRAIL_TABLE = f"{DATABASE}.{SCHEMA}.AGENT_DECISION_TRAIL"


def render_decision_trail_panel():
    """Show the real agent decision trail and the UI action log."""
    session = get_session()

    st.subheader("Agent Decision Trail")
    st.caption("Real sense-reason-act steps from the autonomous agent's LLM loop")

    trail_df = session.sql(f"""
        SELECT SEQUENCE, PHASE, TOOL_NAME, STEP_STATUS, RESULT_SUMMARY,
               STEP_DURATION_MS, RUN_ID, RUN_STATUS, MODEL_ID, STARTED_AT,
               SUMMARY AS RUN_SUMMARY, RUN_DURATION_MS
        FROM {TRAIL_TABLE}
        WHERE RUN_STATUS = 'completed'
        ORDER BY SEQUENCE
    """).to_pandas()

    if trail_df.empty:
        st.info(
            "No agent trail exported yet. Run the agent and export: "
            "`python scripts/run_agent.py && python scripts/export_trail.py`"
        )
    else:
        run_summary = trail_df.iloc[0]["RUN_SUMMARY"]
        run_duration = trail_df.iloc[0]["RUN_DURATION_MS"]
        model_id = trail_df.iloc[0]["MODEL_ID"] or "unknown"

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Steps", len(trail_df))
        col2.metric(
            "Tool Calls", len(trail_df[trail_df["TOOL_NAME"].notna()])
        )
        col3.metric(
            "Failed Steps", len(trail_df[trail_df["STEP_STATUS"] == "failed"])
        )
        col4.metric(
            "Duration", f"{run_duration / 1000:.0f}s" if run_duration else "unknown"
        )

        st.markdown(f"**Model:** {model_id}")

        if run_summary:
            with st.expander("Agent Summary (LLM conclusion)", expanded=True):
                st.markdown(run_summary)

        st.dataframe(
            trail_df[["SEQUENCE", "PHASE", "TOOL_NAME", "STEP_STATUS", "RESULT_SUMMARY"]],
            use_container_width=True,
        )

    st.divider()
    with st.expander("Action Log (UI-triggered writes)", expanded=False):
        audit_df = session.sql(f"""
            SELECT TIMESTAMP, MACHINE_ID, ACTION_TYPE, SEVERITY, DESCRIPTION, INITIATED_BY
            FROM {AUDIT_TABLE}
            ORDER BY TIMESTAMP DESC
            LIMIT 50
        """).to_pandas()

        if audit_df.empty:
            st.info("No actions recorded yet.")
        else:
            st.dataframe(audit_df, use_container_width=True)


def render_insights_panel():
    """Show saved insights and shift note knowledge base."""
    session = get_session()

    st.subheader("Knowledge Base - Operator Insights")
    st.caption("Aggregated operator shift notes and patterns across the fleet")

    tab_notes, tab_patterns = st.tabs(["Recent Notes", "Pattern Summary"])

    with tab_notes:
        notes = session.sql(f"""
            SELECT MACHINE_ID, SHIFT_DATE, AUTHOR_ROLE, NOTE_TEXT
            FROM {SHIFT_NOTE_TABLE}
            ORDER BY SHIFT_DATE DESC
            LIMIT 30
        """).to_pandas()
        if not notes.empty:
            st.dataframe(notes, use_container_width=True)

    with tab_patterns:
        patterns = session.sql(f"""
            SELECT
                MACHINE_ID,
                COUNT(*) AS TOTAL_NOTES,
                COUNT(CASE WHEN NOTE_TEXT ILIKE '%drift%' OR NOTE_TEXT ILIKE '%slow%'
                           OR NOTE_TEXT ILIKE '%creep%' OR NOTE_TEXT ILIKE '%over standard%'
                      THEN 1 END) AS DRIFT_MENTIONS,
                COUNT(CASE WHEN NOTE_TEXT ILIKE '%fault%' OR NOTE_TEXT ILIKE '%trip%'
                           OR NOTE_TEXT ILIKE '%stop%'
                      THEN 1 END) AS FAULT_MENTIONS,
                COUNT(CASE WHEN NOTE_TEXT ILIKE '%maintenance%' OR NOTE_TEXT ILIKE '%repair%'
                           OR NOTE_TEXT ILIKE '%downtime%'
                      THEN 1 END) AS MAINTENANCE_MENTIONS
            FROM {SHIFT_NOTE_TABLE}
            GROUP BY MACHINE_ID
            ORDER BY DRIFT_MENTIONS DESC
        """).to_pandas()

        if not patterns.empty:
            st.dataframe(patterns, use_container_width=True)

            chart = (
                alt.Chart(
                    patterns.melt(
                        id_vars=["MACHINE_ID"],
                        value_vars=[
                            "DRIFT_MENTIONS",
                            "FAULT_MENTIONS",
                            "MAINTENANCE_MENTIONS",
                        ],
                        var_name="Category",
                        value_name="Count",
                    )
                )
                .mark_bar()
                .encode(
                    x="MACHINE_ID:N",
                    y="Count:Q",
                    color="Category:N",
                    tooltip=["MACHINE_ID", "Category", "Count"],
                )
                .properties(height=250, title="Issue Mentions by Machine")
            )
            st.altair_chart(chart, use_container_width=True)
