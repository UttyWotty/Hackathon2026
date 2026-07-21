"""
Root Cause Analysis using Pareto Analysis
========================================

This script performs Pareto analysis on manufacturing data to identify
the most significant contributors to quality issues and production problems.

Key Analysis Areas:
1. Cycle Time Deviations (Short/Long CT)
2. Temperature Variations
3. Equipment Performance Issues
4. Supplier Quality Problems
5. Tooling Family Issues
6. Time-based Trends
"""

import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.shared.constants import SessionDetection

warnings.filterwarnings("ignore")

# Import the data fetching function from master_shot_table
from .master_shot_table import fetch_data_from_snowflake, session  # noqa: E402


class ParetoAnalysis:
    """
    Comprehensive Pareto analysis for manufacturing root cause analysis

    Threshold Configuration:
    - CT_SEVERITY_BINS: Cycle time deviation severity categories
    - TEMP_CV_THRESHOLD: Temperature coefficient of variation threshold (>10%)
    - SUPPLIER_ISSUE_THRESHOLD: Supplier issue rate threshold (>5%)
    - EQUIPMENT_ISSUE_THRESHOLD: Equipment issue rate threshold (>10%)
    - TIME_MULTIPLIER_THRESHOLD: Time-based issue multiplier (1.5x average)
    """

    # Configurable thresholds
    CT_SEVERITY_BINS = [0, 10, 25, 50, 100, np.inf]
    CT_SEVERITY_LABELS = ["Minor", "Moderate", "Significant", "Major", "Critical"]
    TEMP_CV_THRESHOLD = 10.0  # Temperature coefficient of variation threshold
    SUPPLIER_ISSUE_THRESHOLD = 5.0  # Supplier issue rate threshold (%)
    EQUIPMENT_ISSUE_THRESHOLD = 10.0  # Equipment issue rate threshold (%)
    TIME_MULTIPLIER_THRESHOLD = 1.5  # Time-based issue multiplier

    # Statistical outlier detection thresholds
    STD_DEVIATION_THRESHOLD = 3.0  # Standard deviations for outlier detection
    IQR_MULTIPLIER = 1.5  # IQR multiplier for outlier detection
    Z_SCORE_THRESHOLD = 2.5  # Z-score threshold for outlier detection

    def __init__(self, df, thresholds=None):
        """
        Initialize with manufacturing data

        Args:
            df (pd.DataFrame): Manufacturing shot data
            thresholds (dict, optional): Custom thresholds to override defaults
        """
        self.df = df.copy()

        # Override default thresholds if provided
        if thresholds:
            for key, value in thresholds.items():
                if hasattr(self, key):
                    setattr(self, key, value)

        self.setup_data()

    def setup_data(self):
        """Prepare data for analysis"""
        # Convert timestamp
        self.df["LOCAL_SHOT_TIME"] = pd.to_datetime(self.df["LOCAL_SHOT_TIME"])

        # Add date columns for time-based analysis
        self.df["DATE"] = self.df["LOCAL_SHOT_TIME"].dt.date
        self.df["HOUR"] = self.df["LOCAL_SHOT_TIME"].dt.hour
        self.df["DAY_OF_WEEK"] = self.df["LOCAL_SHOT_TIME"].dt.day_name()

        # Calculate cycle time deviations using multiple statistical methods
        self.calculate_statistical_ct_deviations()

        # Calculate real downtime and scrap using company logic
        self.calculate_real_downtime()
        self.calculate_real_scrap()

        # Create severity categories based on our calculated deviations
        self.df["CT_SEVERITY"] = pd.cut(
            self.df["CT_DEVIATION_PCT"].abs(),
            bins=self.CT_SEVERITY_BINS,
            labels=self.CT_SEVERITY_LABELS,
            include_lowest=True,
        )

        print(f"✅ Data prepared: {len(self.df)} records loaded")
        print(
            f"📊 Date range: {self.df['LOCAL_SHOT_TIME'].min()} to {self.df['LOCAL_SHOT_TIME'].max()}"
        )

        # Display current thresholds
        self.display_thresholds()

    def calculate_statistical_ct_deviations(self):
        """
        Calculate cycle time deviations using multiple statistical methods:
        1. Standard deviation method (3-sigma rule)
        2. IQR method (box plot outliers)
        3. Z-score method
        4. Percentile-based method
        5. Rolling window analysis
        """
        print("\n🔬 Calculating statistical cycle time deviations...")

        # Method 1: Standard Deviation Method (3-sigma rule)
        self._calculate_std_deviations()

        # Method 2: IQR Method (box plot outliers)
        self._calculate_iqr_deviations()

        # Method 3: Z-score Method
        self._calculate_zscore_deviations()

        # Method 4: Percentile-based Method
        self._calculate_percentile_deviations()

        # Method 5: Rolling Window Analysis
        self._calculate_rolling_deviations()

        # Combine all methods to create a comprehensive deviation score
        self._combine_deviation_methods()

        print("✅ Statistical deviation calculations complete")

        # Display summary statistics
        self._display_statistical_summary()

    def _display_statistical_summary(self):
        """Display summary of statistical analysis results"""
        print("\n📊 Statistical Analysis Summary:")
        print(f"   Total shots analyzed: {len(self.df):,}")
        print(f"   Shots with issues: {self.df['CT_ISSUE_FLAG'].sum():,}")
        print(
            f"   Issue rate: {(self.df['CT_ISSUE_FLAG'].sum() / len(self.df)) * 100:.2f}%"
        )

        # Breakdown by issue type
        issue_breakdown = self.df["CT_ISSUE_TYPE"].value_counts()
        print("\n📈 Issue Type Breakdown:")
        for issue_type, count in issue_breakdown.items():
            pct = (count / len(self.df)) * 100
            print(f"   {issue_type}: {count:,} shots ({pct:.1f}%)")

        # Outlier score distribution
        outlier_dist = self.df["OUTLIER_SCORE"].value_counts().sort_index()
        print("\n🔬 Outlier Score Distribution:")
        for score, count in outlier_dist.items():
            pct = (count / len(self.df)) * 100
            print(f"   Score {score}: {count:,} shots ({pct:.1f}%)")

    def _calculate_std_deviations(self):
        """Calculate deviations using standard deviation method"""
        # Group by equipment and part to get meaningful statistics
        ct_stats = (
            self.df.groupby(["EQUIPMENT_CODE", "PART_NAME"])["CT"]
            .agg(["count", "mean", "std", "min", "max"])
            .reset_index()
        )

        # Filter for groups with sufficient data (at least 10 shots)
        ct_stats = ct_stats[ct_stats["count"] >= 10]

        # Calculate upper and lower bounds using 3-sigma rule
        ct_stats["lower_bound"] = ct_stats["mean"] - (
            self.STD_DEVIATION_THRESHOLD * ct_stats["std"]
        )
        ct_stats["upper_bound"] = ct_stats["mean"] + (
            self.STD_DEVIATION_THRESHOLD * ct_stats["std"]
        )

        # Merge back to main dataframe
        self.df = self.df.merge(
            ct_stats[
                [
                    "EQUIPMENT_CODE",
                    "PART_NAME",
                    "mean",
                    "std",
                    "lower_bound",
                    "upper_bound",
                ]
            ],
            on=["EQUIPMENT_CODE", "PART_NAME"],
            how="left",
        )

        # Calculate deviation percentage from statistical mean
        self.df["CT_DEVIATION_FROM_MEAN_PCT"] = np.where(
            self.df["mean"].notna(),
            ((self.df["CT"] - self.df["mean"]) / self.df["mean"]) * 100,
            np.nan,
        )

        # Flag outliers using standard deviation method
        self.df["STD_OUTLIER"] = (self.df["CT"] < self.df["lower_bound"]) | (
            self.df["CT"] > self.df["upper_bound"]
        )

    def _calculate_iqr_deviations(self):
        """Calculate deviations using IQR method"""
        # Calculate IQR for each equipment-part combination
        ct_stats = (
            self.df.groupby(["EQUIPMENT_CODE", "PART_NAME"])["CT"]
            .agg(["count", "median"])
            .reset_index()
        )

        # Calculate quartiles using quantile method
        q1_stats = (
            self.df.groupby(["EQUIPMENT_CODE", "PART_NAME"])["CT"]
            .quantile(0.25)
            .reset_index()
        )
        q3_stats = (
            self.df.groupby(["EQUIPMENT_CODE", "PART_NAME"])["CT"]
            .quantile(0.75)
            .reset_index()
        )

        # Rename quantile columns before merging
        q1_stats = q1_stats.rename(columns={"CT": "q1"})
        q3_stats = q3_stats.rename(columns={"CT": "q3"})

        # Merge quartiles with main stats
        ct_stats = ct_stats.merge(q1_stats, on=["EQUIPMENT_CODE", "PART_NAME"])
        ct_stats = ct_stats.merge(q3_stats, on=["EQUIPMENT_CODE", "PART_NAME"])

        # Filter for groups with sufficient data
        ct_stats = ct_stats[ct_stats["count"] >= 10]

        # Calculate IQR and bounds
        ct_stats["iqr"] = ct_stats["q3"] - ct_stats["q1"]
        ct_stats["lower_bound_iqr"] = ct_stats["q1"] - (
            self.IQR_MULTIPLIER * ct_stats["iqr"]
        )
        ct_stats["upper_bound_iqr"] = ct_stats["q3"] + (
            self.IQR_MULTIPLIER * ct_stats["iqr"]
        )

        # Merge back to main dataframe
        self.df = self.df.merge(
            ct_stats[
                [
                    "EQUIPMENT_CODE",
                    "PART_NAME",
                    "median",
                    "iqr",
                    "lower_bound_iqr",
                    "upper_bound_iqr",
                ]
            ],
            on=["EQUIPMENT_CODE", "PART_NAME"],
            how="left",
        )

        # Ensure median column exists
        if "median" not in self.df.columns:
            print("⚠️ Warning: median column not found in IQR method, creating...")
            median_stats = (
                self.df.groupby(["EQUIPMENT_CODE", "PART_NAME"])["CT"]
                .median()
                .reset_index()
                .rename(columns={"CT": "median"})
            )
            self.df = self.df.merge(
                median_stats, on=["EQUIPMENT_CODE", "PART_NAME"], how="left"
            )

        # Calculate deviation from median
        self.df["CT_DEVIATION_FROM_MEDIAN_PCT"] = np.where(
            self.df["median"].notna(),
            ((self.df["CT"] - self.df["median"]) / self.df["median"]) * 100,
            np.nan,
        )

        # Flag outliers using IQR method
        self.df["IQR_OUTLIER"] = (self.df["CT"] < self.df["lower_bound_iqr"]) | (
            self.df["CT"] > self.df["upper_bound_iqr"]
        )

    def _calculate_zscore_deviations(self):
        """Calculate deviations using Z-score method"""
        # Calculate Z-scores for each equipment-part combination
        ct_stats = (
            self.df.groupby(["EQUIPMENT_CODE", "PART_NAME"])["CT"]
            .agg(["count", "mean", "std"])
            .reset_index()
        )

        # Filter for groups with sufficient data
        ct_stats = ct_stats[ct_stats["count"] >= 10]

        # Merge back to main dataframe
        self.df = self.df.merge(
            ct_stats[["EQUIPMENT_CODE", "PART_NAME", "mean", "std"]],
            on=["EQUIPMENT_CODE", "PART_NAME"],
            how="left",
            suffixes=("", "_zscore"),
        )

        # Calculate Z-scores
        self.df["Z_SCORE"] = np.where(
            self.df["std_zscore"].notna() & (self.df["std_zscore"] > 0),
            (self.df["CT"] - self.df["mean_zscore"]) / self.df["std_zscore"],
            np.nan,
        )

        # Flag outliers using Z-score method
        self.df["ZSCORE_OUTLIER"] = np.abs(self.df["Z_SCORE"]) > self.Z_SCORE_THRESHOLD

    def _calculate_percentile_deviations(self):
        """Calculate deviations using percentile method"""
        # Calculate percentiles for each equipment-part combination
        ct_stats = (
            self.df.groupby(["EQUIPMENT_CODE", "PART_NAME"])["CT"]
            .agg(["count", "median"])
            .reset_index()
        )

        # Calculate percentiles using quantile method
        p5_stats = (
            self.df.groupby(["EQUIPMENT_CODE", "PART_NAME"])["CT"]
            .quantile(0.05)
            .reset_index()
        )
        p95_stats = (
            self.df.groupby(["EQUIPMENT_CODE", "PART_NAME"])["CT"]
            .quantile(0.95)
            .reset_index()
        )

        # Rename percentile columns before merging
        p5_stats = p5_stats.rename(columns={"CT": "percentile_5"})
        p95_stats = p95_stats.rename(columns={"CT": "percentile_95"})

        # Merge percentiles with main stats
        ct_stats = ct_stats.merge(p5_stats, on=["EQUIPMENT_CODE", "PART_NAME"])
        ct_stats = ct_stats.merge(p95_stats, on=["EQUIPMENT_CODE", "PART_NAME"])

        # Filter for groups with sufficient data
        ct_stats = ct_stats[ct_stats["count"] >= 10]

        # Merge back to main dataframe
        self.df = self.df.merge(
            ct_stats[
                [
                    "EQUIPMENT_CODE",
                    "PART_NAME",
                    "percentile_5",
                    "percentile_95",
                    "median",
                ]
            ],
            on=["EQUIPMENT_CODE", "PART_NAME"],
            how="left",
        )

        # Ensure median column exists and handle missing values
        if "median" not in self.df.columns:
            print("⚠️ Warning: median column not found, creating from scratch...")
            # Calculate median for each equipment-part combination
            median_stats = (
                self.df.groupby(["EQUIPMENT_CODE", "PART_NAME"])["CT"]
                .median()
                .reset_index()
                .rename(columns={"CT": "median"})
            )
            self.df = self.df.merge(
                median_stats, on=["EQUIPMENT_CODE", "PART_NAME"], how="left"
            )

        # Calculate deviation from median using percentile range
        self.df["PERCENTILE_RANGE"] = self.df["percentile_95"] - self.df["percentile_5"]
        self.df["CT_DEVIATION_PERCENTILE"] = np.where(
            (
                self.df["PERCENTILE_RANGE"].notna()
                & (self.df["PERCENTILE_RANGE"] > 0)
                & self.df["median"].notna()
            ),
            ((self.df["CT"] - self.df["median"]) / self.df["PERCENTILE_RANGE"]) * 100,
            np.nan,
        )

        # Flag outliers using percentile method
        self.df["PERCENTILE_OUTLIER"] = (self.df["CT"] < self.df["percentile_5"]) | (
            self.df["CT"] > self.df["percentile_95"]
        )

    def _calculate_rolling_deviations(self):
        """Calculate deviations using rolling window analysis"""
        # Sort by equipment, part, and time - preserve existing columns
        self.df = self.df.sort_values(
            ["EQUIPMENT_CODE", "PART_NAME", "LOCAL_SHOT_TIME"]
        ).reset_index(drop=True)

        # Calculate rolling statistics for each equipment-part combination
        rolling_stats = []

        for (equipment, part), group in self.df.groupby(
            ["EQUIPMENT_CODE", "PART_NAME"]
        ):
            if len(group) >= 20:  # Need at least 20 shots for rolling analysis
                # Calculate rolling mean and std with window of 10
                rolling_mean = group["CT"].rolling(window=10, min_periods=5).mean()
                rolling_std = group["CT"].rolling(window=10, min_periods=5).std()

                # Calculate rolling deviation
                rolling_deviation = np.where(
                    rolling_std.notna() & (rolling_std > 0),
                    ((group["CT"] - rolling_mean) / rolling_std),
                    np.nan,
                )

                temp_df = group.copy()
                temp_df["ROLLING_DEVIATION"] = rolling_deviation
                temp_df["ROLLING_OUTLIER"] = (
                    np.abs(rolling_deviation) > self.Z_SCORE_THRESHOLD
                )
                rolling_stats.append(temp_df)
            else:
                group["ROLLING_DEVIATION"] = np.nan
                group["ROLLING_OUTLIER"] = False
                rolling_stats.append(group)

        # Combine back
        self.df = pd.concat(rolling_stats, ignore_index=True)

    def _combine_deviation_methods(self):
        """Combine all deviation methods into a comprehensive score"""
        # Create a composite outlier score
        outlier_columns = [
            "STD_OUTLIER",
            "IQR_OUTLIER",
            "ZSCORE_OUTLIER",
            "PERCENTILE_OUTLIER",
            "ROLLING_OUTLIER",
        ]

        # Count how many methods flag each shot as an outlier
        self.df["OUTLIER_SCORE"] = self.df[outlier_columns].sum(axis=1)

        # Create a composite deviation percentage
        deviation_columns = [
            "CT_DEVIATION_FROM_MEAN_PCT",
            "CT_DEVIATION_FROM_MEDIAN_PCT",
            "CT_DEVIATION_PERCENTILE",
        ]

        # Use the maximum absolute deviation as the primary measure
        self.df["CT_DEVIATION_PCT"] = self.df[deviation_columns].abs().max(axis=1)

        # If we have APPROVED_CT, use it as a reference but weight it with statistical measures
        if "APPROVED_CT" in self.df.columns:
            approved_deviation = np.where(
                self.df["APPROVED_CT"].notna(),
                ((self.df["CT"] - self.df["APPROVED_CT"]) / self.df["APPROVED_CT"])
                * 100,
                np.nan,
            )

            # Combine approved CT deviation with statistical deviation (weighted average)
            self.df["CT_DEVIATION_PCT"] = np.where(
                self.df["CT_DEVIATION_PCT"].notna() & pd.notna(approved_deviation),
                (self.df["CT_DEVIATION_PCT"] * 0.7 + np.abs(approved_deviation) * 0.3),
                np.where(
                    self.df["CT_DEVIATION_PCT"].notna(),
                    self.df["CT_DEVIATION_PCT"],
                    np.abs(approved_deviation),
                ),
            )

        # Create a comprehensive issue flag
        self.df["CT_ISSUE_FLAG"] = (
            self.df["OUTLIER_SCORE"] >= 2
        ) | (  # Flagged by at least 2 methods
            self.df["CT_DEVIATION_PCT"] > 25
        )  # Or high deviation percentage

        # Create issue categories
        self.df["CT_ISSUE_TYPE"] = np.where(
            self.df["CT_ISSUE_FLAG"],
            np.where(
                self.df["CT_DEVIATION_PCT"] > 50,
                "Critical",
                np.where(
                    self.df["CT_DEVIATION_PCT"] > 25,
                    "Significant",
                    np.where(self.df["CT_DEVIATION_PCT"] > 10, "Moderate", "Minor"),
                ),
            ),
            "Normal",
        )

    def _calculate_scrap_estimates(self):
        """
        Derive a simple scrap signal compatible with Pareto outputs.
        Logic (non-breaking; uses existing columns):
        - If 'SCRAP' exists: use it to make 'SCRAP_QTY' and 'SCRAP_FLAG'.
        - Else estimate from 'CT_ISSUE_FLAG' and severity ('CT_ISSUE_TYPE'); lightly bump with 'CT_STATUS'.
        - Classify 'SCRAP_REASON' with simple, readable rules:
        - 'Short Shot/Cold Shut' if CT_STATUS indicates short fill
        - 'Porosity/Thermal' if temperature CV is high and a CT issue exists
        - 'Cycle Time Instability' for significant/critical CT deviation
        - 'General/Other' otherwise
        NOTE: Plant-specific defect codes can be mapped in future enhancement.
        """
        import numpy as np

        self.df["SCRAP_QTY"] = 0.0

        # Precompute temperature CV so we can use it consistently below
        high_cv = pd.Series(False, index=self.df.index)  # Default to False

        if "TEMPERATURE" in self.df.columns:
            try:
                temp_stats = (
                    self.df.groupby("EQUIPMENT_CODE")["TEMPERATURE"]
                    .agg(["mean", "std"])  # type: ignore
                    .rename(columns={"mean": "temp_mean", "std": "temp_std"})
                )
                temp_stats["temp_cv"] = (
                    temp_stats["temp_std"] / temp_stats["temp_mean"] * 100
                ).replace([np.inf, -np.inf], np.nan)

                # Merge back to main dataframe
                self.df = self.df.merge(
                    temp_stats[["temp_cv"]],
                    left_on="EQUIPMENT_CODE",
                    right_index=True,
                    how="left",
                )

                # Calculate high CV flag
                high_cv = self.df["temp_cv"] > self.TEMP_CV_THRESHOLD
                high_cv = high_cv.fillna(False)  # Handle NaN values

            except Exception as e:
                print(f"⚠️ Warning: Could not calculate temperature CV: {e}")
                high_cv = pd.Series(False, index=self.df.index)

        if "SCRAP" in self.df.columns:
            self.df["SCRAP_QTY"] = self.df["SCRAP"].fillna(0)
            self.df["SCRAP_FLAG"] = self.df["SCRAP_QTY"] > 0
        else:
            base = np.where(self.df.get("CT_ISSUE_FLAG", False), 0.20, 0.0)
            base += np.where(
                self.df.get("CT_ISSUE_TYPE", "").isin(["Critical", "Significant"]),
                0.20,
                0.0,
            )
            if "CT_STATUS" in self.df.columns:
                base += np.where(
                    self.df["CT_STATUS"].isin(["Short CT", "Long CT"]), 0.10, 0.0
                )  # Labels validated by CT_STATUS mapping
            # Thermal bump for high CV when there is an issue
            base += np.where(high_cv & self.df.get("CT_ISSUE_FLAG", False), 0.10, 0.0)
            self.df["SCRAP_PROB"] = np.clip(base, 0, 0.8)
            self.df["SCRAP_FLAG"] = self.df["SCRAP_PROB"] >= 0.5
            self.df["SCRAP_QTY"] = self.df["SCRAP_PROB"]

        # Reason classification (readable fallbacks)
        self.df["SCRAP_REASON"] = "General/Other"
        if "CT_STATUS" in self.df.columns:
            self.df.loc[self.df["CT_STATUS"] == "Short CT", "SCRAP_REASON"] = (
                "Short Shot/Cold Shut"  # Default mapping
            )
        # Tag porosity/thermal when temperature variation is high and there is an issue
        self.df.loc[high_cv & self.df.get("CT_ISSUE_FLAG", False), "SCRAP_REASON"] = (
            "Porosity/Thermal"
        )
        mask = self.df["SCRAP_REASON"] == "General/Other"
        if "CT_ISSUE_TYPE" in self.df.columns:
            sev = self.df["CT_ISSUE_TYPE"].isin(["Critical", "Significant"])
            self.df.loc[mask, "SCRAP_REASON"] = np.where(
                sev[mask], "Cycle Time Instability", "General/Other"
            )

        # Scrap Pareto summaries
        total = len(self.df) if len(self.df) else 1
        self.scrap_summary = {
            "overall_rate_pct": float(self.df["SCRAP_FLAG"].sum() / total * 100),
            "by_reason": (
                self.df[self.df["SCRAP_FLAG"]]
                .groupby("SCRAP_REASON")
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
            ),
            "by_supplier": (
                self.df[self.df["SCRAP_FLAG"]]
                .groupby("SUPPLIER_NAME")
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
            ),
            "by_equipment": (
                self.df[self.df["SCRAP_FLAG"]]
                .groupby("EQUIPMENT_CODE")
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
            ),
        }

    def calculate_real_downtime(self):
        """
        Calculate real downtime using company logic from supplier dashboard
        Logic: Time between shots - Previous cycle time
        """
        print("⏰ Calculating real downtime using company logic...")

        # Sort by timestamp - preserve existing columns
        self.df = self.df.sort_values("LOCAL_SHOT_TIME").reset_index(drop=True)

        # Calculate time between shots
        self.df["TIME_BETWEEN_SHOTS"] = (
            self.df["LOCAL_SHOT_TIME"].diff().dt.total_seconds()
        )

        # Initialize downtime column
        self.df["DOWNTIME"] = 0.0

        # Calculate downtime for each shot
        for i in range(1, len(self.df)):
            time_between = self.df.iloc[i]["TIME_BETWEEN_SHOTS"]
            prev_ct = self.df.iloc[i - 1]["CT"]

            # Skip if previous CT is >=999 (invalid)
            if prev_ct >= 999:
                continue

            # Calculate downtime: time between shots - previous cycle time
            downtime = time_between - prev_ct

            # Apply company rules:
            # 1. Ignore if above 8 hours - session break
            if downtime > SessionDetection.SESSION_GAP_SECONDS:
                continue

            # 2. Ignore rounding errors (-1, 0, 1 seconds)
            if downtime in [-1, 0, 1]:
                continue

            # 3. Only count positive downtime (actual delays)
            if downtime > 1:
                self.df.iloc[i, self.df.columns.get_loc("DOWNTIME")] = downtime

        # Calculate downtime statistics
        total_downtime = self.df["DOWNTIME"].sum()
        downtime_events = (self.df["DOWNTIME"] > 0).sum()
        total_shots = len(self.df)

        print(
            f"   Total downtime: {total_downtime:.0f} seconds ({total_downtime / 3600:.1f} hours)"
        )
        print(
            f"   Downtime events: {downtime_events:,} shots ({downtime_events / total_shots * 100:.1f}%)"
        )

        return self.df

    def calculate_real_scrap(self):
        """
        Calculate real scrap using existing Pareto analysis logic
        Uses the _calculate_scrap_estimates method but with improved logic
        """
        print("🔍 Calculating real scrap indicators...")

        # Use the existing scrap estimation logic
        self._calculate_scrap_estimates()

        # Now we have:
        # - self.df["SCRAP_FLAG"] - Boolean scrap indicators
        # - self.df["SCRAP_QTY"] - Scrap quantities
        # - self.df["SCRAP_REASON"] - Scrap reasons
        # - self.scrap_summary - Scrap statistics

        # Calculate scrap statistics
        total_scrap = self.df["SCRAP_FLAG"].sum()
        total_shots = len(self.df)
        scrap_rate = (total_scrap / total_shots) * 100 if total_shots > 0 else 0

        print(f"   Total scrap shots: {total_scrap:,} ({scrap_rate:.2f}%)")

        # Add additional scrap indicators from per-tool logic
        self._add_advanced_scrap_indicators()

        return self.df

    def _add_advanced_scrap_indicators(self):
        """
        Add advanced scrap indicators from per-tool analysis
        """
        # Initialize additional scrap indicator columns
        self.df["SCRAP_WARMUP"] = False
        self.df["SCRAP_LOW_TEMP"] = False
        self.df["SCRAP_SENSOR_ANOMALY"] = False
        self.df["SCRAP_MISSING_SENSORS"] = False

        # 1. Warm-up shots after downtime
        self._detect_warmup_shots()

        # 2. Low temperature shots
        self._detect_low_temperature_shots()

        # 3. Sensor anomalies
        self._detect_sensor_anomalies()

        # 4. Missing sensor values
        self._detect_missing_sensors()

        # Update scrap flag to include all indicators
        scrap_columns = [
            "SCRAP_FLAG",
            "SCRAP_WARMUP",
            "SCRAP_LOW_TEMP",
            "SCRAP_SENSOR_ANOMALY",
            "SCRAP_MISSING_SENSORS",
        ]

        # Ensure all columns exist
        for col in scrap_columns:
            if col not in self.df.columns:
                self.df[col] = False

        # Combined scrap indicator - use SCRAP_FLAG as primary, others as additional
        self.df["SCRAP_INDICATOR"] = self.df["SCRAP_FLAG"].copy()

        # Add additional scrap indicators only if they're not already covered by SCRAP_FLAG
        additional_scrap = (
            self.df["SCRAP_WARMUP"]
            | self.df["SCRAP_LOW_TEMP"]
            | self.df["SCRAP_SENSOR_ANOMALY"]
            | self.df["SCRAP_MISSING_SENSORS"]
        )

        # Only add additional scrap if SCRAP_FLAG is False
        self.df.loc[~self.df["SCRAP_FLAG"], "SCRAP_INDICATOR"] = additional_scrap[
            ~self.df["SCRAP_FLAG"]
        ]

        # Calculate comprehensive scrap score
        self.df["SCRAP_SCORE"] = self.df[scrap_columns].sum(axis=1)

        # Debug and validation to avoid unrealistic 100% scrap rates
        total_shots = len(self.df) if len(self.df) else 1
        scrap_flag_count = int(self.df["SCRAP_FLAG"].sum())
        scrap_indicator_count = int(self.df["SCRAP_INDICATOR"].sum())
        scrap_flag_rate = scrap_flag_count / total_shots * 100
        scrap_indicator_rate = scrap_indicator_count / total_shots * 100
        print(f"   SCRAP_FLAG: {scrap_flag_count:,} shots ({scrap_flag_rate:.2f}%)")
        print(
            f"   SCRAP_INDICATOR: {scrap_indicator_count:,} shots ({scrap_indicator_rate:.2f}%)"
        )

        # If combined indicator is overly broad, fallback to primary flag only
        if scrap_indicator_rate > 50:
            print(
                "   ⚠️ Scrap indicator rate > 50%. Using SCRAP_FLAG only to avoid inflation"
            )
            self.df["SCRAP_INDICATOR"] = self.df["SCRAP_FLAG"].copy()

    def _detect_warmup_shots(self):
        """Detect warm-up shots after downtime periods"""
        # Find shots after downtime gaps (gaps > 5 minutes)
        downtime_gaps = self.df["TIME_BETWEEN_SHOTS"] > 300  # 5 minutes
        downtime_after = downtime_gaps.shift(1).fillna(False)

        # Mark the next few shots as warm-up shots (up to 3 shots)
        warmup_mask = downtime_after.copy()
        for i in range(1, 3):  # Up to 3 warm-up shots
            warmup_mask = warmup_mask | downtime_after.shift(-i).fillna(False)

        self.df["SCRAP_WARMUP"] = warmup_mask

    def _detect_low_temperature_shots(self):
        """Detect shots with low temperature"""
        if "TEMPERATURE" in self.df.columns:
            try:
                # Calculate temperature statistics by equipment
                temp_stats = (
                    self.df.groupby("EQUIPMENT_CODE")["TEMPERATURE"]
                    .agg(["mean", "std"])
                    .reset_index()
                )

                # Merge back to main dataframe
                self.df = self.df.merge(
                    temp_stats, on="EQUIPMENT_CODE", how="left", suffixes=("", "_stats")
                )

                # Detect low temperature shots (below 90% of mean)
                self.df["SCRAP_LOW_TEMP"] = self.df["TEMPERATURE"] < (
                    self.df["mean"] * 0.9
                )
                self.df["SCRAP_LOW_TEMP"] = self.df["SCRAP_LOW_TEMP"].fillna(False)

            except Exception as e:
                print(f"⚠️ Warning: Could not detect low temperature shots: {e}")
                self.df["SCRAP_LOW_TEMP"] = False
        else:
            self.df["SCRAP_LOW_TEMP"] = False

    def _detect_sensor_anomalies(self):
        """Detect sensor anomalies"""
        if "TEMPERATURE" in self.df.columns and "temp_cv" in self.df.columns:
            try:
                # Calculate temperature coefficient of variation
                temp_cv = self.df["temp_cv"]
                self.df["SCRAP_SENSOR_ANOMALY"] = temp_cv > self.TEMP_CV_THRESHOLD
                self.df["SCRAP_SENSOR_ANOMALY"] = self.df[
                    "SCRAP_SENSOR_ANOMALY"
                ].fillna(False)
            except Exception as e:
                print(f"⚠️ Warning: Could not detect sensor anomalies: {e}")
                self.df["SCRAP_SENSOR_ANOMALY"] = False
        else:
            self.df["SCRAP_SENSOR_ANOMALY"] = False

    def _detect_missing_sensors(self):
        """Detect shots with missing sensor values"""
        missing_sensors = []

        # Check for missing temperature
        if "TEMPERATURE" in self.df.columns:
            missing_sensors.append(self.df["TEMPERATURE"].isna())

        # Check for missing CT
        if "CT" in self.df.columns:
            missing_sensors.append(self.df["CT"].isna())

        # Combine all missing sensor indicators
        if missing_sensors:
            self.df["SCRAP_MISSING_SENSORS"] = pd.concat(missing_sensors, axis=1).any(
                axis=1
            )
        else:
            self.df["SCRAP_MISSING_SENSORS"] = False

    def _compare_with_original_ct_status(self):
        """Compare our statistical approach with the original CT_STATUS"""
        print("\n" + "=" * 60)
        print("🔄 COMPARISON: Statistical vs Original CT_STATUS")
        print("=" * 60)

        # Original CT_STATUS analysis
        original_issues = self.df[self.df["CT_STATUS"] != "Normal CT"]
        statistical_issues = self.df[self.df["CT_ISSUE_FLAG"]]

        print(f"📊 Original CT_STATUS issues: {len(original_issues):,} shots")
        print(f"📊 Statistical method issues: {len(statistical_issues):,} shots")

        # Overlap analysis
        overlap = self.df[
            (self.df["CT_STATUS"] != "Normal CT") & (self.df["CT_ISSUE_FLAG"])
        ]

        print(f"📊 Overlap (both methods): {len(overlap):,} shots")
        print(f"📊 Only in original: {len(original_issues) - len(overlap):,} shots")
        print(
            f"📊 Only in statistical: {len(statistical_issues) - len(overlap):,} shots"
        )

        # Agreement percentage
        if len(original_issues) > 0:
            agreement_pct = (len(overlap) / len(original_issues)) * 100
            print(f"📈 Agreement with original: {agreement_pct:.1f}%")

        # Show examples of differences
        print("\n🔍 Examples of shots flagged by statistical method but not original:")
        statistical_only = self.df[
            (self.df["CT_STATUS"] == "Normal CT") & (self.df["CT_ISSUE_FLAG"])
        ].head(5)

        if len(statistical_only) > 0:
            print(
                statistical_only[
                    [
                        "EQUIPMENT_CODE",
                        "PART_NAME",
                        "CT",
                        "CT_DEVIATION_PCT",
                        "OUTLIER_SCORE",
                        "CT_ISSUE_TYPE",
                    ]
                ].to_string()
            )

        print("\n🔍 Examples of shots flagged by original but not statistical method:")
        original_only = self.df[
            (self.df["CT_STATUS"] != "Normal CT") & (not self.df["CT_ISSUE_FLAG"])
        ].head(5)

        if len(original_only) > 0:
            print(
                original_only[
                    [
                        "EQUIPMENT_CODE",
                        "PART_NAME",
                        "CT",
                        "CT_DEVIATION_PCT",
                        "OUTLIER_SCORE",
                        "CT_STATUS",
                    ]
                ].to_string()
            )

    def display_thresholds(self):
        """Display current threshold configuration"""
        print("\n" + "=" * 60)
        print("⚙️ CURRENT THRESHOLD CONFIGURATION")
        print("=" * 60)
        print(f"🌡️ Temperature CV Threshold: >{self.TEMP_CV_THRESHOLD}%")
        print(f"🏭 Supplier Issue Rate Threshold: >{self.SUPPLIER_ISSUE_THRESHOLD}%")
        print(f"⚙️ Equipment Issue Rate Threshold: >{self.EQUIPMENT_ISSUE_THRESHOLD}%")
        print(f"⏰ Time-based Multiplier: {self.TIME_MULTIPLIER_THRESHOLD}x average")

        print("\n🔬 Statistical Outlier Detection Thresholds:")
        print(f"   Standard Deviation: {self.STD_DEVIATION_THRESHOLD}σ")
        print(f"   IQR Multiplier: {self.IQR_MULTIPLIER}x")
        print(f"   Z-Score Threshold: {self.Z_SCORE_THRESHOLD}")

        print("\n📊 Cycle Time Severity Categories:")
        for i, (bin_val, label) in enumerate(
            zip(self.CT_SEVERITY_BINS[:-1], self.CT_SEVERITY_LABELS)
        ):
            next_bin = (
                self.CT_SEVERITY_BINS[i + 1]
                if i + 1 < len(self.CT_SEVERITY_BINS)
                else "∞"
            )
            print(f"   {label}: {bin_val}-{next_bin}% deviation")
        print("=" * 60)

    def pareto_chart(self, data, title, x_label, y_label, top_n=10, figsize=(12, 8)):
        """
        Create a Pareto chart

        Args:
            data (pd.Series): Data to analyze
            title (str): Chart title
            x_label (str): X-axis label
            y_label (str): Y-axis label
            top_n (int): Number of top categories to show
            figsize (tuple): Figure size
        """
        # Calculate frequencies
        freq = data.value_counts()
        freq = freq.head(top_n)

        # Calculate cumulative percentage
        total = freq.sum()
        cumsum = freq.cumsum()
        cumsum_pct = (cumsum / total) * 100

        # Create figure
        fig, ax1 = plt.subplots(figsize=figsize)

        # Bar chart
        bars = ax1.bar(range(len(freq)), freq.values, color="skyblue", alpha=0.7)
        ax1.set_xlabel(x_label)
        ax1.set_ylabel(y_label, color="blue")
        ax1.tick_params(axis="y", labelcolor="blue")

        # Set x-axis labels
        ax1.set_xticks(range(len(freq)))
        ax1.set_xticklabels(freq.index, rotation=45, ha="right")

        # Cumulative line
        ax2 = ax1.twinx()
        ax2.plot(
            range(len(freq)), cumsum_pct.values, color="red", marker="o", linewidth=2
        )
        ax2.set_ylabel("Cumulative Percentage (%)", color="red")
        ax2.tick_params(axis="y", labelcolor="red")
        ax2.set_ylim(0, 100)

        # Add percentage labels on bars
        for i, (bar, pct) in enumerate(zip(bars, cumsum_pct)):
            height = bar.get_height()
            ax1.text(
                bar.get_x() + bar.get_width() / 2.0,
                height + height * 0.01,
                f"{pct:.1f}%",
                ha="center",
                va="bottom",
                fontsize=9,
            )

        plt.title(title, fontsize=14, fontweight="bold")
        plt.tight_layout()
        plt.show()

        # Print top contributors
        print(f"\n📈 Top {top_n} Contributors to {title}:")
        for i, (category, count) in enumerate(freq.items()):
            percentage = (count / total) * 100
            cumulative = cumsum_pct.iloc[i]
            print(
                f"{i + 1:2d}. {category}: {count:,} ({percentage:.1f}%) - Cumulative: {cumulative:.1f}%"
            )

        return freq, cumsum_pct

    def analyze_cycle_time_issues(self):
        """Analyze cycle time deviations using statistical methods"""
        print("\n" + "=" * 60)
        print("🔍 STATISTICAL CYCLE TIME DEVIATION ANALYSIS")
        print("=" * 60)

        # Filter for problematic shots using our statistical methods
        problematic_shots = self.df[self.df["CT_ISSUE_FLAG"]]

        if len(problematic_shots) == 0:
            print("✅ No cycle time issues found using statistical methods!")
            return

        print(
            f"📊 Found {len(problematic_shots)} shots with statistical cycle time issues"
        )
        print(f"📈 Issue rate: {(len(problematic_shots) / len(self.df)) * 100:.2f}%")

        # Display statistical method breakdown
        print("\n🔬 Statistical Method Breakdown:")
        outlier_columns = [
            "STD_OUTLIER",
            "IQR_OUTLIER",
            "ZSCORE_OUTLIER",
            "PERCENTILE_OUTLIER",
            "ROLLING_OUTLIER",
        ]
        for col in outlier_columns:
            count = self.df[col].sum()
            pct = (count / len(self.df)) * 100
            print(f"   {col}: {count:,} shots ({pct:.1f}%)")

        # 1. Pareto by Issue Type (our statistical categories)
        print("\n1️⃣ Pareto Analysis by Statistical Issue Type:")
        self.pareto_chart(
            problematic_shots["CT_ISSUE_TYPE"],
            "Cycle Time Issues by Statistical Type",
            "Issue Type",
            "Number of Shots",
        )

        # Compare with original CT_STATUS if available
        if "CT_STATUS" in self.df.columns:
            self._compare_with_original_ct_status()

        # 2. Pareto by Equipment
        print("\n2️⃣ Pareto Analysis by Equipment Code:")
        self.pareto_chart(
            problematic_shots["EQUIPMENT_CODE"],
            "Cycle Time Issues by Equipment",
            "Equipment Code",
            "Number of Shots",
        )

        # 3. Pareto by Supplier
        print("\n3️⃣ Pareto Analysis by Supplier:")
        self.pareto_chart(
            problematic_shots["SUPPLIER_NAME"],
            "Cycle Time Issues by Supplier",
            "Supplier Name",
            "Number of Shots",
        )

        # 4. Pareto by Tooling Family
        print("\n4️⃣ Pareto Analysis by Tooling Family:")
        self.pareto_chart(
            problematic_shots["TOOLING_FAMILY"],
            "Cycle Time Issues by Tooling Family",
            "Tooling Family",
            "Number of Shots",
        )

        # 5. Pareto by Part
        print("\n5️⃣ Pareto Analysis by Part Name:")
        self.pareto_chart(
            problematic_shots["PART_NAME"],
            "Cycle Time Issues by Part",
            "Part Name",
            "Number of Shots",
        )

        # 6. Time-based analysis
        print("\n6️⃣ Pareto Analysis by Day of Week:")
        self.pareto_chart(
            problematic_shots["DAY_OF_WEEK"],
            "Cycle Time Issues by Day of Week",
            "Day of Week",
            "Number of Shots",
        )

        # 7. Hourly analysis
        print("\n7️⃣ Pareto Analysis by Hour of Day:")
        self.pareto_chart(
            problematic_shots["HOUR"],
            "Cycle Time Issues by Hour",
            "Hour of Day",
            "Number of Shots",
        )

    def analyze_temperature_issues(self):
        """Analyze temperature-related issues"""
        print("\n" + "=" * 60)
        print("🌡️ TEMPERATURE ANALYSIS")
        print("=" * 60)

        # Calculate temperature statistics by equipment
        temp_stats = (
            self.df.groupby("EQUIPMENT_CODE")["TEMPERATURE"]
            .agg(["count", "mean", "std", "min", "max"])
            .round(2)
        )

        # Identify equipment with high temperature variation
        temp_stats["cv"] = (temp_stats["std"] / temp_stats["mean"] * 100).round(2)
        high_variation = temp_stats[
            temp_stats["cv"] > self.TEMP_CV_THRESHOLD
        ].sort_values("cv", ascending=False)

        print(f"📊 Temperature analysis for {len(temp_stats)} equipment")
        print(
            f"🔍 Found {len(high_variation)} equipment with high temperature variation (>10% CV)"
        )

        if len(high_variation) > 0:
            print("\n🌡️ Equipment with High Temperature Variation:")
            print(high_variation.head(10))

            # Pareto by equipment with high temperature variation
            high_var_equipment = self.df[
                self.df["EQUIPMENT_CODE"].isin(high_variation.index)
            ]
            self.pareto_chart(
                high_var_equipment["EQUIPMENT_CODE"],
                "Shots from Equipment with High Temperature Variation",
                "Equipment Code",
                "Number of Shots",
            )

    def analyze_supplier_performance(self):
        """Analyze supplier performance issues"""
        print("\n" + "=" * 60)
        print("🏭 SUPPLIER PERFORMANCE ANALYSIS")
        print("=" * 60)

        # Calculate supplier metrics using statistical approach
        supplier_metrics = (
            self.df.groupby("SUPPLIER_NAME")
            .agg(
                {
                    "CT_ISSUE_FLAG": "sum",
                    "CT": "count",
                    "CT_DEVIATION_PCT": ["mean", "std"],
                }
            )
            .round(2)
        )

        supplier_metrics.columns = [
            "Issues",
            "Total_Shots",
            "Avg_Deviation",
            "Std_Deviation",
        ]
        supplier_metrics["Issue_Rate"] = (
            supplier_metrics["Issues"] / supplier_metrics["Total_Shots"] * 100
        ).round(2)
        supplier_metrics = supplier_metrics.sort_values("Issue_Rate", ascending=False)

        print(f"📊 Analyzed {len(supplier_metrics)} suppliers")
        print("\n🏭 Supplier Performance Summary:")
        print(supplier_metrics.head(10))

        # Pareto by supplier issue rate
        high_issue_suppliers = supplier_metrics[
            supplier_metrics["Issue_Rate"] > self.SUPPLIER_ISSUE_THRESHOLD
        ]
        if len(high_issue_suppliers) > 0:
            print(
                f"\n⚠️ Found {len(high_issue_suppliers)} suppliers with >5% issue rate"
            )

            # Create Pareto chart for suppliers with issues
            issue_data = self.df[
                self.df["SUPPLIER_NAME"].isin(high_issue_suppliers.index)
            ]
            self.pareto_chart(
                issue_data["SUPPLIER_NAME"],
                "Shots from Suppliers with High Issue Rates",
                "Supplier Name",
                "Number of Shots",
            )

    def analyze_equipment_performance(self):
        """Analyze equipment performance issues"""
        print("\n" + "=" * 60)
        print("⚙️ EQUIPMENT PERFORMANCE ANALYSIS")
        print("=" * 60)

        # Calculate equipment metrics using statistical approach
        equipment_metrics = (
            self.df.groupby("EQUIPMENT_CODE")
            .agg(
                {
                    "CT_ISSUE_FLAG": "sum",
                    "CT": "count",
                    "CT_DEVIATION_PCT": ["mean", "std"],
                    "TEMPERATURE": ["mean", "std"],
                }
            )
            .round(2)
        )

        equipment_metrics.columns = [
            "Issues",
            "Total_Shots",
            "Avg_CT_Deviation",
            "Std_CT_Deviation",
            "Avg_Temp",
            "Std_Temp",
        ]
        equipment_metrics["Issue_Rate"] = (
            equipment_metrics["Issues"] / equipment_metrics["Total_Shots"] * 100
        ).round(2)
        equipment_metrics = equipment_metrics.sort_values("Issue_Rate", ascending=False)

        print(f"📊 Analyzed {len(equipment_metrics)} equipment")
        print("\n⚙️ Equipment Performance Summary:")
        print(equipment_metrics.head(10))

        # Identify problematic equipment
        problematic_equipment = equipment_metrics[
            equipment_metrics["Issue_Rate"] > self.EQUIPMENT_ISSUE_THRESHOLD
        ]
        if len(problematic_equipment) > 0:
            print(
                f"\n⚠️ Found {len(problematic_equipment)} equipment with >10% issue rate"
            )

            # Pareto chart for problematic equipment
            problem_data = self.df[
                self.df["EQUIPMENT_CODE"].isin(problematic_equipment.index)
            ]
            self.pareto_chart(
                problem_data["EQUIPMENT_CODE"],
                "Shots from Equipment with High Issue Rates",
                "Equipment Code",
                "Number of Shots",
            )

    def time_series_analysis(self):
        """Analyze time-based trends"""
        print("\n" + "=" * 60)
        print("⏰ TIME SERIES ANALYSIS")
        print("=" * 60)

        # Daily issue trends using statistical approach
        daily_issues = self.df.groupby("DATE").agg(
            {"CT_ISSUE_FLAG": "sum", "CT": "count"}
        )
        daily_issues["Issue_Rate"] = (
            daily_issues["CT_ISSUE_FLAG"] / daily_issues["CT"] * 100
        ).round(2)

        # Identify problematic days
        avg_issue_rate = daily_issues["Issue_Rate"].mean()
        problematic_days = daily_issues[
            daily_issues["Issue_Rate"] > avg_issue_rate * self.TIME_MULTIPLIER_THRESHOLD
        ]

        print(f"📊 Analyzed {len(daily_issues)} days")
        print(f"📈 Average daily issue rate: {avg_issue_rate:.2f}%")
        print(
            f"⚠️ Found {len(problematic_days)} days with significantly higher issue rates"
        )

        if len(problematic_days) > 0:
            print("\n📅 Problematic Days:")
            print(problematic_days.head(10))

            # Create time series plot
            plt.figure(figsize=(15, 6))
            plt.plot(
                daily_issues.index, daily_issues["Issue_Rate"], marker="o", linewidth=1
            )
            plt.axhline(
                y=avg_issue_rate,
                color="red",
                linestyle="--",
                label=f"Average: {avg_issue_rate:.2f}%",
            )
            plt.title("Daily Issue Rate Trend", fontsize=14, fontweight="bold")
            plt.xlabel("Date")
            plt.ylabel("Issue Rate (%)")
            plt.legend()
            plt.xticks(rotation=45)
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.show()

    def generate_recommendations(self):
        """Generate actionable recommendations based on Pareto analysis"""
        print("\n" + "=" * 60)
        print("💡 ACTIONABLE RECOMMENDATIONS")
        print("=" * 60)

        recommendations = []

        # Analyze top issues
        ct_issues = self.df[self.df["CT_ISSUE_FLAG"]]

        if len(ct_issues) > 0:
            # Top equipment issues
            top_equipment = ct_issues["EQUIPMENT_CODE"].value_counts().head(3)
            for equipment, count in top_equipment.items():
                recommendations.append(
                    {
                        "Priority": "High",
                        "Category": "Equipment",
                        "Issue": f"Equipment {equipment} has {count} cycle time issues",
                        "Action": f"Perform preventive maintenance on {equipment}",
                        "Impact": f"Addresses {(count / len(ct_issues) * 100):.1f}% of all CT issues",
                    }
                )

            # Top supplier issues
            top_suppliers = ct_issues["SUPPLIER_NAME"].value_counts().head(3)
            for supplier, count in top_suppliers.items():
                recommendations.append(
                    {
                        "Priority": "Medium",
                        "Category": "Supplier",
                        "Issue": f"Supplier {supplier} has {count} cycle time issues",
                        "Action": f"Review quality processes with {supplier}",
                        "Impact": f"Addresses {(count / len(ct_issues) * 100):.1f}% of all CT issues",
                    }
                )

            # Top tooling issues
            top_tooling = ct_issues["TOOLING_FAMILY"].value_counts().head(3)
            for tooling, count in top_tooling.items():
                recommendations.append(
                    {
                        "Priority": "Medium",
                        "Category": "Tooling",
                        "Issue": f"{tooling} tooling has {count} cycle time issues",
                        "Action": f"Review {tooling} tooling maintenance schedule",
                        "Impact": f"Addresses {(count / len(ct_issues) * 100):.1f}% of all CT issues",
                    }
                )

        # Create recommendations DataFrame
        if recommendations:
            rec_df = pd.DataFrame(recommendations)
            print("\n📋 Prioritized Action Items:")
            for i, rec in rec_df.iterrows():
                print(f"\n{i + 1}. {rec['Category']} - {rec['Issue']}")
                print(f"   Action: {rec['Action']}")
                print(f"   Impact: {rec['Impact']}")
                print(f"   Priority: {rec['Priority']}")
        else:
            print(
                "✅ No significant issues identified - current processes are performing well!"
            )

    def run_complete_analysis(self):
        """Run the complete Pareto analysis"""
        print("🚀 Starting Comprehensive Pareto Analysis for Root Cause Analysis")
        print("=" * 80)

        # Run all analyses
        self.analyze_cycle_time_issues()
        self.analyze_temperature_issues()
        self.analyze_supplier_performance()
        self.analyze_equipment_performance()
        self.time_series_analysis()
        self.generate_recommendations()
        # Scrap calculation already done in setup_data() - don't recalculate here

        # Print scrap summary (console) - Always use current SCRAP_FLAG values
        try:
            # Always recalculate from current SCRAP_FLAG to ensure accuracy
            total = len(self.df) if len(self.df) else 1
            current_scrap_count = int(self.df["SCRAP_FLAG"].sum())
            current_scrap_rate = float(current_scrap_count / total * 100)

            print("\n🧾 SCRAP SUMMARY")
            print(
                f"   Overall scrap rate: {current_scrap_rate:.2f}% ({current_scrap_count:,} shots)"
            )

            # Show scrap breakdowns if there are scrap shots
            if current_scrap_count > 0:
                scrap_reasons = (
                    self.df[self.df["SCRAP_FLAG"]]
                    .groupby("SCRAP_REASON")
                    .size()
                    .reset_index(name="count")
                    .sort_values("count", ascending=False)
                )
                if not scrap_reasons.empty:
                    print("   Top scrap reasons:")
                    print(scrap_reasons.head(5).to_string(index=False))

                scrap_suppliers = (
                    self.df[self.df["SCRAP_FLAG"]]
                    .groupby("SUPPLIER_NAME")
                    .size()
                    .reset_index(name="count")
                    .sort_values("count", ascending=False)
                )
                if not scrap_suppliers.empty:
                    print("\n   Top scrap suppliers:")
                    print(scrap_suppliers.head(5).to_string(index=False))

                scrap_equipment = (
                    self.df[self.df["SCRAP_FLAG"]]
                    .groupby("EQUIPMENT_CODE")
                    .size()
                    .reset_index(name="count")
                    .sort_values("count", ascending=False)
                )
                if not scrap_equipment.empty:
                    print("\n   Top scrap equipment:")
                    print(scrap_equipment.head(5).to_string(index=False))
            else:
                print("   No scrap shots detected")

        except Exception as e:
            print(f"⚠️ Could not print scrap summary: {e}")

        print("\n" + "=" * 80)
        print("✅ Pareto Analysis Complete!")
        print("=" * 80)

        # Return the analysis results
        return {
            "df": self.df,
            "pareto_results": {
                "cycle_time_issues": self.df[self.df["CT_ISSUE_FLAG"]],
                "supplier_performance": self.df.groupby("SUPPLIER_NAME")
                .agg({"CT": "count", "CT_ISSUE_FLAG": "sum"})
                .reset_index(),
                "equipment_performance": self.df.groupby("EQUIPMENT_CODE")
                .agg({"CT": "count", "CT_ISSUE_FLAG": "sum"})
                .reset_index(),
                "time_series": self.df.groupby("DATE")
                .agg({"CT": "count", "CT_ISSUE_FLAG": "sum"})
                .reset_index(),
                # New: scrap Pareto outputs
                "scrap": self.scrap_summary,
            },
        }


def main():
    """Main function to run the Pareto analysis"""
    try:
        # Fetch data from Snowflake
        print("📊 Fetching data from Snowflake...")
        df = fetch_data_from_snowflake(session)

        if df.empty:
            print("❌ No data retrieved from Snowflake")
            return

        # Example 1: Run with default thresholds
        print("\n" + "=" * 80)
        print("🔍 ANALYSIS WITH DEFAULT THRESHOLDS")
        print("=" * 80)
        pareto = ParetoAnalysis(df)
        pareto.run_complete_analysis()

        # Example 2: Run with custom thresholds (uncomment to use)
        """
        print("\n" + "=" * 80)
        print("🔍 ANALYSIS WITH CUSTOM THRESHOLDS")
        print("=" * 80)
        
        # Custom thresholds for more sensitive detection
        custom_thresholds = {
            'TEMP_CV_THRESHOLD': 5.0,      # More sensitive temperature detection
            'SUPPLIER_ISSUE_THRESHOLD': 3.0,  # Lower supplier threshold
            'EQUIPMENT_ISSUE_THRESHOLD': 5.0,  # Lower equipment threshold
            'TIME_MULTIPLIER_THRESHOLD': 1.2   # More sensitive time detection
        }
        
        pareto_custom = ParetoAnalysis(df, thresholds=custom_thresholds)
        pareto_custom.run_complete_analysis()
        """

    except Exception as e:
        print(f"❌ Error during analysis: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
