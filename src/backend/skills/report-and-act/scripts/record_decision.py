"""Records an agent's conclusion and the actions it took to the decision trail.

This is a recorder, not a reasoner. The calling agent decides what is wrong and what to do;
this persists that decision with its supporting evidence so the run can be audited later.
Every action recorded here is one the agent asserts it performed.

Usage:
    python scripts/record_decision.py \\
        --equipment MX-7103 --severity high \\
        --finding "Duration drifting, 12.6 percent above approved and rising" \\
        --evidence "risk tower: mttr_vs_peers 0.43, no stop-based signal" \\
        --evidence "shift note 2026-06-15: parts releasing slower from the cavity" \\
        --action "generated duration deviation report" \\
        --action "scheduled tool cooling inspection"
"""

import argparse
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from models.database import init_database  # noqa: E402
from models.decision_trail import (  # noqa: E402
    PHASE_ACT,
    PHASE_REASON,
    STATUS_COMPLETED,
    TRIGGER_MANUAL,
)
from services.workflow.trail_recorder import TrailRecorder  # noqa: E402

EXIT_OK = 0
EXIT_FAILED = 1
SEPARATOR = "-" * 68

# Severity levels the agent may assert. Constrained so the trail stays queryable.
SEVERITY_LEVELS = ("low", "medium", "high", "critical")

BACKEND_COCO = "coco-cli"


def _parse_args() -> argparse.Namespace:
    """Parse the decision being recorded."""
    parser = argparse.ArgumentParser(
        description="Record an agent decision and its actions to the decision trail."
    )
    parser.add_argument(
        "--equipment",
        action="append",
        required=True,
        help="Equipment code this decision concerns. Repeat for several.",
    )
    parser.add_argument(
        "--severity",
        choices=SEVERITY_LEVELS,
        required=True,
        help="Severity the agent assigns.",
    )
    parser.add_argument(
        "--finding", required=True, help="What the agent concluded, in one sentence."
    )
    parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="A metric or quoted note supporting the finding. Repeat for several.",
    )
    parser.add_argument(
        "--action",
        action="append",
        default=[],
        help="An action actually performed. Repeat for several. Omit if none were.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Append to an existing run instead of opening a new one.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model that produced the reasoning, recorded on the run.",
    )
    return parser.parse_args()


def _build_summary(args: argparse.Namespace) -> str:
    """Compose the stored conclusion from the supplied parts."""
    lines = [
        f"Equipment: {', '.join(args.equipment)}",
        f"Severity: {args.severity}",
        f"Finding: {args.finding}",
    ]
    if args.evidence:
        lines.append("Evidence:")
        lines.extend(f"  - {item}" for item in args.evidence)
    if args.action:
        lines.append("Actions performed:")
        lines.extend(f"  - {item}" for item in args.action)
    else:
        lines.append("Actions performed: none")
    return "\n".join(lines)


def _record(args: argparse.Namespace, summary: str) -> str:
    """Persist the run, its reasoning step and one step per action."""
    recorder = TrailRecorder(run_id=args.run_id)
    recorder.start_run(
        trigger=TRIGGER_MANUAL, llm_backend=BACKEND_COCO, model_id=args.model
    )

    recorder.record_step(
        phase=PHASE_REASON,
        status=STATUS_COMPLETED,
        result_summary=summary,
        payload={
            "equipment": args.equipment,
            "severity": args.severity,
            "evidence_count": len(args.evidence),
        },
    )

    for action in args.action:
        recorder.record_step(
            phase=PHASE_ACT,
            status=STATUS_COMPLETED,
            tool_name=action,
            payload={"machine_ids": args.equipment},
            result_summary=action,
        )

    recorder.finish_run(status=STATUS_COMPLETED, summary=summary)
    return recorder.run_id


def _warn_if_unbacked(actions: List[str]) -> None:
    """Point out that a decision with no actions is a recommendation, not an intervention."""
    if actions:
        return
    print("", flush=True)
    print(
        "NOTE: no actions were recorded, so this run is an assessment rather than an "
        "intervention. Do not describe it as work performed.",
        flush=True,
    )


def main() -> int:
    """Record one decision and print the resulting run identifier."""
    args = _parse_args()
    try:
        init_database()
        summary = _build_summary(args)
        run_id = _record(args, summary)
    except Exception as exc:  # noqa: BLE001 - top level entry point
        print(f"RECORD FAILED: {exc}", flush=True)
        return EXIT_FAILED

    print(SEPARATOR, flush=True)
    print(f"run_id  : {run_id}", flush=True)
    print(SEPARATOR, flush=True)
    print(summary, flush=True)
    _warn_if_unbacked(args.action)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
