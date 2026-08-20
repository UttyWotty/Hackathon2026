"""Help-chat agent for the Manufacturing Workflow Agent dashboard.

Provides a sidebar chat interface grounded in app context that answers user
questions about the system using Snowflake Cortex Complete. No RAG or external
retrieval -- purely grounded in a static system prompt describing the app.
"""

import re

import streamlit as st
from session_helper import get_session

HELP_CHAT_MODEL = "mistral-large2"
HELP_CHAT_SESSION_KEY = "help_chat_messages"
HELP_CHAT_MAX_HISTORY = 20
MACHINE_ID_PATTERN = re.compile(r"M[XxLl]-?\d{4}", re.IGNORECASE)

HELP_SYSTEM_PROMPT = """You are a help assistant embedded in the Autonomous Manufacturing Workflow Agent dashboard.
Your role is to answer user questions about what this system does, how it works, and what they are looking at.

== SYSTEM OVERVIEW ==
This is a Streamlit dashboard for an autonomous manufacturing workflow agent. The agent monitors
an injection moulding fleet (8 base machines: MX-7101 through MX-7108) and autonomously detects
anomalies, investigates root causes, and takes corrective action without human intervention.
Additional machines (e.g. MX-9201) may appear if new telemetry has been ingested via CSV upload.

== AGENT ARCHITECTURE (Sense-Reason-Act) ==
1. SENSE: Multi-signal fleet sweep detects duration deviation from target, week-over-week
   stability decline, efficiency degradation, and tooling wear (shot accumulation).
2. REASON: Snowflake Cortex LLM performs cross-signal correlation, prioritizes by severity,
   and decides which equipment to investigate.
3. ACT: Investigates temporal root cause breakdown, corroborates with operator shift notes,
   logs work orders, sends alerts, and updates equipment status.
4. RECORD: Full decision trail written to AUDIT_LOG with evidence and severity.

== SKILLS (CoCo CLI Skills) ==
- $sense-equipment-anomalies: Sweeps the fleet for duration drift and stability decline.
- $investigate-shift-notes: Searches operator notes to explain WHY a machine is abnormal.
- $report-and-act: Records decision, evidence, and actions to the audit trail.

== DATA MODEL (all in DEMO.PUBLIC) ==
- SHOT_DATA: Core production table (243K rows). Columns: MACHINE_ID, DURATION,
  TARGET_DURATION, SHOT_TIME, VOLUME, VENDOR_NAME, SENSOR_CODE, PRODUCT_NAME, TOOL_ID.
- TOOL: Tooling master data (tool IDs, types, specifications).
- VENDOR: Vendor/supplier information.
- PRODUCT: Product catalog (product names and types).
- LOCATION: Plant location data.
- SHIFT_NOTE: Operator-authored free-text shift notes per machine per day.
- WORK_ORDER: Maintenance work orders.
- AUDIT_LOG: Every autonomous action the agent takes is logged here.

== DASHBOARD TABS ==
- Drift Detection: Shows fleet-wide duration deviation over time. Highlights MX-7103 which
  drifts from 2% to 24% while stability stays at 90% (the "invisible anomaly").
- Pareto: Deviation contribution by machine (Pareto chart with cumulative line), plus a
  dimensional drill-down section that breaks down a selected machine's deviation by time
  trend, hour of day, day of week, shift, and product.
- 5 Whys: An AI-driven root cause analysis. User selects a machine and clicks "Run 5 Whys".
  Cortex AI then generates a literal 5 Whys causal chain, where each "Why" digs deeper
  into the previous answer, drilling from the observed symptom down to the root cause.
  It uses actual production data (deviation, shift patterns, product patterns) to ground
  its reasoning.
- Efficiency: Shows each tool's actual cycle duration efficiency against its target time.
  It does NOT benchmark operators or shifts against each other.
- Tooling Life: Shows shot accumulation and usage rates for injection mould tooling.
  It tracks how heavily each tool is being used, NOT a predictive end-of-life forecast.
- Maintenance: Work order history and maintenance impact analysis. Shows correlation
  between maintenance events and production metrics.
- Decision Trail: Full audit log of autonomous agent decisions with evidence and severity.
- Insights: Forecasting, savings opportunities, and health scores.
- Stability: Week-over-week stability score trends per machine.
- Fleet Overview: Summary health table for all 8 machines.

== SIDEBAR CONTROLS ==
- Anomaly Sweep: Triggers an on-demand fleet sweep for anomalies.
- RCA Selector: Pick a machine and run root cause analysis.
- CSV Upload: Ingest new telemetry data into SHOT_DATA.

== KEY INSIGHT ==
The headline finding is that MX-7103 exhibits gradual duration drift (2% to 24% over 6 weeks)
while maintaining high stability (~90%). No single-metric threshold alert would catch this.
The agent detects it by reasoning across deviation AND stability together.

== METRIC DEFINITIONS ==
- Duration: Time in seconds for one injection moulding cycle (one "shot").
- Target Duration: The approved/expected cycle time for that machine.
- Deviation %: ((Avg Duration - Target Duration) / Target Duration) * 100.
  Positive = slower than target. Negative = faster.
- Stability Score: 100% - Coefficient of Variation. Formula: 100 - (StdDev(Duration) / Mean(Duration) * 100).
  High stability (>95%) means consistent cycle times. Low stability means erratic performance.
- Efficiency %: (Target Duration / Actual Duration) * 100. 100% = perfect. Below 100% = slower than target.
- Pareto Contribution: Each machine's share of the total absolute deviation across the fleet.
  Ranked highest-contributor first.

== RULES FOR YOUR RESPONSES ==
- Only answer questions about this system, its data, its architecture, or how to use it.
- If the user asks something you do not have information about, say "I don't have that
  information in my context" rather than guessing or making things up.
- Be CONCISE: max 3-4 bullet points per answer. Lead with the most important finding first.
  Do not list every tab -- only mention what is directly relevant to the question.
- Do not invent data values, table contents, or analysis results.
- When LIVE DATA is provided below the user's question, use it to give a specific,
  data-driven summary. Cite the actual numbers. Do not redirect to tabs when you
  already have the data in context.
- If no live data is provided and the user asks about specific values, redirect them
  to the appropriate dashboard tab.
- BE HONEST: If you only have partial data, say so. For example: "I can see the overall
  metrics and weekly trend, but for the full visual chart check the Drift Detection tab."
  Never pretend to summarize something you do not have data for.
- NEVER mention internal database table names (SHOT_DATA, TOOL, VENDOR, AUDIT_LOG, etc.)
  to the user. Instead, describe information in terms of what they can see on the dashboard
  tabs and controls. The user interacts with the UI, not the database directly.
- When discussing tooling, refer to the "Tooling Life" tab. When discussing audit history,
  refer to the "Decision Trail" tab or "Audit Trail" section. Keep answers UI-focused.
- TERMINOLOGY: MX-xxxx identifiers (e.g. MX-7103) are MACHINES (equipment), not tools.
  Tools are the injection moulds that go into machines. If the user says "tool MX-7103",
  gently clarify that MX-7103 is a machine, not a tool.
- When asked about MX-7103 specifically, always lead with its special status: it is the
  headline anomaly machine that exhibits the "invisible drift" pattern (gradual deviation
  increase while stability stays high).

== FEW-SHOT EXAMPLES ==

User: What does the Drift Detection tab show?
Assistant: The Drift Detection tab shows how each machine's cycle duration deviates from its target over time. The key finding is MX-7103, which drifts from 2% to 24% over 6 weeks while stability stays at ~90% -- the "invisible anomaly" that single-metric alerts miss.

User: Tell me about MX-7103
Assistant: MX-7103 is the headline anomaly in this fleet. It exhibits gradual duration drift (2% to 24% over 6 weeks) while maintaining high stability (~90%). This makes it invisible to simple threshold alerts. The agent catches it by correlating deviation AND stability together. Check the Drift Detection tab for the full visual, or run a 5 Whys analysis to drill into root cause.

User: What is the 5 Whys tab?
Assistant: The 5 Whys tab runs an AI-driven root cause analysis. You select a machine, click "Run 5 Whys", and Cortex AI generates a literal causal chain -- each "Why" digs deeper into the previous answer, drilling from the observed symptom down to the root cause using actual production data.

User: What can you tell me about tool 4100?
Assistant: Tool 4100 is an injection mould (note: MX-xxxx are machines, while tools are the moulds that go into them). You can check its usage and shot accumulation on the Tooling Life tab.
"""


def _fetch_machine_summary(machine_id: str) -> str:
    """Fetch live summary data for a machine from Snowflake.

    Args:
        machine_id: The machine identifier (e.g. MX-7103).

    Returns:
        A formatted string of machine metrics, or empty string if no data.
    """
    session = get_session()
    mid = machine_id.upper()
    try:
        row = session.sql(f"""
            SELECT
                COUNT(*) AS TOTAL_SHOTS,
                ROUND(AVG(DURATION), 2) AS AVG_DURATION,
                ROUND(AVG(TARGET_DURATION), 2) AS AVG_TARGET,
                ROUND(((AVG(DURATION) - AVG(TARGET_DURATION))
                    / NULLIF(AVG(TARGET_DURATION), 0)) * 100, 2) AS DEVIATION_PCT,
                ROUND(100.0 - (STDDEV(DURATION)
                    / NULLIF(AVG(DURATION), 0) * 100), 1) AS STABILITY_SCORE,
                MIN(SHOT_TIME) AS FIRST_SHOT,
                MAX(SHOT_TIME) AS LAST_SHOT
            FROM DEMO.PUBLIC.SHOT_DATA
            WHERE MACHINE_ID = '{mid}'
                AND DURATION < 999.9 AND VOLUME > 0 AND TARGET_DURATION > 0
        """).to_pandas()

        if row.empty or row.iloc[0]["TOTAL_SHOTS"] == 0:
            return ""

        r = row.iloc[0]
        parts = [
            f"\n[LIVE DATA for {mid}]",
            f"Total shots: {int(r['TOTAL_SHOTS']):,}",
            f"Avg duration: {r['AVG_DURATION']}s (target: {r['AVG_TARGET']}s)",
            f"Deviation from target: {r['DEVIATION_PCT']}%",
            f"Stability score: {r['STABILITY_SCORE']}%",
            f"Data range: {r['FIRST_SHOT']} to {r['LAST_SHOT']}",
        ]

        weekly = session.sql(f"""
            SELECT
                DATE_TRUNC('WEEK', SHOT_TIME) AS WEEK,
                ROUND(((AVG(DURATION) - AVG(TARGET_DURATION))
                    / NULLIF(AVG(TARGET_DURATION), 0)) * 100, 2) AS DEVIATION_PCT,
                COUNT(*) AS SHOTS
            FROM DEMO.PUBLIC.SHOT_DATA
            WHERE MACHINE_ID = '{mid}'
                AND DURATION < 999.9 AND VOLUME > 0 AND TARGET_DURATION > 0
            GROUP BY 1 ORDER BY 1
        """).to_pandas()

        if not weekly.empty:
            parts.append("\nWeekly drift trend:")
            for _, w in weekly.iterrows():
                parts.append(
                    f"  {str(w['WEEK'])[:10]}: {w['DEVIATION_PCT']}% "
                    f"({int(w['SHOTS'])} shots)"
                )

        pareto = session.sql(f"""
            SELECT
                MACHINE_ID,
                SUM(ABS(DURATION - TARGET_DURATION)) AS TOTAL_DEV
            FROM DEMO.PUBLIC.SHOT_DATA
            WHERE DURATION < 999.9 AND VOLUME > 0 AND TARGET_DURATION > 0
            GROUP BY MACHINE_ID
            ORDER BY TOTAL_DEV DESC
        """).to_pandas()

        if not pareto.empty:
            total_dev = pareto["TOTAL_DEV"].sum()
            pareto["CONTRIBUTION_PCT"] = (
                pareto["TOTAL_DEV"] / total_dev * 100
            ).round(1)
            rank_row = pareto[pareto["MACHINE_ID"] == mid]
            if not rank_row.empty:
                rank_idx = rank_row.index[0] + 1
                contrib = rank_row.iloc[0]["CONTRIBUTION_PCT"]
                parts.append(
                    f"\nPareto ranking: #{rank_idx} of {len(pareto)} machines "
                    f"({contrib}% of total fleet deviation)"
                )

        return "\n".join(parts) + "\n"
    except Exception:
        return "\n[LIVE DATA: unavailable due to a query error]\n"


def _normalize_machine_id(raw: str) -> str:
    """Normalize a fuzzy machine ID match to canonical MX-NNNN format."""
    digits = re.search(r"\d{4}", raw)
    if digits:
        return f"MX-{digits.group()}"
    return raw.upper()


def _extract_machine_ids(text: str) -> set:
    """Extract and normalize all machine IDs from text."""
    matches = MACHINE_ID_PATTERN.findall(text)
    return {_normalize_machine_id(m) for m in matches}


def _build_prompt_with_history(user_message: str) -> str:
    """Build a single prompt string combining system context, history, and new message.

    Args:
        user_message: The latest user question.

    Returns:
        A formatted prompt string for Cortex Complete.
    """
    messages = st.session_state.get(HELP_CHAT_SESSION_KEY, [])
    parts = [HELP_SYSTEM_PROMPT, ""]

    for msg in messages:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        parts.append(f"{role_label}: {msg['content']}")

    parts.append(f"User: {user_message}")

    # Extract machine IDs from current message
    machine_ids = _extract_machine_ids(user_message)

    # If no machine ID in current message, check recent history for context
    if not machine_ids:
        for msg in reversed(messages[-4:]):
            machine_ids = _extract_machine_ids(msg["content"])
            if machine_ids:
                break

    for mid in machine_ids:
        live_data = _fetch_machine_summary(mid)
        if live_data:
            parts.append(live_data)

    parts.append("Assistant:")
    return "\n".join(parts)


def _get_help_response(user_message: str) -> str:
    """Call Cortex Complete via SQL and return the response.

    Uses SNOWFLAKE.CORTEX.COMPLETE() through Snowpark SQL, which works
    without the snowflake-ml-python package.

    Args:
        user_message: The user's question.

    Returns:
        The LLM's text response.
    """
    prompt = _build_prompt_with_history(user_message)
    session = get_session()
    escaped_prompt = prompt.replace("\\", "\\\\").replace("'", "\\'")
    result = session.sql(
        f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{HELP_CHAT_MODEL}', '{escaped_prompt}') AS RESPONSE"
    ).collect()
    if result and len(result) > 0:
        return str(result[0]["RESPONSE"]).strip()
    return "I was unable to generate a response. Please try again."


def _append_message(role: str, content: str) -> None:
    """Append a message to session chat history, enforcing max length.

    Args:
        role: Either "user" or "assistant".
        content: The message text.
    """
    if HELP_CHAT_SESSION_KEY not in st.session_state:
        st.session_state[HELP_CHAT_SESSION_KEY] = []

    st.session_state[HELP_CHAT_SESSION_KEY].append(
        {"role": role, "content": content}
    )

    if len(st.session_state[HELP_CHAT_SESSION_KEY]) > HELP_CHAT_MAX_HISTORY:
        st.session_state[HELP_CHAT_SESSION_KEY] = (
            st.session_state[HELP_CHAT_SESSION_KEY][-HELP_CHAT_MAX_HISTORY:]
        )


def render_help_chat() -> None:
    """Render the help-chat interface in the Streamlit sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("Help Chat")
    st.sidebar.caption("Ask questions about this system")

    if HELP_CHAT_SESSION_KEY not in st.session_state:
        st.session_state[HELP_CHAT_SESSION_KEY] = []

    with st.sidebar.container():
        for msg in st.session_state[HELP_CHAT_SESSION_KEY]:
            if msg["role"] == "user":
                st.markdown(f"**You:** {msg['content']}")
            else:
                st.markdown(f"**Help:** {msg['content']}")

        if not st.session_state[HELP_CHAT_SESSION_KEY]:
            st.caption("No messages yet. Type a question below.")

    user_input = st.sidebar.text_input(
        "Your question",
        key="help_chat_input",
        placeholder="e.g. What does the Drift tab show?",
        label_visibility="collapsed",
    )

    if st.sidebar.button("Ask", key="help_chat_send", use_container_width=True):
        if user_input and user_input.strip():
            _append_message("user", user_input.strip())
            with st.spinner("Thinking..."):
                response = _get_help_response(user_input.strip())
            _append_message("assistant", response)
            st.experimental_rerun()
