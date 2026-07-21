"""
Metrics Calculation for Capacity Analysis.

Handles session-level and daily metrics calculation including OEE components.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from typing import List, Optional

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from analysis.shared.constants import SessionDetection

from .data_processor import get_cavity_count


def _calculate_mode_ct(df: pd.DataFrame) -> Optional[float]:
    """Calculate mode cycle time from valid shot intervals."""
    valid_mask = (
        df["SHOT_DIFF_SEC"].notna()
        & (df["SHOT_DIFF_SEC"] > 1)
        & (df["SHOT_DIFF_SEC"] < 3600)
    )
    valid_diffs = df.loc[valid_mask, "SHOT_DIFF_SEC"].round().dropna().astype(int)
    if valid_diffs.empty:
        return None
    return float(valid_diffs.value_counts().idxmax())


def _get_approved_ct(df: pd.DataFrame, mode_ct_sec: float) -> float:
    """Get APPROVED_CT (use first positive value, fallback to mode CT)."""
    approved_series = df["APPROVED_CT"].dropna()
    approved_series = approved_series[approved_series > 0]
    if not approved_series.empty:
        return float(approved_series.iloc[0])
    return float(mode_ct_sec)


def _detect_stops(df: pd.DataFrame, mode_ct_sec: float) -> pd.DataFrame:
    """Detect stops using ±5% mode CT tolerance."""
    lower_sec = mode_ct_sec * 0.95
    upper_sec = mode_ct_sec * 1.05

    stops: List[int] = []
    for i, (sec, act_ct) in enumerate(
        zip(df["SHOT_DIFF_SEC"].tolist(), df["ACTUAL_CT"].tolist())
    ):
        if pd.isna(sec) or act_ct > 999 or i == 0 or i == len(df) - 1:
            stops.append(0)
        else:
            if (
                sec < lower_sec or sec > upper_sec
            ) and sec <= SessionDetection.SESSION_GAP_SECONDS:
                stops.append(1)
            else:
                stops.append(0)

    df = df.copy()
    df["STOP"] = stops
    return df


def _calculate_time_metrics(df: pd.DataFrame, mode_ct_sec: float) -> tuple:
    """Calculate time metrics (total run time, production time, downtime)."""
    first_ts = df["LOCAL_SHOT_TIME"].min()
    last_ts = df["LOCAL_SHOT_TIME"].max()
    total_run_sec = float((last_ts - first_ts).total_seconds() + mode_ct_sec)
    total_run_sec = max(total_run_sec, 0.0)

    realistic_mask = (
        (df["STOP"] == 0)
        & df["SHOT_DIFF_SEC"].notna()
        & (df["SHOT_DIFF_SEC"] >= 1)
        & (df["SHOT_DIFF_SEC"] <= 3600)
    )
    production_time_sec = float(df.loc[realistic_mask, "SHOT_DIFF_SEC"].sum())
    if df.iloc[-1]["STOP"] == 0:
        production_time_sec += mode_ct_sec
    production_time_sec = min(max(production_time_sec, 0.0), total_run_sec)

    downtime_sec = max(0.0, total_run_sec - production_time_sec)

    return total_run_sec, production_time_sec, downtime_sec


def _calculate_output_metrics(
    df: pd.DataFrame,
    cavity_count: int,
    approved_ct_sec: float,
    total_run_sec: float,
    oee_target: float,
) -> dict:
    """Calculate output metrics (actual, optimal, losses)."""
    valid_shots = int((df["ACTUAL_CT"] <= 999).sum())
    actual_output = valid_shots * cavity_count
    total_shots_all = int(len(df))
    invalid_999_shots = int((df["ACTUAL_CT"] > 999).sum())

    optimal_output = (
        (total_run_sec / approved_ct_sec) * oee_target * cavity_count
        if approved_ct_sec
        else np.nan
    )

    return {
        "valid_shots": valid_shots,
        "actual_output": actual_output,
        "total_shots_all": total_shots_all,
        "invalid_999_shots": invalid_999_shots,
        "optimal_output": optimal_output,
    }


def _calculate_losses(
    production_time_sec: float,
    downtime_sec: float,
    approved_ct_sec: float,
    cavity_count: int,
    actual_output: float,
) -> dict:
    """Calculate performance and availability losses."""
    if approved_ct_sec > 0:
        potential_parts_during_production = (
            production_time_sec / approved_ct_sec
        ) * cavity_count
        performance_loss = potential_parts_during_production - actual_output
    else:
        performance_loss = 0.0

    availability_loss = (
        (downtime_sec / approved_ct_sec) * cavity_count if approved_ct_sec else 0.0
    )

    return {
        "performance_loss": performance_loss,
        "availability_loss": availability_loss,
    }


def _calculate_oee_components(
    total_run_sec: float,
    planned_production_time_sec: float,
    approved_ct_sec: float,
    total_shots_all: int,
    invalid_999_shots: int,
) -> dict:
    """Calculate OEE components (Availability, Performance, Quality)."""
    availability = (
        (total_run_sec / planned_production_time_sec)
        if planned_production_time_sec > 0
        else 0.0
    )
    availability = min(availability, 1.0)

    performance = (
        (approved_ct_sec * total_shots_all) / total_run_sec
        if total_run_sec > 0 and approved_ct_sec > 0
        else 0.0
    )
    performance = min(performance, 1.0)

    if total_shots_all > 0:
        good_shots = total_shots_all - invalid_999_shots
        quality = good_shots / total_shots_all
    else:
        quality = 1.0

    quality = min(max(quality, 0.0), 1.0)

    calculated_oee = availability * performance * quality

    return {
        "availability": availability,
        "performance": performance,
        "quality": quality,
        "calculated_oee": calculated_oee,
    }


def _calculate_debug_metrics(
    df: pd.DataFrame, mode_ct_sec: float, valid_shots: int
) -> dict:
    """Calculate debug metrics for validation."""
    ideal_production_time_sec = valid_shots * mode_ct_sec if mode_ct_sec > 0 else 0.0
    actual_cycle_time_debug = (
        float(df.loc[df["ACTUAL_CT"] <= 999, "ACTUAL_CT"].sum())
        if valid_shots > 0
        else 0.0
    )
    extra_time_due_to_slow_cycles = max(
        0.0, actual_cycle_time_debug - ideal_production_time_sec
    )

    actual_production_intervals_debug = float(
        df.loc[df["STOP"] == 0, "SHOT_DIFF_SEC"].sum()
    )
    time_efficiency_ratio = (
        ideal_production_time_sec / actual_production_intervals_debug
        if actual_production_intervals_debug > 0
        else 0.0
    )

    return {
        "ideal_production_time_sec": ideal_production_time_sec,
        "actual_cycle_time_debug": actual_cycle_time_debug,
        "extra_time_due_to_slow_cycles": extra_time_due_to_slow_cycles,
        "actual_production_intervals_debug": actual_production_intervals_debug,
        "time_efficiency_ratio": time_efficiency_ratio,
    }


def compute_session_metrics(
    session_df: pd.DataFrame,
    equipment_code: str,
    oee_target: float = 1.00,
    total_actual_runtime_sec: float = float(SessionDetection.SESSION_GAP_SECONDS),
) -> Optional[dict]:
    """
    Compute session metrics using APPROVED_CT for optimal output and loss split.

    Calculates:
    - Mode CT (seconds) from valid shot intervals
    - APPROVED_CT (constant per equipment, fallback to mode CT)
    - Stop classification (±5% of mode CT, ≤8 hours only)
    - Production time and downtime
    - Actual output (shots × cavity count)
    - Performance loss and availability loss
    - OEE components (Availability, Performance, Quality)

    Args:
        session_df: DataFrame with shot data for a single session
        equipment_code: Equipment code to determine cavity count
        oee_target: Target OEE value (default 1.00 = 100%)
        total_actual_runtime_sec: Total actual runtime across all sessions

    Returns:
        dict: Session metrics including:
            - Time metrics (runtime, production time, downtime)
            - Output metrics (actual, optimal, losses)
            - OEE components (availability, performance, quality)
            - Debug metrics for validation
        None: If session is invalid (<50 shots or no valid data)

    Example:
        >>> metrics = compute_session_metrics(
        ...     session_df=session_data,
        ...     equipment_code="EMA-4102",
        ...     oee_target=0.80,
        ...     total_actual_runtime_sec=86400
        ... )
        >>> print(f"OEE: {metrics['OEE_SCORE']:.2%}")
        OEE: 75.3%
    """
    if session_df.empty or len(session_df) < 10:
        return None

    df = session_df.copy()
    df["ACTUAL_CT"] = pd.to_numeric(df["ACTUAL_CT"], errors="coerce")
    df["APPROVED_CT"] = pd.to_numeric(df["APPROVED_CT"], errors="coerce")

    # Get cavity count
    cavity_count = get_cavity_count(equipment_code, data=df)

    # Calculate mode CT
    mode_ct_sec = _calculate_mode_ct(df)
    if mode_ct_sec is None:
        return None

    # Get APPROVED_CT
    approved_ct_sec = _get_approved_ct(df, mode_ct_sec)

    # Detect stops
    df = _detect_stops(df, mode_ct_sec)

    # Calculate time metrics
    total_run_sec, production_time_sec, downtime_sec = _calculate_time_metrics(
        df, mode_ct_sec
    )

    # Calculate output metrics
    output_metrics = _calculate_output_metrics(
        df, cavity_count, approved_ct_sec, total_run_sec, oee_target
    )
    valid_shots = output_metrics["valid_shots"]
    actual_output = output_metrics["actual_output"]
    total_shots_all = output_metrics["total_shots_all"]
    invalid_999_shots = output_metrics["invalid_999_shots"]
    optimal_output = output_metrics["optimal_output"]

    # Calculate losses
    losses = _calculate_losses(
        production_time_sec,
        downtime_sec,
        approved_ct_sec,
        cavity_count,
        actual_output,
    )
    performance_loss = losses["performance_loss"]
    availability_loss = losses["availability_loss"]

    # Gap calculation
    gap = optimal_output - actual_output if not np.isnan(optimal_output) else 0.0

    # Calculate OEE components
    planned_production_time_sec = total_actual_runtime_sec
    oee_components = _calculate_oee_components(
        total_run_sec,
        planned_production_time_sec,
        approved_ct_sec,
        total_shots_all,
        invalid_999_shots,
    )
    availability = oee_components["availability"]
    performance = oee_components["performance"]
    quality = oee_components["quality"]
    calculated_oee = oee_components["calculated_oee"]

    # Quality parts
    quality_parts = int(quality * total_shots_all) if quality > 0 else 0

    # Optimal output at different OEE levels
    optimal_output_100_oee = (
        int((planned_production_time_sec / approved_ct_sec) * cavity_count)
        if approved_ct_sec > 0
        else 0
    )
    optimal_output_target_oee = int(optimal_output_100_oee * oee_target)

    # Debug metrics
    debug_metrics = _calculate_debug_metrics(df, mode_ct_sec, valid_shots)

    day = df["LOCAL_SHOT_TIME"].min().date()
    return {
        "DAY": pd.to_datetime(day),
        "EQUIPMENT_CODE": equipment_code,
        "CAVITY_COUNT": cavity_count,
        "VALID_SHOTS": valid_shots,
        "APPROVED_CT_SEC": approved_ct_sec,
        "MODE_CT_SEC": mode_ct_sec,
        "TOTAL_RUN_SEC": total_run_sec,
        "PRODUCTION_TIME_SEC": production_time_sec,
        "IDEAL_PRODUCTION_TIME_SEC": debug_metrics["ideal_production_time_sec"],
        "ACTUAL_PRODUCTION_INTERVALS_SEC": debug_metrics[
            "actual_production_intervals_debug"
        ],
        "TIME_EFFICIENCY_RATIO": debug_metrics["time_efficiency_ratio"],
        "EXTRA_TIME_SLOW_CYCLES_SEC": debug_metrics["extra_time_due_to_slow_cycles"],
        "ACTUAL_CYCLE_TIME_TOTAL_SEC": debug_metrics["actual_cycle_time_debug"],
        "DOWNTIME_SEC": downtime_sec,
        "ACTUAL_OUTPUT": actual_output,
        "OPTIMAL_OUTPUT": optimal_output,
        "PERFORMANCE_LOSS": performance_loss,
        "AVAILABILITY_LOSS": max(0.0, availability_loss),
        "GAP": gap,
        "TOTAL_SHOTS_ALL": total_shots_all,
        "INVALID_999_SHOTS": invalid_999_shots,
        # OEE Components
        "PLANNED_PRODUCTION_TIME_SEC": planned_production_time_sec,
        "RUN_TIME_SEC": total_run_sec,
        "AVAILABILITY": availability,
        "PERFORMANCE": performance,
        "QUALITY": quality,
        "OEE_SCORE": calculated_oee,
        "TARGET_OEE": oee_target,
        "QUALITY_PARTS": quality_parts,
        # Optimal Output at different OEE levels
        "OPTIMAL_OUTPUT_100_OEE": optimal_output_100_oee,
        "OPTIMAL_OUTPUT_TARGET_OEE": optimal_output_target_oee,
    }


def build_session_metrics(df: pd.DataFrame, oee_target: float = 1.00) -> pd.DataFrame:
    """
    Compute metrics for each session with dynamic runtime calculation.

    Sessions are split by midnight OR 8-hour breaks. Calculates total
    runtime per equipment and computes metrics for each valid session (≥50 shots).

    Args:
        df: DataFrame with processed shot data (must have SESSION_ID column)
        oee_target: Target OEE value (default 1.00 = 100%)

    Returns:
        pd.DataFrame: Session metrics with one row per session

    Example:
        >>> session_metrics = build_session_metrics(
        ...     df=processed_data,
        ...     oee_target=0.80
        ... )
        >>> print(f"Analyzed {len(session_metrics)} sessions")
        Analyzed 45 sessions
    """
    if df.empty:
        return pd.DataFrame()

    working = df.copy()
    working["DAY"] = working["LOCAL_SHOT_TIME"].dt.floor("D")

    # Calculate total actual runtime per equipment
    total_runtime_per_equipment = {}

    for equipment_code, equipment_df in working.groupby("EQUIPMENT_CODE"):
        session_groups = equipment_df.groupby("SESSION_ID")
        total_runtime_sec = 0.0

        for session_id, session_df in session_groups:
            if len(session_df) >= 10:  # Only include valid sessions
                first_ts = session_df["LOCAL_SHOT_TIME"].min()
                last_ts = session_df["LOCAL_SHOT_TIME"].max()

                # Calculate mode CT for this session
                valid_mask = (
                    session_df["SHOT_DIFF_SEC"].notna()
                    & (session_df["SHOT_DIFF_SEC"] > 1)
                    & (session_df["SHOT_DIFF_SEC"] < 3600)
                )
                valid_diffs = (
                    session_df.loc[valid_mask, "SHOT_DIFF_SEC"]
                    .round()
                    .dropna()
                    .astype(int)
                )
                if not valid_diffs.empty:
                    mode_ct_sec = float(valid_diffs.value_counts().idxmax())
                    session_total_run = (
                        last_ts - first_ts
                    ).total_seconds() + mode_ct_sec
                    total_runtime_sec += max(session_total_run, 0.0)

        total_runtime_per_equipment[equipment_code] = max(
            total_runtime_sec, float(SessionDetection.SESSION_GAP_SECONDS)
        )  # Minimum 8 hours

    # Compute metrics for each session
    rows: List[dict] = []
    for (equipment_code, session_id), session_df in working.groupby(
        ["EQUIPMENT_CODE", "SESSION_ID"]
    ):
        total_actual_runtime_sec = total_runtime_per_equipment.get(
            equipment_code, float(SessionDetection.SESSION_GAP_SECONDS)
        )
        session_day = session_df["DAY"].iloc[0]

        metrics = compute_session_metrics(
            session_df, equipment_code, oee_target, total_actual_runtime_sec
        )
        if metrics is not None:
            metrics["DAY"] = session_day
            metrics["SESSION_ID"] = session_id
            rows.append(metrics)

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows).sort_values(["DAY", "SESSION_ID"]).reset_index(drop=True)
    print(f"✅ Computed metrics for {len(out)} sessions")
    return out
