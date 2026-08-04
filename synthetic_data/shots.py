"""Pure generation of MASTER_SHOT_TABLE shot streams from equipment profiles.

Produces multi-week, multi-run shot sequences whose inter-shot gaps, cycle times and hard
stops are constructed to land deterministically on each branch of the stop classification
detection rules. Contains no I/O and no clock access; randomness comes from an injected Random.
"""

from datetime import datetime, timedelta
from random import Random
from typing import Final, List, Tuple

from .constants import (
    ABNORMAL_CT_HIGH_FACTOR,
    ABNORMAL_CT_LOW_FACTOR,
    CT_DECIMALS,
    CT_RESOLUTION_SEC,
    CT_STATUS_ACTIVE,
    CT_STATUS_IDLE,
    GAP_SAFETY_MARGIN_SEC,
    GAP_TIME_TOLERANCE_SECONDS,
    HARD_STOP_CT,
    NORMAL_CT_STEP_OFFSETS,
    NORMAL_CT_STEP_WEIGHTS,
    NORMAL_GAP_JITTER_SEC,
    TEMPERATURE_BASE_C,
    TEMPERATURE_DRIFT_COEFFICIENT_C,
    TEMPERATURE_JITTER_C,
    TEMPERATURE_STOP_DROP_C,
    TIME_GAP_EXTRA_MAX_SEC,
    TIME_GAP_EXTRA_MIN_SEC,
)
from .models import (
    EquipmentProfile,
    GenerationConfig,
    ProfileKind,
    RunBehaviour,
    Shot,
    ShotContext,
    StopKind,
)

# Baseline ratio of observed mode cycle time to approved cycle time for healthy equipment.
# Slightly above 1.0 because real tools rarely beat their contracted cycle.
BASELINE_CT_FACTOR: Final[float] = 1.02

# Probability that an abnormal cycle is a short shot rather than a long one.
ABNORMAL_SHORT_SHARE: Final[float] = 0.5

# Hours of start-time stagger applied per equipment index, so plants do not all start
# at the same instant. Kept small enough that inter-run gaps stay above 8 hours.
START_HOUR_STAGGER: Final[int] = 1
START_HOUR_STAGGER_MODULUS: Final[int] = 3

# One generated event: (cycle_time_seconds, wall_clock_advance_seconds, intended stop kind).
ShotEvent = Tuple[float, float, StopKind]


def _interpolate(start: float, end: float, week_index: int, total_weeks: int) -> float:
    """Linearly interpolate between start and end across the dataset's week window."""
    if total_weeks <= 1:
        return end
    return start + (end - start) * (week_index / (total_weeks - 1))


def resolve_behaviour(
    profile: EquipmentProfile, week_index: int, total_weeks: int
) -> RunBehaviour:
    """Resolve the generation parameters for one equipment in one ISO week of the window.

    CT_DRIFT equipment ramp their mode cycle time away from approved CT week over week;
    DECLINING equipment ramp their hard-stop rate instead, which degrades stability over time.
    """
    if profile.kind is ProfileKind.CT_DRIFT:
        drift_factor = _interpolate(
            BASELINE_CT_FACTOR, profile.drift_end_factor, week_index, total_weeks
        )
    else:
        drift_factor = BASELINE_CT_FACTOR

    if profile.kind is ProfileKind.DECLINING:
        hard_stop_rate = _interpolate(
            profile.base_hard_stop_rate,
            profile.decline_end_stop_rate,
            week_index,
            total_weeks,
        )
    else:
        hard_stop_rate = profile.base_hard_stop_rate

    return RunBehaviour(
        mode_ct=round(profile.mold.approved_ct * drift_factor, CT_DECIMALS),
        hard_stop_rate=hard_stop_rate,
        abnormal_rate=profile.base_abnormal_rate,
        time_gap_rate=profile.base_time_gap_rate,
        max_consecutive_hard_stops=profile.max_consecutive_hard_stops,
        hard_stop_min_sec=profile.hard_stop_min_sec,
        hard_stop_max_sec=profile.hard_stop_max_sec,
        ct_drift_factor=drift_factor,
    )


def _normal_ct(rng: Random, mode_ct: float) -> float:
    """Draw a normal cycle time on the CT grid, peaked at the mode.

    The weights concentrate a majority of draws on the zero offset, so mode_ct is strictly the
    most frequent value even in short runs; the offset range keeps every draw inside the
    +/-5% band so a normal cycle is never misread as an Abnormal Cycle stop.
    """
    steps = rng.choices(NORMAL_CT_STEP_OFFSETS, weights=NORMAL_CT_STEP_WEIGHTS, k=1)[0]
    return round(mode_ct + steps * CT_RESOLUTION_SEC, CT_DECIMALS)


def _normal_advance(rng: Random, ct: float, previous_ct: float) -> float:
    """Advance the clock by roughly one cycle, clamped below the Time Gap boundary.

    The clamp guarantees a normal shot can never satisfy time_diff > previous_ct + 2.0,
    which would otherwise misclassify it as a Time Gap stop.
    """
    advance = ct + rng.uniform(0.0, NORMAL_GAP_JITTER_SEC)
    ceiling = previous_ct + GAP_TIME_TOLERANCE_SECONDS - GAP_SAFETY_MARGIN_SEC
    return min(advance, ceiling)


def _hard_stop_burst(rng: Random, behaviour: RunBehaviour) -> List[ShotEvent]:
    """Emit one or more consecutive CT=999.9 shots, which collapse into a single stop event."""
    count = rng.randint(1, behaviour.max_consecutive_hard_stops)
    return [
        (
            HARD_STOP_CT,
            rng.uniform(behaviour.hard_stop_min_sec, behaviour.hard_stop_max_sec),
            StopKind.HARD_STOP,
        )
        for _ in range(count)
    ]


def _next_events(
    rng: Random, behaviour: RunBehaviour, previous_ct: float
) -> List[ShotEvent]:
    """Draw the next shot (or burst of shots) according to the behaviour's event rates."""
    roll = rng.random()

    if roll < behaviour.hard_stop_rate:
        return _hard_stop_burst(rng, behaviour)
    roll -= behaviour.hard_stop_rate

    if roll < behaviour.abnormal_rate:
        factor = (
            ABNORMAL_CT_LOW_FACTOR
            if rng.random() < ABNORMAL_SHORT_SHARE
            else ABNORMAL_CT_HIGH_FACTOR
        )
        ct = round(behaviour.mode_ct * factor, CT_DECIMALS)
        return [(ct, ct, StopKind.ABNORMAL_CYCLE)]
    roll -= behaviour.abnormal_rate

    if roll < behaviour.time_gap_rate:
        ct = _normal_ct(rng, behaviour.mode_ct)
        extra = rng.uniform(TIME_GAP_EXTRA_MIN_SEC, TIME_GAP_EXTRA_MAX_SEC)
        return [
            (ct, previous_ct + GAP_TIME_TOLERANCE_SECONDS + extra, StopKind.TIME_GAP)
        ]

    ct = _normal_ct(rng, behaviour.mode_ct)
    return [(ct, _normal_advance(rng, ct, previous_ct), StopKind.NORMAL)]


def _temperature(rng: Random, behaviour: RunBehaviour, kind: StopKind) -> float:
    """Derive melt temperature, correlated with cycle-time drift so RCA has a real signal."""
    drift_excess = behaviour.ct_drift_factor - BASELINE_CT_FACTOR
    value = TEMPERATURE_BASE_C + drift_excess * TEMPERATURE_DRIFT_COEFFICIENT_C
    value += rng.uniform(-TEMPERATURE_JITTER_C, TEMPERATURE_JITTER_C)
    if kind is StopKind.HARD_STOP:
        value -= TEMPERATURE_STOP_DROP_C
    return round(value, 1)


def _make_shot(
    profile: EquipmentProfile,
    context: ShotContext,
    behaviour: RunBehaviour,
    rng: Random,
    local_shot_time: datetime,
    ct: float,
    kind: StopKind,
    generated_at: datetime,
) -> Shot:
    """Assemble one fully denormalised MASTER_SHOT_TABLE row."""
    mold = profile.mold
    location = context.location_by_id[mold.location_id]
    part_code = context.part_code_by_id[mold.part_id]
    return Shot(
        supplier_name=context.supplier_name_by_company_id[mold.supplier_company_id],
        equipment_code=mold.equipment_code,
        counter_code=mold.counter_code,
        ct=ct,
        approved_ct=mold.approved_ct,
        temperature=_temperature(rng, behaviour, kind),
        part_name=context.part_name_by_code[part_code],
        tooling_type=mold.tooling_type,
        tooling_family=mold.tooling_type,
        ct_status=CT_STATUS_IDLE if ct >= HARD_STOP_CT else CT_STATUS_ACTIVE,
        local_shot_time=local_shot_time,
        utc_time_zone=local_shot_time - timedelta(hours=location.utc_offset_hours),
        volume=mold.total_cavities,
        counter_id=mold.counter_id,
        mold_id=mold.id,
        company_id=mold.supplier_company_id,
        part_id=part_code,
        upload_time=generated_at,
        processing_date=local_shot_time.date().isoformat(),
        intended_stop_kind=kind,
    )


def generate_run(
    rng: Random,
    profile: EquipmentProfile,
    behaviour: RunBehaviour,
    context: ShotContext,
    run_start: datetime,
    shift_seconds: float,
    generated_at: datetime,
) -> List[Shot]:
    """Generate one production run: a contiguous shot stream bounded by the shift length.

    The first shot of a run is always Normal, matching the rule that a run's opening
    shot is never counted as a stop.
    """
    shots: List[Shot] = []
    first_ct = _normal_ct(rng, behaviour.mode_ct)
    current_time = run_start
    previous_ct = first_ct
    elapsed = 0.0
    shots.append(
        _make_shot(
            profile,
            context,
            behaviour,
            rng,
            current_time,
            first_ct,
            StopKind.NORMAL,
            generated_at,
        )
    )

    while elapsed < shift_seconds:
        for ct, advance, kind in _next_events(rng, behaviour, previous_ct):
            current_time = current_time + timedelta(seconds=advance)
            elapsed += advance
            shots.append(
                _make_shot(
                    profile,
                    context,
                    behaviour,
                    rng,
                    current_time,
                    ct,
                    kind,
                    generated_at,
                )
            )
            previous_ct = ct
    return shots


def generate_equipment_shots(
    rng: Random,
    profile: EquipmentProfile,
    context: ShotContext,
    config: GenerationConfig,
    equipment_index: int,
) -> List[Shot]:
    """Generate every production run for one equipment across the full dataset window.

    Runs are one per production day, so the idle overnight period always exceeds the
    8-hour session gap and each day becomes a distinct production run.
    """
    shift_seconds = config.shift_hours * 3600.0
    stagger = (equipment_index % START_HOUR_STAGGER_MODULUS) * START_HOUR_STAGGER
    shots: List[Shot] = []
    for week_index in range(config.weeks):
        behaviour = resolve_behaviour(profile, week_index, config.weeks)
        for day_index in range(config.production_days_per_week):
            run_start = config.window_start + timedelta(
                days=week_index * 7 + day_index,
                hours=config.shift_start_hour + stagger,
            )
            shots.extend(
                generate_run(
                    rng,
                    profile,
                    behaviour,
                    context,
                    run_start,
                    shift_seconds,
                    config.generated_at,
                )
            )
    return shots


def generate_all_shots(
    profiles: List[EquipmentProfile],
    context: ShotContext,
    config: GenerationConfig,
) -> List[Shot]:
    """Generate the complete shot table for every equipment, seeded per equipment.

    Each equipment gets its own Random derived from the base seed so adding or removing an
    equipment does not perturb the others' streams.
    """
    shots: List[Shot] = []
    for index, profile in enumerate(profiles):
        rng = Random(config.seed + index)
        shots.extend(generate_equipment_shots(rng, profile, context, config, index))
    shots.sort(key=lambda shot: (shot.equipment_code, shot.local_shot_time))
    return shots
