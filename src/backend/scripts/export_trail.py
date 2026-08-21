"""Export the latest agent decision trail from SQLite to Snowflake.

Reads the newest completed run via trail_recorder, flattens it to one row per
step (denormalized with run context), and writes it to DEMO.PUBLIC.AGENT_DECISION_TRAIL
using write_pandas. Run this after run_agent.py to make the trail visible in the dashboard.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from models.database import init_database  # noqa: E402
from services.workflow.trail_recorder import list_runs, load_trail  # noqa: E402
from synthetic_data.constants import TABLE_AGENT_DECISION_TRAIL  # noqa: E402
from synthetic_data.ddl import create_table_statement  # noqa: E402

TARGET_TABLE = TABLE_AGENT_DECISION_TRAIL
TARGET_DATABASE = "DEMO"
TARGET_SCHEMA = "PUBLIC"


def _parse_args() -> argparse.Namespace:
    """Parse command line options."""
    parser = argparse.ArgumentParser(description="Export agent trail to Snowflake.")
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Specific run_id to export. Defaults to the most recent run.",
    )
    return parser.parse_args()


def _get_snowpark_session():
    """Create a Snowpark session for writing to Snowflake."""
    import os

    from snowflake.snowpark import Session

    connection_params = {
        "account": os.environ.get("SNOWFLAKE_ACCOUNT", ""),
        "user": os.environ.get("SNOWFLAKE_USER", ""),
        "password": os.environ.get("SNOWFLAKE_PASSWORD", ""),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        "database": TARGET_DATABASE,
        "schema": TARGET_SCHEMA,
    }
    return Session.builder.configs(connection_params).create()


def _flatten_trail(trail: dict) -> pd.DataFrame:
    """Flatten a trail dict into a DataFrame with one row per step."""
    rows = []
    for step in trail.get("steps", []):
        rows.append(
            {
                "RUN_ID": trail["run_id"],
                "RUN_TRIGGER": trail.get("trigger", ""),
                "RUN_STATUS": trail.get("status", ""),
                "LLM_BACKEND": trail.get("llm_backend", ""),
                "MODEL_ID": trail.get("model_id", ""),
                "STARTED_AT": trail.get("started_at"),
                "COMPLETED_AT": trail.get("completed_at"),
                "RUN_DURATION_MS": trail.get("duration_ms"),
                "SUMMARY": trail.get("summary", ""),
                "SEQUENCE": step["sequence"],
                "PHASE": step["phase"],
                "TOOL_NAME": step.get("tool_name"),
                "STEP_STATUS": step["status"],
                "RESULT_SUMMARY": step.get("result_summary", ""),
                "STEP_DURATION_MS": step.get("duration_ms"),
                "STEP_CREATED_AT": step.get("created_at"),
                "PAYLOAD": (
                    json.dumps(step.get("payload")) if step.get("payload") else None
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    """Export the trail to Snowflake."""
    args = _parse_args()
    init_database()

    if args.run_id:
        run_id = args.run_id
    else:
        runs = list_runs(limit=10)
        completed = [r for r in runs if r.get("status") == "completed"]
        if not completed:
            print("No completed runs found in the decision trail database.", flush=True)
            return 1
        run_id = completed[0]["run_id"]

    trail = load_trail(run_id)
    if not trail:
        print(f"Run {run_id} not found.", flush=True)
        return 1

    df = _flatten_trail(trail)
    if df.empty:
        print(f"Run {run_id} has no steps to export.", flush=True)
        return 1

    print(f"Exporting run {run_id}: {len(df)} steps", flush=True)

    session = _get_snowpark_session()
    # Create before truncating: on a freshly rebuilt account the table does not exist yet,
    # and TRUNCATE on a missing table aborts the export.
    session.sql(
        create_table_statement(TARGET_DATABASE, TARGET_SCHEMA, TARGET_TABLE)
    ).collect()
    session.sql(
        f"TRUNCATE TABLE {TARGET_DATABASE}.{TARGET_SCHEMA}.{TARGET_TABLE}"
    ).collect()
    session.write_pandas(
        df,
        table_name=TARGET_TABLE,
        database=TARGET_DATABASE,
        schema=TARGET_SCHEMA,
        auto_create_table=False,
        overwrite=False,
    )
    print(f"Exported to {TARGET_DATABASE}.{TARGET_SCHEMA}.{TARGET_TABLE}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
