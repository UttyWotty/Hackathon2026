"""Pure generation of unstructured shift notes for the synthetic dataset.

Produces one free-text operator or maintenance note per production day per equipment, worded
to match that equipment's planted defect, so a semantic search over the notes corroborates
what the numeric detectors find. Contains no I/O and no clock access; randomness comes from
an injected Random.

The demo hinges on timing: notes for the cycle-time-drift equipment describe symptoms from
the second week onward, while its measured deviation only crosses the critical threshold in
the final week. Search therefore surfaces the problem weeks before a threshold would.
"""

from datetime import timedelta
from random import Random
from typing import Dict, Final, List, Tuple

from .constants import SHIFT_NOTE_ID_BASE
from .models import EquipmentProfile, GenerationConfig, ProfileKind, ShiftNote

# Who wrote the note. Kept coarse: the search demo filters by equipment and date, not author.
ROLE_OPERATOR: Final[str] = "Operator"
ROLE_MAINTENANCE: Final[str] = "Maintenance"
ROLE_SHIFT_LEAD: Final[str] = "Shift Lead"

# Hour of day the note is filed, at the end of the shift.
NOTE_HOUR: Final[int] = 14

# Week index from which drift symptoms start appearing in notes. Zero-based, so 1 is the
# second week of the window. The measured deviation does not cross the critical threshold
# until the final week, and that gap is the point of the whole search story.
CT_DRIFT_FIRST_SYMPTOM_WEEK: Final[int] = 1

# Probability that a defective equipment's note on a given day mentions its symptom rather
# than routine content. Below 1.0 so the notes read like a real log, with quiet days.
SYMPTOM_NOTE_RATE: Final[float] = 0.65

# Routine notes, used for healthy equipment and for the quiet days of defective ones.
#
# These must contain no symptom vocabulary at all, including negated ("no stoppages").
# Embedding models match on topic rather than polarity, so a negated mention still pulls a
# healthy machine into a semantic search for stop problems. Phrase the good news positively.
ROUTINE_NOTES: Final[Tuple[str, ...]] = (
    "Shift ran clean. Continuous production, no quality concerns raised.",
    "Routine tool check completed at start of shift. Nothing to report.",
    "Production steady all shift. Part weights within tolerance.",
    "No issues. Material feed consistent, dryer temperatures nominal.",
    "Handover clean. Cavity surfaces checked, no flash or short shots.",
    "Uneventful shift. Operator confirmed cycle running to standard.",
    "Standard run. Scrap bin near empty at end of shift.",
    "All nominal. Water lines checked, no restriction found.",
)

# Symptom notes per archetype, as severity bands ordered from subtle to obvious. The week
# selects the band; the run's Random picks a phrasing within it.
#
# The nesting exists because a single phrasing per band made every symptom note in a week
# byte-identical, which reads as obviously generated and would return duplicate hits from a
# semantic search. Different shifts describe the same problem differently.
SYMPTOM_NOTES: Final[Dict[ProfileKind, Tuple[Tuple[str, ...], ...]]] = {
    ProfileKind.CT_DRIFT: (
        (
            "Cycle feels a touch slower than the board time. Nothing alarming, monitoring it.",
            "Running a shade off the posted rate today. Probably nothing, noting it anyway.",
            "Slight lag on the cycle. Asked the next shift to keep an eye on it.",
        ),
        (
            "Parts releasing slower from the cavity. Added a couple of seconds cooling.",
            "Ejection is dragging a little. Bumped cooling to keep the parts clean.",
            "Tool is holding heat more than it was. Cycle stretched slightly as a result.",
        ),
        (
            "Cycle time creeping up again this week. Operator compensating manually.",
            "Still climbing. We are adjusting every shift now just to hold quality.",
            "Cycle drifting further from standard. Manual compensation is not keeping up.",
        ),
        (
            "Noticeably slower than the approved standard. Ejection sluggish on the B half.",
            "Well over standard cycle now. Suspect tool cooling or a worn ejector return.",
            "Running significantly long. Recommend pulling the tool for a cooling check.",
        ),
    ),
    ProfileKind.FREQUENT_STOPS: (
        (
            "Machine faulted twice this shift, cleared both times without intervention.",
            "Couple of brief trips today. Restarted fine, no cause found.",
        ),
        (
            "Three short stoppages today. Each restarted cleanly, no obvious cause.",
            "Several quick faults again. Nothing serious individually, adds up over a shift.",
        ),
        (
            "Repeated brief faults. Losing a few minutes each time but they accumulate.",
            "Interruptions all shift. Short each time, constant enough to hurt output.",
        ),
        (
            "Frequent short stops continue. Operator spending the shift restarting.",
            "Faulting constantly now. Cannot get a clean run of any length.",
        ),
    ),
    ProfileKind.LONG_REPAIRS: (
        (
            "Down waiting on maintenance for most of the morning. Single fault, long wait.",
            "One trip today but we lost a long stretch waiting for a fitter.",
        ),
        (
            "Extended downtime again. One stoppage but over half an hour to clear.",
            "Another slow recovery. The fault itself was minor, the wait was not.",
        ),
        (
            "Long repair on the hydraulic side. Few faults but each costs us the shift.",
            "Rare stoppages, very long ones. Downtime per event is the problem here.",
        ),
        (
            "Another lengthy outage. Stop count is low, downtime per event is not.",
            "Hours lost to a single fault again. Recovery time is the issue, not frequency.",
        ),
    ),
    ProfileKind.DECLINING: (
        (
            "Slightly more interruptions than usual this week, nothing serious yet.",
            "A touch more unsettled than last month. Worth keeping an eye on.",
        ),
        (
            "Stoppage count is climbing compared to last month. Worth watching.",
            "Trending the wrong way. More faults this week than last, consistently.",
        ),
        (
            "Noticeably less stable than earlier in the run. More faults each shift.",
            "Getting worse week on week. Nothing dramatic, but the trend is clear.",
        ),
        (
            "Stability has degraded badly. Frequent faults, operator confidence is low.",
            "Machine is unreliable now. Crew has stopped trusting it to run unattended.",
        ),
    ),
}


def symptom_texts(kind: ProfileKind) -> frozenset:
    """Every symptom phrasing for an archetype, flattened across severity bands.

    Args:
        kind: The behavioural archetype.

    Returns:
        All phrasings that archetype can produce, for membership checks.
    """
    return frozenset(text for band in SYMPTOM_NOTES[kind] for text in band)


# Equipment with no planted defect. Their notes must stay routine.
HEALTHY_KIND: Final[ProfileKind] = ProfileKind.STABLE


def _note_role(kind: ProfileKind, mentions_symptom: bool) -> str:
    """Choose an author role that fits the note's content."""
    if not mentions_symptom:
        return ROLE_OPERATOR
    if kind is ProfileKind.LONG_REPAIRS:
        return ROLE_MAINTENANCE
    if kind is ProfileKind.DECLINING:
        return ROLE_SHIFT_LEAD
    return ROLE_OPERATOR


def _escalation_index(week_index: int, total_weeks: int, bands: int) -> int:
    """Map a week to a severity band, so wording escalates across the window."""
    if total_weeks <= 1:
        return bands - 1
    position = week_index / (total_weeks - 1)
    return min(bands - 1, int(position * bands))


def _symptom_active(kind: ProfileKind, week_index: int) -> bool:
    """Whether this archetype should show symptoms in notes by the given week."""
    if kind is HEALTHY_KIND:
        return False
    if kind is ProfileKind.CT_DRIFT:
        return week_index >= CT_DRIFT_FIRST_SYMPTOM_WEEK
    return True


def _build_note(
    rng: Random,
    profile: EquipmentProfile,
    week_index: int,
    config: GenerationConfig,
    note_id: int,
    day_offset: int,
) -> ShiftNote:
    """Build one shift note for one equipment on one production day."""
    kind = profile.kind
    wants_symptom = _symptom_active(kind, week_index) and (
        rng.random() < SYMPTOM_NOTE_RATE
    )

    if wants_symptom:
        bands = SYMPTOM_NOTES[kind]
        band = bands[_escalation_index(week_index, config.weeks, len(bands))]
        text = rng.choice(band)
    else:
        text = rng.choice(ROUTINE_NOTES)

    return ShiftNote(
        id=note_id,
        equipment_code=profile.mold.equipment_code,
        shift_date=config.window_start + timedelta(days=day_offset, hours=NOTE_HOUR),
        author_role=_note_role(kind, wants_symptom),
        note_text=text,
        mentions_symptom=wants_symptom,
    )


def build_shift_notes(
    profiles: List[EquipmentProfile], config: GenerationConfig
) -> List[ShiftNote]:
    """Build one shift note per production day per equipment across the window.

    Each equipment is seeded from the base seed plus its index, matching the shot generator,
    so adding or removing equipment does not perturb the others' note streams.

    Args:
        profiles: The equipment roster with its archetypes.
        config: The generation window and seed.

    Returns:
        Notes ordered by equipment then date.
    """
    notes: List[ShiftNote] = []
    next_id = SHIFT_NOTE_ID_BASE

    for index, profile in enumerate(profiles):
        rng = Random(config.seed + index)
        for week_index in range(config.weeks):
            for day_index in range(config.production_days_per_week):
                notes.append(
                    _build_note(
                        rng,
                        profile,
                        week_index,
                        config,
                        next_id,
                        week_index * 7 + day_index,
                    )
                )
                next_id += 1

    notes.sort(key=lambda note: (note.equipment_code, note.shift_date))
    return notes
