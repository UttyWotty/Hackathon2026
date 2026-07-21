"""
Data formatting and validation for Excel reports.

Handles data sanitization and validation to prevent Excel corruption.
"""

import numpy as np
import pandas as pd


def validate_data_for_excel(df_result: pd.DataFrame) -> pd.DataFrame:
    """
    Validate and sanitize data to prevent Excel corruption issues.

    Performs the following operations:
    - Validates required columns exist
    - Limits data size to Excel-safe limits (375K rows)
    - Replaces infinite values with NaN
    - Fills NaN values appropriately (0 for numeric, "" for strings)
    - Clips extreme numeric values to prevent Excel issues

    Args:
        df_result: Raw session analysis DataFrame

    Returns:
        pd.DataFrame: Sanitized DataFrame safe for Excel export

    Raises:
        ValueError: If data is empty or missing required columns

    Example:
        >>> df = process_sessions(raw_data)
        >>> df_clean = validate_data_for_excel(df)
        >>> create_excel_report(df_clean, "output.xlsx")
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

    # Limit data size to prevent Excel corruption
    # Excel limit is ~1M rows, we use 375K for balance with formulas
    if len(df_result) > 375000:
        print(
            f"⚠️  Data has {len(df_result):,} rows. Limiting to 375,000 for Excel stability."
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


def format_excel_number(value: float, decimals: int = 2) -> str:
    """
    Format a numeric value for Excel display.

    Args:
        value: Numeric value to format
        decimals: Number of decimal places

    Returns:
        str: Formatted number string
    """
    if pd.isna(value) or value == 0:
        return "0"
    return f"{value:.{decimals}f}"


def sanitize_sheet_name(name: str, max_length: int = 31) -> str:
    """
    Sanitize worksheet name for Excel compatibility.
    
    Excel worksheet names must be:
    - <= 31 characters
    - Cannot contain: [ ] : * ? / \\
    
    Args:
        name: Proposed sheet name
        max_length: Maximum length (default: 31 for Excel)
        
    Returns:
        str: Sanitized sheet name
    """
    # Remove invalid characters
    invalid_chars = ["[", "]", ":", "*", "?", "/", "\\"]
    for char in invalid_chars:
        name = name.replace(char, "_")

    # Truncate to max length
    if len(name) > max_length:
        name = name[:max_length]

    return name
