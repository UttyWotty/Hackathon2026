"""
Analysis functions for Pareto-based root cause analysis on manufacturing shot data.
Provides standalone functions to analyze duration issues, temperature, downtime
patterns, scrap patterns, equipment performance, and time series trends.
Recommendation generation is delegated to pareto_recommendations.py.
"""

from typing import List

import matplotlib.pyplot as plt
import pandas as pd

from .pareto_recommendations import generate_recommendations  # noqa: F401 -- re-export

# ---------------------------------------------------------------------------
# Default thresholds (callers may override)
# ---------------------------------------------------------------------------
TEMP_CV_THRESHOLD: float = 10.0
EQUIPMENT_ISSUE_THRESHOLD: float = 10.0
TIME_MULTIPLIER_THRESHOLD: float = 1.5

# Number of top items to display in pareto charts
DEFAULT_TOP_N: int = 10


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_duration_issues(
    df: pd.DataFrame,
    pareto_chart_fn: object,
) -> None:
    """Analyze duration deviations using pre-computed statistical flags.

    Args:
        df: DataFrame with CT_ISSUE_FLAG, DURATION_ISSUE_TYPE, and outlier columns.
        pareto_chart_fn: Callable that creates a pareto chart (from ParetoAnalysis).
    """
    print("\n" + "=" * 60)
    print("  STATISTICAL CYCLE TIME DEVIATION ANALYSIS")
    print("=" * 60)

    problematic = df[df["CT_ISSUE_FLAG"]]
    if len(problematic) == 0:
        print("  No duration issues found using statistical methods.")
        return

    print("  Found %d shots with statistical duration issues" % len(problematic))
    print("  Issue rate: %.2f%%" % ((len(problematic) / len(df)) * 100))

    _print_outlier_method_breakdown(df)

    print("\n  1. Pareto Analysis by Statistical Issue Type:")
    pareto_chart_fn(
        problematic["CT_ISSUE_TYPE"],
        "Duration Issues by Statistical Type",
        "Issue Type",
        "Number of Shots",
    )

    if "STATUS" in df.columns:
        from .pareto_deviations import compare_with_original_status_flag

        compare_with_original_status_flag(df)

    print("\n  2. Pareto Analysis by Equipment Code:")
    pareto_chart_fn(
        problematic["MACHINE_ID"],
        "Duration Issues by Equipment",
        "Equipment Code",
        "Number of Shots",
    )

    print("\n  3. Pareto Analysis by Part Name:")
    pareto_chart_fn(
        problematic["PRODUCT_NAME"],
        "Duration Issues by Part",
        "Part Name",
        "Number of Shots",
    )

    print("\n  4. Pareto Analysis by Day of Week:")
    pareto_chart_fn(
        problematic["DAY_OF_WEEK"],
        "Duration Issues by Day of Week",
        "Day of Week",
        "Number of Shots",
    )

    print("\n  5. Pareto Analysis by Hour of Day:")
    pareto_chart_fn(
        problematic["HOUR"],
        "Duration Issues by Hour",
        "Hour of Day",
        "Number of Shots",
    )


def analyze_temperature_issues(
    df: pd.DataFrame,
    pareto_chart_fn: object,
    temp_cv_threshold: float = TEMP_CV_THRESHOLD,
) -> None:
    """Analyze temperature-related issues per equipment.

    Args:
        df: DataFrame with TEMPERATURE and MACHINE_ID columns.
        pareto_chart_fn: Callable for creating pareto charts.
        temp_cv_threshold: CV percentage above which variation is flagged.
    """
    print("\n" + "=" * 60)
    print("  TEMPERATURE ANALYSIS")
    print("=" * 60)

    temp_stats = (
        df.groupby("MACHINE_ID")["TEMPERATURE"]
        .agg(["count", "mean", "std", "min", "max"])
        .round(2)
    )
    temp_stats["cv"] = (temp_stats["std"] / temp_stats["mean"] * 100).round(2)
    high_var = temp_stats[temp_stats["cv"] > temp_cv_threshold].sort_values(
        "cv",
        ascending=False,
    )

    print("  Temperature analysis for %d equipment" % len(temp_stats))
    print(
        "  Found %d equipment with high temperature variation (>%.0f%% CV)"
        % (len(high_var), temp_cv_threshold)
    )

    if len(high_var) > 0:
        print("\n  Equipment with High Temperature Variation:")
        print(high_var.head(DEFAULT_TOP_N))

        high_var_shots = df[df["MACHINE_ID"].isin(high_var.index)]
        pareto_chart_fn(
            high_var_shots["MACHINE_ID"],
            "Shots from Equipment with High Temperature Variation",
            "Equipment Code",
            "Number of Shots",
        )


def analyze_downtime_patterns(
    df: pd.DataFrame,
    pareto_chart_fn: object,
) -> None:
    """Analyze downtime patterns by part, day, and hour.

    Args:
        df: DataFrame with DOWNTIME_EVENT, TIME_GAP_MINUTES, and time columns.
        pareto_chart_fn: Callable for creating pareto charts.
    """
    print("\n" + "=" * 60)
    print("  DOWNTIME PATTERN ANALYSIS")
    print("=" * 60)

    downtime_shots = df[df["DOWNTIME_EVENT"]]
    if len(downtime_shots) == 0:
        print("  No downtime events detected.")
        return

    print("  Found %d downtime events" % len(downtime_shots))
    print("  Downtime rate: %.2f%%" % ((len(downtime_shots) / len(df)) * 100))

    print("\n  1. Pareto Analysis by Part (Downtime Events):")
    pareto_chart_fn(
        downtime_shots["PRODUCT_NAME"],
        "Downtime Events by Part",
        "Part Name",
        "Number of Downtime Events",
    )

    print("\n  3. Downtime Events by Day of Week:")
    pareto_chart_fn(
        downtime_shots["DAY_OF_WEEK"],
        "Downtime Events by Day of Week",
        "Day of Week",
        "Number of Downtime Events",
    )

    print("\n  4. Downtime Events by Hour of Day:")
    pareto_chart_fn(
        downtime_shots["HOUR"],
        "Downtime Events by Hour",
        "Hour of Day",
        "Number of Downtime Events",
    )

    _print_downtime_duration_stats(df)
    _print_longest_downtimes(df)


def analyze_scrap_patterns(
    df: pd.DataFrame,
    pareto_chart_fn: object,
) -> None:
    """Analyze scrap patterns for single equipment.

    Args:
        df: DataFrame with SCRAP_INDICATOR and related scrap columns.
        pareto_chart_fn: Callable for creating pareto charts.
    """
    print("\n" + "=" * 60)
    print("  SCRAP PATTERN ANALYSIS")
    print("=" * 60)

    scrap_shots = df[df["SCRAP_INDICATOR"]]
    if len(scrap_shots) == 0:
        print("  No scrap indicators detected.")
        return

    print("  Found %d suspected scrap shots" % len(scrap_shots))
    print("  Scrap rate: %.2f%%" % ((len(scrap_shots) / len(df)) * 100))

    print("\n  1. Pareto Analysis by Part (Scrap Events):")
    pareto_chart_fn(
        scrap_shots["PRODUCT_NAME"],
        "Scrap Events by Part",
        "Part Name",
        "Number of Scrap Events",
    )

    _print_scrap_type_pareto(scrap_shots, pareto_chart_fn)

    print("\n  3. Scrap Events by Day of Week:")
    pareto_chart_fn(
        scrap_shots["DAY_OF_WEEK"],
        "Scrap Events by Day of Week",
        "Day of Week",
        "Number of Scrap Events",
    )

    print("\n  4. Scrap Events by Hour of Day:")
    pareto_chart_fn(
        scrap_shots["HOUR"],
        "Scrap Events by Hour",
        "Hour of Day",
        "Number of Scrap Events",
    )

    _print_scrap_score_distribution(df)
    _print_highest_scrap_shots(df)


def analyze_equipment_performance(
    df: pd.DataFrame,
    pareto_chart_fn: object,
    equipment_issue_threshold: float = EQUIPMENT_ISSUE_THRESHOLD,
) -> None:
    """Analyze equipment performance issues.

    Args:
        df: DataFrame with CT_ISSUE_FLAG, DEVIATION_PCT, TEMPERATURE columns.
        pareto_chart_fn: Callable for creating pareto charts.
        equipment_issue_threshold: Issue-rate percentage above which equipment is flagged.
    """
    print("\n" + "=" * 60)
    print("  EQUIPMENT PERFORMANCE ANALYSIS")
    print("=" * 60)

    equip_metrics = (
        df.groupby("MACHINE_ID")
        .agg(
            {
                "CT_ISSUE_FLAG": "sum",
                "DURATION": "count",
                "DEVIATION_PCT": ["mean", "std"],
                "TEMPERATURE": ["mean", "std"],
            }
        )
        .round(2)
    )
    equip_metrics.columns = [
        "Issues",
        "Total_Shots",
        "Avg_CT_Deviation",
        "Std_CT_Deviation",
        "Avg_Temp",
        "Std_Temp",
    ]
    equip_metrics["Issue_Rate"] = (
        equip_metrics["Issues"] / equip_metrics["Total_Shots"] * 100
    ).round(2)
    equip_metrics = equip_metrics.sort_values("Issue_Rate", ascending=False)

    print("  Analyzed %d equipment" % len(equip_metrics))
    print("\n  Equipment Performance Summary:")
    print(equip_metrics.head(DEFAULT_TOP_N))

    problematic = equip_metrics[equip_metrics["Issue_Rate"] > equipment_issue_threshold]
    if len(problematic) > 0:
        print(
            "\n  Found %d equipment with >%.0f%% issue rate"
            % (len(problematic), equipment_issue_threshold)
        )
        problem_data = df[df["MACHINE_ID"].isin(problematic.index)]
        pareto_chart_fn(
            problem_data["MACHINE_ID"],
            "Shots from Equipment with High Issue Rates",
            "Equipment Code",
            "Number of Shots",
        )


def time_series_analysis(
    df: pd.DataFrame,
    time_multiplier_threshold: float = TIME_MULTIPLIER_THRESHOLD,
) -> None:
    """Analyze daily issue-rate trends and plot them.

    Args:
        df: DataFrame with DATE, DURATION_ISSUE_FLAG, and DURATION columns.
        time_multiplier_threshold: Multiplier above daily average to flag a day.
    """
    print("\n" + "=" * 60)
    print("  TIME SERIES ANALYSIS")
    print("=" * 60)

    daily = df.groupby("DATE").agg({"CT_ISSUE_FLAG": "sum", "DURATION": "count"})
    daily["Issue_Rate"] = (daily["CT_ISSUE_FLAG"] / daily["DURATION"] * 100).round(2)

    avg_rate = daily["Issue_Rate"].mean()
    problematic_days = daily[daily["Issue_Rate"] > avg_rate * time_multiplier_threshold]

    print("  Analyzed %d days" % len(daily))
    print("  Average daily issue rate: %.2f%%" % avg_rate)
    print(
        "  Found %d days with significantly higher issue rates" % len(problematic_days)
    )

    if len(problematic_days) > 0:
        print("\n  Problematic Days:")
        print(problematic_days.head(DEFAULT_TOP_N))

        plt.figure(figsize=(15, 6))
        plt.plot(daily.index, daily["Issue_Rate"], marker="o", linewidth=1)
        plt.axhline(
            y=avg_rate,
            color="red",
            linestyle="--",
            label="Average: %.2f%%" % avg_rate,
        )
        plt.title("Daily Issue Rate Trend", fontsize=14, fontweight="bold")
        plt.xlabel("Date")
        plt.ylabel("Issue Rate (%%)")
        plt.legend()
        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _print_outlier_method_breakdown(df: pd.DataFrame) -> None:
    """Print per-method outlier counts."""
    outlier_cols = [
        "STD_OUTLIER",
        "IQR_OUTLIER",
        "ZSCORE_OUTLIER",
        "PERCENTILE_OUTLIER",
        "ROLLING_OUTLIER",
    ]
    print("\n  Statistical Method Breakdown:")
    for col in outlier_cols:
        count = int(df[col].sum())
        pct = (count / len(df)) * 100
        print("   %s: %d shots (%.1f%%)" % (col, count, pct))


def _print_downtime_duration_stats(df: pd.DataFrame) -> None:
    """Print downtime duration aggregates."""
    gap_downs = df[df["DOWNTIME_GAP_FLAG"]]
    print("\n  5. Downtime Duration Analysis:")
    if len(gap_downs) > 0:
        print(
            "   Average downtime gap: %.1f minutes"
            % gap_downs["TIME_GAP_MINUTES"].mean()
        )
        print(
            "   Maximum downtime gap: %.1f minutes"
            % gap_downs["TIME_GAP_MINUTES"].max()
        )
        print("   Total idle time: %.1f minutes" % gap_downs["TIME_GAP_MINUTES"].sum())


def _print_longest_downtimes(df: pd.DataFrame) -> None:
    """Print the top-10 longest downtime events."""
    print("\n  6. Longest Downtime Events:")
    longest = df[df["TIME_GAP_MINUTES"] > 0].nlargest(10, "TIME_GAP_MINUTES")
    if len(longest) > 0:
        for _, row in longest.iterrows():
            print(
                "   %s: %s - %s - %.1f min gap"
                % (
                    row["SHOT_TIME"],
                    row["MACHINE_ID"],
                    row["PRODUCT_NAME"],
                    row["TIME_GAP_MINUTES"],
                )
            )


def _print_scrap_type_pareto(
    scrap_shots: pd.DataFrame,
    pareto_chart_fn: object,
) -> None:
    """Build a series of scrap-type labels and chart them."""
    print("\n  2. Pareto Analysis by Scrap Type:")
    type_labels: List[str] = []
    type_map = {
        "SCRAP_CT_ABNORMAL": "Abnormal CT",
        "SCRAP_WARMUP": "Warm-up",
        "SCRAP_LOW_TEMP": "Low Temperature",
        "SCRAP_SENSOR_ANOMALY": "Sensor Anomaly",
        "SCRAP_MISSING_SENSORS": "Missing Sensors",
    }
    for _, row in scrap_shots.iterrows():
        for col, label in type_map.items():
            if row.get(col, False):
                type_labels.append(label)

    if type_labels:
        pareto_chart_fn(
            pd.Series(type_labels),
            "Scrap Events by Type",
            "Scrap Type",
            "Number of Events",
        )


def _print_scrap_score_distribution(df: pd.DataFrame) -> None:
    """Print the distribution of scrap scores."""
    print("\n  5. Scrap Score Distribution:")
    score_dist = df["SCRAP_SCORE"].value_counts().sort_index()
    for score, count in score_dist.items():
        pct = (count / len(df)) * 100
        print("   Score %s: %d shots (%.1f%%)" % (score, count, pct))


def _print_highest_scrap_shots(df: pd.DataFrame) -> None:
    """Print examples of shots with the highest scrap scores."""
    print("\n  6. Shots with Highest Scrap Scores:")
    high = df[df["SCRAP_SCORE"] >= 2].nlargest(10, "SCRAP_SCORE")
    if len(high) > 0:
        for _, row in high.iterrows():
            print(
                "   %s: %s - Score %s - CT: %.1fs"
                % (
                    row["SHOT_TIME"],
                    row["PRODUCT_NAME"],
                    row["SCRAP_SCORE"],
                    row["DURATION"],
                )
            )
