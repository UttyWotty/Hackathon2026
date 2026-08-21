"""Named constants for the synthetic manufacturing dataset generator.

Every threshold here mirrors a value the production analysis modules depend on, so that
generated data lands deterministically on the intended side of each detection rule.
Values sourced from analysis/shared/constants.py.
are marked as such and must not be changed independently of the analysis code.
"""

from typing import Final, Tuple

# --- Mirrored from analysis/shared/constants.py (SessionDetection) ---
SESSION_GAP_SECONDS: Final[int] = 28800
HARD_STOP_DURATION: Final[float] = 999.9
GAP_TIME_TOLERANCE_SECONDS: Final[float] = 2.0
STOP_DEVIATION_THRESHOLD: Final[float] = 0.05

# --- Mirrored from analysis/shared/constants.py (AnalysisThresholds) ---
DEVIATION_WARNING_PCT: Final[float] = 10.0
DEVIATION_CRITICAL_PCT: Final[float] = 20.0

# --- Generation safety margins ---
# A "normal" shot must not accidentally trip the Time Gap rule
# (time_diff > previous_ct + GAP_TIME_TOLERANCE_SECONDS), so advances are clamped
# below that boundary by this margin.
GAP_SAFETY_MARGIN_SEC: Final[float] = 0.25
NORMAL_GAP_JITTER_SEC: Final[float] = 0.6

# Machine durations are reported on a fixed grid, not as continuous values. Quantizing to
# this resolution is what makes MODE_CT a well-defined statistical mode; with continuous
# jitter almost every CT would be unique and the mode would be arbitrary.
CT_RESOLUTION_SEC: Final[float] = 0.1
CT_DECIMALS: Final[int] = 1

# Normal cycles vary by a whole number of grid steps around the mode. The distribution is
# sharply peaked at zero so the mode stays unambiguous even in short runs, where a flatter
# spread produces ties. Offsets stay inside the +/-5% band for the shortest roster cycle.
NORMAL_CT_STEP_OFFSETS: Final[Tuple[int, ...]] = (-3, -2, -1, 0, 1, 2, 3)
NORMAL_CT_STEP_WEIGHTS: Final[Tuple[float, ...]] = (
    0.015,
    0.06,
    0.15,
    0.55,
    0.15,
    0.06,
    0.015,
)

# An "abnormal" cycle must land clearly outside the +/-5% mode band.
ABNORMAL_CT_LOW_FACTOR: Final[float] = 0.78
ABNORMAL_CT_HIGH_FACTOR: Final[float] = 1.32

# A "time gap" stop needs time_diff > previous_ct + 2.0; this is the extra idle time added.
TIME_GAP_EXTRA_MIN_SEC: Final[float] = 6.0
TIME_GAP_EXTRA_MAX_SEC: Final[float] = 240.0

# Hard stop (CT = 999.9) wall-clock duration is set per archetype in
# dimensions.PROFILE_PARAMETERS, since it is what separates the long-repair machine
# (high MTTR) from the frequent-stop machine (low MTBF).

# --- Dataset shape defaults (all explicit, all overridable via the CLI) ---
DEFAULT_SEED: Final[int] = 20260721
DEFAULT_WEEKS: Final[int] = 6
DEFAULT_PRODUCTION_DAYS_PER_WEEK: Final[int] = 5
DEFAULT_SHIFT_HOURS: Final[float] = 8.0
DEFAULT_SHIFT_START_HOUR: Final[int] = 6

# --- Column value enums (must match what the pipelines write) ---
STATUS_ACTIVE: Final[str] = "active"
STATUS_IDLE: Final[str] = "idle"

TYPE_INJECTION: Final[str] = "Injection Molding"
TYPE_DIE_CASTING: Final[str] = "Die Casting"
TYPE_STAMPING: Final[str] = "Stamping"

WORK_ORDER_STATUS_COMPLETED: Final[str] = "completed"

# --- Process physics used to make temperature and volume plausible ---
TEMPERATURE_BASE_C: Final[float] = 182.0
TEMPERATURE_JITTER_C: Final[float] = 4.5
# Degrees of extra melt temperature per 1.0 of duration drift factor above baseline. Gives
# RCA a real correlated signal to find rather than pure noise.
TEMPERATURE_DRIFT_COEFFICIENT_C: Final[float] = 26.0
TEMPERATURE_STOP_DROP_C: Final[float] = 12.0

# --- Snowflake object names ---
TABLE_MASTER_SHOT: Final[str] = "SHOT_DATA"
TABLE_TOOL: Final[str] = "TOOL"
TABLE_VENDOR: Final[str] = "VENDOR"
TABLE_LOCATION: Final[str] = "LOCATION"
TABLE_PRODUCT: Final[str] = "PRODUCT"
TABLE_WORK_ORDER: Final[str] = "WORK_ORDER"
TABLE_SHIFT_NOTE: Final[str] = "SHIFT_NOTE"

# Runtime tables. Not part of the generated dataset: the dashboard writes AUDIT_LOG and
# scripts/export_trail.py writes AGENT_DECISION_TRAIL. Declared here so one schema build
# stands up every object the application needs.
TABLE_AUDIT_LOG: Final[str] = "AUDIT_LOG"
TABLE_AGENT_DECISION_TRAIL: Final[str] = "AGENT_DECISION_TRAIL"

# --- Identifier bases, so ids are stable and collision-free across dimensions ---
TOOL_ID_BASE: Final[int] = 4100
VENDOR_ID_BASE: Final[int] = 700
LOCATION_ID_BASE: Final[int] = 310
SENSOR_ID_BASE: Final[int] = 88200
WORK_ORDER_ID_BASE: Final[int] = 55000
SHIFT_NOTE_ID_BASE: Final[int] = 61000
