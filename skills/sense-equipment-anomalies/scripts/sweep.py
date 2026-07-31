"""Runs the manufacturing anomaly sweep and prints condensed findings.

Executes the cycle-time deviation and Risk Tower detectors across the fleet, then follows up
with run rate on the machines those implicate, and prints a compact text summary for the
calling agent to reason over. Deterministic and read-only: it gathers signal and draws no
conclusions.

Usage:
    python scripts/sweep.py                 # whole fleet
    python scripts/sweep.py MX-7103        # one machine
"""

import asyncio
import sys
from pathlib import Path

# The skill lives at <repo>/skills/<skill-name>/scripts/, so the repo root is three up.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.infrastructure.scheduler.tool_dispatcher import (  # noqa: E402
    dispatch_tool_direct,
)
from services.workflow.sense import (  # noqa: E402
    DEFAULT_SENSE_TASKS,
    SenseTask,
    derive_followup_tasks,
    format_findings,
    run_sense_tasks,
)

EXIT_OK = 0
EXIT_FAILED = 1
SEPARATOR = "-" * 68


async def _sweep(equipment_code: str) -> int:
    """Run the opening sweep plus its derived follow-ups, and print the findings."""
    tasks = list(DEFAULT_SENSE_TASKS)
    if equipment_code:
        tasks = [
            SenseTask(
                tool_name=task.tool_name,
                arguments={"equipment_codes": [equipment_code]},
            )
            for task in tasks
        ]

    findings = await run_sense_tasks(tasks, dispatch_tool_direct)

    # Run rate needs explicit equipment codes - there is no wildcard - so the machines to
    # follow up on come from what the deviation pass just named.
    followups = derive_followup_tasks(findings)
    if followups:
        findings.extend(await run_sense_tasks(followups, dispatch_tool_direct))

    print(SEPARATOR, flush=True)
    print(format_findings(findings), flush=True)
    print(SEPARATOR, flush=True)

    failed = [finding.tool_name for finding in findings if not finding.ok]
    if failed:
        print(
            f"WARNING: these detectors failed and their signal is missing: {failed}",
            flush=True,
        )
        print(
            "Absence of a finding from them proves nothing about those machines.",
            flush=True,
        )
    return EXIT_OK if not failed else EXIT_FAILED


def main() -> int:
    """Entry point. Optional first argument narrows the sweep to one equipment code."""
    equipment_code = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        return asyncio.run(_sweep(equipment_code))
    except Exception as exc:  # noqa: BLE001 - top level entry point
        print(f"SWEEP FAILED: {exc}", flush=True)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
