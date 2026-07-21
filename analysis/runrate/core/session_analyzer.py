"""
Session analysis and stop detection for RunRate analysis.

Contains the core logic for detecting production stops and calculating
session-level metrics including MTTR, MTBF, efficiency, and stability index.
"""

from typing import Tuple

import numpy as np
import pandas as pd
from scipy.stats import mode

from analysis.shared.constants import SessionDetection

# Default thresholds (V2.6) - derived from shared constants
RUN_INTERVAL_THRESHOLD_SEC = SessionDetection.SESSION_GAP_SECONDS
MODE_CT_TOLERANCE = SessionDetection.STOP_DEVIATION_THRESHOLD
DOWNTIME_GAP_TOLERANCE = SessionDetection.GAP_TIME_TOLERANCE_SECONDS


def process_shots(session_df: pd.DataFrame) -> pd.DataFrame:
    """
    Process shots for a session with run-based stop detection (V2.6 Logic).

    Stop Detection Logic:
    1. First shot of any run is ALWAYS Normal (stop_flag = 0)
       - No previous shot to calculate gap against
    2. Stop conditions checked in order:
       a) Hard Stop: Current CT >= 999.9
       b) Abnormal Cycle: Current CT outside Mode Band (±5%)
       c) Time Gap: time_diff_sec > previous_CT + 2.0 seconds

    Downtime Duration (ADJ_CT_SEC):
    - Normal shot: 0
    - Hard Stop: time_diff_sec (the gap)
    - Abnormal Cycle: ACTUAL_CT (the slow/fast cycle itself)
    - Time Gap Stop: time_diff_sec (the gap duration)

    Args:
        session_df: Session data with ACTUAL_CT, SHOT_DIFF_SEC, LOCAL_SHOT_TIME

    Returns:
        Processed DataFrame with stop detection and metrics
    """
    session_df = session_df.copy()

    # Filter out CT=999.9 for mode calculation (prevents skewing)
    valid_ct_values = session_df[
        (session_df["ACTUAL_CT"] > 1)
        & (session_df["ACTUAL_CT"] < 999)
        & (session_df["ACTUAL_CT"] != 999.9)
    ]["ACTUAL_CT"]

    # Calculate mode cycle time
    mode_ct_sec = _calculate_mode_ct(valid_ct_values)

    # Set thresholds for normal operation (±5% of mode)
    lower_sec = (
        mode_ct_sec * (1 - MODE_CT_TOLERANCE) if not np.isnan(mode_ct_sec) else np.nan
    )
    upper_sec = (
        mode_ct_sec * (1 + MODE_CT_TOLERANCE) if not np.isnan(mode_ct_sec) else np.nan
    )

    # Store mode and limits
    session_df["MODE_CT"] = mode_ct_sec if not np.isnan(mode_ct_sec) else np.nan
    session_df["LOWER_LIMIT"] = lower_sec if not np.isnan(lower_sec) else np.nan
    session_df["UPPER_LIMIT"] = upper_sec if not np.isnan(upper_sec) else np.nan
    session_df["SHOT_DIFF"] = session_df["SHOT_DIFF_SEC"]
    session_df["MIN_CT"] = session_df["ACTUAL_CT"]

    # Apply V2.6 stop detection
    session_df = _detect_stops_v26(session_df, mode_ct_sec, lower_sec, upper_sec)

    # Calculate cumulative metrics
    session_df = _calculate_cumulative_metrics(session_df, mode_ct_sec)

    # Calculate session-level KPIs
    session_df = _calculate_session_kpis(session_df, mode_ct_sec)

    return session_df


def _calculate_mode_ct(valid_ct_values: pd.Series) -> float:
    """Calculate mode cycle time with scipy version compatibility."""
    if valid_ct_values.empty:
        return np.nan

    try:
        mode_result = mode(valid_ct_values)
        mode_value = mode_result.mode
        if hasattr(mode_value, "item"):
            return round(float(mode_value.item()), 2)
        elif hasattr(mode_value, "__len__") and len(mode_value) > 0:
            return round(float(mode_value[0]), 2)
        else:
            return round(float(mode_value), 2)
    except Exception:
        try:
            return round(float(valid_ct_values.median()), 2)
        except Exception:
            return np.nan


def _detect_stops_v26(
    session_df: pd.DataFrame,
    mode_ct_sec: float,
    lower_sec: float,
    upper_sec: float,
) -> pd.DataFrame:
    """
    Detect stops using V2.6 logic.

    Stop Detection Order:
    1. First shot of run → Always Normal (stop_flag = 0)
    2. Hard Stop: Current CT >= 999.9
    3. Abnormal Cycle: Current CT outside mode band (±5%)
    4. Time Gap: time_diff_sec > prev_CT + 2.0 seconds

    Also calculates ADJ_CT_SEC (adjusted downtime) for each shot.
    """
    session_df["STOP"] = 0
    session_df["STOP_TYPE"] = "Normal"
    session_df["ADJ_CT_SEC"] = 0.0

    for i in range(len(session_df)):
        time_diff_sec = session_df.iloc[i]["SHOT_DIFF_SEC"]
        current_ct = session_df.iloc[i]["ACTUAL_CT"]

        stop_col = session_df.columns.get_loc("STOP")
        stop_type_col = session_df.columns.get_loc("STOP_TYPE")
        adj_ct_col = session_df.columns.get_loc("ADJ_CT_SEC")

        # RULE 1: First shot of run is ALWAYS Normal
        if i == 0:
            session_df.iloc[i, stop_col] = 0
            session_df.iloc[i, stop_type_col] = "Normal"
            session_df.iloc[i, adj_ct_col] = 0.0
            continue

        # Check for run boundary (gap > 8 hours = new run)
        if pd.notna(time_diff_sec) and time_diff_sec > RUN_INTERVAL_THRESHOLD_SEC:
            session_df.iloc[i, stop_col] = 0
            session_df.iloc[i, stop_type_col] = "Normal"
            session_df.iloc[i, adj_ct_col] = 0.0
            continue

        if pd.isna(time_diff_sec) or pd.isna(current_ct):
            continue

        prev_ct = session_df.iloc[i - 1]["ACTUAL_CT"]

        # RULE 2: Hard Stop (current CT >= 999.9)
        if current_ct >= 999.9:
            session_df.iloc[i, stop_col] = 1
            session_df.iloc[i, stop_type_col] = "Hard Stop"
            session_df.iloc[i, adj_ct_col] = time_diff_sec
            continue

        # RULE 3: Abnormal Cycle (current CT outside mode band ±5%)
        if not np.isnan(lower_sec) and not np.isnan(upper_sec):
            if current_ct < lower_sec or current_ct > upper_sec:
                session_df.iloc[i, stop_col] = 1
                session_df.iloc[i, stop_type_col] = "Abnormal Cycle"
                session_df.iloc[i, adj_ct_col] = current_ct
                continue

        # RULE 4: Time Gap (gap > prev_CT + 2.0 seconds)
        if pd.notna(prev_ct) and prev_ct != 999.9 and prev_ct > 0:
            expected_interval = prev_ct + DOWNTIME_GAP_TOLERANCE
            if time_diff_sec > expected_interval:
                session_df.iloc[i, stop_col] = 1
                session_df.iloc[i, stop_type_col] = "Time Gap"
                session_df.iloc[i, adj_ct_col] = time_diff_sec
                continue

        # Normal shot - no stop condition met
        session_df.iloc[i, stop_col] = 0
        session_df.iloc[i, stop_type_col] = "Normal"
        session_df.iloc[i, adj_ct_col] = 0.0

    return session_df


def _calculate_cumulative_metrics(
    session_df: pd.DataFrame, mode_ct_sec: float
) -> pd.DataFrame:
    """Calculate cumulative count and run duration for each shot."""
    cumulative_counts = []
    run_durations = []

    for i in range(len(session_df)):
        stop = session_df.iloc[i]["STOP"]
        ct_min = session_df.iloc[i]["MIN_CT"]
        actual_ct = session_df.iloc[i]["ACTUAL_CT"]
        shot_diff_sec = session_df.iloc[i]["SHOT_DIFF_SEC"]

        # For CT=999.9, use SHOT_DIFF_SEC as production time
        if actual_ct == 999.9:
            ct_for_cumulative = shot_diff_sec if pd.notna(shot_diff_sec) else 0.0
            ct_min_minutes = ct_for_cumulative / 60
        else:
            ct_min_minutes = (ct_min / 60) if not pd.isna(ct_min) else 0.0

        if i == 0:
            if stop == 0:
                cumulative_counts.append(ct_min_minutes)
                run_durations.append("")
            else:
                cumulative_counts.append(0.0)
                run_durations.append(0.0)
            continue

        prev_stop = session_df.iloc[i - 1]["STOP"]
        prev_cum = cumulative_counts[i - 1]

        if stop == 1:
            cumulative_counts.append(0.0)
            if prev_stop == 0:
                run_durations.append(prev_cum)
            else:
                run_durations.append("")
        else:
            if prev_stop == 1:
                cumulative_counts.append(ct_min_minutes)
                run_durations.append("")
            else:
                cumulative_counts.append(prev_cum + ct_min_minutes)
                run_durations.append("")

    session_df["CUMULATIVE_COUNT"] = cumulative_counts
    session_df["RUN_DURATION"] = run_durations

    if not session_df.empty and session_df.iloc[-1]["STOP"] == 0:
        session_df.at[session_df.index[-1], "RUN_DURATION"] = session_df.iloc[-1][
            "CUMULATIVE_COUNT"
        ]

    session_df["TIME_BUCKET"] = session_df["RUN_DURATION"].apply(_get_time_bucket)

    return session_df


def _get_time_bucket(run_duration) -> int:
    """Assign time bucket (every 20 minutes = 1 bucket)."""
    if pd.isna(run_duration) or run_duration == "":
        return None
    try:
        duration = float(run_duration)
        return max(1, int(duration / 20) + 1)
    except (ValueError, TypeError):
        return None


def _calculate_session_kpis(
    session_df: pd.DataFrame, mode_ct_sec: float
) -> pd.DataFrame:
    """
    Calculate session-level KPIs using V2.6 formulas.

    Efficiency: Normal Shots / Total Shots × 100
    Stability Index: Production Time / Total Run Duration × 100
    MTTR: Total Downtime / Stop Events
    MTBF: Production Time / Stop Events
    """
    # Exclude first shot's interval (represents break before session)
    all_intervals_mask = session_df["SHOT_DIFF_SEC"].notna()
    if not session_df.empty:
        first_row_idx = session_df.index[0]
        all_intervals_mask = all_intervals_mask & (session_df.index != first_row_idx)

    # Total Run Duration
    total_time_sec = float(session_df.loc[all_intervals_mask, "SHOT_DIFF_SEC"].sum())
    if not np.isnan(mode_ct_sec) and not session_df.empty:
        total_time_sec += mode_ct_sec

    # Production Time (normal shots only)
    normal_intervals_mask = (session_df["STOP"] == 0) & (
        session_df["SHOT_DIFF_SEC"].notna()
    )
    if not session_df.empty:
        first_row_idx = session_df.index[0]
        normal_intervals_mask = normal_intervals_mask & (
            session_df.index != first_row_idx
        )

    prod_time_sec = float(session_df.loc[normal_intervals_mask, "SHOT_DIFF_SEC"].sum())

    if (
        not np.isnan(mode_ct_sec)
        and not session_df.empty
        and session_df.iloc[-1]["STOP"] == 0
    ):
        prod_time_sec += float(mode_ct_sec)

    prod_time_sec = min(max(prod_time_sec, 0.0), float(total_time_sec))

    # Downtime: sum of ADJ_CT_SEC for stop shots (V2.6 method)
    stop_mask = (session_df["STOP"] == 1) & (session_df["ADJ_CT_SEC"].notna())
    if not session_df.empty:
        first_row_idx = session_df.index[0]
        stop_mask = stop_mask & (session_df.index != first_row_idx)

    downtime_sec = float(session_df.loc[stop_mask, "ADJ_CT_SEC"].sum())
    downtime_sec = max(0.0, min(downtime_sec, float(total_time_sec)))

    # Stability Index (Uptime %): Production Time / Total Run Duration
    uptime_pct = (
        min(100.0, round((prod_time_sec / total_time_sec) * 100, 1))
        if total_time_sec > 0
        else 0.0
    )
    downtime_pct = round(100 - uptime_pct, 1)

    session_df["PRODUCTION_TIME"] = prod_time_sec / 60
    session_df["TOTAL_RUN_TIME"] = total_time_sec / 60
    session_df["TOTAL_DOWN_TIME"] = downtime_sec / 60

    # Stop events (consecutive stops = 1 event)
    stop_events = _count_stop_events(session_df)

    session_df["TOTAL_STOPS"] = stop_events
    session_df["INDIVIDUAL_STOPS"] = session_df["STOP"].sum()
    session_df["UPTIME_PCT"] = uptime_pct
    session_df["DOWNTIME_PCT"] = downtime_pct

    # Efficiency: Normal Shots / Total Shots × 100
    shots_in_session = len(session_df)
    normal_shots = (session_df["STOP"] == 0).sum()

    session_df["SHOTS_IN_SESSION"] = shots_in_session
    session_df["NORMAL_SHOTS"] = normal_shots
    session_df["EFFICIENCY"] = (
        round((normal_shots / shots_in_session) * 100, 1)
        if shots_in_session > 0
        else 0.0
    )

    # MTTR and MTBF
    mttr_min, mtbf_min, time_to_first_dt_min = _calculate_maintenance_metrics(
        session_df, stop_events, downtime_sec, prod_time_sec
    )

    # Average cycle time (excluding CT=999.9)
    avg_cycle_time_min = 0.0
    valid_ct = session_df[session_df["ACTUAL_CT"] != 999.9]["ACTUAL_CT"]
    if not valid_ct.empty:
        avg_cycle_time_min = valid_ct.mean() / 60

    session_df["MTTR"] = mttr_min
    session_df["MTBF"] = mtbf_min
    session_df["TIME_TO_FIRST_DT"] = time_to_first_dt_min
    session_df["AVG_CYCLE_TIME"] = avg_cycle_time_min
    session_df["AVG_CYCLE_TIME_SEC"] = (
        avg_cycle_time_min * 60 if avg_cycle_time_min > 0 else 0.0
    )

    return session_df


def _count_stop_events(session_df: pd.DataFrame) -> int:
    """Count stop events (consecutive stops = 1 event)."""
    stop_events = 0
    in_stop_event = False

    for i in range(len(session_df)):
        is_stop = session_df.iloc[i]["STOP"] == 1

        if is_stop and not in_stop_event:
            stop_events += 1
            in_stop_event = True
        elif not is_stop:
            in_stop_event = False

    return stop_events


def _calculate_maintenance_metrics(
    session_df: pd.DataFrame,
    stop_events: int,
    downtime_sec: float,
    prod_time_sec: float,
) -> Tuple[float, float, float]:
    """
    Calculate MTTR, MTBF, and time to first downtime (V2.6 formulas).

    MTTR = Total Downtime / Stop Events
    MTBF = Production Time / Stop Events
    """
    # MTTR: Mean Time To Repair
    mttr_min = 0.0
    if stop_events > 0:
        mttr_min = (downtime_sec / 60) / stop_events

    # MTBF: Mean Time Between Failures
    mtbf_min = 0.0
    if stop_events > 0 and prod_time_sec > 0:
        mtbf_min = (prod_time_sec / 60) / stop_events

    # Time until first downtime
    time_to_first_dt_min = 0.0
    first_stop_idx = session_df[session_df["STOP"] == 1].index
    if not first_stop_idx.empty and not session_df.empty:
        first_stop_row = session_df.loc[first_stop_idx[0]]
        if (
            pd.notna(first_stop_row["RUN_DURATION"])
            and first_stop_row["RUN_DURATION"] != ""
        ):
            time_to_first_dt_min = float(first_stop_row["RUN_DURATION"])

    return mttr_min, mtbf_min, time_to_first_dt_min
