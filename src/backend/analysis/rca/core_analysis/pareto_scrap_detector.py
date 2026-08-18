"""
Scrap detection functions for Pareto analysis on manufacturing shot data.
Provides standalone functions to detect various scrap indicators including warmup shots,
low parameter shots, sensor anomalies, and missing sensor values.
Used by ParetoAnalysis to identify suspected scrap in single-equipment analysis.
"""

from typing import Dict, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Scrap detection thresholds (defaults -- callers may override)
# ---------------------------------------------------------------------------
WARMUP_SHOTS_AFTER_IDLE: int = 3
LOW_PRESSURE_THRESHOLD: float = 0.8
LOW_TEMP_THRESHOLD: float = 0.9
SENSOR_ANOMALY_THRESHOLD: float = 3.0

# Scrap indicator column names used across all functions
SCRAP_COLUMNS = [
    "SCRAP_CT_ABNORMAL",
    "SCRAP_WARMUP",
    "SCRAP_LOW_PRESSURE",
    "SCRAP_LOW_TEMP",
    "SCRAP_SENSOR_ANOMALY",
    "SCRAP_MISSING_SENSORS",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_scrap_indicators(
    df: pd.DataFrame,
    warmup_shots_after_idle: int = WARMUP_SHOTS_AFTER_IDLE,
    low_temp_threshold: float = LOW_TEMP_THRESHOLD,
    sensor_anomaly_threshold: float = SENSOR_ANOMALY_THRESHOLD,
) -> pd.DataFrame:
    """Detect all scrap indicators and combine them into a composite score.

    Mutates *df* in place (adds scrap columns) and returns the same frame.

    Args:
        df: Manufacturing shot data with at least CT_ISSUE_FLAG and
            DOWNTIME_GAP_FLAG columns already computed.
        warmup_shots_after_idle: Number of shots to treat as warm-up after idle.
        low_temp_threshold: Fraction of mean temperature below which a shot
            is considered low-temperature.
        sensor_anomaly_threshold: Number of standard deviations for the
            sensor anomaly 3-sigma rule.

    Returns:
        The input DataFrame with SCRAP_* columns added.
    """
    # Initialise indicator columns
    for col in SCRAP_COLUMNS:
        df[col] = False
    df["SCRAP_INDICATOR"] = False
    df["SCRAP_SCORE"] = 0

    # 1. Abnormal CT (relies on pre-computed CT_ISSUE_FLAG)
    df["SCRAP_CT_ABNORMAL"] = df["CT_ISSUE_FLAG"]

    # 2. Warm-up shots
    df = detect_warmup_shots(df, warmup_shots_after_idle=warmup_shots_after_idle)

    # 3. Low parameter shots
    df = detect_low_parameter_shots(df, low_temp_threshold=low_temp_threshold)

    # 4. Sensor anomalies
    df = detect_sensor_anomalies(df, sensor_anomaly_threshold=sensor_anomaly_threshold)

    # 5. Missing sensors
    df = detect_missing_sensors(df)

    # Combine all indicators into a score
    for col in SCRAP_COLUMNS:
        if col not in df.columns:
            df[col] = False

    df["SCRAP_SCORE"] = df[SCRAP_COLUMNS].sum(axis=1)
    df["SCRAP_INDICATOR"] = df["SCRAP_SCORE"] >= 1

    # Apply conservative fallback when indicator rate is unrealistically high
    df = _apply_conservative_fallback(df)

    return df


def detect_warmup_shots(
    df: pd.DataFrame,
    warmup_shots_after_idle: int = WARMUP_SHOTS_AFTER_IDLE,
) -> pd.DataFrame:
    """Mark the first N shots after an idle-gap as warm-up scrap candidates.

    Args:
        df: DataFrame with DOWNTIME_GAP_FLAG column.
        warmup_shots_after_idle: How many shots after a gap to flag.

    Returns:
        DataFrame with SCRAP_WARMUP column updated.
    """
    df = df.sort_values("SHOT_TIME")
    downtime_after = df["DOWNTIME_GAP_FLAG"].shift(1).fillna(False)

    warmup_mask = downtime_after.copy()
    for i in range(1, warmup_shots_after_idle):
        warmup_mask = warmup_mask | downtime_after.shift(-i).fillna(False)

    df["SCRAP_WARMUP"] = warmup_mask
    return df


def detect_low_parameter_shots(
    df: pd.DataFrame,
    low_temp_threshold: float = LOW_TEMP_THRESHOLD,
) -> pd.DataFrame:
    """Flag shots with temperature below a fraction of the part-level mean.

    Pressure data is not available so SCRAP_LOW_PRESSURE is always False.

    Args:
        df: DataFrame with optional TEMPERATURE and PRODUCT_NAME columns.
        low_temp_threshold: Fraction of mean temperature to use as cutoff.

    Returns:
        DataFrame with SCRAP_LOW_PRESSURE and SCRAP_LOW_TEMP updated.
    """
    df["SCRAP_LOW_PRESSURE"] = False

    if "TEMPERATURE" in df.columns:
        temp_stats = (
            df.groupby("PRODUCT_NAME")["TEMPERATURE"].agg(["mean", "std"]).reset_index()
        )
        df = df.merge(
            temp_stats, on="PRODUCT_NAME", how="left", suffixes=("", "_temp_stats")
        ).reset_index(drop=True)

        df["SCRAP_LOW_TEMP"] = df["TEMPERATURE"] < (
            df["mean_temp_stats"] * low_temp_threshold
        )
    else:
        df["SCRAP_LOW_TEMP"] = False

    return df


def detect_sensor_anomalies(
    df: pd.DataFrame,
    sensor_anomaly_threshold: float = SENSOR_ANOMALY_THRESHOLD,
) -> pd.DataFrame:
    """Detect temperature sensor anomalies using the 3-sigma rule per part.

    Args:
        df: DataFrame with optional TEMPERATURE and PRODUCT_NAME columns.
        sensor_anomaly_threshold: Number of standard deviations for the bound.

    Returns:
        DataFrame with SCRAP_SENSOR_ANOMALY updated.
    """
    if "TEMPERATURE" not in df.columns:
        df["SCRAP_SENSOR_ANOMALY"] = False
        return df

    # Drop prior stats columns to avoid merge conflicts
    cols_to_drop = [c for c in df.columns if c.startswith(("mean_temp_", "std_temp_"))]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    temp_stats = (
        df.groupby("PRODUCT_NAME")["TEMPERATURE"].agg(["mean", "std"]).reset_index()
    )
    df = df.merge(
        temp_stats, on="PRODUCT_NAME", how="left", suffixes=("", "_temp_stats")
    ).reset_index(drop=True)

    mean_col = "mean_temp_stats"
    std_col = "std_temp_stats"

    if mean_col in df.columns and std_col in df.columns:
        mean_vals = df[mean_col].values
        std_vals = df[std_col].values
        temp_vals = df["TEMPERATURE"].values

        valid_mask = ~(np.isnan(mean_vals) | np.isnan(std_vals) | np.isnan(temp_vals))
        anomaly_mask = np.zeros(len(df), dtype=bool)

        if np.any(valid_mask):
            lower = (
                mean_vals[valid_mask] - sensor_anomaly_threshold * std_vals[valid_mask]
            )
            upper = (
                mean_vals[valid_mask] + sensor_anomaly_threshold * std_vals[valid_mask]
            )
            temp_valid = temp_vals[valid_mask]
            anomaly_mask[valid_mask] = (temp_valid < lower) | (temp_valid > upper)

        df["SCRAP_SENSOR_ANOMALY"] = anomaly_mask
    else:
        df["SCRAP_SENSOR_ANOMALY"] = False

    return df


def detect_missing_sensors(df: pd.DataFrame) -> pd.DataFrame:
    """Interpolate missing temperature values rather than flagging as scrap.

    Args:
        df: DataFrame with optional TEMPERATURE column.

    Returns:
        DataFrame with SCRAP_MISSING_SENSORS set to False and temperature
        values interpolated where possible.
    """
    df["SCRAP_MISSING_SENSORS"] = False

    if "TEMPERATURE" not in df.columns:
        return df

    df = df.sort_values("SHOT_TIME").reset_index(drop=True)
    missing_before = int(df["TEMPERATURE"].isnull().sum())

    df["TEMPERATURE"] = df["TEMPERATURE"].interpolate(method="linear")
    df["TEMPERATURE"] = df["TEMPERATURE"].fillna(method="ffill").fillna(method="bfill")

    missing_after = int(df["TEMPERATURE"].isnull().sum())
    if missing_before > 0:
        print(
            "   Temperature interpolation: %d missing values -> %d remaining",
        )
        interpolated = missing_before - missing_after
        print("   Interpolated %d temperature values", interpolated)

    return df


def calculate_scrap_statistics(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Print scrap statistics and return per-part scrap breakdown.

    Args:
        df: DataFrame with all SCRAP_* columns already computed.

    Returns:
        A per-part scrap summary DataFrame, or None if PRODUCT_NAME is absent.
    """
    total_shots = len(df)
    scrap_shots = int(df["SCRAP_INDICATOR"].sum())
    total_scrap_score = int(df["SCRAP_SCORE"].sum())

    print("\n  Scrap Statistics for Equipment:")
    print("   Total shots: %d" % total_shots)
    print(
        "   Suspected scrap shots: %d (%.1f%%)"
        % (scrap_shots, (scrap_shots / total_shots) * 100)
    )
    print("   Total scrap indicators: %d" % total_scrap_score)

    scrap_type_labels: Dict[str, str] = {
        "Abnormal CT": "SCRAP_CT_ABNORMAL",
        "Warm-up shots": "SCRAP_WARMUP",
        "Low temperature": "SCRAP_LOW_TEMP",
        "Sensor anomalies": "SCRAP_SENSOR_ANOMALY",
        "Missing sensors": "SCRAP_MISSING_SENSORS",
    }

    print("\n  Scrap Type Breakdown:")
    for label, column in scrap_type_labels.items():
        if column in df.columns:
            count = int(df[column].sum())
            pct = (count / total_shots) * 100
            print("   %s: %d shots (%.1f%%)" % (label, count, pct))

    part_scrap: Optional[pd.DataFrame] = None
    if "PRODUCT_NAME" in df.columns:
        part_scrap = (
            df.groupby("PRODUCT_NAME")
            .agg({"SCRAP_INDICATOR": "sum", "DURATION": "count", "SCRAP_SCORE": "sum"})
            .round(2)
        )
        part_scrap.columns = ["Scrap_Shots", "Total_Shots", "Total_Scrap_Score"]
        part_scrap["Scrap_Rate"] = (
            part_scrap["Scrap_Shots"] / part_scrap["Total_Shots"] * 100
        ).round(2)
        part_scrap = part_scrap.sort_values("Scrap_Rate", ascending=False)

        print("\n  Scrap by Part:")
        print(part_scrap.head(10))

    if scrap_shots > 0:
        avg_duration = df["DURATION"].mean()
        time_lost_min = scrap_shots * avg_duration / 60
        print("\n  Estimated time lost to scrap: %.1f minutes" % time_lost_min)

    return part_scrap


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_conservative_fallback(df: pd.DataFrame) -> pd.DataFrame:
    """Reduce scrap indicator set when the rate is unrealistically high.

    If more than 50% of shots are flagged, first exclude SCRAP_MISSING_SENSORS.
    If still above 50%, fall back to SCRAP_CT_ABNORMAL only.
    """
    total_shots = len(df) if len(df) else 1
    indicator_count = int(df["SCRAP_INDICATOR"].sum())
    indicator_rate = indicator_count / total_shots * 100

    if indicator_rate <= 50:
        return df

    print(
        "   WARNING: Scrap indicator rate > 50%%. "
        "Excluding SCRAP_MISSING_SENSORS from indicator"
    )
    conservative = (
        df["SCRAP_CT_ABNORMAL"]
        | df["SCRAP_WARMUP"]
        | df["SCRAP_LOW_PRESSURE"]
        | df["SCRAP_LOW_TEMP"]
        | df["SCRAP_SENSOR_ANOMALY"]
    )
    df["SCRAP_INDICATOR"] = conservative

    indicator_count = int(df["SCRAP_INDICATOR"].sum())
    indicator_rate = indicator_count / total_shots * 100
    print(
        "   Equipment Scrap Indicator (conservative): %d shots (%.2f%%)"
        % (indicator_count, indicator_rate)
    )

    if indicator_rate > 50:
        print("   WARNING: Still high. Falling back to SCRAP_CT_ABNORMAL only.")
        df["SCRAP_INDICATOR"] = df["SCRAP_CT_ABNORMAL"].copy()

    return df
