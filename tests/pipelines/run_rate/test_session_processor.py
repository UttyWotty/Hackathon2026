"""Unit tests for the run_rate session_processor module.
Covers detect_sessions, get_session_statistics, and validate_sessions
with happy-path, boundary, and error cases.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from services.config.features.analytics.pipelines.run_rate.session_processor import (
    detect_sessions,
    get_session_statistics,
    validate_sessions,
)

SESSION_GAP_SECONDS = 8 * 3600  # 28800


# ===================================================================
# detect_sessions
# ===================================================================


class TestDetectSessions:
    """Tests for detect_sessions."""

    def test_happy_path_creates_session_id(self, raw_shot_df: pd.DataFrame) -> None:
        """SESSION_ID and SHOT_DIFF_SEC columns are created."""
        result = detect_sessions(raw_shot_df.copy())
        assert "SESSION_ID" in result.columns
        assert "SHOT_DIFF_SEC" in result.columns

    def test_no_gaps_single_session(self) -> None:
        """All shots within threshold produce a single session per equipment."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"] * 5,
                "LOCAL_SHOT_TIME": [base + timedelta(seconds=i * 10) for i in range(5)],
                "CT": [10.0] * 5,
            }
        )
        result = detect_sessions(df)
        assert result["SESSION_ID"].nunique() == 1

    def test_exact_boundary_no_break(self) -> None:
        """Gap of exactly 28800s (8h) does NOT trigger a session break."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A", "EQ_A"],
                "LOCAL_SHOT_TIME": [
                    base,
                    base + timedelta(seconds=SESSION_GAP_SECONDS),
                ],
                "CT": [10.0, 10.0],
            }
        )
        result = detect_sessions(df)
        assert result["SESSION_ID"].nunique() == 1

    def test_one_second_over_boundary_breaks(self) -> None:
        """Gap of 28801s (8h + 1s) DOES trigger a session break."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A", "EQ_A"],
                "LOCAL_SHOT_TIME": [
                    base,
                    base + timedelta(seconds=SESSION_GAP_SECONDS + 1),
                ],
                "CT": [10.0, 10.0],
            }
        )
        result = detect_sessions(df)
        assert result["SESSION_ID"].nunique() == 2

    def test_multi_equipment_isolation(self) -> None:
        """Sessions are isolated per equipment -- no cross-equipment leakage."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A", "EQ_A", "EQ_B", "EQ_B"],
                "LOCAL_SHOT_TIME": [
                    base,
                    base + timedelta(seconds=10),
                    base,
                    base + timedelta(seconds=10),
                ],
                "CT": [10.0] * 4,
            }
        )
        result = detect_sessions(df)
        # 2 equipment, each with 1 session = 2 unique session IDs
        assert result["SESSION_ID"].nunique() == 2
        # Sessions for different equipment have different IDs
        eq_a_sessions = result[result["EQUIPMENT_CODE"] == "EQ_A"][
            "SESSION_ID"
        ].unique()
        eq_b_sessions = result[result["EQUIPMENT_CODE"] == "EQ_B"][
            "SESSION_ID"
        ].unique()
        assert not set(eq_a_sessions) & set(eq_b_sessions)

    def test_single_shot(self, single_shot_df: pd.DataFrame) -> None:
        """A single shot is assigned a session with no errors."""
        result = detect_sessions(single_shot_df.copy())
        assert len(result) == 1
        assert result["SESSION_ID"].notna().all()

    def test_unsorted_input(self) -> None:
        """Input not sorted by time is sorted internally and produces correct sessions."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        times = [
            base + timedelta(seconds=30),
            base + timedelta(seconds=10),
            base + timedelta(seconds=0),
            base + timedelta(seconds=20),
        ]
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"] * 4,
                "LOCAL_SHOT_TIME": times,
                "CT": [10.0] * 4,
            }
        )
        result = detect_sessions(df)
        assert result["SESSION_ID"].nunique() == 1
        # Verify sorted order
        assert result["LOCAL_SHOT_TIME"].is_monotonic_increasing

    def test_first_shot_diff_is_none(self) -> None:
        """First shot of each equipment has SHOT_DIFF_SEC == None."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A", "EQ_A", "EQ_B"],
                "LOCAL_SHOT_TIME": [
                    base,
                    base + timedelta(seconds=10),
                    base,
                ],
                "CT": [10.0] * 3,
            }
        )
        result = detect_sessions(df)
        # First shot per equipment should have None/NaN (pandas stores None as NaN)
        for eq in ["EQ_A", "EQ_B"]:
            eq_data = result[result["EQUIPMENT_CODE"] == eq].sort_values(
                "LOCAL_SHOT_TIME"
            )
            assert pd.isna(eq_data["SHOT_DIFF_SEC"].iloc[0])

    def test_sessioned_df_has_multiple_sessions(
        self, sessioned_df: pd.DataFrame
    ) -> None:
        """The sessioned_df fixture produces at least 4 sessions (2 per equipment)."""
        assert sessioned_df["SESSION_ID"].nunique() >= 4


# ===================================================================
# get_session_statistics
# ===================================================================


class TestGetSessionStatistics:
    """Tests for get_session_statistics."""

    def test_basic_stats(self, sessioned_df: pd.DataFrame) -> None:
        """Returns dict with expected keys and positive values."""
        stats = get_session_statistics(sessioned_df)
        assert "total_sessions" in stats
        assert "total_shots" in stats
        assert "avg_shots_per_session" in stats
        assert stats["total_sessions"] >= 1
        assert stats["total_shots"] == len(sessioned_df)

    def test_multi_equipment_counts(self, sessioned_df: pd.DataFrame) -> None:
        """sessions_per_equipment has entries for both equipments."""
        stats = get_session_statistics(sessioned_df)
        assert "EQ_A" in stats["sessions_per_equipment"]
        assert "EQ_B" in stats["sessions_per_equipment"]

    def test_avg_calculation(self, sessioned_df: pd.DataFrame) -> None:
        """avg_shots_per_session == total_shots / total_sessions."""
        stats = get_session_statistics(sessioned_df)
        expected = stats["total_shots"] / stats["total_sessions"]
        assert abs(stats["avg_shots_per_session"] - expected) < 1e-6


# ===================================================================
# validate_sessions
# ===================================================================


class TestValidateSessions:
    """Tests for validate_sessions."""

    def test_valid_data_passes(self, sessioned_df: pd.DataFrame) -> None:
        """Properly sessioned data passes validation."""
        assert validate_sessions(sessioned_df) is True

    def test_nan_session_id_raises(self, sessioned_df: pd.DataFrame) -> None:
        """Raises ValueError when SESSION_ID contains NaN."""
        df = sessioned_df.copy()
        df.loc[df.index[0], "SESSION_ID"] = np.nan
        with pytest.raises(ValueError, match="missing SESSION_ID"):
            validate_sessions(df)

    def test_long_session_warns_but_passes(self) -> None:
        """Session > 24h logs a warning but still returns True."""
        base = datetime(2025, 6, 1, 0, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"] * 3,
                "LOCAL_SHOT_TIME": [
                    base,
                    base + timedelta(hours=12),
                    base + timedelta(hours=25),
                ],
                "SESSION_ID": [1, 1, 1],
            }
        )
        # Should not raise, just warn
        assert validate_sessions(df) is True
