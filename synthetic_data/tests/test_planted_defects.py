"""Proves that each planted defect is measurable by the metric its expected finding names.

Computes the runrate KPIs and CT deviation from the generated dataset and asserts the
defective equipment separate from the fleet by the margins declared in ground_truth.py.
Without these assertions the dataset could look plausible while being undetectable.
"""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import pytest

from synthetic_data.constants import (
    CT_DEVIATION_CRITICAL_PCT,
    CT_DEVIATION_WARNING_PCT,
    HARD_STOP_CT,
)
from synthetic_data.dataset import build_dataset
from synthetic_data.ground_truth import (
    MTBF_FLEET_MULTIPLE,
    MTTR_FLEET_MULTIPLE,
    RISK_TOWER_DECLINE_THRESHOLD_PCT,
)
from synthetic_data.models import GenerationConfig, ProfileKind, Shot

from .runrate_reference import RunMetrics, run_metrics, split_runs

PERCENT = 100.0


@pytest.fixture(name="config", scope="module")
def config_fixture() -> GenerationConfig:
    """A six-week window, long enough for the Risk Tower's four-week trend to be meaningful."""
    return GenerationConfig(
        seed=20260721,
        weeks=6,
        production_days_per_week=5,
        shift_hours=4.0,
        shift_start_hour=6,
        window_start=datetime(2026, 6, 1, 0, 0, 0),
        generated_at=datetime(2026, 7, 21, 12, 0, 0),
        database="MMS_DEMO",
        schema="PUBLIC",
    )


@pytest.fixture(name="shots_by_equipment", scope="module")
def shots_by_equipment_fixture(config: GenerationConfig) -> Dict[str, List[Shot]]:
    """Group the generated shot table by equipment code."""
    grouped: Dict[str, List[Shot]] = defaultdict(list)
    for shot in build_dataset(config).shots:
        grouped[shot.equipment_code].append(shot)
    return dict(grouped)


@pytest.fixture(name="code_by_kind", scope="module")
def code_by_kind_fixture(config: GenerationConfig) -> Dict[ProfileKind, str]:
    """Map each archetype to the equipment code carrying it."""
    return {
        profile.kind: profile.mold.equipment_code
        for profile in build_dataset(config).profiles
    }


def _metrics(shots: List[Shot]) -> List[RunMetrics]:
    """Compute per-run KPIs for one equipment."""
    return [run_metrics(run) for run in split_runs(shots)]


def _mean(values: List[float]) -> float:
    """Return the arithmetic mean, or zero for an empty series."""
    return sum(values) / len(values) if values else 0.0


def _deviation_pct(shots: List[Shot]) -> float:
    """Return mean CT deviation from approved CT, as a percentage.

    Hard stops are excluded, matching the CT < 999.9 guard the ct_deviation data loader applies;
    including them would swamp the mean with idle markers rather than real cycle behaviour.
    """
    active = [shot for shot in shots if shot.ct < HARD_STOP_CT]
    return _mean(
        [(shot.ct - shot.approved_ct) / shot.approved_ct * PERCENT for shot in active]
    )


def test_ct_drift_crosses_critical_only_at_the_end(
    shots_by_equipment: Dict[str, List[Shot]],
    code_by_kind: Dict[ProfileKind, str],
    config: GenerationConfig,
) -> None:
    """The drifting tool must start inside tolerance and end above the critical threshold."""
    shots = shots_by_equipment[code_by_kind[ProfileKind.CT_DRIFT]]
    runs = split_runs(shots)
    runs_per_week = config.production_days_per_week
    first_week = [shot for run in runs[:runs_per_week] for shot in run]
    last_week = [shot for run in runs[-runs_per_week:] for shot in run]

    assert _deviation_pct(first_week) < CT_DEVIATION_WARNING_PCT
    assert _deviation_pct(last_week) > CT_DEVIATION_CRITICAL_PCT


def test_ct_drift_is_invisible_to_stability(
    shots_by_equipment: Dict[str, List[Shot]], code_by_kind: Dict[ProfileKind, str]
) -> None:
    """The drifting tool must look healthy on run-rate metrics.

    This is the whole point of the demo narrative: a single-metric monitor misses it, and only
    reasoning across CT deviation and run rate together surfaces the problem.
    """
    drift = _mean(
        [
            metric.stability
            for metric in _metrics(
                shots_by_equipment[code_by_kind[ProfileKind.CT_DRIFT]]
            )
        ]
    )
    stable = _mean(
        [
            metric.stability
            for metric in _metrics(shots_by_equipment[code_by_kind[ProfileKind.STABLE]])
        ]
    )
    assert abs(drift - stable) < 5.0


def test_long_repairs_exceeds_fleet_mttr(
    shots_by_equipment: Dict[str, List[Shot]], code_by_kind: Dict[ProfileKind, str]
) -> None:
    """The long-repair tool's MTTR must exceed the Risk Tower's 1.2x fleet-average trigger."""
    by_code = {
        code: _mean([m.mttr for m in _metrics(shots)])
        for code, shots in shots_by_equipment.items()
    }
    target = code_by_kind[ProfileKind.LONG_REPAIRS]
    fleet_average = _mean([value for code, value in by_code.items() if code != target])
    assert by_code[target] > fleet_average * MTTR_FLEET_MULTIPLE


def test_frequent_stops_falls_below_fleet_mtbf(
    shots_by_equipment: Dict[str, List[Shot]], code_by_kind: Dict[ProfileKind, str]
) -> None:
    """The frequent-stop tool's MTBF must fall below the Risk Tower's 0.8x fleet-average trigger."""
    by_code = {
        code: _mean([m.mtbf for m in _metrics(shots)])
        for code, shots in shots_by_equipment.items()
    }
    target = code_by_kind[ProfileKind.FREQUENT_STOPS]
    fleet_average = _mean([value for code, value in by_code.items() if code != target])
    assert by_code[target] < fleet_average * MTBF_FLEET_MULTIPLE


def test_declining_tool_shows_a_stability_trend(
    shots_by_equipment: Dict[str, List[Shot]],
    code_by_kind: Dict[ProfileKind, str],
    config: GenerationConfig,
) -> None:
    """Stability must fall by more than the Risk Tower's 5 percent decline threshold."""
    metrics = _metrics(shots_by_equipment[code_by_kind[ProfileKind.DECLINING]])
    runs_per_week = config.production_days_per_week
    first_week = _mean([metric.stability for metric in metrics[:runs_per_week]])
    last_week = _mean([metric.stability for metric in metrics[-runs_per_week:]])
    decline_pct = (first_week - last_week) / first_week * PERCENT
    assert decline_pct > RISK_TOWER_DECLINE_THRESHOLD_PCT


def test_stable_equipment_stays_within_tolerance(
    shots_by_equipment: Dict[str, List[Shot]], code_by_kind: Dict[ProfileKind, str]
) -> None:
    """Negative controls must not trip the CT deviation warning, or the demo shows false positives."""
    shots = shots_by_equipment[code_by_kind[ProfileKind.STABLE]]
    assert _deviation_pct(shots) < CT_DEVIATION_WARNING_PCT
