"""Tests for the data-coverage window fed into the agent's system prompt.

The demo dataset is historical, so a "last 30 days" window returns almost
nothing. Without being told this, the agent reported the dataset ending as a
production collapse. These tests cover the staleness arithmetic and the prompt
text that prevents that reading.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.data_coverage import DataCoverage  # noqa: E402
from core.prompts import _coverage_section, get_system_prompt  # noqa: E402


def _coverage(last_shot: date, today: date) -> DataCoverage:
    return DataCoverage(first_shot=date(2026, 6, 15), last_shot=last_shot, today=today)


class TestDataCoverage:
    """Tests for the staleness calculation."""

    def test_days_stale_counts_the_gap(self):
        cov = _coverage(date(2026, 7, 24), date(2026, 8, 20))
        assert cov.days_stale == 27

    def test_current_data_is_not_stale(self):
        assert _coverage(date(2026, 8, 20), date(2026, 8, 20)).is_stale is False

    def test_one_day_behind_is_not_stale(self):
        assert _coverage(date(2026, 8, 19), date(2026, 8, 20)).is_stale is False

    def test_two_days_behind_is_stale(self):
        assert _coverage(date(2026, 8, 18), date(2026, 8, 20)).is_stale is True

    def test_the_real_demo_window_is_stale(self):
        assert _coverage(date(2026, 7, 24), date(2026, 8, 20)).is_stale is True


class TestCoverageSection:
    """Tests for the prompt fragment."""

    def test_absent_coverage_yields_nothing(self):
        assert _coverage_section(None) == ""

    def test_stale_coverage_states_the_gap(self):
        text = _coverage_section(_coverage(date(2026, 7, 24), date(2026, 8, 20)))
        assert "27 days before today" in text

    def test_stale_coverage_names_both_bounds(self):
        text = _coverage_section(_coverage(date(2026, 7, 24), date(2026, 8, 20)))
        assert "2026-06-15" in text
        assert "2026-07-24" in text

    def test_stale_coverage_forbids_reporting_a_collapse(self):
        text = _coverage_section(_coverage(date(2026, 7, 24), date(2026, 8, 20)))
        assert "NOT a production stoppage" in text
        assert "collapse" in text

    def test_current_coverage_says_so_without_warnings(self):
        text = _coverage_section(_coverage(date(2026, 8, 20), date(2026, 8, 20)))
        assert "current through today" in text
        assert "collapse" not in text


class TestSystemPrompt:
    """Tests that the prompt carries the section without losing its own content."""

    def test_prompt_without_coverage_still_builds(self):
        assert len(get_system_prompt()) > 1000

    def test_coverage_is_included_when_supplied(self):
        prompt = get_system_prompt(_coverage(date(2026, 7, 24), date(2026, 8, 20)))
        assert "Data Coverage" in prompt

    def test_coverage_is_absent_when_not_supplied(self):
        assert "Data Coverage" not in get_system_prompt()

    def test_prompt_keeps_its_existing_content(self):
        prompt = get_system_prompt(_coverage(date(2026, 7, 24), date(2026, 8, 20)))
        assert "Current Date" in prompt
        assert "run_deviation_analysis" in prompt

    @pytest.mark.parametrize("stale_days", [2, 27, 400])
    def test_any_stale_window_carries_the_warning(self, stale_days):
        from datetime import timedelta

        today = date(2026, 8, 20)
        prompt = get_system_prompt(_coverage(today - timedelta(days=stale_days), today))
        assert "NOT a production stoppage" in prompt

    def test_prompt_stays_above_the_caching_threshold(self):
        # The module docstring targets >1024 tokens for Cortex prompt caching.
        assert len(get_system_prompt()) > 4096
