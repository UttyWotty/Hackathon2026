"""
Time Utilities
==============

Time formatting, parsing, and calculation utilities for analysis modules.

Author: Utku Gulbardak
Date: 2025-10-28
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple

import pandas as pd


def format_time_readable(total_minutes: float) -> str:
    """
    Convert decimal minutes to human-readable format.

    Args:
        total_minutes: Time duration in decimal minutes

    Returns:
        str: Formatted time string (e.g., "2h 15m 30s")

    Examples:
        >>> format_time_readable(125.5)
        "2h 5m 30s"
        >>> format_time_readable(3.25)
        "3m 15s"
        >>> format_time_readable(0.5)
        "30s"
    """
    if pd.isna(total_minutes) or total_minutes == 0:
        return "0s"

    # Convert to total seconds for calculation
    total_seconds = int(total_minutes * 60)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    # Build readable string
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:  # Always show seconds if no other parts
        parts.append(f"{seconds}s")

    return " ".join(parts)


def format_seconds_readable(total_seconds: float) -> str:
    """
    Convert seconds to human-readable format.

    Args:
        total_seconds: Time duration in seconds

    Returns:
        str: Formatted time string

    Example:
        >>> format_seconds_readable(3665)
        "1h 1m 5s"
    """
    return format_time_readable(total_seconds / 60)


def parse_date_string(date_str: str, formats: Optional[list] = None) -> datetime:
    """
    Parse a date string with multiple format attempts.

    Args:
        date_str: Date string to parse
        formats: List of format strings to try (default: common formats)

    Returns:
        datetime: Parsed datetime object

    Raises:
        ValueError: If date string cannot be parsed

    Example:
        >>> date = parse_date_string("2024-01-15")
        >>> print(date)
    """
    if formats is None:
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
        ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    raise ValueError(f"Could not parse date string: {date_str}")


def parse_date_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    default_days_back: int = 30,
) -> Tuple[datetime, datetime]:
    """
    Parse and validate a date range.

    Args:
        start_date: Start date string (optional)
        end_date: End date string (optional)
        default_days_back: Default number of days to look back if dates not provided

    Returns:
        tuple: (start_datetime, end_datetime)

    Example:
        >>> start, end = parse_date_range("2024-01-01", "2024-12-31")
        >>> print(f"Analyzing from {start} to {end}")
    """
    if end_date is None:
        end_dt = datetime.now()
    else:
        end_dt = parse_date_string(end_date)

    if start_date is None:
        start_dt = end_dt - timedelta(days=default_days_back)
    else:
        start_dt = parse_date_string(start_date)

    # Validate order
    if start_dt > end_dt:
        raise ValueError(f"Start date ({start_dt}) is after end date ({end_dt})")

    return start_dt, end_dt


def calculate_business_days(start_date: datetime, end_date: datetime) -> int:
    """
    Calculate number of business days between two dates (excluding weekends).

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        int: Number of business days

    Example:
        >>> start = datetime(2024, 1, 1)
        >>> end = datetime(2024, 1, 15)
        >>> days = calculate_business_days(start, end)
    """
    # Use pandas for business day calculation
    return len(pd.bdate_range(start_date, end_date))


def format_duration_seconds(seconds: float, precision: int = 2) -> str:
    """
    Format a duration in seconds to a readable string with precision.

    Args:
        seconds: Duration in seconds
        precision: Number of decimal places (default: 2)

    Returns:
        str: Formatted duration

    Example:
        >>> format_duration_seconds(3665.5)
        "1h 1m 5.50s"
    """
    if seconds < 60:
        return f"{seconds:.{precision}f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.{precision}f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.{precision}f}h"


def get_timestamp_str(fmt: str = "%Y%m%d_%H%M%S") -> str:
    """
    Get current timestamp as formatted string.

    Args:
        fmt: strftime format string (default: YYYYMMDD_HHMMSS)

    Returns:
        str: Formatted timestamp

    Example:
        >>> timestamp = get_timestamp_str()
        >>> print(timestamp)  # e.g., "20241028_153045"
    """
    return datetime.now().strftime(fmt)


def get_date_range_str(start_date: datetime, end_date: datetime) -> str:
    """
    Format a date range as a string.

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        str: Formatted date range (e.g., "2024-01-01 to 2024-12-31")

    Example:
        >>> range_str = get_date_range_str(start, end)
        >>> print(f"Analyzing: {range_str}")
    """
    return f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"


def is_business_day(date: datetime) -> bool:
    """
    Check if a date is a business day (Monday-Friday).

    Args:
        date: Date to check

    Returns:
        bool: True if business day, False otherwise

    Example:
        >>> if is_business_day(datetime.now()):
        ...     print("Today is a business day")
    """
    return date.weekday() < 5  # Monday = 0, Friday = 4


def get_quarter(date: datetime) -> int:
    """
    Get the quarter (1-4) for a given date.

    Args:
        date: Date to get quarter for

    Returns:
        int: Quarter number (1-4)

    Example:
        >>> quarter = get_quarter(datetime(2024, 7, 15))
        >>> print(f"Q{quarter}")  # Q3
    """
    return (date.month - 1) // 3 + 1


def format_uptime_percentage(uptime_minutes: float, total_minutes: float) -> str:
    """
    Calculate and format uptime percentage.

    Args:
        uptime_minutes: Minutes of uptime
        total_minutes: Total minutes in period

    Returns:
        str: Formatted percentage (e.g., "95.5%")

    Example:
        >>> uptime = format_uptime_percentage(955, 1000)
        >>> print(f"Uptime: {uptime}")
    """
    if total_minutes == 0:
        return "0.0%"

    percentage = (uptime_minutes / total_minutes) * 100
    return f"{percentage:.1f}%"


# Module metadata
__version__ = "1.0.0"
__author__ = "Utku Gulbardak"
__all__ = [
    "format_time_readable",
    "format_seconds_readable",
    "parse_date_string",
    "parse_date_range",
    "calculate_business_days",
    "format_duration_seconds",
    "get_timestamp_str",
    "get_date_range_str",
    "is_business_day",
    "get_quarter",
    "format_uptime_percentage",
]
