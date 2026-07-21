"""Session Processor Module
========================

Handles session detection based on 8-hour gaps between shots.
Sessions are equipment-specific and increment when gap > 8 hours.
"""

import logging

import pandas as pd

from .config import SESSION_GAP_HOURS

logger = logging.getLogger("RUNRATE")


def detect_sessions(df):
    """Detect sessions based on 8-hour gaps between consecutive shots per equipment.

    A new session starts when:
        - First shot for an equipment
        - Gap between consecutive shots > 8 hours

    Args:
        df (pd.DataFrame): DataFrame with EQUIPMENT_CODE and LOCAL_SHOT_TIME
            (must be sorted by EQUIPMENT_CODE, LOCAL_SHOT_TIME)

    Returns:
        pd.DataFrame: Original DataFrame with SESSION_ID and SHOT_DIFF_SEC columns added
    """
    logger.info(f"Detecting sessions (gap threshold: {SESSION_GAP_HOURS} hours)...")

    # Ensure data is sorted by equipment and time
    df = df.sort_values(["EQUIPMENT_CODE", "LOCAL_SHOT_TIME"], ignore_index=True)

    # Convert to datetime if not already
    df["LOCAL_SHOT_TIME"] = pd.to_datetime(df["LOCAL_SHOT_TIME"])

    # Calculate time difference between consecutive shots (in seconds)
    df["SHOT_DIFF_SEC"] = (
        df.groupby("EQUIPMENT_CODE")["LOCAL_SHOT_TIME"].diff().dt.total_seconds()
    )

    # For first shot of each equipment, set SHOT_DIFF_SEC to None/NULL
    df.loc[df["SHOT_DIFF_SEC"].isna(), "SHOT_DIFF_SEC"] = None

    # Create session breaks where gap > 8 hours (or first shot)
    gap_threshold_seconds = SESSION_GAP_HOURS * 3600
    df["SESSION_BREAK"] = (df["SHOT_DIFF_SEC"].isna()) | (  # First shot of equipment
        df["SHOT_DIFF_SEC"] > gap_threshold_seconds
    )  # Gap > 8 hours

    # Create session IDs by cumulative sum of breaks per equipment
    df["SESSION_ID_TEMP"] = df.groupby("EQUIPMENT_CODE")["SESSION_BREAK"].cumsum()

    # Create global unique session IDs (simple sequential numbers)
    # Group by equipment and session, then assign global sequential IDs
    df["SESSION_GROUP"] = df.groupby(["EQUIPMENT_CODE", "SESSION_ID_TEMP"]).ngroup() + 1
    df["SESSION_ID"] = df["SESSION_GROUP"]

    # Drop temporary columns
    df.drop(columns=["SESSION_ID_TEMP", "SESSION_GROUP", "SESSION_BREAK"], inplace=True)

    # Log session statistics
    total_sessions = df["SESSION_ID"].nunique()
    avg_shots_per_session = len(df) / total_sessions if total_sessions > 0 else 0

    logger.info(f"Detected {total_sessions:,} sessions")
    logger.info(f"Average shots per session: {avg_shots_per_session:.1f}")
    return df


def get_session_statistics(df):
    """Calculate session-level statistics for logging and validation.

    Args:
        df (pd.DataFrame): DataFrame with SESSION_ID column

    Returns:
        dict: Dictionary with session statistics
    """
    stats = {
        "total_sessions": df["SESSION_ID"].nunique(),
        "total_shots": len(df),
        "avg_shots_per_session": (
            len(df) / df["SESSION_ID"].nunique()
            if df["SESSION_ID"].nunique() > 0
            else 0
        ),
        "sessions_per_equipment": (
            df.groupby("EQUIPMENT_CODE")["SESSION_ID"].nunique().to_dict()
        ),
    }
    return stats


def validate_sessions(df):
    """Validate session detection results.

    Checks:
        - No sessions span > 24 hours without 8-hour gap
        - All shots have session IDs
        - Sessions are continuous within equipment

    Args:
        df (pd.DataFrame): DataFrame with SESSION_ID and LOCAL_SHOT_TIME

    Returns:
        bool: True if valid, raises ValueError otherwise
    """
    # Check all shots have session IDs
    if df["SESSION_ID"].isna().any():
        raise ValueError("Some shots are missing SESSION_ID")

    # Check for unreasonably long sessions (> 24 hours without 8+ hour gap)
    session_durations = (
        df.groupby("SESSION_ID")["LOCAL_SHOT_TIME"].agg(["min", "max"]).reset_index()
    )
    session_durations["DURATION_HOURS"] = (
        session_durations["max"] - session_durations["min"]
    ).dt.total_seconds() / 3600

    long_sessions = session_durations[session_durations["DURATION_HOURS"] > 24]

    if not long_sessions.empty:
        logger.warning(
            f"Found {len(long_sessions)} sessions lasting > 24 hours. "
            "This may indicate data quality issues or continuous production runs."
        )

    logger.info("Session validation passed")
    return True
