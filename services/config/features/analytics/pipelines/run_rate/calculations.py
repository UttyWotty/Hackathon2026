"""Calculations Module
===================

Handles all metric calculations for run rate analysis:
    - Mode CT per session
    - Stop detection (+-5% from mode CT)
    - Run efficiency per session
    - Total run time per session
"""

import logging

import numpy as np
import pandas as pd
from scipy import stats

from .config import (
    GAP_TIME_TOLERANCE,
    MAX_CT_THRESHOLD,
    MODE_CT_DECIMALS,
    STOP_THRESHOLD,
)

logger = logging.getLogger("RUNRATE")


def calculate_mode_ct(df):
    """Calculate mode CT (most frequent CT value) per session per equipment.

    Mode is rounded to 2 decimal places.

    Args:
        df (pd.DataFrame): DataFrame with SESSION_ID, EQUIPMENT_CODE, and CT columns

    Returns:
        pd.DataFrame: Original DataFrame with MODE_CT column added
    """
    logger.info("Calculating MODE_CT per session...")

    def get_mode_ct(group):
        """Calculate mode CT for a session, rounded to 2 decimals."""
        # Round CT values to 2 decimals before finding mode
        ct_rounded = np.round(group["CT"], MODE_CT_DECIMALS)

        # Calculate mode (most frequent value)
        mode_result = stats.mode(ct_rounded, keepdims=True)
        mode_value = mode_result.mode[0]

        return mode_value

    # Calculate mode CT per session
    mode_ct_per_session = (
        df.groupby("SESSION_ID")
        .apply(get_mode_ct)
        .reset_index()
        .rename(columns={0: "MODE_CT"})
    )

    # Merge back to original dataframe
    df = df.merge(mode_ct_per_session, on="SESSION_ID", how="left")

    logger.info("MODE_CT calculated for all sessions")
    return df


def detect_stops(df):
    """Detect stops based on three criteria (any one triggers STOP = 1):

    1. CT >= 999.9 (Hard Stop)
    2. CT outside Mode Band (|CT - MODE_CT| / MODE_CT > 5%)
    3. Gap > CT + 2.0s (Time difference vs actual CT with 2s tolerance)

    Special Case: First shot of each session is always STOP = 0

    Args:
        df (pd.DataFrame): DataFrame with CT, MODE_CT, SHOT_DIFF_SEC, SESSION_ID columns

    Returns:
        pd.DataFrame: Original DataFrame with STOP column added
    """
    logger.info(
        f"Detecting stops (3 criteria: CT>=999.9, Mode band +-{STOP_THRESHOLD * 100}%, Gap>CT+2s)..."
    )

    # Initialize STOP column to 0
    df["STOP"] = 0

    # Criterion 1: Hard stop (CT >= 999.9)
    hard_stop = df["CT"] >= MAX_CT_THRESHOLD

    # Criterion 2: CT outside mode band (+-5%)
    ct_deviation_pct = np.abs(df["CT"] - df["MODE_CT"]) / df["MODE_CT"]
    mode_band_violation = ct_deviation_pct > STOP_THRESHOLD

    # Criterion 3: Gap > CT + tolerance (only for non-first shots)
    # For first shot of session, SHOT_DIFF_SEC is None/NaN
    gap_violation = df["SHOT_DIFF_SEC"] > (df["CT"] + GAP_TIME_TOLERANCE)

    # Combine all criteria (any one triggers stop)
    df["STOP"] = (hard_stop | mode_band_violation | gap_violation).astype(int)

    # Special case: First shot of each session is always STOP = 0
    # First shots have NaN in SHOT_DIFF_SEC
    first_shot_mask = df["SHOT_DIFF_SEC"].isna()
    df.loc[first_shot_mask, "STOP"] = 0

    # Log stop statistics by criterion
    total_shots = len(df)
    hard_stops = hard_stop.sum()
    mode_stops = (mode_band_violation & ~hard_stop).sum()
    gap_stops = (gap_violation & ~hard_stop & ~mode_band_violation).sum()
    total_stops = df["STOP"].sum()
    stop_percentage = (total_stops / total_shots * 100) if total_shots > 0 else 0

    logger.info(
        f"Stop detection complete: {total_stops:,} total stops ({stop_percentage:.1f}%)"
    )
    logger.info(f"-> Hard stops (CT>=999.9): {hard_stops:,}")
    logger.info(f"-> Mode band violations: {mode_stops:,}")
    logger.info(f"-> Gap violations (>CT+2s): {gap_stops:,}")
    return df


def calculate_run_efficiency(df):
    """Calculate run efficiency per session.

    Run Efficiency = (Sum of CT where STOP=0) / Total Run Time * 100

    Total Run Time = (Last Shot Time - First Shot Time) + Last CT
    - If last CT > 999.9, use MODE_CT instead

    Args:
        df (pd.DataFrame): DataFrame with SESSION_ID, LOCAL_SHOT_TIME, CT, MODE_CT, STOP

    Returns:
        pd.DataFrame: Original DataFrame with RUN_EFFICIENCY and TOTAL_RUN_TIME columns
    """
    logger.info("Calculating run efficiency per session...")

    def calc_session_efficiency(group):
        """Calculate run efficiency for a single session."""
        # Sort by time to ensure correct ordering
        group = group.sort_values("LOCAL_SHOT_TIME")

        # Get first and last shot times
        first_shot_time = group["LOCAL_SHOT_TIME"].iloc[0]
        last_shot_time = group["LOCAL_SHOT_TIME"].iloc[-1]
        last_ct = group["CT"].iloc[-1]
        mode_ct = group["MODE_CT"].iloc[0]  # Mode CT is same for all shots in session

        # Use MODE_CT if last CT > 999.9
        final_ct = mode_ct if last_ct > MAX_CT_THRESHOLD else last_ct

        # Calculate total run time in seconds
        time_span = (last_shot_time - first_shot_time).total_seconds()
        total_run_time = time_span + final_ct

        # Calculate productive time (sum of CT where STOP=0)
        productive_shots = group[group["STOP"] == 0]
        productive_time = productive_shots["CT"].sum()

        # Calculate run efficiency (clamped to 0-100)
        run_efficiency = (
            (productive_time / total_run_time * 100) if total_run_time > 0 else 0
        )
        run_efficiency = max(0, min(100, run_efficiency))

        # Return series with calculated values
        return pd.Series(
            {
                "TOTAL_RUN_TIME": total_run_time,
                "RUN_EFFICIENCY": round(run_efficiency, 2),
            }
        )

    # Calculate efficiency per session
    session_metrics = (
        df.groupby("SESSION_ID").apply(calc_session_efficiency).reset_index()
    )

    # Merge back to original dataframe
    df = df.merge(session_metrics, on="SESSION_ID", how="left")

    # Log efficiency statistics
    avg_efficiency = df.groupby("SESSION_ID")["RUN_EFFICIENCY"].first().mean()
    logger.info(f"Run efficiency calculated. Average: {avg_efficiency:.2f}%")
    return df


def calculate_weighted_efficiency(df, session_ids=None):
    """Calculate weighted average run efficiency across multiple sessions.

    Weight = shot count per session (more shots = higher weight)

    Args:
        df (pd.DataFrame): DataFrame with SESSION_ID, RUN_EFFICIENCY
        session_ids (list, optional): List of session IDs to include. If None, use all.

    Returns:
        float: Weighted average run efficiency
    """
    # Filter to specific sessions if provided
    if session_ids is not None:
        df = df[df["SESSION_ID"].isin(session_ids)]

    # Get unique efficiency per session with shot count
    session_data = (
        df.groupby("SESSION_ID")
        .agg({"RUN_EFFICIENCY": "first", "SESSION_ID": "count"})
        .rename(columns={"SESSION_ID": "SHOT_COUNT"})
        .reset_index()
    )

    # Calculate weighted average
    total_shots = session_data["SHOT_COUNT"].sum()
    weighted_efficiency = (
        (session_data["RUN_EFFICIENCY"] * session_data["SHOT_COUNT"]).sum()
        / total_shots
        if total_shots > 0
        else 0
    )
    return round(weighted_efficiency, 2)


def _calculate_mttr(total_downtime, stop_events):
    """Calculate MTTR (Mean Time To Repair).

    Formula: Total Downtime / Stop Events (in minutes)

    Args:
        total_downtime: Sum of CT where STOP = 1 (in seconds)
        stop_events: Number of stop events

    Returns:
        float: MTTR in minutes
    """
    if stop_events == 0:
        return 0

    # Convert seconds to minutes
    mttr_minutes = (total_downtime / stop_events) / 60.0
    return mttr_minutes


def _calculate_mtbf(total_production_time, stop_events):
    """Calculate MTBF (Mean Time Between Failures).

    Formula: Total Production Time / Stop Events (in minutes)

    Args:
        total_production_time: Sum of CT where STOP = 0 (in seconds)
        stop_events: Number of stop events

    Returns:
        float: MTBF in minutes
    """
    if stop_events == 0:
        return 0

    # Convert seconds to minutes
    mtbf_minutes = (total_production_time / stop_events) / 60.0
    return mtbf_minutes


def calculate_stop_metrics(df):
    """Calculate stop-related metrics per session:
        - TOTAL_STOPS: Count of shots where STOP = 1
        - DOWNTIME: Total downtime (sum of CT where STOP = 1) in seconds
        - PRODUCTION_TIME: Total production time (sum of CT where STOP = 0) in seconds
        - STOP_EVENTS: Count of consecutive stop sequences (back-to-back stops = 1 event)
        - MTTR (Mean Time To Repair): Total Downtime / Stop Events (in minutes)
        - MTBF (Mean Time Between Failures): Total Production Time / Stop Events (in minutes)

    Args:
        df (pd.DataFrame): DataFrame with SESSION_ID, STOP, LOCAL_SHOT_TIME, CT columns

    Returns:
        pd.DataFrame: Original DataFrame with stop metrics columns added
    """
    logger.info("Calculating stop metrics (MTTR, MTBF, stop events)...")

    def calc_session_stop_metrics(group):
        """Calculate stop metrics for a single session."""
        # Sort by time to ensure correct ordering
        group = group.sort_values("LOCAL_SHOT_TIME").reset_index(drop=True)

        # Total stops (count of STOP = 1)
        total_stops = group["STOP"].sum()

        # Downtime: Sum of CT where STOP = 1 (in seconds)
        total_downtime = group[group["STOP"] == 1]["CT"].sum()

        # Production time: Sum of CT where STOP = 0 (in seconds)
        total_production_time = group[group["STOP"] == 0]["CT"].sum()

        # Detect stop events (consecutive stops = 1 event)
        stop_transitions = group["STOP"].ne(group["STOP"].shift()).cumsum()

        # Count stop events (groups where STOP = 1)
        stop_events = group[group["STOP"] == 1].groupby(stop_transitions).ngroups

        # Calculate MTTR and MTBF using helper functions (returns minutes)
        mttr = _calculate_mttr(total_downtime, stop_events)
        mtbf = _calculate_mtbf(total_production_time, stop_events)

        return pd.Series(
            {
                "TOTAL_STOPS": int(total_stops),
                "DOWNTIME": round(total_downtime, 2),
                "PRODUCTION_TIME": round(total_production_time, 2),
                "STOP_EVENTS": int(stop_events),
                "MTTR": round(mttr, 2),
                "MTBF": round(mtbf, 2),
            }
        )

    # Calculate stop metrics per session
    session_stop_metrics = (
        df.groupby("SESSION_ID").apply(calc_session_stop_metrics).reset_index()
    )

    # Merge back to original dataframe
    df = df.merge(session_stop_metrics, on="SESSION_ID", how="left")

    # Log stop metrics statistics
    avg_mttr = df.groupby("SESSION_ID")["MTTR"].first().mean()
    avg_mtbf = df.groupby("SESSION_ID")["MTBF"].first().mean()
    total_stop_events = df.groupby("SESSION_ID")["STOP_EVENTS"].first().sum()

    logger.info("Stop metrics calculated:")
    logger.info(f"-> Total stop events: {total_stop_events:,}")
    logger.info(f"-> Average MTTR: {avg_mttr:.2f} minutes")
    logger.info(f"-> Average MTBF: {avg_mtbf:.2f} minutes")
    return df


def validate_calculations(df):
    """Validate calculated metrics.

    Checks:
        - MODE_CT exists for all sessions
        - STOP is binary (0 or 1)
        - RUN_EFFICIENCY is between 0 and 100
        - TOTAL_RUN_TIME is positive

    Args:
        df (pd.DataFrame): DataFrame with calculated metrics

    Returns:
        bool: True if valid, raises ValueError otherwise
    """
    # Check MODE_CT
    if df["MODE_CT"].isna().any():
        raise ValueError("Some sessions are missing MODE_CT")

    # Check STOP is binary
    if not df["STOP"].isin([0, 1]).all():
        raise ValueError("STOP column contains non-binary values")

    # Check RUN_EFFICIENCY range
    if (df["RUN_EFFICIENCY"] < 0).any() or (df["RUN_EFFICIENCY"] > 100).any():
        raise ValueError("RUN_EFFICIENCY contains values outside [0, 100] range")

    # Check TOTAL_RUN_TIME is positive
    if (df["TOTAL_RUN_TIME"] <= 0).any():
        raise ValueError("TOTAL_RUN_TIME contains non-positive values")

    logger.info("Calculation validation passed")
    return True
