"""
Streamlit entry point for the autonomous agent demo.

Lays out three tabs - trigger a live run, inspect any run's decision trail, and
see the drift the agent is meant to catch - and holds the selected run in
session state. Contains layout only; work is delegated to runner and views.

Run with:
    LOCAL_DATA_DIR=./synthetic_out streamlit run demo/app.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load .env BEFORE any project imports so module-level os.getenv() calls see values.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env", override=True)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from demo import runner, views  # noqa: E402
from demo.presenters import run_label  # noqa: E402
from demo.story import weekly_deviation  # noqa: E402

PAGE_TITLE = "Autonomous Manufacturing Workflow Agent"
LAYOUT_WIDE = "wide"

TAB_RUN = "Run the agent"
TAB_TRAIL = "Decision trail"
TAB_STORY = "What it has to catch"

# Key under which the run being inspected is held between reruns. Streamlit
# re-executes this script on every interaction, so nothing survives without it.
STATE_RUN_ID = "selected_run_id"

SHOT_CACHE_TTL_SECONDS = 600

SPINNER_TEXT = "Sensing, reasoning, acting. A full cycle takes a minute or two."


@st.cache_data(ttl=SHOT_CACHE_TTL_SECONDS)
def _load_weekly_deviation() -> pd.DataFrame:
    """Load and aggregate the shot table, cached so tab switches are cheap."""
    return weekly_deviation(runner.read_shots())


def _render_run_tab() -> None:
    """Draw the trigger button and the outcome of the most recent run."""
    st.write(
        "The agent runs headless: no prompt, no chat turn. It sweeps the fleet "
        "for anomalies, reasons over what it found, chains tool calls to "
        "investigate and report, and writes every step to a decision trail."
    )
    if st.button("Trigger an autonomous run", type="primary"):
        with st.spinner(SPINNER_TEXT):
            try:
                result = runner.trigger_run()
            except runner.DemoRunnerError as exc:
                st.error(str(exc))
                return
        st.session_state[STATE_RUN_ID] = result["run_id"]
        st.success(f"Run {result['run_id']} finished with status {result['status']}.")

    run_id = st.session_state.get(STATE_RUN_ID)
    if not run_id:
        st.info("No run selected yet. Trigger one, or pick a past run below.")
        return

    trail = runner.read_trail(run_id)
    if not trail:
        st.warning("That run has no persisted trail.")
        return
    views.render_summary(trail)
    st.divider()
    st.subheader("Graded against the planted defects")
    views.render_score(runner.grade(trail))


def _render_trail_tab() -> None:
    """Draw the run picker and the full trail for the selected run."""
    history = runner.read_history()
    if not history:
        st.info("No runs recorded yet.")
        return

    labels = {run_label(run): run["run_id"] for run in history}
    current = st.session_state.get(STATE_RUN_ID)
    options = list(labels)
    index = next(
        (position for position, key in enumerate(options) if labels[key] == current),
        0,
    )
    chosen = st.selectbox("Run", options, index=index)
    st.session_state[STATE_RUN_ID] = labels[chosen]

    trail = runner.read_trail(labels[chosen])
    if not trail:
        st.warning("That run has no persisted trail.")
        return
    views.render_summary(trail)
    st.divider()
    views.render_trail(trail)


def _render_story_tab() -> None:
    """Draw the drift chart that motivates the whole run."""
    st.write(
        "Every defect in this dataset is planted deliberately and declared in "
        "ground_truth.json, so the agent is scored against a contract rather "
        "than a recollection."
    )
    config = runner.read_config()
    try:
        weekly = _load_weekly_deviation()
    except runner.DemoRunnerError as exc:
        st.info(str(exc))
        return
    views.render_drift_chart(weekly, config.headline_equipment)


def main() -> None:
    """Configure the page and draw the three tabs."""
    st.set_page_config(page_title=PAGE_TITLE, layout=LAYOUT_WIDE)
    st.title(PAGE_TITLE)
    views.render_config(runner.read_config())
    st.divider()

    run_tab, trail_tab, story_tab = st.tabs([TAB_RUN, TAB_TRAIL, TAB_STORY])
    with run_tab:
        _render_run_tab()
    with trail_tab:
        _render_trail_tab()
    with story_tab:
        _render_story_tab()


main()
