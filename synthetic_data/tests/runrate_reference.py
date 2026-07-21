"""Independent reference implementation of the runrate v2.6 stop and KPI calculations.

Transcribed directly from analysis/runrate/CALCULATION_SPEC.md rather than imported from the
production code, so the tests verify the dataset against the specification instead of against
whatever the implementation happens to do. Pure functions over generated Shot objects only.
"""

from dataclasses import dataclass
from statistics import multimode
from typing import List

from synthetic_data.constants import (
    GAP_TIME_TOLERANCE_SECONDS,
    HARD_STOP_CT,
    SESSION_GAP_SECONDS,
    STOP_DEVIATION_THRESHOLD,
)
from synthetic_data.models import Shot, StopKind

# Tolerance for float drift when recomputing inter-shot gaps from timestamps.
TIME_EPSILON_SEC = 1e-6

# CT range the mode calculation considers, per the spec's exclusion of hard stops.
MODE_CT_LOWER_BOUND = 1.0
MODE_CT_UPPER_BOUND = 999.0

SECONDS_PER_MINUTE = 60.0
PERCENT = 100.0


@dataclass(frozen=True)
class RunMetrics:
    """The KPI set the spec defines for one production run, in minutes and percent."""

    total_run_time: float
    production_time: float
    down_time: float
    stop_events: int
    mttr: float
    mtbf: float
    stability: float


def split_runs(shots: List[Shot]) -> List[List[Shot]]:
    """Split a shot stream into production runs on any gap above the 8-hour session threshold."""
    runs: List[List[Shot]] = []
    current: List[Shot] = []
    for shot in shots:
        if (
            current
            and (shot.local_shot_time - current[-1].local_shot_time).total_seconds()
            > SESSION_GAP_SECONDS
        ):
            runs.append(current)
            current = []
        current.append(shot)
    if current:
        runs.append(current)
    return runs


def mode_ct(run: List[Shot]) -> float:
    """Compute MODE_CT for a run, excluding hard stops, rounded to two decimals."""
    candidates = [
        shot.ct for shot in run if MODE_CT_LOWER_BOUND < shot.ct < MODE_CT_UPPER_BOUND
    ]
    if not candidates:
        raise ValueError("run has no cycle times eligible for the mode calculation")
    return round(min(multimode(candidates)), 2)


def classify(run: List[Shot]) -> List[StopKind]:
    """Apply the v2.6 stop detection rules, in their specified order, to one run."""
    mode = mode_ct(run)
    low = mode * (1 - STOP_DEVIATION_THRESHOLD)
    high = mode * (1 + STOP_DEVIATION_THRESHOLD)
    kinds: List[StopKind] = [StopKind.NORMAL]
    for index in range(1, len(run)):
        shot, previous = run[index], run[index - 1]
        time_diff = (shot.local_shot_time - previous.local_shot_time).total_seconds()
        if shot.ct >= HARD_STOP_CT:
            kinds.append(StopKind.HARD_STOP)
        elif shot.ct < low or shot.ct > high:
            kinds.append(StopKind.ABNORMAL_CYCLE)
        elif time_diff > previous.ct + GAP_TIME_TOLERANCE_SECONDS + TIME_EPSILON_SEC:
            kinds.append(StopKind.TIME_GAP)
        else:
            kinds.append(StopKind.NORMAL)
    return kinds


def _adjusted_ct(kind: StopKind, ct: float, time_diff: float) -> float:
    """Return ADJ_CT_SEC for one shot, which is the downtime that stop contributes."""
    if kind is StopKind.HARD_STOP or kind is StopKind.TIME_GAP:
        return time_diff
    if kind is StopKind.ABNORMAL_CYCLE:
        return ct
    return 0.0


def _count_stop_events(kinds: List[StopKind]) -> int:
    """Count maximal runs of consecutive stopped shots; each collapses into one stop event."""
    events = 0
    previous_was_stop = False
    for kind in kinds:
        is_stop = kind is not StopKind.NORMAL
        if is_stop and not previous_was_stop:
            events += 1
        previous_was_stop = is_stop
    return events


def run_metrics(run: List[Shot]) -> RunMetrics:
    """Compute the spec's time components and KPIs for one production run."""
    kinds = classify(run)
    total_diff = 0.0
    production_seconds = 0.0
    down_seconds = 0.0
    for index in range(1, len(run)):
        time_diff = (
            run[index].local_shot_time - run[index - 1].local_shot_time
        ).total_seconds()
        total_diff += time_diff
        if kinds[index] is StopKind.NORMAL:
            production_seconds += time_diff
        else:
            down_seconds += _adjusted_ct(kinds[index], run[index].ct, time_diff)

    total_run_time = (total_diff + mode_ct(run)) / SECONDS_PER_MINUTE
    production_time = production_seconds / SECONDS_PER_MINUTE
    down_time = down_seconds / SECONDS_PER_MINUTE
    stop_events = _count_stop_events(kinds)
    return RunMetrics(
        total_run_time=total_run_time,
        production_time=production_time,
        down_time=down_time,
        stop_events=stop_events,
        mttr=down_time / stop_events if stop_events else 0.0,
        mtbf=production_time / stop_events if stop_events else 0.0,
        stability=(
            (production_time / total_run_time * PERCENT) if total_run_time else 0.0
        ),
    )
