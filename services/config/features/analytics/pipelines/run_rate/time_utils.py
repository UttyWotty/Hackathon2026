"""Time Utilities Module
=====================

Extracts time dimensions (day, week, month, year) from LOCAL_SHOT_TIME
for Retool filtering and time-based analysis.
"""

import logging

import pandas as pd

logger = logging.getLogger("RUNRATE")


def extract_time_dimensions(df):
    """Extract day, week, month, and year from LOCAL_SHOT_TIME column.

    Adds columns:
        - DAY: Day of the month (1-31)
        - WEEK: ISO week number (1-53)
        - MONTH: Month number (1-12)
        - YEAR: Year (YYYY)
        - DATE: Date only (YYYY-MM-DD)

    Args:
        df (pd.DataFrame): DataFrame with LOCAL_SHOT_TIME column

    Returns:
        pd.DataFrame: Original DataFrame with time dimension columns added
    """
    logger.info("Extracting time dimensions from LOCAL_SHOT_TIME...")

    # Ensure LOCAL_SHOT_TIME is datetime
    df["LOCAL_SHOT_TIME"] = pd.to_datetime(df["LOCAL_SHOT_TIME"])

    # Extract time dimensions
    df["DAY"] = df["LOCAL_SHOT_TIME"].dt.day
    df["WEEK"] = df["LOCAL_SHOT_TIME"].dt.isocalendar().week
    df["MONTH"] = df["LOCAL_SHOT_TIME"].dt.month
    df["YEAR"] = df["LOCAL_SHOT_TIME"].dt.year
    df["DATE"] = df["LOCAL_SHOT_TIME"].dt.date

    logger.info(
        f"Time dimensions extracted: "
        f"{df['YEAR'].min()}-{df['YEAR'].max()} "
        f"({df['DATE'].nunique()} unique dates)"
    )
    return df


def get_time_range_summary(df):
    """Get summary statistics for time range in the dataset.

    Args:
        df (pd.DataFrame): DataFrame with time dimension columns

    Returns:
        dict: Dictionary with time range statistics
    """
    summary = {
        "min_date": df["LOCAL_SHOT_TIME"].min(),
        "max_date": df["LOCAL_SHOT_TIME"].max(),
        "total_days": (df["LOCAL_SHOT_TIME"].max() - df["LOCAL_SHOT_TIME"].min()).days,
        "unique_dates": df["DATE"].nunique(),
        "unique_weeks": df["WEEK"].nunique(),
        "unique_months": df["MONTH"].nunique(),
        "unique_years": df["YEAR"].nunique(),
    }
    return summary


def validate_time_dimensions(df):
    """Validate extracted time dimensions.

    Checks:
        - All time dimension columns exist
        - Values are within valid ranges
        - No null values in time columns

    Args:
        df (pd.DataFrame): DataFrame with time dimension columns

    Returns:
        bool: True if valid, raises ValueError otherwise
    """
    required_columns = ["DAY", "WEEK", "MONTH", "YEAR", "DATE"]

    # Check all columns exist
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing time dimension columns: {missing_columns}")

    # Check for null values
    for col in required_columns:
        if df[col].isna().any():
            raise ValueError(f"Found null values in {col} column")

    # Validate ranges
    if (df["DAY"] < 1).any() or (df["DAY"] > 31).any():
        raise ValueError("DAY column contains invalid values (must be 1-31)")
    if (df["WEEK"] < 1).any() or (df["WEEK"] > 53).any():
        raise ValueError("WEEK column contains invalid values (must be 1-53)")
    if (df["MONTH"] < 1).any() or (df["MONTH"] > 12).any():
        raise ValueError("MONTH column contains invalid values (must be 1-12)")

    logger.info("Time dimension validation passed")
    return True
