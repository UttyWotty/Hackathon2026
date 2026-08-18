"""Prints a decision trail, and grades it against ground truth when one is available.

The trail is the record of what an agent actually did; the summary it wrote is only a claim.
This prints both and, offline, scores the decision against the dataset's planted defects so
the run is judged on a contract rather than on how confident it sounded.

Usage:
    python scripts/show_trail.py                # most recent run
    python scripts/show_trail.py <run_id>       # a specific run
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.shared.local_source import (  # noqa: E402
    LocalDataError,
    is_local_data_enabled,
    load_ground_truth,
)
from models.database import get_session, init_database  # noqa: E402
from models.decision_trail import DecisionRun  # noqa: E402
from services.workflow.scoring import score_run  # noqa: E402
from services.workflow.trail_recorder import load_trail  # noqa: E402

EXIT_OK = 0
EXIT_FAILED = 1
SEPARATOR = "-" * 68


def _latest_run_id() -> str:
    """Return the most recently started run, or an empty string if there are none."""
    with get_session() as session:
        run = session.query(DecisionRun).order_by(DecisionRun.id.desc()).first()
        return run.run_id if run else ""


def _print_trail(trail: dict) -> None:
    """Render the run header and its ordered steps."""
    print(SEPARATOR, flush=True)
    print(f"run_id  : {trail['run_id']}", flush=True)
    print(f"status  : {trail['status']}", flush=True)
    print(f"backend : {trail['llm_backend']} / {trail['model_id']}", flush=True)
    print(f"actions : {trail['action_count']}", flush=True)
    print(SEPARATOR, flush=True)
    for step in trail["steps"]:
        label = step["tool_name"] or "-"
        print(f"  {step['sequence']:>2}. {step['phase']:<6} {label}", flush=True)
    print(SEPARATOR, flush=True)
    print(trail.get("summary") or "(no summary recorded)", flush=True)


def _print_score(trail: dict) -> None:
    """Grade the decision against ground truth, when a local dataset is configured."""
    if not is_local_data_enabled():
        print("", flush=True)
        print("score   : skipped (no LOCAL_DATA_DIR, so no ground truth)", flush=True)
        return

    try:
        ground_truth = load_ground_truth()
    except LocalDataError as exc:
        print(f"score   : unavailable ({exc})", flush=True)
        return

    report = score_run(ground_truth, trail.get("summary") or "", trail["steps"])
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
        print("", flush=True)
        print(
            f"  UNBACKED CLAIMS: {report.claimed_only} - named in the summary but absent "
            "from the recorded actions.",
            flush=True,
        )


def main() -> int:
    """Print one decision trail and its score."""
    try:
        init_database()
        run_id = sys.argv[1] if len(sys.argv) > 1 else _latest_run_id()
        if not run_id:
            print("No decision runs recorded yet.", flush=True)
            return EXIT_FAILED

        trail = load_trail(run_id)
        if not trail:
            print(f"No trail found for run {run_id}.", flush=True)
            return EXIT_FAILED

        _print_trail(trail)
        _print_score(trail)
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001 - top level entry point
        print(f"SHOW TRAIL FAILED: {exc}", flush=True)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
