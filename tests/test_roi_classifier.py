"""
Tests for CycleTimeClassifier used in ROI analysis.

Verifies that cycle times are correctly classified as WITHIN, FASTER, SLOWER,
or OTHER based on the delta tolerance from ROIAnalysisConfig. Covers happy path
with standard tolerance, boundary values at tolerance edges, and edge cases.
"""

import pandas as pd

from analysis.roi.classifier import CycleTimeClassifier
from analysis.roi.config import ROIAnalysisConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DEFAULT_TOLERANCE: float = 0.05  # 5% default from ROIAnalysisConfig


def _make_df(ct_values: list[float], approved_values: list[float]) -> pd.DataFrame:
    """Build a minimal DataFrame with CT and APPROVED_CT columns."""
    return pd.DataFrame({"CT": ct_values, "APPROVED_CT": approved_values})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCycleTimeClassifierInit:
    """Tests for CycleTimeClassifier initialization."""

    def test_init_with_default_config(self) -> None:
        """Classifier stores the provided config object."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        assert classifier.config is config

    def test_init_with_custom_tolerance(self) -> None:
        """Classifier accepts a custom delta tolerance."""
        config = ROIAnalysisConfig(delta_tolerance=0.10)
        classifier = CycleTimeClassifier(config)
        assert classifier.config.delta_tolerance == 0.10


class TestClassifyWithinTolerance:
    """Tests for CT values that fall WITHIN the approved tolerance."""

    def test_exact_match(self) -> None:
        """CT exactly equal to APPROVED_CT is classified as WITHIN."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        df = _make_df([10.0], [10.0])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "WITHIN"

    def test_slightly_above_within_tolerance(self) -> None:
        """CT slightly above APPROVED_CT but inside 5% band is WITHIN."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = 100.0
        ct = approved * (1 + DEFAULT_TOLERANCE * 0.5)  # 2.5% above
        df = _make_df([ct], [approved])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "WITHIN"

    def test_slightly_below_within_tolerance(self) -> None:
        """CT slightly below APPROVED_CT but inside 5% band is WITHIN."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = 100.0
        ct = approved * (1 - DEFAULT_TOLERANCE * 0.5)  # 2.5% below
        df = _make_df([ct], [approved])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "WITHIN"

    def test_at_upper_boundary(self) -> None:
        """CT exactly at the upper tolerance boundary is WITHIN (abs diff == threshold)."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = 100.0
        ct = approved * (1 + DEFAULT_TOLERANCE)  # Exactly at +5%
        df = _make_df([ct], [approved])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "WITHIN"

    def test_at_lower_boundary(self) -> None:
        """CT exactly at the lower tolerance boundary is WITHIN (abs diff == threshold)."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = 100.0
        ct = approved * (1 - DEFAULT_TOLERANCE)  # Exactly at -5%
        df = _make_df([ct], [approved])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "WITHIN"


class TestClassifySlower:
    """Tests for CT values classified as SLOWER."""

    def test_clearly_slower(self) -> None:
        """CT 20% above APPROVED_CT is classified as SLOWER."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = 100.0
        ct = 120.0  # 20% above
        df = _make_df([ct], [approved])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "SLOWER"

    def test_just_above_upper_boundary(self) -> None:
        """CT just beyond the upper tolerance boundary is SLOWER."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = 100.0
        ct = approved * (1 + DEFAULT_TOLERANCE) + 0.01  # Just past +5%
        df = _make_df([ct], [approved])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "SLOWER"

    def test_very_slow_cycle_time(self) -> None:
        """CT double the APPROVED_CT is classified as SLOWER."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        df = _make_df([200.0], [100.0])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "SLOWER"


class TestClassifyFaster:
    """Tests for CT values classified as FASTER."""

    def test_clearly_faster(self) -> None:
        """CT 20% below APPROVED_CT is classified as FASTER."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = 100.0
        ct = 80.0  # 20% below
        df = _make_df([ct], [approved])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "FASTER"

    def test_just_below_lower_boundary(self) -> None:
        """CT just beyond the lower tolerance boundary is FASTER."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = 100.0
        ct = approved * (1 - DEFAULT_TOLERANCE) - 0.01  # Just past -5%
        df = _make_df([ct], [approved])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "FASTER"

    def test_very_fast_cycle_time(self) -> None:
        """CT half the APPROVED_CT is classified as FASTER."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        df = _make_df([50.0], [100.0])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "FASTER"


class TestClassifyMultipleRows:
    """Tests for classifying multiple rows in a single DataFrame."""

    def test_mixed_classifications(self) -> None:
        """DataFrame with mixed CT values gets correct per-row classification."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = [100.0, 100.0, 100.0]
        ct = [100.0, 120.0, 80.0]  # WITHIN, SLOWER, FASTER
        df = _make_df(ct, approved)
        result = classifier.classify(df)

        categories = result["CT_CATEGORY"].tolist()
        assert categories[0] == "WITHIN"
        assert categories[1] == "SLOWER"
        assert categories[2] == "FASTER"

    def test_all_within(self) -> None:
        """All rows within tolerance are classified as WITHIN."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = [100.0, 200.0, 50.0]
        ct = [100.0, 200.0, 50.0]  # All exact matches
        df = _make_df(ct, approved)
        result = classifier.classify(df)

        assert (result["CT_CATEGORY"] == "WITHIN").all()

    def test_different_approved_values(self) -> None:
        """Classification is relative to each row's own APPROVED_CT."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = [10.0, 200.0]
        ct = [10.0, 250.0]  # WITHIN for 10, SLOWER for 200
        df = _make_df(ct, approved)
        result = classifier.classify(df)

        assert result["CT_CATEGORY"].iloc[0] == "WITHIN"
        assert result["CT_CATEGORY"].iloc[1] == "SLOWER"


class TestClassifyCustomTolerance:
    """Tests with non-default delta tolerance values."""

    def test_wider_tolerance_reclassifies_to_within(self) -> None:
        """A value that is SLOWER at 5% tolerance becomes WITHIN at 25% tolerance."""
        narrow_config = ROIAnalysisConfig(delta_tolerance=0.05)
        wide_config = ROIAnalysisConfig(delta_tolerance=0.25)

        approved = 100.0
        ct = 115.0  # 15% above

        narrow_result = CycleTimeClassifier(narrow_config).classify(
            _make_df([ct], [approved])
        )
        wide_result = CycleTimeClassifier(wide_config).classify(
            _make_df([ct], [approved])
        )

        assert narrow_result["CT_CATEGORY"].iloc[0] == "SLOWER"
        assert wide_result["CT_CATEGORY"].iloc[0] == "WITHIN"

    def test_zero_tolerance(self) -> None:
        """With zero tolerance, only exact matches are WITHIN."""
        config = ROIAnalysisConfig(delta_tolerance=0.0)
        classifier = CycleTimeClassifier(config)

        df = _make_df([100.0, 100.01], [100.0, 100.0])
        result = classifier.classify(df)

        assert result["CT_CATEGORY"].iloc[0] == "WITHIN"
        assert result["CT_CATEGORY"].iloc[1] == "SLOWER"

    def test_ten_percent_tolerance(self) -> None:
        """With 10% tolerance, 9% deviation is WITHIN."""
        config = ROIAnalysisConfig(delta_tolerance=0.10)
        classifier = CycleTimeClassifier(config)

        approved = 100.0
        ct = 109.0  # 9% above, within 10% band
        df = _make_df([ct], [approved])
        result = classifier.classify(df)

        assert result["CT_CATEGORY"].iloc[0] == "WITHIN"


class TestClassifyEdgeCases:
    """Tests for edge cases and unusual input values."""

    def test_ct_category_column_added(self) -> None:
        """Classify adds CT_CATEGORY column to the DataFrame."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        df = _make_df([10.0], [10.0])
        result = classifier.classify(df)
        assert "CT_CATEGORY" in result.columns

    def test_original_columns_preserved(self) -> None:
        """Classify preserves the original CT and APPROVED_CT columns."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        df = _make_df([10.0], [10.0])
        result = classifier.classify(df)
        assert "CT" in result.columns
        assert "APPROVED_CT" in result.columns

    def test_returns_dataframe(self) -> None:
        """Classify returns a pandas DataFrame."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        df = _make_df([10.0], [10.0])
        result = classifier.classify(df)
        assert isinstance(result, pd.DataFrame)

    def test_large_approved_ct(self) -> None:
        """Classification works correctly with large APPROVED_CT values."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = 10000.0
        ct = approved * 1.5  # 50% above
        df = _make_df([ct], [approved])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "SLOWER"

    def test_small_approved_ct(self) -> None:
        """Classification works correctly with small APPROVED_CT values."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        approved = 0.5
        ct = 0.5  # Exact match
        df = _make_df([ct], [approved])
        result = classifier.classify(df)
        assert result["CT_CATEGORY"].iloc[0] == "WITHIN"

    def test_empty_dataframe(self) -> None:
        """Classify handles an empty DataFrame without error."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        df = _make_df([], [])
        result = classifier.classify(df)
        assert len(result) == 0
        assert "CT_CATEGORY" in result.columns

    def test_single_row(self) -> None:
        """Classify handles a single-row DataFrame."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        df = _make_df([50.0], [50.0])
        result = classifier.classify(df)
        assert len(result) == 1
        assert result["CT_CATEGORY"].iloc[0] == "WITHIN"

    def test_many_rows(self) -> None:
        """Classify handles a large number of rows."""
        config = ROIAnalysisConfig()
        classifier = CycleTimeClassifier(config)
        n = 1000
        approved = [100.0] * n
        ct = [100.0] * n
        df = _make_df(ct, approved)
        result = classifier.classify(df)
        assert len(result) == n
        assert (result["CT_CATEGORY"] == "WITHIN").all()
