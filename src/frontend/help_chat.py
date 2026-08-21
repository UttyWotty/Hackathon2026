"""Help-chat agent for the Manufacturing Workflow Agent dashboard.

Provides a sidebar chat interface grounded in app context that answers user
questions about the system using Snowflake Cortex Complete. No RAG or external
retrieval -- purely grounded in a static system prompt describing the app.
"""

import re

import streamlit as st
from frontend_constants import CORTEX_COMPLETE_MODEL
from help_prompt import HELP_SYSTEM_PROMPT
from session_helper import get_session

HELP_CHAT_SESSION_KEY = "help_chat_messages"
HELP_CHAT_MAX_HISTORY = 20
# Suggested questions offered when the transcript is empty, so the panel is not
# a bare input box on first view.
# Shown before the first question, in place of an empty panel.
ASK_GREETING = "How can I help you today?"

# Messages rendered in the panel; the full history still feeds the prompt.
ASK_PANEL_VISIBLE_MESSAGES = 8

MACHINE_ID_PATTERN = re.compile(r"M[XxLl]-?\d{4}", re.IGNORECASE)

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

        pareto = session.sql("""
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
            pareto["CONTRIBUTION_PCT"] = (pareto["TOTAL_DEV"] / total_dev * 100).round(
                1
            )
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
        f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{CORTEX_COMPLETE_MODEL}', '{escaped_prompt}') AS RESPONSE"
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

    st.session_state[HELP_CHAT_SESSION_KEY].append({"role": role, "content": content})

    if len(st.session_state[HELP_CHAT_SESSION_KEY]) > HELP_CHAT_MAX_HISTORY:
        st.session_state[HELP_CHAT_SESSION_KEY] = st.session_state[
            HELP_CHAT_SESSION_KEY
        ][-HELP_CHAT_MAX_HISTORY:]


def _render_message(role: str, content: str) -> None:
    """Render one chat message, preferring native chat bubbles when available.

    `st.chat_message` landed in Streamlit 1.24. The Streamlit-in-Snowflake
    runtime version is not pinned, so fall back to labelled markdown rather than
    risk an AttributeError taking down the sidebar.

    Args:
        role: Either "user" or "assistant".
        content: The message text.
    """
    if hasattr(st, "chat_message"):
        with st.chat_message(role):
            st.markdown(content)
        return
    label = "You" if role == "user" else "Help"
    st.markdown(f"**{label}:** {content}")


def _answer(question: str) -> None:
    """Record a question and its answer without forcing a rerun.

    The dialog and popover surfaces close when the script reruns, so this
    variant appends to history in place and lets the caller redraw.

    Args:
        question: The user's question, already stripped.
    """
    _append_message("user", question)
    with st.spinner("Thinking..."):
        response = _get_help_response(question)
    _append_message("assistant", response)


def render_agent_panel() -> None:
    """Render the agent chat panel wherever it is placed.

    Currently mounted in the left sidebar beneath the collapsed control
    sections, so a conversation of any length scrolls in its own column rather
    than growing the main page.

    History is drawn into a container reserved before the composer, so a new
    answer appears above the input on the same run it was requested.
    """
    history_box = st.container()

    pending = None
    typed = st.text_input(
        "Ask the agent",
        key="ask_panel_input",
        placeholder="Ask about a machine, a chart, or what to do next",
        label_visibility="collapsed",
    )
    col_send, col_clear = st.columns(2)
    with col_send:
        send = st.button(
            "Ask", key="ask_panel_send", type="primary", use_container_width=True
        )
    with col_clear:
        if st.button("Clear", key="ask_panel_clear", use_container_width=True):
            st.session_state[HELP_CHAT_SESSION_KEY] = []

    if send and typed.strip():
        pending = typed.strip()

    if pending:
        _answer(pending)

    history = st.session_state.get(HELP_CHAT_SESSION_KEY, [])
    with history_box:
        if not history:
            st.markdown(ASK_GREETING)
        else:
            hidden = max(0, len(history) - ASK_PANEL_VISIBLE_MESSAGES)
            if hidden:
                st.caption(f"{hidden} earlier message(s) hidden.")
            for msg in history[-ASK_PANEL_VISIBLE_MESSAGES:]:
                _render_message(msg["role"], msg["content"])
