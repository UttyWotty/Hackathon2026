"""
Data Validation Utilities
=========================

Validation functions for DataFrames, parameters, and data quality checks.

Author: Utku Gulbardak
Date: 2025-10-28
"""

import logging
from typing import Any, List, Optional

import pandas as pd

from .error_handling import DataValidationError

logger = logging.getLogger(__name__)


def validate_dataframe(
    df: pd.DataFrame,
    required_columns: Optional[List[str]] = None,
    min_rows: int = 1,
    name: str = "DataFrame",
) -> bool:
    """
    Validate a DataFrame has required columns and minimum rows.

    Args:
        df: DataFrame to validate
        required_columns: List of required column names (optional)
        min_rows: Minimum number of rows required (default: 1)
        name: Name for error messages

    Returns:
        bool: True if valid

    Raises:
        DataValidationError: If validation fails

    Example:
        >>> validate_dataframe(df, ["EQUIPMENT_CODE", "DATE"], min_rows=10)
    """
    # Check if DataFrame exists and is not None
    if df is None:
        raise DataValidationError(f"{name} is None")

    # Check if DataFrame is actually a DataFrame
    if not isinstance(df, pd.DataFrame):
        raise DataValidationError(f"{name} is not a pandas DataFrame")

    # Check if DataFrame is empty
    if df.empty:
        raise DataValidationError(f"{name} is empty")

    # Check minimum rows
    if len(df) < min_rows:
        raise DataValidationError(
            f"{name} has only {len(df)} rows, minimum required is {min_rows}"
        )

    # Check required columns
    if required_columns:
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise DataValidationError(
                f"{name} is missing required columns: {missing_columns}"
            )

    logger.debug(
        f"✅ {name} validation passed: {len(df)} rows, {len(df.columns)} columns"
    )
    return True


def validate_equipment_codes(
    equipment_codes: Any,
    allow_empty: bool = False,
) -> List[str]:
    """
    Validate and normalize equipment codes.

    Args:
        equipment_codes: Equipment code(s) - can be string, list, or None
        allow_empty: Whether to allow empty/None values

    Returns:
        list: Validated list of equipment codes

    Raises:
        DataValidationError: If validation fails

    Example:
        >>> codes = validate_equipment_codes("EMA-4110")
        >>> codes = validate_equipment_codes(["EMA-4110", "EMA-4109"])
    """
    if equipment_codes is None or equipment_codes == []:
        if allow_empty:
            return []
        raise DataValidationError("Equipment codes cannot be empty")

    # Convert to list if single string
    if isinstance(equipment_codes, str):
        equipment_codes = [equipment_codes]

    # Validate it's a list
    if not isinstance(equipment_codes, list):
        raise DataValidationError(
            f"Equipment codes must be a string or list, got {type(equipment_codes)}"
        )

    # Validate each code is a non-empty string
    validated_codes = []
    for code in equipment_codes:
        if not isinstance(code, str):
            raise DataValidationError(
                f"Equipment code must be string, got {type(code)}: {code}"
            )

        code = code.strip()
        if not code:
            raise DataValidationError("Equipment code cannot be empty string")

        validated_codes.append(code)

    logger.debug(f"✅ Validated {len(validated_codes)} equipment code(s)")
    return validated_codes


def validate_date_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    allow_none: bool = True,
) -> bool:
    """
    Validate date range parameters.

    Args:
        start_date: Start date string
        end_date: End date string
        allow_none: Whether to allow None values

    Returns:
        bool: True if valid

    Raises:
        DataValidationError: If validation fails

    Example:
        >>> validate_date_range("2024-01-01", "2024-12-31")
    """
    if start_date is None and end_date is None:
        if allow_none:
            return True
        raise DataValidationError("Both start_date and end_date cannot be None")

    # Date validation: Basic format check only (YYYY-MM-DD)
    # For now, just check they're strings if provided
    if start_date is not None and not isinstance(start_date, str):
        raise DataValidationError(f"start_date must be string, got {type(start_date)}")

    if end_date is not None and not isinstance(end_date, str):
        raise DataValidationError(f"end_date must be string, got {type(end_date)}")

    logger.debug(f"✅ Date range validated: {start_date} to {end_date}")
    return True


def validate_numeric_parameter(
    value: Any,
    name: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    allow_none: bool = False,
) -> bool:
    """
    Validate a numeric parameter.

    Args:
        value: Value to validate
        name: Parameter name for error messages
        min_value: Minimum allowed value (optional)
        max_value: Maximum allowed value (optional)
        allow_none: Whether to allow None

    Returns:
        bool: True if valid

    Raises:
        DataValidationError: If validation fails

    Example:
        >>> validate_numeric_parameter(0.95, "delta_tolerance", min_value=0, max_value=1)
    """
    if value is None:
        if allow_none:
            return True
        raise DataValidationError(f"{name} cannot be None")

    # Check if numeric
    if not isinstance(value, (int, float)):
        raise DataValidationError(f"{name} must be numeric, got {type(value)}")

    # Check range
    if min_value is not None and value < min_value:
        raise DataValidationError(f"{name} must be >= {min_value}, got {value}")

    if max_value is not None and value > max_value:
        raise DataValidationError(f"{name} must be <= {max_value}, got {value}")

    logger.debug(f"✅ Numeric parameter '{name}' validated: {value}")
    return True


def check_data_quality(
    df: pd.DataFrame,
    column: str,
    max_null_percentage: float = 10.0,
) -> dict:
    """
    Check data quality for a specific column.

    Args:
        df: DataFrame to check
        column: Column name to analyze
        max_null_percentage: Maximum allowed null percentage

    Returns:
        dict: Data quality report

    Example:
        >>> report = check_data_quality(df, "EQUIPMENT_CODE", max_null_percentage=5.0)
        >>> print(f"Null percentage: {report['null_percentage']:.2f}%")
    """
    if column not in df.columns:
        raise DataValidationError(f"Column '{column}' not found in DataFrame")

    total_rows = len(df)
    null_count = df[column].isnull().sum()
    null_percentage = (null_count / total_rows) * 100 if total_rows > 0 else 0

    report = {
        "column": column,
        "total_rows": total_rows,
        "null_count": null_count,
        "null_percentage": null_percentage,
        "unique_values": df[column].nunique(),
        "quality_passed": null_percentage <= max_null_percentage,
    }

    if not report["quality_passed"]:
        logger.warning(
            f"⚠️  Data quality issue: Column '{column}' has {null_percentage:.1f}% nulls "
            f"(max allowed: {max_null_percentage}%)"
        )
    else:
        logger.debug(f"✅ Data quality check passed for column '{column}'")

    return report


def validate_schema(
    df: pd.DataFrame,
    expected_schema: dict,
    strict: bool = False,
) -> bool:
    """
    Validate DataFrame schema against expected types.

    Args:
        df: DataFrame to validate
        expected_schema: Dict mapping column names to expected types
        strict: If True, raise error on mismatch; if False, log warning

    Returns:
        bool: True if schema matches

    Example:
        >>> schema = {
        ...     "EQUIPMENT_CODE": "object",
        ...     "DATE": "datetime64[ns]",
        ...     "SHOTS": "int64"
        ... }
        >>> validate_schema(df, schema)
    """
    mismatches = []

    for column, expected_type in expected_schema.items():
        if column not in df.columns:
            mismatches.append(f"Missing column: {column}")
            continue

        actual_type = str(df[column].dtype)
        if actual_type != expected_type:
            mismatches.append(
                f"Column '{column}': expected {expected_type}, got {actual_type}"
            )

    if mismatches:
        message = "Schema validation failed:\n" + "\n".join(
            f"  - {m}" for m in mismatches
        )
        if strict:
            raise DataValidationError(message)
        else:
            logger.warning(f"⚠️  {message}")
            return False

    logger.debug("✅ Schema validation passed")
    return True


# Module metadata
__version__ = "1.0.0"
__author__ = "Utku Gulbardak"
__all__ = [
    "validate_dataframe",
    "validate_equipment_codes",
    "validate_date_range",
    "validate_numeric_parameter",
    "check_data_quality",
    "validate_schema",
]
