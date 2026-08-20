"""
Entry point for one autonomous agent run.

Triggers the headless sense-reason-act controller against the configured LLM
backend and data source, then prints the resulting decision trail. This is the
demo driver and the way to exercise a full run outside the scheduler.

Usage:
    python scripts/run_agent.py
    python scripts/run_agent.py --tools 5         # limit tool schema size
    python scripts/run_agent.py --max-iterations 12  # more reasoning turns
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Suppress noisy query-level errors from the connection pool during agent runs.
# The agent handles these gracefully; they just pollute the demo terminal.
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logging.getLogger("services.infrastructure.snowflake.session_pool").setLevel(logging.CRITICAL)
logging.getLogger("services.config.features.insights.tools").setLevel(logging.CRITICAL)
logging.getLogger("analysis").setLevel(logging.CRITICAL)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from analysis.shared.local_source import (  # noqa: E402
    LocalDataError,
    is_local_data_enabled,
    load_ground_truth,
)
from core.tools_config import get_tools_for_llm  # noqa: E402
from models.database import init_database  # noqa: E402
from models.decision_trail import TRIGGER_MANUAL  # noqa: E402
from services.infrastructure.observability.trace_llm import (  # noqa: E402
    get_traced_llm_client,
)
from services.workflow.controller import WorkflowController  # noqa: E402
from services.workflow.scoring import score_run  # noqa: E402
from services.workflow.trail_recorder import load_trail  # noqa: E402

SEPARATOR = "=" * 70
EXIT_OK = 0
EXIT_FAILED = 1


def _parse_args() -> argparse.Namespace:
    """Parse command line options."""
    parser = argparse.ArgumentParser(description="Run the autonomous agent once.")
    parser.add_argument(
        "--tools",
        type=int,
        default=0,
        help="Limit the tool schema to N tools. 0 means all, the default.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=8,
        help="Cap on reason-act turns. Defaults to 8.",
    )
    return parser.parse_args()


def _print_trail(run_id: str) -> None:
    """Print the persisted decision trail for a finished run."""
    trail = load_trail(run_id)
    if not trail:
        print("No trail was persisted.", flush=True)
        return

    print(SEPARATOR, flush=True)
    print(
        f"trail   : {trail['status']} in {trail['duration_ms']:.0f}ms "
        f"({trail['action_count']} actions)",
        flush=True,
    )
    print(f"backend : {trail['llm_backend']} / {trail['model_id']}", flush=True)
    for step in trail["steps"]:
        label = step["tool_name"] or "-"
        print(
            f"  {step['sequence']:>2}. {step['phase']:<6} {step['status']:<9} {label}",
            flush=True,
        )


def _print_score(run_id: str, summary: str) -> None:
    """Grade the run against ground truth, when a local dataset is configured."""
    if not is_local_data_enabled():
        print("score   : skipped (no LOCAL_DATA_DIR, so no ground truth)", flush=True)
        return

    try:
        ground_truth = load_ground_truth()
    except LocalDataError as exc:
        print(f"score   : unavailable ({exc})", flush=True)
        return

    trail = load_trail(run_id)
    report = score_run(ground_truth, summary, trail.get("steps", []))

    print(SEPARATOR, flush=True)
    print(
        f"score   : precision={report.precision:.2f} recall={report.recall:.2f} "
        f"f1={report.f1:.2f}",
        flush=True,
    )
    print(f"  found   : {report.true_positives or 'none'}", flush=True)
    print(f"  missed  : {report.false_negatives or 'none'}", flush=True)
    print(f"  false + : {report.false_positives or 'none'}", flush=True)
    print(f"  acted on: {report.investigated or 'none'}", flush=True)
    if report.claimed_only:
        # The narrative claimed work the trail has no record of.
        print(f"  UNBACKED CLAIMS: {report.claimed_only}", flush=True)


# Tools to exclude from demo runs: broken imports, missing tables, or local-only artifacts.
EXCLUDED_TOOLS = {
    "run_rca_analysis",
    "get_plant_health_snapshot",
    "generate_presentation",
    "create_chart",
}


async def _run(args: argparse.Namespace) -> int:
    """Execute one autonomous run and report the outcome."""
    init_database()
    client = get_traced_llm_client()

    full = get_tools_for_llm()
    filtered = [t for t in full if t["name"] not in EXCLUDED_TOOLS]

    tools_provider = None
    if args.tools:
        trimmed = filtered[: args.tools]
        print(f"tools   : limited to {len(trimmed)} of {len(full)}", flush=True)

        def tools_provider() -> list:
            """Return the trimmed tool schema."""
            return trimmed
    else:
        def tools_provider() -> list:
            """Return filtered tool schema (excluded broken tools)."""
            return filtered

    controller = WorkflowController(
        llm_client=client,
        max_iterations=args.max_iterations,
        tools_provider=tools_provider,
    )

    print(SEPARATOR, flush=True)
    print("running autonomous cycle...", flush=True)

    result = await controller.run(trigger=TRIGGER_MANUAL)

    print(SEPARATOR, flush=True)
    print(f"run_id  : {result['run_id']}", flush=True)
    print(f"status  : {result['status']}", flush=True)
    print(f"actions : {result['actions']}", flush=True)
    print(SEPARATOR, flush=True)
    print("SUMMARY:", flush=True)
    print(result["summary"], flush=True)

    _print_trail(result["run_id"])
    _print_score(result["run_id"], result["summary"])
    return EXIT_OK


def main() -> int:
    """Run the agent, converting any failure into a non-zero exit code."""
    try:
        return asyncio.run(_run(_parse_args()))
    except Exception as exc:  # noqa: BLE001 - top level entry point
        print(f"FAILED  : {exc}", flush=True)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
