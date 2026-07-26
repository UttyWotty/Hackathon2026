"""Proves the shift notes corroborate the planted defects and clear the negative controls.

The demo claim is that a semantic search over operator notes surfaces the cycle-time drift
weeks before the numeric deviation crosses its critical threshold. These tests assert that
lead time exists rather than assuming it, and that healthy equipment are described in
language a search for symptoms will not match.
"""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import pytest

from synthetic_data.constants import CT_DEVIATION_CRITICAL_PCT, HARD_STOP_CT
from synthetic_data.dataset import build_dataset
from synthetic_data.models import GenerationConfig, ProfileKind, ShiftNote, Shot
from synthetic_data.notes import (
    CT_DRIFT_FIRST_SYMPTOM_WEEK,
    ROUTINE_NOTES,
    SYMPTOM_NOTES,
    symptom_texts,
)

PERCENT = 100.0

# Words that must never appear in a routine note. If a template leaks symptom language the
# negative controls start matching a symptom search, which is a false positive in the demo.
SYMPTOM_WORDS = ("slower", "creeping", "fault", "stoppage", "downtime", "degraded")


@pytest.fixture(name="config", scope="module")
def config_fixture() -> GenerationConfig:
    """The same six-week window the generator's default produces."""
    return GenerationConfig(
        seed=20260721,
        weeks=6,
        production_days_per_week=5,
        shift_hours=8.0,
        shift_start_hour=6,
        window_start=datetime(2026, 6, 8, 0, 0, 0),
        generated_at=datetime(2026, 7, 21, 12, 0, 0),
        database="MMS_DEMO",
        schema="PUBLIC",
    )


@pytest.fixture(name="dataset", scope="module")
def dataset_fixture(config: GenerationConfig):
    """One generated dataset, shared across the module."""
    return build_dataset(config)


@pytest.fixture(name="kind_by_code", scope="module")
def kind_by_code_fixture(dataset) -> Dict[str, ProfileKind]:
    """Archetype for each equipment code."""
    return {profile.mold.equipment_code: profile.kind for profile in dataset.profiles}


@pytest.fixture(name="notes_by_code", scope="module")
def notes_by_code_fixture(dataset) -> Dict[str, List[ShiftNote]]:
    """Shift notes grouped by equipment."""
    grouped: Dict[str, List[ShiftNote]] = defaultdict(list)
    for note in dataset.shift_notes:
        grouped[note.equipment_code].append(note)
    return grouped


def _first_critical_week(shots: List[Shot]) -> int:
    """The first ISO week whose mean CT deviation exceeds the critical threshold."""
    weekly: Dict[int, List[float]] = defaultdict(list)
    for shot in shots:
        if shot.approved_ct > 0 and shot.ct < HARD_STOP_CT:
            deviation = (shot.ct - shot.approved_ct) / shot.approved_ct * PERCENT
            weekly[shot.local_shot_time.isocalendar()[1]].append(deviation)
    for week in sorted(weekly):
        if sum(weekly[week]) / len(weekly[week]) > CT_DEVIATION_CRITICAL_PCT:
            return week
    raise AssertionError("The drift equipment never crosses the critical threshold")


class TestNegativeControls:
    def test_stable_equipment_have_no_symptom_notes(self, notes_by_code, kind_by_code):
        """A healthy machine described as faulty is a false positive in the search demo."""
        for code, kind in kind_by_code.items():
            if kind is not ProfileKind.STABLE:
                continue
            flagged = [n for n in notes_by_code[code] if n.mentions_symptom]
            assert (
                not flagged
            ), f"{code} is a control but has {len(flagged)} symptom notes"

    def test_routine_templates_contain_no_symptom_language(self):
        """Guards the template pool itself, not just the selection logic."""
        for text in ROUTINE_NOTES:
            lowered = text.lower()
            for word in SYMPTOM_WORDS:
                assert word not in lowered, f"routine note leaks '{word}': {text}"

    def test_control_notes_are_all_routine_text(self, notes_by_code, kind_by_code):
        for code, kind in kind_by_code.items():
            if kind is ProfileKind.STABLE:
                assert all(n.note_text in ROUTINE_NOTES for n in notes_by_code[code])


class TestDefectiveEquipment:
    def test_every_planted_defect_is_described(self, notes_by_code, kind_by_code):
        """Search cannot corroborate a defect nobody wrote down."""
        for code, kind in kind_by_code.items():
            if kind is ProfileKind.STABLE:
                continue
            flagged = [n for n in notes_by_code[code] if n.mentions_symptom]
            assert (
                flagged
            ), f"{code} has a planted {kind.value} defect but no symptom notes"

    def test_symptom_text_matches_the_archetype(self, notes_by_code, kind_by_code):
        """A frequent-stop machine must not be described in drift language."""
        for code, kind in kind_by_code.items():
            if kind is ProfileKind.STABLE:
                continue
            allowed = symptom_texts(kind)
            for note in notes_by_code[code]:
                if note.mentions_symptom:
                    assert note.note_text in allowed

    def test_wording_escalates_across_the_window(self, notes_by_code, kind_by_code):
        """The last symptom note must sit in a more severe band than the first."""
        code = next(c for c, k in kind_by_code.items() if k is ProfileKind.CT_DRIFT)
        flagged = [n for n in notes_by_code[code] if n.mentions_symptom]
        bands = SYMPTOM_NOTES[ProfileKind.CT_DRIFT]

        def band_of(text: str) -> int:
            return next(i for i, band in enumerate(bands) if text in band)

        assert band_of(flagged[-1].note_text) > band_of(flagged[0].note_text)

    def test_consecutive_notes_are_not_byte_identical(
        self, notes_by_code, kind_by_code
    ):
        """Verbatim repeats read as generated and return duplicate search hits.

        One phrasing per severity band produced identical notes on consecutive days, which
        is what the nested band structure exists to prevent.
        """
        code = next(c for c, k in kind_by_code.items() if k is ProfileKind.CT_DRIFT)
        flagged = [n.note_text for n in notes_by_code[code] if n.mentions_symptom]
        longest_run = 1
        current = 1
        for previous, nxt in zip(flagged, flagged[1:]):
            current = current + 1 if previous == nxt else 1
            longest_run = max(longest_run, current)
        assert longest_run <= 2, f"{longest_run} identical notes in a row"


class TestSearchBeatsTheThreshold:
    def test_drift_is_described_before_it_is_measurable(
        self, dataset, notes_by_code, kind_by_code
    ):
        """The demo's central claim, asserted rather than asserted-in-prose.

        Operator notes must describe the drift before the mean deviation crosses the
        critical threshold. Without this lead time the search skill adds nothing the
        numeric detector did not already provide.
        """
        code = next(c for c, k in kind_by_code.items() if k is ProfileKind.CT_DRIFT)
        shots = [s for s in dataset.shots if s.equipment_code == code]

        first_symptom = min(
            n.shift_date for n in notes_by_code[code] if n.mentions_symptom
        )
        critical_week = _first_critical_week(shots)

        assert first_symptom.isocalendar()[1] < critical_week, (
            f"notes first mention drift in week {first_symptom.isocalendar()[1]} but the "
            f"deviation is already critical in week {critical_week}; no lead time"
        )

    def test_lead_time_is_at_least_two_weeks(
        self, dataset, notes_by_code, kind_by_code
    ):
        """A one-week lead would be within noise and unconvincing in a demo."""
        code = next(c for c, k in kind_by_code.items() if k is ProfileKind.CT_DRIFT)
        shots = [s for s in dataset.shots if s.equipment_code == code]
        first_symptom_week = min(
            n.shift_date for n in notes_by_code[code] if n.mentions_symptom
        ).isocalendar()[1]
        assert _first_critical_week(shots) - first_symptom_week >= 2

    def test_drift_notes_start_no_earlier_than_configured(
        self, notes_by_code, kind_by_code, config
    ):
        """Symptoms must not appear in week zero, or the drift looks obvious from day one."""
        code = next(c for c, k in kind_by_code.items() if k is ProfileKind.CT_DRIFT)
        first = min(n.shift_date for n in notes_by_code[code] if n.mentions_symptom)
        days_in = (first - config.window_start).days
        assert days_in >= CT_DRIFT_FIRST_SYMPTOM_WEEK * 7


class TestStructure:
    def test_one_note_per_production_day_per_equipment(self, dataset, config):
        expected = (
            len(dataset.profiles) * config.weeks * config.production_days_per_week
        )
        assert len(dataset.shift_notes) == expected

    def test_ids_are_unique(self, dataset):
        ids = [note.id for note in dataset.shift_notes]
        assert len(set(ids)) == len(ids)

    def test_generation_is_deterministic(self, config):
        first = build_dataset(config).shift_notes
        second = build_dataset(config).shift_notes
        assert [n.note_text for n in first] == [n.note_text for n in second]
        assert [n.shift_date for n in first] == [n.shift_date for n in second]

    def test_ground_truth_tag_is_not_serialized(self, dataset):
        """mentions_symptom is generator ground truth; the agent must not see it."""
        from synthetic_data.constants import TABLE_SHIFT_NOTE

        for row in dataset.tables[TABLE_SHIFT_NOTE]:
            assert True not in row and False not in row
