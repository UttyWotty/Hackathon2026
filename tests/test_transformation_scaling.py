"""Unit tests for the pure feature-scaling helpers used by /transformation/transform.

Exercises min-max normalization and z-score standardization directly on small
DataFrames, covering the happy path, constant-column edge cases, and that missing
columns are skipped rather than raising. No I/O and no mocks.
"""

import pandas as pd  # type: ignore[import-untyped]

from services.infrastructure.transformation.scaling import (
    CONSTANT_COLUMN_FILL,
    NORMALIZE_METHOD,
    STANDARDIZE_METHOD,
    normalize_columns,
    standardize_columns,
)

ABS_TOLERANCE = 1e-9


def test_normalize_columns_scales_to_unit_range() -> None:
    """Min-max scaling maps the min to 0.0 and the max to 1.0."""
    df = pd.DataFrame({"v": [10.0, 20.0, 30.0]})
    result, stats = normalize_columns(df, ["v"])
    assert result["v"].tolist() == [0.0, 0.5, 1.0]
    assert stats == {"scaled_columns": ["v"], "method": NORMALIZE_METHOD}


def test_normalize_columns_constant_column_uses_fill() -> None:
    """A zero-span column collapses to the constant fill instead of dividing by zero."""
    df = pd.DataFrame({"v": [7.0, 7.0, 7.0]})
    result, _ = normalize_columns(df, ["v"])
    assert result["v"].tolist() == [CONSTANT_COLUMN_FILL] * 3


def test_normalize_columns_skips_missing_columns() -> None:
    """An absent column is ignored and leaves the frame otherwise untouched."""
    df = pd.DataFrame({"v": [1.0, 2.0]})
    result, stats = normalize_columns(df, ["missing"])
    assert stats["scaled_columns"] == []
    assert result["v"].tolist() == [1.0, 2.0]


def test_normalize_columns_does_not_mutate_input() -> None:
    """The source DataFrame is copied, not modified in place."""
    df = pd.DataFrame({"v": [10.0, 20.0]})
    normalize_columns(df, ["v"])
    assert df["v"].tolist() == [10.0, 20.0]


def test_standardize_columns_yields_zero_mean() -> None:
    """Z-score standardization centers the column on zero mean."""
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0, 4.0]})
    result, stats = standardize_columns(df, ["v"])
    assert abs(result["v"].mean()) < ABS_TOLERANCE
    assert stats == {"scaled_columns": ["v"], "method": STANDARDIZE_METHOD}


def test_standardize_columns_constant_column_uses_fill() -> None:
    """A zero-variance column collapses to the constant fill, not NaN."""
    df = pd.DataFrame({"v": [5.0, 5.0, 5.0]})
    result, _ = standardize_columns(df, ["v"])
    assert result["v"].tolist() == [CONSTANT_COLUMN_FILL] * 3


def test_standardize_columns_single_row_uses_fill() -> None:
    """A single-row column has an undefined (NaN) sample std and uses the fill.

    Guards against emitting NaN, which serializes to the invalid JSON token
    ``NaN`` in the /transformation/transform response.
    """
    df = pd.DataFrame({"v": [5.0]})
    result, _ = standardize_columns(df, ["v"])
    assert result["v"].tolist() == [CONSTANT_COLUMN_FILL]
