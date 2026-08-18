"""Typed row and configuration models for the synthetic manufacturing dataset.

Each dataclass mirrors exactly one Snowflake table's column contract as consumed by the
production analysis modules, so a generated row can be written to CSV or Snowflake without
any further mapping. These are pure data containers with no I/O and no behaviour.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Optional


class ProfileKind(str, Enum):
    """Behavioural archetypes assigned to each synthetic equipment.

    The kind determines how the shot stream is perturbed over the dataset window.
    Every kind except STABLE plants a defect that a specific sense tool is expected to find.
    """

    STABLE = "stable"
    CT_DRIFT = "ct_drift"
    FREQUENT_STOPS = "frequent_stops"
    LONG_REPAIRS = "long_repairs"
    DECLINING = "declining"


class StopKind(str, Enum):
    """Stop classification a generated shot is intended to receive downstream.

    These mirror the STOP_TYPE values produced by the stop detection module.
    The generator tags each shot so the ground-truth file can assert what the analysis
    should conclude without re-implementing the detection logic.
    """

    NORMAL = "Normal"
    HARD_STOP = "Hard Stop"
    ABNORMAL_CYCLE = "Abnormal Cycle"
    TIME_GAP = "Time Gap"


@dataclass(frozen=True)
class Company:
    """A supplier company row for the COMPANY dimension table."""

    id: int
    name: str


@dataclass(frozen=True)
class Location:
    """A plant row for the LOCATION dimension table, including its IANA timezone."""

    id: int
    name: str
    tz_code: str
    utc_offset_hours: int


@dataclass(frozen=True)
class Part:
    """A produced part row for the PART dimension table.

    Note that SHOT_DATA.PRODUCT_ID carries product_code (a string), not this numeric id.
    """

    id: int
    product_code: str
    name: str


@dataclass(frozen=True)
class Mold:
    """A tool/mold row for the TOOL dimension table and the grain of shot generation.

    target_duration is stored in deci-seconds exactly as the production table does;
    target_duration in SHOT_DATA is this value divided by ten.
    """

    id: int
    machine_id: str
    sensor_code: str
    sensor_id: int
    vendor_vendor_id: int
    location_id: int
    product_id: int
    process_type: str
    target_duration: int
    total_cavities: int
    designed_shot: int
    max_daily_output: int
    production_days: int
    shifts_per_day: int

    @property
    def target_duration(self) -> float:
        """Approved duration in seconds, matching the pipeline's /10.0 derivation."""
        return self.target_duration / 10.0


@dataclass(frozen=True)
class Shot:
    """One SHOT_DATA row plus the generator's ground-truth stop tag.

    Column names and types match the authoritative DDL in the shot_data pipeline.
    intended_stop_kind is generator metadata and is never written to the shot table.
    """

    vendor_name: str
    machine_id: str
    sensor_code: str
    ct: float
    target_duration: float
    temperature: float
    product_name: str
    process_type: str
    type_category: str
    status_flag: str
    shot_time: datetime
    shot_time_utc: datetime
    volume: int
    sensor_id: int
    tool_id: int
    vendor_id: int
    product_id: str
    upload_time: datetime
    processing_date: str
    intended_stop_kind: StopKind


@dataclass(frozen=True)
class WorkOrder:
    """A completed maintenance work order, used by tooling_eol maintenance-interval logic."""

    id: int
    tool_id: int
    status: str
    completed_at: datetime
    order_type: str


@dataclass(frozen=True)
class ShiftNote:
    """One free-text shift note, the dataset's only unstructured content.

    mentions_symptom is the generator's ground-truth tag, mirroring Shot's stop tag: it is
    used by the tests to assert that defective equipment are described and controls are not,
    and is deliberately never serialized to the table.
    """

    id: int
    machine_id: str
    shift_date: datetime
    author_role: str
    note_text: str
    mentions_symptom: bool


@dataclass(frozen=True)
class RunBehaviour:
    """Per-run generation parameters resolved from an equipment profile and week index.

    Rates are probabilities per shot and must sum to well under 1.0 so that normal cycles
    remain dominant and MODE_CT stays well defined.
    """

    mode_ct: float
    hard_stop_rate: float
    abnormal_rate: float
    time_gap_rate: float
    max_consecutive_hard_stops: int
    hard_stop_min_sec: float
    hard_stop_max_sec: float
    ct_drift_factor: float


@dataclass(frozen=True)
class EquipmentProfile:
    """Binds a mold to a behavioural archetype and its planted-defect parameters.

    drift_end_factor is the CT-to-approved-duration ratio reached at the end of the window for
    CT_DRIFT equipment; decline_end_stop_rate is the terminal hard-stop rate for DECLINING.
    """

    mold: Mold
    kind: ProfileKind
    base_hard_stop_rate: float
    base_abnormal_rate: float
    base_time_gap_rate: float
    drift_end_factor: float
    decline_end_stop_rate: float
    max_consecutive_hard_stops: int
    hard_stop_min_sec: float
    hard_stop_max_sec: float


@dataclass(frozen=True)
class GenerationConfig:
    """Top-level knobs for one dataset generation run.

    generated_at is injected rather than read from the clock so generation stays pure and
    byte-for-byte reproducible for a given seed.
    """

    seed: int
    weeks: int
    production_days_per_week: int
    shift_hours: float
    shift_start_hour: int
    window_start: datetime
    generated_at: datetime
    database: str
    schema: str


@dataclass(frozen=True)
class ShotContext:
    """Dimension lookups needed to denormalise a shot row.

    SHOT_DATA is fully denormalised, so every shot must carry supplier, plant,
    and part attributes resolved from the dimension tables at generation time.
    """

    vendor_name_by_vendor_id: Dict[int, str]
    location_by_id: Dict[int, Location]
    product_code_by_id: Dict[int, str]
    product_name_by_code: Dict[str, str]


@dataclass(frozen=True)
class ExpectedFinding:
    """One planted defect, stated as what a sense tool is expected to report.

    This is the demo's verification contract: the agent's autonomous output is scored
    against these rows rather than against a human's recollection of the seed.
    """

    machine_id: str
    profile_kind: ProfileKind
    detector: str
    claim: str
    metric: str
    expected_direction: str
    expected_value: Optional[float]
