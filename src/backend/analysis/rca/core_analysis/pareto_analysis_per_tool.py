"""
Pareto analysis orchestrator for single-equipment root cause analysis.
Provides the ParetoAnalysis class that coordinates duration deviation detection, downtime
calculation, scrap detection, and issue analysis by delegating to specialised modules.
Imported by root_cause_analysis_pipeline.py as the main entry point for Pareto RCA.
"""

import warnings
from typing import Dict, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .pareto_deviations import calculate_statistical_deviations
from .pareto_downtime import calculate_real_downtime, detect_downtime_events
from .pareto_issue_analyzer import (
    analyze_downtime_patterns,
    analyze_duration_issues,
    analyze_equipment_performance,
    analyze_scrap_patterns,
    analyze_temperature_issues,
    generate_recommendations,
    time_series_analysis,
)
from .pareto_scrap_detector import calculate_scrap_statistics, detect_scrap_indicators

# Import the data fetching function from shot_data (may not exist after sanitization)
try:
    from .shot_data import fetch_data_from_snowflake, session
except ImportError:
    fetch_data_from_snowflake = None  # type: ignore[assignment]
    session = None

warnings.filterwarnings("ignore")


class ParetoAnalysis:
    """Comprehensive Pareto analysis for single equipment with downtime detection.

    Threshold Configuration:
    - CT_SEVERITY_BINS: Duration deviation severity categories
    - TEMP_CV_THRESHOLD: Temperature coefficient of variation threshold (>10%)
    - EQUIPMENT_ISSUE_THRESHOLD: Equipment issue rate threshold (>10%)
    - TIME_MULTIPLIER_THRESHOLD: Time-based issue multiplier (1.5x average)
    - DOWNTIME_GAP_THRESHOLD: Minimum gap to consider as downtime (minutes)
    - DOWNTIME_DURATION_MULTIPLIER: CT multiplier to detect downtime spikes
    """

    # Configurable thresholds
    CT_SEVERITY_BINS = [0, 10, 25, 50, 100, np.inf]
    CT_SEVERITY_LABELS = ["Minor", "Moderate", "Significant", "Major", "Critical"]
    TEMP_CV_THRESHOLD: float = 10.0
    EQUIPMENT_ISSUE_THRESHOLD: float = 10.0
    TIME_MULTIPLIER_THRESHOLD: float = 1.5

    # Statistical outlier detection thresholds
    STD_DEVIATION_THRESHOLD: float = 3.0
    IQR_MULTIPLIER: float = 1.5
    Z_SCORE_THRESHOLD: float = 2.5

    # Downtime detection thresholds
    DOWNTIME_GAP_THRESHOLD: float = 5.0
    DOWNTIME_DURATION_MULTIPLIER: float = 2.0

    # Scrap detection thresholds
    WARMUP_SHOTS_AFTER_IDLE: int = 3
    LOW_PRESSURE_THRESHOLD: float = 0.8
    LOW_TEMP_THRESHOLD: float = 0.9
    SENSOR_ANOMALY_THRESHOLD: float = 3.0

    def __init__(
        self,
        df: pd.DataFrame,
        thresholds: Optional[Dict[str, object]] = None,
    ) -> None:
        """Initialize with manufacturing data.

        Args:
            df: Manufacturing shot data.
            thresholds: Custom thresholds to override class-level defaults.
        """
        self.df = df.copy()

        if thresholds:
            for key, value in thresholds.items():
                if hasattr(self, key):
                    setattr(self, key, value)

        self.setup_data()

    def setup_data(self) -> None:
        """Prepare data for analysis by running all detection pipelines."""
        self.df = self.df.reset_index(drop=True)

        self.df["SHOT_TIME"] = pd.to_datetime(self.df["SHOT_TIME"])
        self.df["DATE"] = self.df["SHOT_TIME"].dt.date
        self.df["HOUR"] = self.df["SHOT_TIME"].dt.hour
        self.df["DAY_OF_WEEK"] = self.df["SHOT_TIME"].dt.day_name()

        self.df = calculate_statistical_deviations(
            self.df,
            std_threshold=self.STD_DEVIATION_THRESHOLD,
            iqr_multiplier=self.IQR_MULTIPLIER,
            z_score_threshold=self.Z_SCORE_THRESHOLD,
        )

        self.df = calculate_real_downtime(self.df)

        self.df = detect_downtime_events(
            self.df,
            gap_threshold=self.DOWNTIME_GAP_THRESHOLD,
            ct_multiplier=self.DOWNTIME_DURATION_MULTIPLIER,
        )

        self.df = detect_scrap_indicators(
            self.df,
            warmup_shots_after_idle=self.WARMUP_SHOTS_AFTER_IDLE,
            low_temp_threshold=self.LOW_TEMP_THRESHOLD,
            sensor_anomaly_threshold=self.SENSOR_ANOMALY_THRESHOLD,
        )
        calculate_scrap_statistics(self.df)

        print("  Data prepared: %d records loaded" % len(self.df))
        print(
            "  Date range: %s to %s"
            % (self.df["SHOT_TIME"].min(), self.df["SHOT_TIME"].max())
        )

    def display_thresholds(self) -> None:
        """Display current threshold configuration."""
        print("\n" + "=" * 60)
        print("  CURRENT THRESHOLD CONFIGURATION")
        print("=" * 60)
        print("  Temperature CV Threshold: >%.1f%%" % self.TEMP_CV_THRESHOLD)
        print(
            "  Equipment Issue Rate Threshold: >%.1f%%" % self.EQUIPMENT_ISSUE_THRESHOLD
        )
        print("  Time-based Multiplier: %.1fx average" % self.TIME_MULTIPLIER_THRESHOLD)

        print("\n  Statistical Outlier Detection Thresholds:")
        print("   Standard Deviation: %.1f sigma" % self.STD_DEVIATION_THRESHOLD)
        print("   IQR Multiplier: %.1fx" % self.IQR_MULTIPLIER)
        print("   Z-Score Threshold: %.1f" % self.Z_SCORE_THRESHOLD)

        print("\n  Downtime Detection Thresholds:")
        print("   Minimum Gap Threshold: %.1f minutes" % self.DOWNTIME_GAP_THRESHOLD)
        print(
            "   CT Spike Multiplier: %.1fx typical duration"
            % self.DOWNTIME_DURATION_MULTIPLIER
        )

        print("\n  Scrap Detection Thresholds:")
        print("   Warm-up Shots After Idle: %d shots" % self.WARMUP_SHOTS_AFTER_IDLE)
        print(
            "   Low Pressure Threshold: <%.0f%% of typical"
            % (self.LOW_PRESSURE_THRESHOLD * 100)
        )
        print(
            "   Low Temperature Threshold: <%.0f%% of typical"
            % (self.LOW_TEMP_THRESHOLD * 100)
        )
        print("   Sensor Anomaly Threshold: %.1f sigma" % self.SENSOR_ANOMALY_THRESHOLD)

        print("\n  Duration Severity Categories:")
        for i, (bin_val, label) in enumerate(
            zip(self.CT_SEVERITY_BINS[:-1], self.CT_SEVERITY_LABELS)
        ):
            next_bin = (
                self.CT_SEVERITY_BINS[i + 1]
                if i + 1 < len(self.CT_SEVERITY_BINS)
                else "inf"
            )
            print("   %s: %s-%s%% deviation" % (label, bin_val, next_bin))
        print("=" * 60)

    def pareto_chart(
        self,
        data: pd.Series,
        title: str,
        x_label: str,
        y_label: str,
        top_n: int = 10,
        figsize: Tuple[int, int] = (12, 8),
    ) -> Tuple[pd.Series, pd.Series]:
        """Create a Pareto chart with bar and cumulative-percentage line.

        Args:
            data: Categorical series to analyse.
            title: Chart title.
            x_label: X-axis label.
            y_label: Y-axis label.
            top_n: Number of top categories to show.
            figsize: Figure dimensions.

        Returns:
            A tuple of (frequency series, cumulative percentage series).
        """
        freq = data.value_counts().head(top_n)
        total = freq.sum()
        cumsum = freq.cumsum()
        cumsum_pct = (cumsum / total) * 100

        fig, ax1 = plt.subplots(figsize=figsize)

        bars = ax1.bar(range(len(freq)), freq.values, color="skyblue", alpha=0.7)
        ax1.set_xlabel(x_label)
        ax1.set_ylabel(y_label, color="blue")
        ax1.tick_params(axis="y", labelcolor="blue")

        ax1.set_xticks(range(len(freq)))
        ax1.set_xticklabels(freq.index, rotation=45, ha="right")

        ax2 = ax1.twinx()
        ax2.plot(
            range(len(freq)),
            cumsum_pct.values,
            color="red",
            marker="o",
            linewidth=2,
        )
        ax2.set_ylabel("Cumulative Percentage (%%)", color="red")
        ax2.tick_params(axis="y", labelcolor="red")
        ax2.set_ylim(0, 100)

        for bar, pct in zip(bars, cumsum_pct):
            height = bar.get_height()
            ax1.text(
                bar.get_x() + bar.get_width() / 2.0,
                height + height * 0.01,
                "%.1f%%" % pct,
                ha="center",
                va="bottom",
                fontsize=9,
            )

        plt.title(title, fontsize=14, fontweight="bold")
        plt.tight_layout()
        plt.show()

        print("\n  Top %d Contributors to %s:" % (top_n, title))
        for i, (category, count) in enumerate(freq.items()):
            percentage = (count / total) * 100
            cumulative = cumsum_pct.iloc[i]
            print(
                "%2d. %s: %d (%.1f%%) - Cumulative: %.1f%%"
                % (i + 1, category, count, percentage, cumulative)
            )

        return freq, cumsum_pct

    # ------------------------------------------------------------------
    # Delegating analysis methods
    # ------------------------------------------------------------------

    def analyze_duration_issues(self) -> None:
        """Analyze duration deviations using statistical methods."""
        analyze_duration_issues(self.df, self.pareto_chart)

    def analyze_temperature_issues(self) -> None:
        """Analyze temperature-related issues."""
        analyze_temperature_issues(
            self.df,
            self.pareto_chart,
            temp_cv_threshold=self.TEMP_CV_THRESHOLD,
        )

    def analyze_downtime_patterns(self) -> None:
        """Analyze downtime patterns by tool and equipment."""
        analyze_downtime_patterns(self.df, self.pareto_chart)

    def analyze_scrap_patterns(self) -> None:
        """Analyze scrap patterns for single equipment."""
        analyze_scrap_patterns(self.df, self.pareto_chart)

    def analyze_equipment_performance(self) -> None:
        """Analyze equipment performance issues."""
        analyze_equipment_performance(
            self.df,
            self.pareto_chart,
            equipment_issue_threshold=self.EQUIPMENT_ISSUE_THRESHOLD,
        )

    def time_series_analysis(self) -> None:
        """Analyze time-based trends."""
        time_series_analysis(
            self.df,
            time_multiplier_threshold=self.TIME_MULTIPLIER_THRESHOLD,
        )

    def generate_recommendations(self) -> None:
        """Generate actionable recommendations based on Pareto analysis."""
        generate_recommendations(self.df)

    def run_complete_analysis(self) -> None:
        """Run the complete Pareto analysis with downtime detection."""
        print("  Starting Comprehensive Pareto Analysis with Downtime Detection")
        print("=" * 80)

        self.analyze_duration_issues()
        self.analyze_downtime_patterns()
        self.analyze_scrap_patterns()
        self.analyze_temperature_issues()
        self.analyze_equipment_performance()
        self.time_series_analysis()
        self.generate_recommendations()

        print("\n" + "=" * 80)
        print("  Pareto Analysis with Downtime Detection Complete")
        print("=" * 80)


def main() -> None:
    """Main function to run the Pareto analysis for single equipment MX-7108."""
    try:
        print("  Fetching data from Snowflake...")
        df = fetch_data_from_snowflake(session)

        if df.empty:
            print("  ERROR: No data retrieved from Snowflake")
            return

        print("  Filtering for single equipment MX-7108...")
        df_filtered = df[df["MACHINE_ID"] == "MX-7108"].copy()

        if df_filtered.empty:
            print("  ERROR: No data found for equipment MX-7108")
            return

        print("  Found %d shots for equipment MX-7108" % len(df_filtered))
        print(
            "  Date range: %s to %s"
            % (
                df_filtered["SHOT_TIME"].min(),
                df_filtered["SHOT_TIME"].max(),
            )
        )
        print(
            "  Parts produced: %d different parts"
            % df_filtered["PRODUCT_NAME"].nunique()
        )

        print("\n" + "=" * 80)
        print("  SINGLE EQUIPMENT DOWNTIME ANALYSIS - EQUIPMENT MX-7108")
        print("=" * 80)
        pareto = ParetoAnalysis(df_filtered)
        pareto.run_complete_analysis()

    except Exception as e:
        print("  ERROR during analysis: %s" % str(e))
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
