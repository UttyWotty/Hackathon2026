"""
Visualization helpers for manufacturing root cause analysis heatmaps and summaries.
Provides day-of-week issue rate heatmaps and downtime classification summary tables.
This module is extracted from advanced_analysis.py for single-responsibility compliance.
"""

import logging
from typing import Optional

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
import seaborn as sns  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Heatmap layout constants
HEATMAP_FIGURE_WIDTH = 15
HEATMAP_FIGURE_HEIGHT = 8
HEATMAP_DPI = 300
HEATMAP_TITLE_FONTSIZE = 16
HEATMAP_AXIS_FONTSIZE = 12
HEATMAP_LINE_WIDTH = 0.5

DAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# Summary formatting
SUMMARY_SEPARATOR_WIDTH = 60
PATTERN_SEPARATOR_WIDTH = 40


def create_day_of_week_heatmap(
    df: pd.DataFrame, save_path: Optional[str] = None
) -> pd.DataFrame:
    """Create day-of-week vs hour-of-day heatmap for issue rates.

    Builds a pivot table of issue rates grouped by DAY_OF_WEEK and HOUR,
    then renders a seaborn heatmap with optional file save.

    Args:
        df: DataFrame with DAY_OF_WEEK, HOUR, CT, and optionally CT_ISSUE_FLAG columns.
        save_path: File path to save the heatmap image. None skips saving.

    Returns:
        Pivot table DataFrame of issue rates (day x hour).
    """
    logger.info("Creating day of week heatmap...")

    heatmap_data = _build_heatmap_data(df)

    heatmap_pivot = heatmap_data.pivot(
        index="DAY_OF_WEEK", columns="HOUR", values="Issue_Rate"
    )
    heatmap_pivot = heatmap_pivot.reindex(DAY_ORDER)

    _render_heatmap(heatmap_pivot, save_path)

    return heatmap_pivot


def _build_heatmap_data(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate issue rate data by day and hour.

    Args:
        df: Source DataFrame with DAY_OF_WEEK, HOUR, CT columns.

    Returns:
        Aggregated DataFrame with Issue_Rate column.
    """
    if "CT_ISSUE_FLAG" in df.columns:
        heatmap_data = (
            df.groupby(["DAY_OF_WEEK", "HOUR"])
            .agg({"CT_ISSUE_FLAG": "sum", "CT": "count"})
            .reset_index()
        )
        heatmap_data["Issue_Rate"] = (
            heatmap_data["CT_ISSUE_FLAG"] / heatmap_data["CT"] * 100
        ).round(2)
    else:
        heatmap_data = (
            df.groupby(["DAY_OF_WEEK", "HOUR"]).agg({"CT": "count"}).reset_index()
        )
        heatmap_data["CT_ISSUE_FLAG"] = 0
        heatmap_data["Issue_Rate"] = 0.0

    return heatmap_data


def _render_heatmap(
    heatmap_pivot: pd.DataFrame, save_path: Optional[str] = None
) -> None:
    """Render and optionally save the heatmap figure.

    Args:
        heatmap_pivot: Pivot table of issue rates (day x hour).
        save_path: File path to save the figure. None skips saving.
    """
    plt.figure(figsize=(HEATMAP_FIGURE_WIDTH, HEATMAP_FIGURE_HEIGHT))
    sns.heatmap(
        heatmap_pivot,
        annot=True,
        fmt=".1f",
        cmap="RdYlBu_r",
        cbar_kws={"label": "Issue Rate (%)"},
        linewidths=HEATMAP_LINE_WIDTH,
    )

    plt.title(
        "Day of Week vs Hour Issue Rate Heatmap",
        fontsize=HEATMAP_TITLE_FONTSIZE,
        fontweight="bold",
    )
    plt.xlabel("Hour of Day", fontsize=HEATMAP_AXIS_FONTSIZE)
    plt.ylabel("Day of Week", fontsize=HEATMAP_AXIS_FONTSIZE)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=HEATMAP_DPI, bbox_inches="tight")
        logger.info("Heatmap saved to: %s", save_path)

    plt.show()


def create_downtime_classification_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Create summary of downtime classifications with pattern distribution.

    Aggregates downtime type statistics including shot count, issue count,
    mean risk score, and issue rate. Also logs CT pattern distribution.

    Args:
        df: DataFrame with DOWNTIME_TYPE, CT, RISK_SCORE, CT_PATTERN columns
            and optionally CT_ISSUE_FLAG.

    Returns:
        Summary DataFrame sorted by Issue_Rate descending.
    """
    logger.info("Creating downtime classification summary...")

    downtime_summary = _aggregate_downtime_stats(df)
    downtime_summary = downtime_summary.sort_values("Issue_Rate", ascending=False)

    logger.info("Downtime Classification Summary:")
    logger.info("=" * SUMMARY_SEPARATOR_WIDTH)
    logger.info("\n%s", downtime_summary)

    _log_pattern_distribution(df)

    return downtime_summary


def _aggregate_downtime_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate downtime statistics by type.

    Args:
        df: Source DataFrame with DOWNTIME_TYPE, CT, RISK_SCORE columns.

    Returns:
        Aggregated DataFrame with Issue_Rate column.
    """
    if "CT_ISSUE_FLAG" in df.columns:
        summary = (
            df.groupby("DOWNTIME_TYPE")
            .agg({"CT": "count", "CT_ISSUE_FLAG": "sum", "RISK_SCORE": "mean"})
            .round(3)
        )
        summary["Issue_Rate"] = (summary["CT_ISSUE_FLAG"] / summary["CT"] * 100).round(
            2
        )
    else:
        summary = (
            df.groupby("DOWNTIME_TYPE")
            .agg({"CT": "count", "RISK_SCORE": "mean"})
            .round(3)
        )
        summary["CT_ISSUE_FLAG"] = 0
        summary["Issue_Rate"] = 0.0

    return summary


def _log_pattern_distribution(df: pd.DataFrame) -> None:
    """Log the CT pattern distribution.

    Args:
        df: DataFrame with CT_PATTERN column.
    """
    pattern_dist = df["CT_PATTERN"].value_counts()
    logger.info("CT Pattern Distribution:")
    logger.info("=" * PATTERN_SEPARATOR_WIDTH)
    total_rows = len(df)
    for pattern, count in pattern_dist.items():
        pct = (count / total_rows) * 100
        logger.info("   %s: %s shots (%.1f%%)", pattern, f"{count:,}", pct)
