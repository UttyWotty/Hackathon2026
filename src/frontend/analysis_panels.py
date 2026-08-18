"""Analysis visualization panels for the Streamlit dashboard.

Provides SQL-driven Pareto, 5 Whys, efficiency, tooling EOL, maintenance impact,
decision trail, and insights panels that render directly from Snowflake queries.
"""

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session

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
    session = get_active_session()

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


def render_five_whys_panel():
    """5 Whys temporal breakdown for a selected machine."""
    session = get_active_session()

    st.subheader("5 Whys - Temporal Root Cause Drill-Down")
    st.caption("Drill through 5 layers of WHY to isolate the root cause")

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

    # Why 1: Time trend
    st.markdown(f"**Why 1: Is there a {granularity.lower()} trend?**")
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

    # Why 2: Hour of day
    with col1:
        st.markdown("**Why 2: Which hours of day are worst?**")
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

    # Why 3: Day of week
    with col2:
        st.markdown("**Why 3: Is there a day-of-week pattern?**")
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

    # Why 4: By shift (morning/afternoon/night)
    with col3:
        st.markdown("**Why 4: Which shift is responsible?**")
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

    # Why 5: By product
    with col4:
        st.markdown("**Why 5: Is a specific product causing it?**")
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


def render_efficiency_panel():
    """Fleet efficiency: TARGET_DURATION / DURATION ratio per machine."""
    session = get_active_session()

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
    session = get_active_session()

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
    session = get_active_session()

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


def render_decision_trail_panel():
    """Show the full audit trail of agent decisions and actions."""
    session = get_active_session()

    st.subheader("Decision Trail")
    st.caption("Complete audit log of all autonomous agent actions")

    df = session.sql(f"""
        SELECT TIMESTAMP, MACHINE_ID, ACTION_TYPE, SEVERITY, DESCRIPTION, INITIATED_BY
        FROM {AUDIT_TABLE}
        ORDER BY TIMESTAMP DESC
        LIMIT 50
    """).to_pandas()

    if df.empty:
        st.info("No decisions recorded yet. Run a sweep to trigger autonomous actions.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Actions", len(df))
    col2.metric("Work Orders", len(df[df["ACTION_TYPE"] == "WORK_ORDER"]))
    col3.metric("Alerts Sent", len(df[df["ACTION_TYPE"] == "ALERT"]))

    st.dataframe(df, use_container_width=True)


def render_insights_panel():
    """Show saved insights and shift note knowledge base."""
    session = get_active_session()

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
