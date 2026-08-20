"""
Duration deviation calculations using multiple statistical methods for Pareto analysis.
Provides standalone functions for standard deviation, IQR, Z-score, percentile, and rolling
window outlier detection on manufacturing shot data.
Used by ParetoAnalysis to compute composite duration deviation scores.
"""

from typing import List

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Default thresholds (callers may override)
# ---------------------------------------------------------------------------
STD_DEVIATION_THRESHOLD: float = 3.0
IQR_MULTIPLIER: float = 1.5
Z_SCORE_THRESHOLD: float = 2.5

# Minimum number of shots per group to perform statistics
MIN_GROUP_SIZE: int = 10
MIN_ROLLING_SIZE: int = 20
ROLLING_WINDOW: int = 10
ROLLING_MIN_PERIODS: int = 5

# Composite issue thresholds
OUTLIER_METHODS_REQUIRED: int = 2
HIGH_DEVIATION_PCT: float = 25.0
CRITICAL_DEVIATION_PCT: float = 50.0
SIGNIFICANT_DEVIATION_PCT: float = 25.0
MODERATE_DEVIATION_PCT: float = 10.0
TARGET_DURATION_WEIGHT: float = 0.3
STATISTICAL_WEIGHT: float = 0.7


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------


def calculate_statistical_deviations(
    df: pd.DataFrame,
    std_threshold: float = STD_DEVIATION_THRESHOLD,
    iqr_multiplier: float = IQR_MULTIPLIER,
    z_score_threshold: float = Z_SCORE_THRESHOLD,
) -> pd.DataFrame:
    """Run all five statistical deviation methods and combine results.

    Mutates *df* in place and returns the same frame with deviation columns.

    Args:
        df: Manufacturing shot data with MACHINE_ID, PRODUCT_NAME, DURATION columns.
        std_threshold: Sigma multiplier for standard deviation method.
        iqr_multiplier: IQR multiplier for box-plot method.
        z_score_threshold: Z-score cutoff for outlier detection.

    Returns:
        DataFrame with outlier flags, deviation percentages, and composite scores.
    """
    print("\n  Calculating statistical duration deviations...")

    df = calculate_std_deviations(df, std_threshold=std_threshold)
    df = calculate_iqr_deviations(df, iqr_multiplier=iqr_multiplier)
    df = calculate_zscore_deviations(df, z_score_threshold=z_score_threshold)
    df = calculate_percentile_deviations(df)
    df = calculate_rolling_deviations(df, z_score_threshold=z_score_threshold)
    df = combine_deviation_methods(df)

    print("  Statistical deviation calculations complete")
    display_statistical_summary(df)
    return df


# ---------------------------------------------------------------------------
# Individual methods
# ---------------------------------------------------------------------------


def calculate_std_deviations(
    df: pd.DataFrame,
    std_threshold: float = STD_DEVIATION_THRESHOLD,
) -> pd.DataFrame:
    """Flag outliers using the N-sigma rule per equipment-part group.

    Args:
        df: Shot data.
        std_threshold: Number of standard deviations for the bound.

    Returns:
        DataFrame with STD_OUTLIER and DEVIATION_FROM_MEAN_PCT columns.
    """
    df = df.reset_index(drop=True)

    ct_stats = (
        df.groupby(["MACHINE_ID", "PRODUCT_NAME"])["DURATION"]
        .agg(["count", "mean", "std", "min", "max"])
        .reset_index()
    )
    ct_stats = ct_stats[ct_stats["count"] >= MIN_GROUP_SIZE]
    ct_stats["lower_bound"] = ct_stats["mean"] - (std_threshold * ct_stats["std"])
    ct_stats["upper_bound"] = ct_stats["mean"] + (std_threshold * ct_stats["std"])

    merge_cols = [
        "MACHINE_ID",
        "PRODUCT_NAME",
        "mean",
        "std",
        "lower_bound",
        "upper_bound",
    ]
    df = df.merge(
        ct_stats[merge_cols],
        on=["MACHINE_ID", "PRODUCT_NAME"],
        how="left",
    ).reset_index(drop=True)

    df["DEVIATION_FROM_MEAN_PCT"] = np.where(
        df["mean"].notna(),
        ((df["DURATION"] - df["mean"]) / df["mean"]) * 100,
        np.nan,
    )
    df["STD_OUTLIER"] = (df["DURATION"] < df["lower_bound"]) | (
        df["DURATION"] > df["upper_bound"]
    )
    return df


def calculate_iqr_deviations(
    df: pd.DataFrame,
    iqr_multiplier: float = IQR_MULTIPLIER,
) -> pd.DataFrame:
    """Flag outliers using the IQR (box-plot) method per equipment-part group.

    Args:
        df: Shot data.
        iqr_multiplier: Multiplier for IQR bounds.

    Returns:
        DataFrame with IQR_OUTLIER and DEVIATION_FROM_MEDIAN_PCT columns.
    """
    df = df.reset_index(drop=True)

    ct_stats = (
        df.groupby(["MACHINE_ID", "PRODUCT_NAME"])["DURATION"]
        .agg(["count", "median"])
        .reset_index()
    )
    q1_stats = (
        df.groupby(["MACHINE_ID", "PRODUCT_NAME"])["DURATION"]
        .quantile(0.25)
        .reset_index()
        .rename(columns={"DURATION": "q1"})
    )
    q3_stats = (
        df.groupby(["MACHINE_ID", "PRODUCT_NAME"])["DURATION"]
        .quantile(0.75)
        .reset_index()
        .rename(columns={"DURATION": "q3"})
    )

    ct_stats = ct_stats.merge(q1_stats, on=["MACHINE_ID", "PRODUCT_NAME"])
    ct_stats = ct_stats.merge(q3_stats, on=["MACHINE_ID", "PRODUCT_NAME"])
    ct_stats = ct_stats[ct_stats["count"] >= MIN_GROUP_SIZE]

    ct_stats["iqr"] = ct_stats["q3"] - ct_stats["q1"]
    ct_stats["lower_bound_iqr"] = ct_stats["q1"] - (iqr_multiplier * ct_stats["iqr"])
    ct_stats["upper_bound_iqr"] = ct_stats["q3"] + (iqr_multiplier * ct_stats["iqr"])

    merge_cols = [
        "MACHINE_ID",
        "PRODUCT_NAME",
        "median",
        "iqr",
        "lower_bound_iqr",
        "upper_bound_iqr",
    ]
    df = df.merge(
        ct_stats[merge_cols],
        on=["MACHINE_ID", "PRODUCT_NAME"],
        how="left",
    ).reset_index(drop=True)

    if "median" not in df.columns:
        print("   WARNING: median column not found in IQR method, creating...")
        median_stats = (
            df.groupby(["MACHINE_ID", "PRODUCT_NAME"])["DURATION"]
            .median()
            .reset_index()
            .rename(columns={"DURATION": "median"})
        )
        df = df.merge(median_stats, on=["MACHINE_ID", "PRODUCT_NAME"], how="left")

    df["DEVIATION_FROM_MEDIAN_PCT"] = np.where(
        df["median"].notna(),
        ((df["DURATION"] - df["median"]) / df["median"]) * 100,
        np.nan,
    )
    df["IQR_OUTLIER"] = (df["DURATION"] < df["lower_bound_iqr"]) | (
        df["DURATION"] > df["upper_bound_iqr"]
    )
    return df


def calculate_zscore_deviations(
    df: pd.DataFrame,
    z_score_threshold: float = Z_SCORE_THRESHOLD,
) -> pd.DataFrame:
    """Flag outliers using Z-scores per equipment-part group.

    Args:
        df: Shot data.
        z_score_threshold: Absolute Z-score above which a shot is an outlier.

    Returns:
        DataFrame with Z_SCORE and ZSCORE_OUTLIER columns.
    """
    df = df.reset_index(drop=True)

    ct_stats = (
        df.groupby(["MACHINE_ID", "PRODUCT_NAME"])["DURATION"]
        .agg(["count", "mean", "std"])
        .reset_index()
    )
    ct_stats = ct_stats[ct_stats["count"] >= MIN_GROUP_SIZE]

    df = df.merge(
        ct_stats[["MACHINE_ID", "PRODUCT_NAME", "mean", "std"]],
        on=["MACHINE_ID", "PRODUCT_NAME"],
        how="left",
        suffixes=("", "_zscore"),
    ).reset_index(drop=True)

    df["Z_SCORE"] = np.where(
        df["std_zscore"].notna() & (df["std_zscore"] > 0),
        (df["DURATION"] - df["mean_zscore"]) / df["std_zscore"],
        np.nan,
    )
    df["ZSCORE_OUTLIER"] = np.abs(df["Z_SCORE"]) > z_score_threshold
    return df


def calculate_percentile_deviations(df: pd.DataFrame) -> pd.DataFrame:
    """Flag outliers using the 5th/95th percentile method per equipment-part.

    Returns:
        DataFrame with PERCENTILE_OUTLIER and DEVIATION_PERCENTILE columns.
    """
    df = df.reset_index(drop=True)

    ct_stats = (
        df.groupby(["MACHINE_ID", "PRODUCT_NAME"])["DURATION"]
        .agg(["count", "median"])
        .reset_index()
    )
    p5 = (
        df.groupby(["MACHINE_ID", "PRODUCT_NAME"])["DURATION"]
        .quantile(0.05)
        .reset_index()
        .rename(columns={"DURATION": "percentile_5"})
    )
    p95 = (
        df.groupby(["MACHINE_ID", "PRODUCT_NAME"])["DURATION"]
        .quantile(0.95)
        .reset_index()
        .rename(columns={"DURATION": "percentile_95"})
    )

    ct_stats = ct_stats.merge(p5, on=["MACHINE_ID", "PRODUCT_NAME"])
    ct_stats = ct_stats.merge(p95, on=["MACHINE_ID", "PRODUCT_NAME"])
    ct_stats = ct_stats[ct_stats["count"] >= MIN_GROUP_SIZE]

    merge_cols = [
        "MACHINE_ID",
        "PRODUCT_NAME",
        "percentile_5",
        "percentile_95",
        "median",
    ]
    df = df.merge(
        ct_stats[merge_cols],
        on=["MACHINE_ID", "PRODUCT_NAME"],
        how="left",
    ).reset_index(drop=True)

    if "median" not in df.columns:
        print("   WARNING: median column not found, creating from scratch...")
        median_stats = (
            df.groupby(["MACHINE_ID", "PRODUCT_NAME"])["DURATION"]
            .median()
            .reset_index()
            .rename(columns={"DURATION": "median"})
        )
        df = df.merge(median_stats, on=["MACHINE_ID", "PRODUCT_NAME"], how="left")

    df["PERCENTILE_RANGE"] = df["percentile_95"] - df["percentile_5"]
    df["DEVIATION_PERCENTILE"] = np.where(
        (
            df["PERCENTILE_RANGE"].notna()
            & (df["PERCENTILE_RANGE"] > 0)
            & df["median"].notna()
        ),
        ((df["DURATION"] - df["median"]) / df["PERCENTILE_RANGE"]) * 100,
        np.nan,
    )
    df["PERCENTILE_OUTLIER"] = (df["DURATION"] < df["percentile_5"]) | (
        df["DURATION"] > df["percentile_95"]
    )
    return df


def calculate_rolling_deviations(
    df: pd.DataFrame,
    z_score_threshold: float = Z_SCORE_THRESHOLD,
) -> pd.DataFrame:
    """Flag outliers using a rolling-window Z-score per equipment-part.

    Args:
        df: Shot data.
        z_score_threshold: Absolute rolling Z-score cutoff.

    Returns:
        DataFrame with ROLLING_DEVIATION and ROLLING_OUTLIER columns.
    """
    df = df.sort_values(["MACHINE_ID", "PRODUCT_NAME", "SHOT_TIME"])
    rolling_parts: List[pd.DataFrame] = []

    for (_equipment, _part), group in df.groupby(["MACHINE_ID", "PRODUCT_NAME"]):
        if len(group) >= MIN_ROLLING_SIZE:
            rolling_mean = (
                group["DURATION"]
                .rolling(
                    window=ROLLING_WINDOW,
                    min_periods=ROLLING_MIN_PERIODS,
                )
                .mean()
            )
            rolling_std = (
                group["DURATION"]
                .rolling(
                    window=ROLLING_WINDOW,
                    min_periods=ROLLING_MIN_PERIODS,
                )
                .std()
            )

            rolling_dev = np.where(
                rolling_std.notna() & (rolling_std > 0),
                ((group["DURATION"] - rolling_mean) / rolling_std),
                np.nan,
            )
            temp = group.copy()
            temp["ROLLING_DEVIATION"] = rolling_dev
            temp["ROLLING_OUTLIER"] = np.abs(rolling_dev) > z_score_threshold
            rolling_parts.append(temp)
        else:
            grp = group.copy()
            grp["ROLLING_DEVIATION"] = np.nan
            grp["ROLLING_OUTLIER"] = False
            rolling_parts.append(grp)

    df = pd.concat(rolling_parts, ignore_index=True)
    return df


def combine_deviation_methods(df: pd.DataFrame) -> pd.DataFrame:
    """Combine all five outlier methods into a composite score and issue flag.

    Returns:
        DataFrame with OUTLIER_SCORE, DEVIATION_PCT, DURATION_ISSUE_FLAG,
        and CT_ISSUE_TYPE columns.
    """
    outlier_cols = [
        "STD_OUTLIER",
        "IQR_OUTLIER",
        "ZSCORE_OUTLIER",
        "PERCENTILE_OUTLIER",
        "ROLLING_OUTLIER",
    ]
    for col in outlier_cols:
        if col not in df.columns:
            df[col] = False

    df["OUTLIER_SCORE"] = df[outlier_cols].sum(axis=1)

    deviation_cols = [
        "DEVIATION_FROM_MEAN_PCT",
        "DEVIATION_FROM_MEDIAN_PCT",
        "DEVIATION_PERCENTILE",
    ]
    for col in deviation_cols:
        if col not in df.columns:
            df[col] = 0.0

    df["DEVIATION_PCT"] = df[deviation_cols].abs().max(axis=1)

    # Blend with TARGET_DURATION when available
    if "TARGET_DURATION" in df.columns:
        approved_dev = np.where(
            df["TARGET_DURATION"].notna(),
            ((df["DURATION"] - df["TARGET_DURATION"]) / df["TARGET_DURATION"]) * 100,
            np.nan,
        )
        df["DEVIATION_PCT"] = np.where(
            df["DEVIATION_PCT"].notna() & pd.notna(approved_dev),
            (
                df["DEVIATION_PCT"] * STATISTICAL_WEIGHT
                + np.abs(approved_dev) * TARGET_DURATION_WEIGHT
            ),
            np.where(
                df["DEVIATION_PCT"].notna(),
                df["DEVIATION_PCT"],
                np.abs(approved_dev),
            ),
        )

    # Composite issue flag
    df["CT_ISSUE_FLAG"] = (df["OUTLIER_SCORE"] >= OUTLIER_METHODS_REQUIRED) | (
        df["DEVIATION_PCT"] > HIGH_DEVIATION_PCT
    )

    # Issue severity categories
    df["CT_ISSUE_TYPE"] = np.where(
        df["CT_ISSUE_FLAG"],
        np.where(
            df["DEVIATION_PCT"] > CRITICAL_DEVIATION_PCT,
            "Critical",
            np.where(
                df["DEVIATION_PCT"] > SIGNIFICANT_DEVIATION_PCT,
                "Significant",
                np.where(
                    df["DEVIATION_PCT"] > MODERATE_DEVIATION_PCT,
                    "Moderate",
                    "Minor",
                ),
            ),
        ),
        "Normal",
    )
    return df


def compare_with_original_status_flag(df: pd.DataFrame) -> None:
    """Print a comparison between statistical flags and original STATUS.

    Args:
        df: DataFrame with STATUS, DURATION_ISSUE_FLAG, and related columns.
    """
    print("\n" + "=" * 60)
    print("  COMPARISON: Statistical vs Original STATUS")
    print("=" * 60)

    original_issues = df[df["STATUS"] != "Normal CT"]
    statistical_issues = df[df["CT_ISSUE_FLAG"]]

    print("  Original STATUS issues: %d shots" % len(original_issues))
    print("  Statistical method issues: %d shots" % len(statistical_issues))

    overlap = df[(df["STATUS"] != "Normal CT") & df["CT_ISSUE_FLAG"]]

    print("  Overlap (both methods): %d shots" % len(overlap))
    print("  Only in original: %d shots" % (len(original_issues) - len(overlap)))
    print("  Only in statistical: %d shots" % (len(statistical_issues) - len(overlap)))

    if len(original_issues) > 0:
        agreement_pct = (len(overlap) / len(original_issues)) * 100
        print("  Agreement with original: %.1f%%" % agreement_pct)

    _print_comparison_examples(df)


def display_statistical_summary(df: pd.DataFrame) -> None:
    """Print a summary of the statistical analysis results.

    Args:
        df: DataFrame with CT_ISSUE_FLAG, DURATION_ISSUE_TYPE, and OUTLIER_SCORE.
    """
    total = len(df)
    issues = int(df["CT_ISSUE_FLAG"].sum())

    print("\n  Statistical Analysis Summary:")
    print("   Total shots analyzed: %d" % total)
    print("   Shots with issues: %d" % issues)
    print("   Issue rate: %.2f%%" % ((issues / total) * 100))

    issue_breakdown = df["CT_ISSUE_TYPE"].value_counts()
    print("\n  Issue Type Breakdown:")
    for issue_type, count in issue_breakdown.items():
        pct = (count / total) * 100
        print("   %s: %d shots (%.1f%%)" % (issue_type, count, pct))

    outlier_dist = df["OUTLIER_SCORE"].value_counts().sort_index()
    print("\n  Outlier Score Distribution:")
    for score, count in outlier_dist.items():
        pct = (count / total) * 100
        print("   Score %s: %d shots (%.1f%%)" % (score, count, pct))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _print_comparison_examples(df: pd.DataFrame) -> None:
    """Print example rows where statistical and original methods disagree."""
    show_cols_stat = [
        "MACHINE_ID",
        "PRODUCT_NAME",
        "DURATION",
        "DEVIATION_PCT",
        "OUTLIER_SCORE",
        "CT_ISSUE_TYPE",
    ]
    show_cols_orig = [
        "MACHINE_ID",
        "PRODUCT_NAME",
        "DURATION",
        "DEVIATION_PCT",
        "OUTLIER_SCORE",
        "STATUS",
    ]

    stat_only = df[(df["STATUS"] == "Normal CT") & df["CT_ISSUE_FLAG"]].head(5)
    print("\n  Shots flagged by statistical method but not original:")
    if len(stat_only) > 0:
        print(stat_only[show_cols_stat].to_string())

    orig_only = df[(df["STATUS"] != "Normal CT") & ~df["CT_ISSUE_FLAG"]].head(5)
    print("\n  Shots flagged by original but not statistical method:")
    if len(orig_only) > 0:
        print(orig_only[show_cols_orig].to_string())
