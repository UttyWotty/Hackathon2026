"""
Duration Deviation Calculator.

This module contains functions for calculating duration deviation metrics
and statistical analysis.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import logging
from typing import Dict, List, Tuple

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from ..models import (
    IQR_MULTIPLIER,
    ON_TARGET_TOLERANCE,
    ROLLING_WINDOW_SIZE,
    Z_SCORE_THRESHOLD,
    DeviationMetrics,
    calculate_efficiency_score,
    calculate_stability_score,
    categorize_deviation,
)

logger = logging.getLogger(__name__)


# ==================== Deviation Metrics Calculation ==================== #


def calculate_deviation_metrics(df: pd.DataFrame) -> List[DeviationMetrics]:
    """Calculate comprehensive duration deviation metrics for each equipment in the dataset.

    Args:
        df: DataFrame with shot data (must have duration, TARGET_DURATION, MACHINE_ID, VENDOR_NAME)

    Returns:
        List[DeviationMetrics]: List of deviation metrics for each equipment

    Raises:
        ValueError: If required columns are missing
    """
    if df.empty:
        logger.warning("⚠️ No data to analyze")
        return []

    # Validate required columns
    required_cols = ["DURATION", "TARGET_DURATION", "MACHINE_ID", "VENDOR_NAME"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    metrics_list = []

    # Group by equipment code
    for machine_id, group in df.groupby("MACHINE_ID"):
        try:
            metrics = _calculate_equipment_metrics(machine_id, group)
            metrics_list.append(metrics)

        except Exception as e:
            logger.error(f"❌ Error calculating metrics for {machine_id}: {e}")
            continue

    logger.info(f"✅ Calculated metrics for {len(metrics_list)} equipment")
    return metrics_list


def _calculate_equipment_metrics(
    machine_id: str, group: pd.DataFrame
) -> DeviationMetrics:
    """Calculate deviation metrics for a single equipment.

    Args:
        machine_id: Equipment identifier
        group: DataFrame with shots for this equipment

    Returns:
        DeviationMetrics: Comprehensive metrics for the equipment
    """
    # Basic calculations
    total_shots = len(group)
    avg_duration = group["DURATION"].mean()
    std_ct = group["DURATION"].std()
    target_duration = group["TARGET_DURATION"].iloc[0]  # Should be same for all rows
    vendor_name = group["VENDOR_NAME"].iloc[0]

    # Deviation calculations
    deviation = avg_duration - target_duration
    deviation_percentage = (deviation / target_duration) * 100

    # Categorize deviation
    deviation_category = categorize_deviation(deviation_percentage)

    # Shot distribution analysis
    tolerance = target_duration * (ON_TARGET_TOLERANCE / 100)
    shots_above_target = len(group[group["DURATION"] > (target_duration + tolerance)])
    shots_below_target = len(group[group["DURATION"] < (target_duration - tolerance)])
    shots_on_target = total_shots - shots_above_target - shots_below_target

    # Efficiency score (based on shots within tolerance and average deviation)
    efficiency = calculate_efficiency_score(
        shots_on_target, total_shots, deviation_percentage
    )

    # Stability score (based on coefficient of variation)
    stability = calculate_stability_score(std_ct, avg_duration)

    return DeviationMetrics(
        machine_id=machine_id,
        vendor_name=vendor_name,
        total_shots=total_shots,
        avg_duration=round(avg_duration, 2),
        target_duration=round(target_duration, 2),
        deviation=round(deviation, 2),
        deviation_percentage=round(deviation_percentage, 2),
        deviation_category=deviation_category,
        shots_above_target=shots_above_target,
        shots_below_target=shots_below_target,
        shots_on_target=shots_on_target,
        efficiency_score=efficiency,
        stability_score=stability,
    )


# ==================== Statistical Outlier Detection ==================== #


def detect_statistical_outliers(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Detect statistical outliers using mean/std, IQR, and z-score methods.

    Args:
        df: DataFrame with CT data

    Returns:
        Tuple of (mean_std_outliers, iqr_outliers, zscore_outliers) DataFrames
    """
    if df.empty or "DURATION" not in df.columns:
        empty_df = pd.DataFrame()
        return empty_df, empty_df, empty_df

    ct_mean = df["DURATION"].mean()
    ct_std = df["DURATION"].std()

    # Method 1: Mean ± 2*std
    mean_std_outliers = df[
        (df["DURATION"] < ct_mean - 2 * ct_std) | (df["DURATION"] > ct_mean + 2 * ct_std)
    ].copy()

    # Method 2: IQR method
    q1 = df["DURATION"].quantile(0.25)
    q3 = df["DURATION"].quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - IQR_MULTIPLIER * iqr
    upper_bound = q3 + IQR_MULTIPLIER * iqr
    iqr_outliers = df[(df["DURATION"] < lower_bound) | (df["DURATION"] > upper_bound)].copy()

    # Method 3: Z-score
    df["z_score"] = np.abs((df["DURATION"] - ct_mean) / ct_std)
    zscore_outliers = df[df["z_score"] > Z_SCORE_THRESHOLD].copy()

    logger.info(
        f"🔍 Detected outliers: Mean/Std={len(mean_std_outliers)}, "
        f"IQR={len(iqr_outliers)}, Z-score={len(zscore_outliers)}"
    )

    return mean_std_outliers, iqr_outliers, zscore_outliers


def calculate_rolling_deviation(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate rolling deviation statistics over a moving window.

    Args:
        df: DataFrame with DURATION and TARGET_DURATION columns, sorted by time

    Returns:
        pd.DataFrame: Original data with added rolling deviation columns
    """
    if df.empty or len(df) < ROLLING_WINDOW_SIZE:
        logger.warning(
            f"⚠️ Insufficient data for rolling window analysis "
            f"(need {ROLLING_WINDOW_SIZE}, got {len(df)})"
        )
        return df

    df = df.copy()

    # Calculate rolling statistics
    df["rolling_mean_duration"] = df["DURATION"].rolling(window=ROLLING_WINDOW_SIZE).mean()
    df["rolling_std_ct"] = df["DURATION"].rolling(window=ROLLING_WINDOW_SIZE).std()

    # Calculate rolling deviation from approved duration
    if "TARGET_DURATION" in df.columns:
        df["rolling_deviation"] = df["rolling_mean_duration"] - df["TARGET_DURATION"]
        df["rolling_deviation_pct"] = (
            df["rolling_deviation"] / df["TARGET_DURATION"]
        ) * 100

    logger.info(f"✅ Calculated rolling deviation over {ROLLING_WINDOW_SIZE} shots")

    return df


# ==================== Summary Statistics ==================== #


def generate_summary_statistics(metrics_list: List[DeviationMetrics]) -> Dict:
    """Generate comprehensive summary statistics from deviation metrics.

    Args:
        metrics_list: List of DeviationMetrics for all equipment

    Returns:
        Dict: Summary statistics including averages, distributions, and rankings
    """
    if not metrics_list:
        return {}

    # Overall statistics
    total_equipment = len(metrics_list)
    total_shots = sum(m.total_shots for m in metrics_list)
    avg_deviation = np.mean([m.deviation_percentage for m in metrics_list])
    avg_efficiency = np.mean([m.efficiency_score for m in metrics_list])
    avg_stability = np.mean([m.stability_score for m in metrics_list])

    # Category distribution
    category_counts = {}
    for m in metrics_list:
        cat = m.deviation_category.value
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Rankings
    top_performers = sorted(metrics_list, key=lambda x: abs(x.deviation_percentage))[:5]
    worst_performers = sorted(
        metrics_list, key=lambda x: abs(x.deviation_percentage), reverse=True
    )[:5]

    # Convert to dict for serialization
    top_performers_dict = [
        {
            "machine_id": m.machine_id,
            "deviation_pct": round(m.deviation_percentage, 2),
            "efficiency": round(m.efficiency_score, 2),
            "stability": round(m.stability_score, 2),
        }
        for m in top_performers
    ]

    worst_performers_dict = [
        {
            "machine_id": m.machine_id,
            "deviation_pct": round(m.deviation_percentage, 2),
            "efficiency": round(m.efficiency_score, 2),
            "stability": round(m.stability_score, 2),
        }
        for m in worst_performers
    ]

    return {
        "total_equipment": total_equipment,
        "total_shots": total_shots,
        "avg_deviation": round(avg_deviation, 2),
        "avg_efficiency": round(avg_efficiency, 2),
        "avg_stability": round(avg_stability, 2),
        "category_distribution": category_counts,
        "top_performers": top_performers_dict,
        "worst_performers": worst_performers_dict,
    }
