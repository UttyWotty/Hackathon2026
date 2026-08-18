"""
Duration Efficiency Calculator.

This module contains functions for calculating duration efficiency metrics
with statistical confidence intervals.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import logging
from typing import Dict, List

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
from scipy import stats  # type: ignore[import-untyped]

from ..models import CONFIDENCE_LEVEL, EfficiencyMetrics

logger = logging.getLogger(__name__)


# ==================== Efficiency Calculation ==================== #


def calculate_duration_efficiency(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate duration efficiency using TARGET_DURATION as baseline.

    Args:
        df: DataFrame with DURATION and TARGET_DURATION columns

    Returns:
        pd.DataFrame: Data with efficiency and efficiency_pct columns added

    Formula:
        efficiency = TARGET_DURATION / actual_CT
        efficiency_pct = (efficiency - 1) * 100
    """
    logger.info("Calculating duration efficiency using TARGET_DURATION...")

    df = df.copy()

    # Calculate efficiency: TARGET_DURATION / actual_duration
    df["efficiency"] = df["TARGET_DURATION"] / df["DURATION"]
    df["efficiency_pct"] = (df["efficiency"] - 1) * 100

    # Handle edge cases - cap at reasonable bounds
    df.loc[df["efficiency_pct"] > 100, "efficiency_pct"] = (
        100  # Cap at 100% improvement
    )
    df.loc[df["efficiency_pct"] < -50, "efficiency_pct"] = -50  # Cap at 50% worse

    logger.info(
        f"Efficiency statistics: Mean={df['efficiency_pct'].mean():.2f}%, "
        f"Std={df['efficiency_pct'].std():.2f}%"
    )

    return df


def aggregate_per_tool(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate efficiency metrics per tool.

    Args:
        df: DataFrame with tool_id and efficiency_pct columns

    Returns:
        pd.DataFrame: Aggregated metrics per tool
    """
    logger.info("Aggregating efficiency metrics per tool...")

    tool_metrics = (
        df.groupby(["tool_id", "VENDOR_NAME", "TYPE"])
        .agg(
            mean_efficiency=("efficiency_pct", "mean"),
            std_efficiency=("efficiency_pct", "std"),
            median_efficiency=("efficiency_pct", "median"),
            sample_size=("efficiency_pct", "count"),
            min_duration=("DURATION", "min"),
            max_duration=("DURATION", "max"),
            mean_duration=("DURATION", "mean"),
            target_duration=("TARGET_DURATION", "first"),
        )
        .reset_index()
    )

    logger.info(f"✅ Aggregated data for {len(tool_metrics)} tools")

    return tool_metrics


def calculate_confidence_intervals(
    tool_metrics: pd.DataFrame, confidence_level: float = CONFIDENCE_LEVEL
) -> List[EfficiencyMetrics]:
    """Calculate confidence intervals for efficiency metrics.

    Args:
        tool_metrics: DataFrame with aggregated tool metrics
        confidence_level: Confidence level for intervals (default: 0.95)

    Returns:
        List[EfficiencyMetrics]: List of efficiency metrics with CIs
    """
    confidence_pct = int(confidence_level * 100)
    logger.info("Calculating %d%% confidence intervals...", confidence_pct)

    metrics_list = []

    for _, row in tool_metrics.iterrows():
        mean_eff = row["mean_efficiency"]
        std_eff = row["std_efficiency"]
        n = row["sample_size"]

        # Calculate standard error
        if n > 1 and not pd.isna(std_eff):
            se = std_eff / np.sqrt(n)

            # Calculate confidence interval using t-distribution
            t_critical = stats.t.ppf((1 + confidence_level) / 2, df=n - 1)
            ci_lower = mean_eff - t_critical * se
            ci_upper = mean_eff + t_critical * se
        else:
            # Not enough data for CI
            se = 0
            ci_lower = mean_eff
            ci_upper = mean_eff

        metrics = EfficiencyMetrics(
            efficiency=mean_eff,
            confidence_interval_lower=ci_lower,
            confidence_interval_upper=ci_upper,
            sample_size=int(n),
            standard_error=se,
        )

        metrics_list.append(metrics)

    logger.info(f"✅ Calculated CIs for {len(metrics_list)} tools")

    return metrics_list


def normalize_efficiency_scores(
    tool_metrics: pd.DataFrame, method: str = "z_score"
) -> pd.DataFrame:
    """Normalize efficiency scores for cross-comparison.

    Args:
        tool_metrics: DataFrame with mean_efficiency column
        method: Normalization method ('z_score', 'min_max', or 'percentile')

    Returns:
        pd.DataFrame: Data with normalized_efficiency column added
    """
    logger.info(f"Normalizing efficiency scores using {method} method...")

    tool_metrics = tool_metrics.copy()

    if method == "z_score":
        mean = tool_metrics["mean_efficiency"].mean()
        std = tool_metrics["mean_efficiency"].std()
        if std > 0:
            tool_metrics["normalized_efficiency"] = (
                tool_metrics["mean_efficiency"] - mean
            ) / std
        else:
            tool_metrics["normalized_efficiency"] = 0

    elif method == "min_max":
        min_val = tool_metrics["mean_efficiency"].min()
        max_val = tool_metrics["mean_efficiency"].max()
        if max_val > min_val:
            tool_metrics["normalized_efficiency"] = (
                tool_metrics["mean_efficiency"] - min_val
            ) / (max_val - min_val)
        else:
            tool_metrics["normalized_efficiency"] = 0.5

    elif method == "percentile":
        tool_metrics["normalized_efficiency"] = tool_metrics["mean_efficiency"].rank(
            pct=True
        )

    else:
        logger.warning(f"Unknown normalization method: {method}, using z_score")
        return normalize_efficiency_scores(tool_metrics, method="z_score")

    logger.info("✅ Normalization complete")

    return tool_metrics


def generate_efficiency_summary(tool_metrics: pd.DataFrame) -> Dict:
    """Generate summary statistics for efficiency analysis.

    Args:
        tool_metrics: DataFrame with aggregated tool metrics

    Returns:
        Dict: Summary statistics
    """
    summary = {
        "total_tools": len(tool_metrics),
        "total_shots": int(tool_metrics["sample_size"].sum()),
        "mean_efficiency": round(float(tool_metrics["mean_efficiency"].mean()), 2),
        "median_efficiency": round(float(tool_metrics["mean_efficiency"].median()), 2),
        "std_efficiency": round(float(tool_metrics["mean_efficiency"].std()), 2),
        "min_efficiency": round(float(tool_metrics["mean_efficiency"].min()), 2),
        "max_efficiency": round(float(tool_metrics["mean_efficiency"].max()), 2),
        "top_performers": tool_metrics.nlargest(5, "mean_efficiency")[
            ["tool_id", "VENDOR_NAME", "mean_efficiency"]
        ].to_dict("records"),
        "bottom_performers": tool_metrics.nsmallest(5, "mean_efficiency")[
            ["tool_id", "VENDOR_NAME", "mean_efficiency"]
        ].to_dict("records"),
    }

    return summary
