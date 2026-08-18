"""Deterministic construction of the synthetic dimension tables and equipment roster.

Builds COMPANY, LOCATION, PART and TOOL rows plus the per-equipment behavioural profiles
that drive shot generation, from a fixed roster rather than randomness so ids and names are
stable across runs. All functions here are pure and perform no I/O.
"""

from typing import Dict, Final, List, Tuple

from .constants import (
    VENDOR_ID_BASE,
    SENSOR_ID_BASE,
    LOCATION_ID_BASE,
    TOOL_ID_BASE,
    TYPE_DIE_CASTING,
    TYPE_INJECTION,
    TYPE_STAMPING,
)
from .models import Company, EquipmentProfile, Location, Mold, Part, ProfileKind

# Synthetic supplier names. Deliberately invented; no real client name may appear here.
VENDOR_NAMES: Final[Tuple[str, ...]] = (
    "NORDPLAST INDUSTRIES",
    "ARCWELD COMPONENTS",
    "MERIDIAN TOOLING",
)

# Synthetic plants with real IANA timezone ids so CONVERT_TIMEZONE behaves realistically.
PLANT_SPECS: Final[Tuple[Tuple[str, str, int], ...]] = (
    ("Halden Plant", "Europe/Oslo", 2),
    ("Kestrel Ridge Plant", "America/Chicago", -5),
)

# Design life in shots per tooling type, mirroring tooling_eol get_design_life defaults.
DESIGN_LIFE_BY_TYPE: Final[Dict[str, int]] = {
    TYPE_INJECTION: 1_500_000,
    TYPE_DIE_CASTING: 800_000,
    TYPE_STAMPING: 500_000,
}

# Roster of synthetic equipment.
# Fields: machine_id, process_type, target_duration (deci-seconds), cavities,
# product_code, product_name, profile kind.
EQUIPMENT_ROSTER: Final[
    Tuple[Tuple[str, str, int, int, str, str, ProfileKind], ...]
] = (
    (
        "MX-7101",
        TYPE_INJECTION,
        284,
        4,
        "218-155",
        "Door Handle Carrier",
        ProfileKind.STABLE,
    ),
    (
        "MX-7102",
        TYPE_INJECTION,
        312,
        2,
        "218-160",
        "Pillar Trim Left",
        ProfileKind.STABLE,
    ),
    (
        "MX-7103",
        TYPE_INJECTION,
        268,
        4,
        "224-071",
        "Coolant Reservoir Cap",
        ProfileKind.CT_DRIFT,
    ),
    (
        "MX-7104",
        TYPE_DIE_CASTING,
        455,
        2,
        "331-902",
        "Gearbox End Cover",
        ProfileKind.FREQUENT_STOPS,
    ),
    (
        "MX-7105",
        TYPE_DIE_CASTING,
        512,
        1,
        "331-915",
        "Pump Housing",
        ProfileKind.LONG_REPAIRS,
    ),
    (
        "MX-7106",
        TYPE_INJECTION,
        196,
        8,
        "218-188",
        "Clip Retainer",
        ProfileKind.DECLINING,
    ),
    (
        "MX-7107",
        TYPE_STAMPING,
        88,
        1,
        "402-330",
        "Bracket Reinforcement",
        ProfileKind.STABLE,
    ),
    (
        "MX-7108",
        TYPE_INJECTION,
        342,
        2,
        "224-088",
        "Air Duct Elbow",
        ProfileKind.STABLE,
    ),
)

# Duration the per-shot stop rates below are calibrated against, in seconds.
# Roughly the fleet-typical cycle; build_profiles scales each machine's rates by
# its own duration over this value so archetypes control stops per hour.
REFERENCE_DURATION_SEC: Final[float] = 30.0

# Per-archetype base rates. Tuple order:
# (base_hard_stop_rate, base_abnormal_rate, base_time_gap_rate, max_consecutive_hard_stops,
#  hard_stop_min_sec, hard_stop_max_sec, drift_end_factor, decline_end_stop_rate)
PROFILE_PARAMETERS: Final[
    Dict[ProfileKind, Tuple[float, float, float, int, float, float, float, float]]
] = {
    ProfileKind.STABLE: (0.004, 0.010, 0.006, 2, 90.0, 420.0, 1.0, 0.004),
    ProfileKind.CT_DRIFT: (0.005, 0.012, 0.006, 2, 90.0, 420.0, 1.24, 0.005),
    ProfileKind.FREQUENT_STOPS: (0.038, 0.014, 0.022, 3, 60.0, 180.0, 1.0, 0.038),
    ProfileKind.LONG_REPAIRS: (0.006, 0.011, 0.005, 3, 900.0, 2400.0, 1.0, 0.006),
    ProfileKind.DECLINING: (0.006, 0.010, 0.006, 3, 120.0, 600.0, 1.0, 0.042),
}


def build_companies() -> List[Company]:
    """Return the fixed list of synthetic supplier companies."""
    return [
        Company(id=VENDOR_ID_BASE + index, name=name)
        for index, name in enumerate(VENDOR_NAMES)
    ]


def build_locations() -> List[Location]:
    """Return the fixed list of synthetic plants with their timezone metadata."""
    return [
        Location(
            id=LOCATION_ID_BASE + index,
            name=name,
            tz_code=tz_code,
            utc_offset_hours=utc_offset_hours,
        )
        for index, (name, tz_code, utc_offset_hours) in enumerate(PLANT_SPECS)
    ]


def build_parts() -> List[Part]:
    """Return one PART row per distinct product_code in the equipment roster."""
    seen: Dict[str, str] = {}
    for _, _, _, _, product_code, product_name, _ in EQUIPMENT_ROSTER:
        seen.setdefault(product_code, product_name)
    return [
        Part(id=index + 1, product_code=product_code, name=product_name)
        for index, (product_code, product_name) in enumerate(sorted(seen.items()))
    ]


def _max_daily_output(
    target_duration: float, cavities: int, shift_hours: float, shifts_per_day: int
) -> int:
    """Compute nameplate daily part capacity from duration, cavities and shift length."""
    seconds_available = shift_hours * shifts_per_day * 3600.0
    return int(seconds_available / target_duration * cavities)


def build_molds(
    parts: List[Part],
    production_days_per_week: int,
    shift_hours: float,
) -> List[Mold]:
    """Build one MOLD row per roster entry, round-robin assigning suppliers and plants."""
    product_id_by_code = {part.product_code: part.id for part in parts}
    molds: List[Mold] = []
    for index, entry in enumerate(EQUIPMENT_ROSTER):
        (
            machine_id,
            process_type,
            target_duration,
            cavities,
            product_code,
            _,
            _,
        ) = entry
        target_duration = target_duration / 10.0
        sensor_id = SENSOR_ID_BASE + index
        molds.append(
            Mold(
                id=TOOL_ID_BASE + index,
                machine_id=machine_id,
                sensor_code=f"CNT-{sensor_id}",
                sensor_id=sensor_id,
                vendor_vendor_id=VENDOR_ID_BASE + (index % len(VENDOR_NAMES)),
                location_id=LOCATION_ID_BASE + (index % len(PLANT_SPECS)),
                product_id=product_id_by_code[product_code],
                process_type=process_type,
                target_duration=target_duration,
                total_cavities=cavities,
                designed_shot=DESIGN_LIFE_BY_TYPE[process_type],
                max_daily_output=_max_daily_output(
                    target_duration, cavities, shift_hours, 1
                ),
                production_days=production_days_per_week,
                shifts_per_day=1,
            )
        )
    return molds


def build_profiles(molds: List[Mold]) -> List[EquipmentProfile]:
    """Bind each mold to its roster archetype and that archetype's planted-defect parameters.

    Stop rates in PROFILE_PARAMETERS are per shot, but MTBF is per unit of time. Without
    normalisation a fast machine stops more often per hour than a slow one at the same
    per-shot rate, which made a stable 8.8-second machine look like it stopped more often
    than the machine whose planted defect is frequent stops. Each rate is therefore scaled
    by the mold's duration relative to REFERENCE_DURATION_SEC, so an archetype controls
    stops per hour and MTBF stays comparable across machines of different speeds.
    """
    kind_by_code = {entry[0]: entry[6] for entry in EQUIPMENT_ROSTER}
    profiles: List[EquipmentProfile] = []
    for mold in molds:
        kind = kind_by_code[mold.machine_id]
        (
            base_hard_stop_rate,
            base_abnormal_rate,
            base_time_gap_rate,
            max_consecutive_hard_stops,
            hard_stop_min_sec,
            hard_stop_max_sec,
            drift_end_factor,
            decline_end_stop_rate,
        ) = PROFILE_PARAMETERS[kind]
        rate_scale = mold.target_duration / REFERENCE_DURATION_SEC
        profiles.append(
            EquipmentProfile(
                mold=mold,
                kind=kind,
                base_hard_stop_rate=base_hard_stop_rate * rate_scale,
                base_abnormal_rate=base_abnormal_rate * rate_scale,
                base_time_gap_rate=base_time_gap_rate * rate_scale,
                drift_end_factor=drift_end_factor,
                decline_end_stop_rate=decline_end_stop_rate * rate_scale,
                max_consecutive_hard_stops=max_consecutive_hard_stops,
                hard_stop_min_sec=hard_stop_min_sec,
                hard_stop_max_sec=hard_stop_max_sec,
            )
        )
    return profiles


def product_name_by_code(parts: List[Part]) -> Dict[str, str]:
    """Return a product_code to part name lookup for shot-row construction."""
    return {part.product_code: part.name for part in parts}


def product_code_by_id(parts: List[Part]) -> Dict[int, str]:
    """Return a numeric part id to product_code lookup, bridging the two key spaces."""
    return {part.id: part.product_code for part in parts}
