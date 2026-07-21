"""
Data Cleaning and Validation Module.

Features:
- Remove duplicates
- Handle missing values
- Data type validation
- Outlier detection and handling
- Data quality checks

Author: Utku Gulbardak
Date: 2025-11-12
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataCleaner:
    """
    Data Cleaning and Validation.

    Provides data cleaning and quality validation capabilities.
    """

    def __init__(self):
        """Initialize Data Cleaner."""
        self.stats = {
            "rows_removed": 0,
            "duplicates_removed": 0,
            "nulls_handled": 0,
            "outliers_handled": 0,
            "validations_performed": 0,
        }
        logger.info("✅ Data Cleaner initialized")

    def remove_duplicates(
        self,
        df: pd.DataFrame,
        subset: Optional[List[str]] = None,
        keep: str = "first",
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Remove duplicate rows from DataFrame.

        Args:
            df: Input DataFrame
            subset: Column names to check for duplicates (None = all columns)
            keep: 'first', 'last', or False (remove all duplicates)

        Returns:
            tuple: (cleaned DataFrame, statistics)
        """
        original_count = len(df)

        df_clean = df.drop_duplicates(subset=subset, keep=keep)

        duplicates_removed = original_count - len(df_clean)
        self.stats["duplicates_removed"] += duplicates_removed

        return df_clean, {
            "original_rows": original_count,
            "final_rows": len(df_clean),
            "duplicates_removed": duplicates_removed,
            "duplicate_percentage": (
                round(duplicates_removed / original_count * 100, 2)
                if original_count > 0
                else 0
            ),
        }

    def handle_missing_values(
        self,
        df: pd.DataFrame,
        strategy: str = "drop",
        columns: Optional[List[str]] = None,
        fill_value: Any = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Handle missing values in DataFrame.

        Args:
            df: Input DataFrame
            strategy: 'drop', 'fill', 'forward_fill', 'backward_fill', 'mean', 'median', 'mode'
            columns: Specific columns to handle (None = all columns)
            fill_value: Value to use for 'fill' strategy

        Returns:
            tuple: (cleaned DataFrame, statistics)
        """
        cols_to_check = columns if columns else df.columns.tolist()
        original_nulls = df[cols_to_check].isnull().sum().sum()

        df_clean = df.copy()

        if strategy == "drop":
            df_clean = df_clean.dropna(subset=cols_to_check)
        elif strategy == "fill":
            df_clean[cols_to_check] = df_clean[cols_to_check].fillna(fill_value)
        elif strategy == "forward_fill":
            df_clean[cols_to_check] = df_clean[cols_to_check].fillna(method="ffill")
        elif strategy == "backward_fill":
            df_clean[cols_to_check] = df_clean[cols_to_check].fillna(method="bfill")
        elif strategy == "mean":
            for col in cols_to_check:
                if pd.api.types.is_numeric_dtype(df_clean[col]):
                    df_clean[col] = df_clean[col].fillna(df_clean[col].mean())
        elif strategy == "median":
            for col in cols_to_check:
                if pd.api.types.is_numeric_dtype(df_clean[col]):
                    df_clean[col] = df_clean[col].fillna(df_clean[col].median())
        elif strategy == "mode":
            for col in cols_to_check:
                mode_val = df_clean[col].mode()
                if len(mode_val) > 0:
                    df_clean[col] = df_clean[col].fillna(mode_val[0])
        else:
            raise ValueError(
                f"Unknown strategy: {strategy}. Use 'drop', 'fill', 'forward_fill', 'backward_fill', 'mean', 'median', or 'mode'"
            )

        final_nulls = df_clean[cols_to_check].isnull().sum().sum()
        nulls_handled = original_nulls - final_nulls
        self.stats["nulls_handled"] += nulls_handled

        return df_clean, {
            "original_nulls": int(original_nulls),
            "final_nulls": int(final_nulls),
            "nulls_handled": int(nulls_handled),
            "original_rows": len(df),
            "final_rows": len(df_clean),
            "strategy": strategy,
        }

    def detect_outliers(
        self,
        df: pd.DataFrame,
        columns: List[str],
        method: str = "iqr",
        threshold: float = 1.5,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Detect outliers in numerical columns.

        Args:
            df: Input DataFrame
            columns: Columns to check for outliers
            method: 'iqr' (Interquartile Range) or 'zscore'
            threshold: IQR multiplier (default 1.5) or Z-score threshold (default 3)

        Returns:
            tuple: (DataFrame with outlier flags, statistics)
        """
        df_result = df.copy()
        outlier_stats = {}

        for col in columns:
            if col not in df.columns:
                logger.warning(f"Column '{col}' not found in DataFrame")
                continue

            if not pd.api.types.is_numeric_dtype(df[col]):
                logger.warning(f"Column '{col}' is not numeric, skipping")
                continue

            if method == "iqr":
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - threshold * IQR
                upper_bound = Q3 + threshold * IQR

                outliers = (df[col] < lower_bound) | (df[col] > upper_bound)

                outlier_stats[col] = {
                    "method": "iqr",
                    "outlier_count": int(outliers.sum()),
                    "outlier_percentage": round(outliers.sum() / len(df) * 100, 2),
                    "lower_bound": float(lower_bound),
                    "upper_bound": float(upper_bound),
                    "Q1": float(Q1),
                    "Q3": float(Q3),
                    "IQR": float(IQR),
                }

            elif method == "zscore":
                mean = df[col].mean()
                std = df[col].std()

                if std == 0:
                    outliers = pd.Series([False] * len(df), index=df.index)
                else:
                    z_scores = np.abs((df[col] - mean) / std)
                    outliers = z_scores > threshold

                outlier_stats[col] = {
                    "method": "zscore",
                    "outlier_count": int(outliers.sum()),
                    "outlier_percentage": round(outliers.sum() / len(df) * 100, 2),
                    "mean": float(mean),
                    "std": float(std),
                    "threshold": threshold,
                }

            else:
                raise ValueError(f"Unknown method: {method}. Use 'iqr' or 'zscore'")

            df_result[f"{col}_outlier"] = outliers

        total_outliers = sum(stats["outlier_count"] for stats in outlier_stats.values())

        return df_result, {
            "total_outliers_detected": total_outliers,
            "columns_checked": len(columns),
            "outlier_details": outlier_stats,
        }

    def remove_outliers(
        self,
        df: pd.DataFrame,
        columns: List[str],
        method: str = "iqr",
        threshold: float = 1.5,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Remove outliers from DataFrame.

        Args:
            df: Input DataFrame
            columns: Columns to check for outliers
            method: 'iqr' or 'zscore'
            threshold: IQR multiplier or Z-score threshold

        Returns:
            tuple: (cleaned DataFrame, statistics)
        """
        df_with_flags, detection_stats = self.detect_outliers(
            df, columns, method, threshold
        )

        # Remove rows where any column has an outlier
        outlier_columns = [
            f"{col}_outlier"
            for col in columns
            if f"{col}_outlier" in df_with_flags.columns
        ]

        if outlier_columns:
            mask = df_with_flags[outlier_columns].any(axis=1)
            df_clean = df_with_flags[~mask].drop(columns=outlier_columns)
        else:
            df_clean = df

        outliers_removed = len(df) - len(df_clean)
        self.stats["outliers_handled"] += outliers_removed

        return df_clean, {
            "original_rows": len(df),
            "final_rows": len(df_clean),
            "outliers_removed": outliers_removed,
            "outlier_percentage": (
                round(outliers_removed / len(df) * 100, 2) if len(df) > 0 else 0
            ),
            **detection_stats,
        }

    def validate_data_types(
        self, df: pd.DataFrame, schema: Dict[str, str]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate DataFrame columns match expected data types.

        Args:
            df: Input DataFrame
            schema: Dict of {column_name: expected_type}
                    Types: 'int', 'float', 'str', 'datetime', 'bool'

        Returns:
            tuple: (is_valid, validation_report)
        """
        validation_report = {
            "is_valid": True,
            "columns_checked": len(schema),
            "errors": [],
            "warnings": [],
        }

        for col, expected_type in schema.items():
            if col not in df.columns:
                validation_report["errors"].append(
                    {"column": col, "error": "Column not found in DataFrame"}
                )
                validation_report["is_valid"] = False
                continue

            actual_dtype = df[col].dtype

            type_valid = False
            if expected_type == "int" and pd.api.types.is_integer_dtype(actual_dtype):
                type_valid = True
            elif expected_type == "float" and pd.api.types.is_float_dtype(actual_dtype):
                type_valid = True
            elif expected_type == "str" and pd.api.types.is_string_dtype(actual_dtype):
                type_valid = True
            elif expected_type == "datetime" and pd.api.types.is_datetime64_any_dtype(
                actual_dtype
            ):
                type_valid = True
            elif expected_type == "bool" and pd.api.types.is_bool_dtype(actual_dtype):
                type_valid = True

            if not type_valid:
                validation_report["errors"].append(
                    {
                        "column": col,
                        "expected_type": expected_type,
                        "actual_type": str(actual_dtype),
                        "error": f"Type mismatch: expected {expected_type}, got {actual_dtype}",
                    }
                )
                validation_report["is_valid"] = False

        self.stats["validations_performed"] += 1

        return validation_report["is_valid"], validation_report

    def check_data_quality(
        self, df: pd.DataFrame, checks: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive data quality check.

        Args:
            df: Input DataFrame
            checks: Optional custom checks

        Returns:
            dict: Quality report
        """
        report = {
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "memory_usage_mb": round(
                df.memory_usage(deep=True).sum() / (1024 * 1024), 2
            ),
            "duplicates": {
                "count": int(df.duplicated().sum()),
                "percentage": (
                    round(df.duplicated().sum() / len(df) * 100, 2)
                    if len(df) > 0
                    else 0
                ),
            },
            "missing_values": {},
            "column_stats": {},
        }

        # Check missing values per column
        for col in df.columns:
            null_count = df[col].isnull().sum()
            if null_count > 0:
                report["missing_values"][col] = {
                    "count": int(null_count),
                    "percentage": round(null_count / len(df) * 100, 2),
                }

        # Column statistics
        for col in df.columns:
            col_stats = {
                "dtype": str(df[col].dtype),
                "unique_values": int(df[col].nunique()),
            }

            if pd.api.types.is_numeric_dtype(df[col]):
                col_stats.update(
                    {
                        "min": (
                            float(df[col].min()) if not df[col].isnull().all() else None
                        ),
                        "max": (
                            float(df[col].max()) if not df[col].isnull().all() else None
                        ),
                        "mean": (
                            float(df[col].mean())
                            if not df[col].isnull().all()
                            else None
                        ),
                        "median": (
                            float(df[col].median())
                            if not df[col].isnull().all()
                            else None
                        ),
                        "std": (
                            float(df[col].std()) if not df[col].isnull().all() else None
                        ),
                    }
                )

            report["column_stats"][col] = col_stats

        return report

    def get_stats(self) -> Dict[str, Any]:
        """Get cleaner statistics."""
        return {
            "status": "success",
            **self.stats,
        }


# Global data cleaner instance
_data_cleaner: Optional[DataCleaner] = None


def get_data_cleaner() -> DataCleaner:
    """
    Get global data cleaner instance.

    Returns:
        DataCleaner: Global data cleaner instance
    """
    global _data_cleaner
    if _data_cleaner is None:
        _data_cleaner = DataCleaner()
    return _data_cleaner
