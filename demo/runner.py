"""
I/O adapter between the Streamlit demo and the autonomous agent.

Triggers a controller run from synchronous Streamlit code, reads decision
trails and past runs back, and grades a finished run against the generator's
ground truth. All database, network and filesystem access for the demo lives
here; presenters.py and story.py stay pure.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from analysis.shared.local_source import (
    LOCAL_DATA_DIR,
    LocalDataError,
    is_local_data_enabled,
    load_ground_truth,
    load_master_shot_table,
)
from core.llm_backend import LLM_BACKEND
from models.database import init_database
from models.decision_trail import TRIGGER_MANUAL
from services.infrastructure.observability.trace_llm import get_traced_llm_client
from services.workflow.controller import WorkflowController
from services.workflow.scoring import score_run
from services.workflow.trail_recorder import list_runs, load_trail

logger = logging.getLogger(__name__)

# Cap on reason-act turns for a demo run. Matches the controller default; named
# here so the UI can state the bound it is running under.
DEMO_MAX_ITERATIONS = 8

DATA_SOURCE_SNOWFLAKE = "Snowflake"
DATA_SOURCE_LOCAL = "local CSVs"

KEY_HEADLINE = "headline_equipment"
KEY_RUN_ID = "run_id"
KEY_SUMMARY = "summary"
KEY_STATUS = "status"
KEY_ACTIONS = "actions"
KEY_STEPS = "steps"


class DemoRunnerError(Exception):
    """Raised when a demo action cannot be completed."""


@dataclass(frozen=True)
class DemoConfig:
    """What the demo is pointed at, shown so a run is never ambiguous."""

    llm_backend: str
    data_source: str
    data_dir: str
    max_iterations: int
    ground_truth_available: bool
    headline_equipment: Optional[str]


def read_config() -> DemoConfig:
    """
    Describe the environment this demo will run against.

    Returns:
        The configured backend, data source and headline machine. Ground truth
        is reported as unavailable rather than raising when absent, since a
        Snowflake-backed run legitimately has none.
    """
    local = is_local_data_enabled()
    headline: Optional[str] = None
    available = False
    if local:
        try:
            headline = load_ground_truth().get(KEY_HEADLINE)
            available = True
        except LocalDataError as exc:
            logger.warning("Ground truth unavailable: %s", exc)
    return DemoConfig(
        llm_backend=LLM_BACKEND,
        data_source=DATA_SOURCE_LOCAL if local else DATA_SOURCE_SNOWFLAKE,
        data_dir=LOCAL_DATA_DIR,
        max_iterations=DEMO_MAX_ITERATIONS,
        ground_truth_available=available,
        headline_equipment=headline,
    )


def trigger_run() -> Dict[str, Any]:
    """
    Execute one full autonomous cycle and return its outcome.

    Blocks until the agent finishes. Streamlit runs the script synchronously,
    so the controller's event loop is created and torn down here.

    Returns:
        The controller result: run_id, status, actions and summary.

    Raises:
        DemoRunnerError: If the run could not be started or completed.
    """
    try:
        init_database()
        client = get_traced_llm_client()
        controller = WorkflowController(
            llm_client=client, max_iterations=DEMO_MAX_ITERATIONS
        )
        return asyncio.run(controller.run(trigger=TRIGGER_MANUAL))
    except Exception as exc:
        raise DemoRunnerError(f"Autonomous run failed: {exc}") from exc


def read_history() -> List[Dict[str, Any]]:
    """
    List past runs for the history picker, newest first.

    Returns:
        Serialised runs, or an empty list before the database exists.
    """
    try:
        init_database()
        return list_runs()
    except Exception as exc:
        logger.warning("Could not read run history: %s", exc)
        return []


def read_trail(run_id: str) -> Dict[str, Any]:
    """
    Load one run's full decision trail.

    Args:
        run_id: The run to load.

    Returns:
        The run with its steps, or an empty dict when the run is unknown.
    """
    return load_trail(run_id)


def grade(trail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Score a finished run against the generator's ground truth.

    Args:
        trail: A trail as returned by read_trail.

    Returns:
        The serialised ScoreReport, or None when no ground truth is configured.
        Grading a Snowflake-backed run is not possible and is not an error.
    """
    if not is_local_data_enabled():
        return None
    try:
        ground_truth = load_ground_truth()
    except LocalDataError as exc:
        logger.warning("Cannot grade run: %s", exc)
        return None
    report = score_run(
        ground_truth, trail.get(KEY_SUMMARY) or "", trail.get(KEY_STEPS, [])
    )
    return report.to_dict()


def read_shots() -> pd.DataFrame:
    """
    Load the shot table backing the drift chart.

    Returns:
        Raw MASTER_SHOT_TABLE rows.

    Raises:
        DemoRunnerError: If no local dataset is configured or it cannot be read.
    """
    if not is_local_data_enabled():
        raise DemoRunnerError(
            "The drift chart reads the generated dataset. Set LOCAL_DATA_DIR "
            "to the generator's output directory."
        )
    try:
        return load_master_shot_table()
    except LocalDataError as exc:
        raise DemoRunnerError(str(exc)) from exc


__all__ = [
    "DemoConfig",
    "DemoRunnerError",
    "read_config",
    "trigger_run",
    "read_history",
    "read_trail",
    "grade",
    "read_shots",
]
