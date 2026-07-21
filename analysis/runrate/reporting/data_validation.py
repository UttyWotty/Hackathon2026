"""
Data validation and sanitization utilities for Excel report generation.

Ensures data integrity and Excel compatibility before report generation.
"""

import numpy as np
import pandas as pd


def validate_data_for_excel(df_result: pd.DataFrame) -> pd.DataFrame:
    """
    Validate and sanitize data to prevent Excel corruption issues.

    Performs:
    - Column validation
    - Size limiting (max 375K rows)
    - Infinite value handling
    - NaN replacement
    - Value clipping

    Args:
        df_result: DataFrame with session data

    Returns:
        Sanitized DataFrame ready for Excel

    Raises:
        ValueError: If data is empty or missing required columns

    Example:
        >>> df_clean = validate_data_for_excel(df_raw)
        >>> print(f"Validated {len(df_clean)} rows")
    """
    if df_result is None or df_result.empty:
        raise ValueError("No data available for Excel report generation")

    # Check for required columns
    required_columns = [
        "SUPPLIER_NAME",
        "EQUIPMENT_CODE",
        "LOCAL_SHOT_TIME",
        "ACTUAL_CT",
    ]
    missing_columns = [col for col in required_columns if col not in df_result.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    # Limit data size to prevent Excel corruption (Excel limit is ~1M rows, we'll use 375K for balance)
    if len(df_result) > 375000:
        print(
            f"⚠️  Data has {len(df_result):,} rows. Limiting to 375,000 for Excel stability with complex formulas."
        )
        df_result = df_result.head(375000)

    # Sanitize data to prevent Excel corruption
    print("🧹 Sanitizing data to prevent Excel corruption...")

    # Replace infinite values with NaN, then fill with appropriate defaults
    df_result = df_result.replace([np.inf, -np.inf], np.nan)

    # Fill numeric NaN values with zeros for Excel compatibility
    numeric_columns = df_result.select_dtypes(include=[np.number]).columns
    for col in numeric_columns:
        df_result[col] = df_result[col].fillna(0)

    # Fill string NaN values with empty strings
    string_columns = df_result.select_dtypes(include=["object"]).columns
    for col in string_columns:
        df_result[col] = df_result[col].fillna("")

    # Ensure all numeric values are finite
    for col in numeric_columns:
        df_result[col] = df_result[col].clip(-1e15, 1e15)  # Prevent extreme values

    print(f"✅ Data sanitized: {len(df_result):,} rows ready for Excel")

    return df_result


def format_time_readable(total_minutes: float) -> str:
    """
    Convert decimal minutes to readable format.

    Args:
        total_minutes: Time in minutes

    Returns:
        Formatted string (e.g., "12 min 30 sec", "2h 15m 30s")

    Example:
        >>> format_time_readable(2.5)
        '2 min 30 sec'
        >>> format_time_readable(125.5)
        '2h 5m 30s'
    """
    if pd.isna(total_minutes) or total_minutes == 0:
        return "0 sec"

    # Convert to total seconds for calculation
    total_seconds = total_minutes * 60

    # Calculate hours, minutes, seconds
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)

    # Format based on magnitude
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes} min {seconds} sec"
    else:
        return f"{seconds} sec"


def format_time_readable_seconds(total_seconds: float) -> str:
    """
    Convert decimal seconds to readable format.

    Args:
        total_seconds: Time in seconds

    Returns:
        Formatted string (e.g., "95 sec", "1 min 35 sec")

    Example:
        >>> format_time_readable_seconds(95)
        '1 min 35 sec'
        >>> format_time_readable_seconds(30)
        '30 sec'
    """
    if pd.isna(total_seconds) or total_seconds == 0:
        return "0 sec"

    # Calculate hours, minutes, seconds
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)

    # Format based on magnitude
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes} min {seconds} sec"
    else:
        return f"{int(total_seconds)} sec"
