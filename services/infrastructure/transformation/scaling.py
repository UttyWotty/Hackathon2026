"""Feature-scaling helpers for the transform endpoint's numeric operations.

Provides pure min-max normalization and z-score standardization over selected
DataFrame columns, each returning the transformed frame plus per-run statistics.
Kept separate from the transformer and router so the scaling math stays testable
and free of I/O.
"""

import logging
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

NORMALIZE_METHOD = "min_max"
STANDARDIZE_METHOD = "z_score"
# Value assigned to a column whose scaled result is otherwise undefined: the
# min-max span is zero, or the standard deviation is zero or undefined (as for a
# single-row column, where the sample std is NaN rather than 0).
CONSTANT_COLUMN_FILL = 0.0


def _existing_columns(df: pd.DataFrame, columns: List[str]) -> List[str]:
    """Return the requested columns that are actually present in the frame."""
    return [col for col in columns if col in df.columns]


def normalize_columns(
    df: pd.DataFrame, columns: List[str]
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Min-max scale the given columns into the [0, 1] range.

    Args:
        df: Input DataFrame (not mutated).
        columns: Columns to scale; missing columns are skipped.

    Returns:
        tuple: (transformed DataFrame, statistics with scaled columns and method).
    """
    df_result = df.copy()
    scaled: List[str] = []
    for col in _existing_columns(df_result, columns):
        col_min = df_result[col].min()
        col_span = df_result[col].max() - col_min
        if col_span == 0:
            df_result[col] = CONSTANT_COLUMN_FILL
        else:
            df_result[col] = (df_result[col] - col_min) / col_span
        scaled.append(col)
    return df_result, {"scaled_columns": scaled, "method": NORMALIZE_METHOD}


def standardize_columns(
    df: pd.DataFrame, columns: List[str]
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Z-score standardize the given columns to mean 0 and unit variance.

    Args:
        df: Input DataFrame (not mutated).
        columns: Columns to scale; missing columns are skipped.

    Returns:
        tuple: (transformed DataFrame, statistics with scaled columns and method).
    """
    df_result = df.copy()
    scaled: List[str] = []
    for col in _existing_columns(df_result, columns):
        col_mean = df_result[col].mean()
        col_std = df_result[col].std()
        if col_std == 0 or pd.isna(col_std):
            df_result[col] = CONSTANT_COLUMN_FILL
        else:
            df_result[col] = (df_result[col] - col_mean) / col_std
        scaled.append(col)
    return df_result, {"scaled_columns": scaled, "method": STANDARDIZE_METHOD}
