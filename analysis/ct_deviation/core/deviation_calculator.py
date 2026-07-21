"""
CT Deviation Calculator.

This module contains functions for calculating cycle time deviation metrics
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
    """Calculate comprehensive CT deviation metrics for each equipment in the dataset.

    Args:
        df: DataFrame with shot data (must have CT, APPROVED_CT, EQUIPMENT_CODE, SUPPLIER_NAME)

    Returns:
        List[DeviationMetrics]: List of deviation metrics for each equipment

    Raises:
        ValueError: If required columns are missing
    """
    if df.empty:
        logger.warning("⚠️ No data to analyze")
        return []

    # Validate required columns
    required_cols = ["CT", "APPROVED_CT", "EQUIPMENT_CODE", "SUPPLIER_NAME"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    metrics_list = []

    # Group by equipment code
    for equipment_code, group in df.groupby("EQUIPMENT_CODE"):
        try:
            metrics = _calculate_equipment_metrics(equipment_code, group)
            metrics_list.append(metrics)

        except Exception as e:
            logger.error(f"❌ Error calculating metrics for {equipment_code}: {e}")
            continue

    logger.info(f"✅ Calculated metrics for {len(metrics_list)} equipment")
    return metrics_list


def _calculate_equipment_metrics(
    equipment_code: str, group: pd.DataFrame
) -> DeviationMetrics:
    """Calculate deviation metrics for a single equipment.

    Args:
        equipment_code: Equipment identifier
        group: DataFrame with shots for this equipment

    Returns:
        DeviationMetrics: Comprehensive metrics for the equipment
    """
    # Basic calculations
    total_shots = len(group)
    avg_ct = group["CT"].mean()
    std_ct = group["CT"].std()
    approved_ct = group["APPROVED_CT"].iloc[0]  # Should be same for all rows
    supplier_name = group["SUPPLIER_NAME"].iloc[0]

    # Deviation calculations
    ct_deviation = avg_ct - approved_ct
    deviation_percentage = (ct_deviation / approved_ct) * 100

    # Categorize deviation
    deviation_category = categorize_deviation(deviation_percentage)

    # Shot distribution analysis
    tolerance = approved_ct * (ON_TARGET_TOLERANCE / 100)
    shots_above_target = len(group[group["CT"] > (approved_ct + tolerance)])
    shots_below_target = len(group[group["CT"] < (approved_ct - tolerance)])
    shots_on_target = total_shots - shots_above_target - shots_below_target

    # Efficiency score (based on shots within tolerance and average deviation)
    efficiency = calculate_efficiency_score(
        shots_on_target, total_shots, deviation_percentage
    )

    # Stability score (based on coefficient of variation)
    stability = calculate_stability_score(std_ct, avg_ct)

    return DeviationMetrics(
        equipment_code=equipment_code,
        supplier_name=supplier_name,
        total_shots=total_shots,
        avg_ct=round(avg_ct, 2),
        approved_ct=round(approved_ct, 2),
        ct_deviation=round(ct_deviation, 2),
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
    if df.empty or "CT" not in df.columns:
        empty_df = pd.DataFrame()
        return empty_df, empty_df, empty_df

    ct_mean = df["CT"].mean()
    ct_std = df["CT"].std()

    # Method 1: Mean ± 2*std
    mean_std_outliers = df[
        (df["CT"] < ct_mean - 2 * ct_std) | (df["CT"] > ct_mean + 2 * ct_std)
    ].copy()

    # Method 2: IQR method
    q1 = df["CT"].quantile(0.25)
    q3 = df["CT"].quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - IQR_MULTIPLIER * iqr
    upper_bound = q3 + IQR_MULTIPLIER * iqr
    iqr_outliers = df[(df["CT"] < lower_bound) | (df["CT"] > upper_bound)].copy()

    # Method 3: Z-score
    df["z_score"] = np.abs((df["CT"] - ct_mean) / ct_std)
    zscore_outliers = df[df["z_score"] > Z_SCORE_THRESHOLD].copy()

    logger.info(
        f"🔍 Detected outliers: Mean/Std={len(mean_std_outliers)}, "
        f"IQR={len(iqr_outliers)}, Z-score={len(zscore_outliers)}"
    )

    return mean_std_outliers, iqr_outliers, zscore_outliers


def calculate_rolling_deviation(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate rolling deviation statistics over a moving window.

    Args:
        df: DataFrame with CT and APPROVED_CT columns, sorted by time

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
    df["rolling_mean_ct"] = df["CT"].rolling(window=ROLLING_WINDOW_SIZE).mean()
    df["rolling_std_ct"] = df["CT"].rolling(window=ROLLING_WINDOW_SIZE).std()

    # Calculate rolling deviation from approved CT
    if "APPROVED_CT" in df.columns:
        df["rolling_deviation"] = df["rolling_mean_ct"] - df["APPROVED_CT"]
        df["rolling_deviation_pct"] = (
            df["rolling_deviation"] / df["APPROVED_CT"]
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
            "equipment_code": m.equipment_code,
            "deviation_pct": round(m.deviation_percentage, 2),
            "efficiency": round(m.efficiency_score, 2),
            "stability": round(m.stability_score, 2),
        }
        for m in top_performers
    ]

    worst_performers_dict = [
        {
            "equipment_code": m.equipment_code,
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
