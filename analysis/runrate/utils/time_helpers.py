"""
Time formatting utilities for RunRate analysis.

Provides functions to convert time values to human-readable formats.
"""

import pandas as pd


def format_time_readable(total_minutes: float) -> str:
    """
    Convert decimal minutes to readable format (e.g., "12 min 30 sec").

    Args:
        total_minutes: Time in minutes (can be decimal)

    Returns:
        str: Human-readable time format

    Examples:
        >>> format_time_readable(1.5)
        '1 min 30 sec'
        >>> format_time_readable(125.0)
        '2h 5m 0s'
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
    Convert decimal seconds to readable format (e.g., "95 sec" or "1 min 35 sec").

    Args:
        total_seconds: Time in seconds (can be decimal)

    Returns:
        str: Human-readable time format

    Examples:
        >>> format_time_readable_seconds(95.5)
        '1 min 35 sec'
        >>> format_time_readable_seconds(45.0)
        '45 sec'
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
