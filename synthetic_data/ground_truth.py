"""Declaration of the defects deliberately planted in the synthetic dataset.

Each planted defect is expressed as the finding a specific sense tool is expected to report,
which turns the hackathon demo into a verifiable claim rather than an anecdote. This module
is pure: it describes expectations and never inspects generated rows or touches Snowflake.
"""

from typing import Dict, Final, List

from .constants import CT_DEVIATION_CRITICAL_PCT
from .models import EquipmentProfile, ExpectedFinding, ProfileKind

DETECTOR_CT_DEVIATION: Final[str] = "run_ct_deviation_analysis"
DETECTOR_CONTROL: Final[str] = "negative_control"

DIRECTION_ABOVE: Final[str] = "above"
DIRECTION_BELOW: Final[str] = "below"
DIRECTION_NONE: Final[str] = "no_finding"

# Stability decline fraction the Risk Tower treats as a declining trend (risk_tower.py).
RISK_TOWER_DECLINE_THRESHOLD_PCT: Final[float] = 5.0

# Multiples of the fleet average that the frequent-stop and long-repair profiles are
# built to exceed, matching the Risk Tower's primary-risk-factor tests.
MTTR_FLEET_MULTIPLE: Final[float] = 1.2
MTBF_FLEET_MULTIPLE: Final[float] = 0.8

_CLAIMS: Final[Dict[ProfileKind, str]] = {
    ProfileKind.CT_DRIFT: (
        "Observed cycle time drifts week over week from approximately 2 percent above "
        "approved CT to critical deviation in the final week, while stop behaviour stays normal."
    ),
    ProfileKind.FREQUENT_STOPS: (
        "Many short hard stops produce a low mean time between failures without inflating "
        "mean time to repair."
    ),
    ProfileKind.LONG_REPAIRS: (
        "Few but very long hard-stop bursts produce a high mean time to repair while stop "
        "frequency stays near fleet baseline."
    ),
    ProfileKind.DECLINING: (
        "Hard-stop rate ramps across the window so stability declines by more than the Risk "
        "Tower's 5 percent trend threshold between the first and last active week."
    ),
    ProfileKind.STABLE: (
        "Behaves within tolerance for the whole window and must not be flagged by any "
        "sense tool; a flag here is a false positive."
    ),
}


def _finding_for(profile: EquipmentProfile) -> ExpectedFinding:
    """Map one equipment profile to the single finding its planted defect should produce."""
    equipment_code = profile.mold.equipment_code
    claim = _CLAIMS[profile.kind]

    if profile.kind is ProfileKind.CT_DRIFT:
        return ExpectedFinding(
            equipment_code=equipment_code,
            profile_kind=profile.kind,
            detector=DETECTOR_CT_DEVIATION,
            claim=claim,
            metric="ct_deviation_pct",
            expected_direction=DIRECTION_ABOVE,
            expected_value=CT_DEVIATION_CRITICAL_PCT,
        )
    if profile.kind is ProfileKind.FREQUENT_STOPS:
        return ExpectedFinding(
            equipment_code=equipment_code,
            profile_kind=profile.kind,
            detector=DETECTOR_CT_DEVIATION,
            claim=claim,
            metric="mtbf_minutes",
            expected_direction=DIRECTION_BELOW,
            expected_value=MTBF_FLEET_MULTIPLE,
        )
    if profile.kind is ProfileKind.LONG_REPAIRS:
        return ExpectedFinding(
            equipment_code=equipment_code,
            profile_kind=profile.kind,
            detector=DETECTOR_CT_DEVIATION,
            claim=claim,
            metric="mttr_minutes",
            expected_direction=DIRECTION_ABOVE,
            expected_value=MTTR_FLEET_MULTIPLE,
        )
    if profile.kind is ProfileKind.DECLINING:
        return ExpectedFinding(
            equipment_code=equipment_code,
            profile_kind=profile.kind,
            detector=DETECTOR_CT_DEVIATION,
            claim=claim,
            metric="stability_decline_pct",
            expected_direction=DIRECTION_ABOVE,
            expected_value=RISK_TOWER_DECLINE_THRESHOLD_PCT,
        )
    return ExpectedFinding(
        equipment_code=equipment_code,
        profile_kind=profile.kind,
        detector=DETECTOR_CONTROL,
        claim=claim,
        metric="none",
        expected_direction=DIRECTION_NONE,
        expected_value=None,
    )


def build_expected_findings(profiles: List[EquipmentProfile]) -> List[ExpectedFinding]:
    """Return the full expectation set, one entry per equipment including negative controls."""
    return [_finding_for(profile) for profile in profiles]


def demo_headline_equipment(profiles: List[EquipmentProfile]) -> str:
    """Return the equipment code the Phase 4 demo narrative is built around.

    The CT-drift tool is the headline because its anomaly is invisible to single-metric monitors,
    which makes the agent's cross-tool reasoning the visible value in the demo.
    """
    for profile in profiles:
        if profile.kind is ProfileKind.CT_DRIFT:
            return profile.mold.equipment_code
    raise ValueError(
        "roster contains no CT_DRIFT equipment; the demo narrative has no subject"
    )
