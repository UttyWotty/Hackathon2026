"""Verifies that generated shots land on the stop branch the generator intended.

Re-implements the runrate v2.6 detection rules independently from CALCULATION_SPEC.md and
asserts every generated shot classifies as its declared intended_stop_kind. This is the
contract that makes the dataset usable: if it fails, the planted defects are not detectable.
"""

from datetime import datetime
from random import Random
from statistics import multimode
from typing import Dict, List

import pytest

from hackathon.synthetic_data.dimensions import build_molds, build_parts, build_profiles
from hackathon.synthetic_data.models import (
    GenerationConfig,
    ProfileKind,
    Shot,
    StopKind,
)
from hackathon.synthetic_data.shots import generate_equipment_shots

from .conftest import build_context
from .runrate_reference import (
    MODE_CT_LOWER_BOUND,
    MODE_CT_UPPER_BOUND,
    classify,
    split_runs,
)


@pytest.fixture(name="config")
def config_fixture() -> GenerationConfig:
    """A short, fully deterministic generation window sufficient to exercise every branch."""
    return GenerationConfig(
        seed=4242,
        weeks=3,
        production_days_per_week=5,
        shift_hours=4.0,
        shift_start_hour=6,
        window_start=datetime(2026, 6, 1, 0, 0, 0),
        generated_at=datetime(2026, 7, 21, 12, 0, 0),
        database="MMS_DEMO",
        schema="PUBLIC",
    )


def _shots_for(config: GenerationConfig, kind: ProfileKind) -> List[Shot]:
    """Generate the shot stream for the first equipment matching an archetype."""
    parts = build_parts()
    molds = build_molds(parts, config.production_days_per_week, config.shift_hours)
    profiles = build_profiles(molds)
    context = build_context(parts)
    for index, profile in enumerate(profiles):
        if profile.kind is kind:
            return generate_equipment_shots(
                Random(config.seed + index), profile, context, config, index
            )
    raise AssertionError(f"no equipment with profile {kind}")


@pytest.mark.parametrize("kind", list(ProfileKind))
def test_intended_stop_kind_matches_detection(
    config: GenerationConfig, kind: ProfileKind
) -> None:
    """Every generated shot must classify as the stop kind the generator tagged it with."""
    shots = _shots_for(config, kind)
    for run in split_runs(shots):
        derived = classify(run)
        intended = [shot.intended_stop_kind for shot in run]
        assert derived == intended


@pytest.mark.parametrize("kind", list(ProfileKind))
def test_runs_align_with_production_days(
    config: GenerationConfig, kind: ProfileKind
) -> None:
    """Each production day must form exactly one run, so overnight idle is never counted."""
    runs = split_runs(_shots_for(config, kind))
    assert len(runs) == config.weeks * config.production_days_per_week


@pytest.mark.parametrize("kind", list(ProfileKind))
def test_mode_is_well_defined_per_run(
    config: GenerationConfig, kind: ProfileKind
) -> None:
    """The modal cycle time must be unique, otherwise the +/-5% stop band is arbitrary."""
    for run in split_runs(_shots_for(config, kind)):
        candidates = [
            s.ct for s in run if MODE_CT_LOWER_BOUND < s.ct < MODE_CT_UPPER_BOUND
        ]
        assert len(multimode(candidates)) == 1


def test_generation_is_reproducible(config: GenerationConfig) -> None:
    """The same seed and config must produce byte-identical streams across runs."""
    first = _shots_for(config, ProfileKind.STABLE)
    second = _shots_for(config, ProfileKind.STABLE)
    assert first == second


def test_every_stop_branch_is_exercised(config: GenerationConfig) -> None:
    """The dataset must contain all four stop kinds, or some detection paths go untested."""
    seen: Dict[StopKind, int] = {}
    for kind in ProfileKind:
        for shot in _shots_for(config, kind):
            seen[shot.intended_stop_kind] = seen.get(shot.intended_stop_kind, 0) + 1
    assert set(seen) == set(StopKind)
