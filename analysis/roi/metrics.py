"""
ROI Metrics Calculator
======================

Calculates comprehensive metrics for ROI analysis including efficiency,
time analysis, and process stability.

Author: Utku Gulbardak
Date: 2025-10-24
"""

import logging
from typing import Tuple

import numpy as np
import pandas as pd

from .config import ROIAnalysisConfig


class ROIMetricsCalculator:
    """
    Calculates comprehensive metrics for ROI analysis.

    Metrics include:
    - Grouped aggregations by supplier, equipment, and date (daily)
    - Time metrics (hours used, expected, gains, losses)
    - Efficiency metrics (tooling efficiency, category-specific)
    - Process stability metrics
    - Data quality filtering
    """

    def __init__(self, config: ROIAnalysisConfig):
        """
        Initialize metrics calculator with configuration.

        Args:
            config: ROI analysis configuration
        """
        self.config = config

    def calculate_grouped_metrics(
        self, df: pd.DataFrame, aggregation_level: str = "daily"
    ) -> pd.DataFrame:
        """
        Calculate grouped summary metrics by supplier, equipment, and time period.

        Args:
            df: Preprocessed DataFrame with CT classifications
            aggregation_level: Time aggregation level - "daily", "weekly", or "monthly"

        Returns:
            DataFrame with grouped metrics at specified aggregation level
        """
        # Choose aggregation column based on level
        time_col_map = {
            "daily": "DATE",
            "weekly": "WEEK",
            "monthly": "MONTH",
        }
        time_col = time_col_map.get(aggregation_level, "DATE")

        # Pre-calculate weighted CT to avoid slow lambda lookups
        df["WEIGHTED_CT"] = df["CT"] * df["TOTAL_SHOT_COUNT"]

        # Main grouping and aggregation
        grouped = (
            df.groupby(["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col])
            .agg(
                TOTAL_SHOTS=("TOTAL_SHOT_COUNT", "sum"),
                PARTS_PRODUCED=("VOLUME", "sum"),
                APPROVED_CT=("APPROVED_CT", "first"),
                WEIGHTED_CT_SUM=("WEIGHTED_CT", "sum"),  # Sum of weighted CTs
                WITHIN_SHOT_COUNT=("CT_CATEGORY", lambda x: (x == "WITHIN").sum()),
                SLOWER_SHOT_COUNT=("CT_CATEGORY", lambda x: (x == "SLOWER").sum()),
                FASTER_SHOT_COUNT=("CT_CATEGORY", lambda x: (x == "FASTER").sum()),
                # NEW: Uptime metrics
                PRODUCTION_TIME=("PRODUCTION_SECONDS", "sum"),
                IDLE_TIME=("IDLE_SECONDS", "sum"),
            )
            .reset_index()
        )

        # Calculate weighted average CT efficiently
        grouped["AVERAGE_CT"] = (
            grouped["WEIGHTED_CT_SUM"] / grouped["TOTAL_SHOTS"]
        ).round(2)
        grouped.drop(columns=["WEIGHTED_CT_SUM"], inplace=True)

        # Calculate TOTAL_RUNTIME and UPTIME_PERCENTAGE
        grouped["TOTAL_RUNTIME"] = grouped["PRODUCTION_TIME"] + grouped["IDLE_TIME"]
        grouped["UPTIME_PERCENTAGE"] = np.where(
            grouped["TOTAL_RUNTIME"] > 0,
            (grouped["PRODUCTION_TIME"] / grouped["TOTAL_RUNTIME"] * 100).round(2),
            0,
        )

        # Calculate weighted average CTs for each category
        grouped = self._add_weighted_category_cts(df, grouped, time_col)

        # Calculate time metrics
        grouped = self._calculate_time_metrics(grouped)

        # Calculate efficiency metrics
        grouped = self._calculate_efficiency_metrics(grouped)

        # Add process stability metrics
        grouped = self._add_process_stability(df, grouped, time_col)

        return grouped

    def _add_weighted_category_cts(
        self, df: pd.DataFrame, grouped: pd.DataFrame, time_col: str
    ) -> pd.DataFrame:
        """
        Add weighted average CTs for SLOWER and FASTER categories.

        Args:
            df: Original DataFrame with individual records
            grouped: Grouped DataFrame
            time_col: Time aggregation column (DATE, WEEK, or MONTH)

        Returns:
            DataFrame with category-specific average CTs
        """

        # Calculate weighted average CT for SLOWER category using efficient aggregation
        slow_df = df[df["CT_CATEGORY"] == "SLOWER"].copy()
        if not slow_df.empty:
            slow_df["WEIGHTED_CT"] = slow_df["CT"] * slow_df["TOTAL_SHOT_COUNT"]
            slow_agg = (
                slow_df.groupby(["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col])
                .agg(
                    WEIGHTED_CT_SUM=("WEIGHTED_CT", "sum"),
                    TOTAL_SHOTS=("TOTAL_SHOT_COUNT", "sum"),
                )
                .reset_index()
            )
            slow_agg["AVG_CT_SLOW"] = (
                slow_agg["WEIGHTED_CT_SUM"] / slow_agg["TOTAL_SHOTS"]
            )
            slow_ct = slow_agg[
                ["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col, "AVG_CT_SLOW"]
            ]
        else:
            slow_ct = pd.DataFrame(
                columns=["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col, "AVG_CT_SLOW"]
            )

        # Calculate weighted average CT for FASTER category using efficient aggregation
        fast_df = df[df["CT_CATEGORY"] == "FASTER"].copy()
        if not fast_df.empty:
            fast_df["WEIGHTED_CT"] = fast_df["CT"] * fast_df["TOTAL_SHOT_COUNT"]
            fast_agg = (
                fast_df.groupby(["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col])
                .agg(
                    WEIGHTED_CT_SUM=("WEIGHTED_CT", "sum"),
                    TOTAL_SHOTS=("TOTAL_SHOT_COUNT", "sum"),
                )
                .reset_index()
            )
            fast_agg["AVG_CT_FAST"] = (
                fast_agg["WEIGHTED_CT_SUM"] / fast_agg["TOTAL_SHOTS"]
            )
            fast_ct = fast_agg[
                ["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col, "AVG_CT_FAST"]
            ]
        else:
            fast_ct = pd.DataFrame(
                columns=["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col, "AVG_CT_FAST"]
            )

        # Calculate weighted average CT for WITHIN category using efficient aggregation
        within_df = df[df["CT_CATEGORY"] == "WITHIN"].copy()
        if not within_df.empty:
            within_df["WEIGHTED_CT"] = within_df["CT"] * within_df["TOTAL_SHOT_COUNT"]
            within_agg = (
                within_df.groupby(["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col])
                .agg(
                    WEIGHTED_CT_SUM=("WEIGHTED_CT", "sum"),
                    TOTAL_SHOTS=("TOTAL_SHOT_COUNT", "sum"),
                )
                .reset_index()
            )
            within_agg["AVG_CT_WITHIN"] = (
                within_agg["WEIGHTED_CT_SUM"] / within_agg["TOTAL_SHOTS"]
            )
            within_ct = within_agg[
                ["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col, "AVG_CT_WITHIN"]
            ]
        else:
            within_ct = pd.DataFrame(
                columns=["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col, "AVG_CT_WITHIN"]
            )

        # Merge and fill nulls with approved CT
        grouped = grouped.merge(
            slow_ct, on=["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col], how="left"
        )
        grouped = grouped.merge(
            fast_ct, on=["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col], how="left"
        )
        grouped = grouped.merge(
            within_ct, on=["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col], how="left"
        )

        grouped["AVG_CT_SLOW"] = grouped["AVG_CT_SLOW"].fillna(grouped["APPROVED_CT"])
        grouped["AVG_CT_FAST"] = grouped["AVG_CT_FAST"].fillna(grouped["APPROVED_CT"])
        grouped["AVG_CT_WITHIN"] = grouped["AVG_CT_WITHIN"].fillna(
            grouped["APPROVED_CT"]
        )

        return grouped

    def _calculate_time_metrics(self, grouped: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate time-related metrics (hours, percentages, gains/losses).

        Args:
            grouped: Grouped DataFrame with aggregated data

        Returns:
            DataFrame with time metrics added
        """
        # Used hours by category
        grouped["USED_HOURS_SLOW"] = (
            (grouped["AVG_CT_SLOW"] * grouped["SLOWER_SHOT_COUNT"]) / 3600
        ).round(2)
        grouped["USED_HOURS_FAST"] = (
            (grouped["AVG_CT_FAST"] * grouped["FASTER_SHOT_COUNT"]) / 3600
        ).round(2)
        grouped["USED_HOURS_WITHIN"] = (
            (grouped["AVG_CT_WITHIN"] * grouped["WITHIN_SHOT_COUNT"]) / 3600
        ).round(2)

        # Expected hours by category
        grouped["EXPECTED_HOURS_FAST"] = (
            (grouped["APPROVED_CT"] * grouped["FASTER_SHOT_COUNT"]) / 3600
        ).round(2)
        grouped["EXPECTED_HOURS_SLOW"] = (
            (grouped["APPROVED_CT"] * grouped["SLOWER_SHOT_COUNT"]) / 3600
        ).round(2)
        grouped["EXPECTED_HOURS_WITHIN"] = (
            (grouped["APPROVED_CT"] * grouped["WITHIN_SHOT_COUNT"]) / 3600
        ).round(2)

        # Total metrics
        grouped["EXPECTED_HOURS"] = (
            (grouped["APPROVED_CT"] * grouped["TOTAL_SHOTS"]) / 3600
        ).round(2)
        grouped["USED_HOURS"] = (
            (grouped["AVERAGE_CT"] * grouped["TOTAL_SHOTS"]) / 3600
        ).round(2)
        grouped["HOURS_DIFF"] = (
            grouped["EXPECTED_HOURS"] - grouped["USED_HOURS"]
        ).round(2)

        # Gain/Loss calculations (clipped to positive values)
        grouped["GAIN_HOURS"] = (
            (grouped["EXPECTED_HOURS_FAST"] - grouped["USED_HOURS_FAST"])
            .clip(lower=0)
            .round(2)
        )
        grouped["LOSS_HOURS"] = (
            (grouped["USED_HOURS_SLOW"] - grouped["EXPECTED_HOURS_SLOW"])
            .clip(lower=0)
            .round(2)
        )

        # Percentages
        grouped["WITHIN_SHOT_PCT"] = (
            grouped["WITHIN_SHOT_COUNT"] / grouped["TOTAL_SHOTS"] * 100
        ).round(2)
        grouped["SLOWER_SHOT_PCT"] = (
            grouped["SLOWER_SHOT_COUNT"] / grouped["TOTAL_SHOTS"] * 100
        ).round(2)
        grouped["FASTER_SHOT_PCT"] = (
            grouped["FASTER_SHOT_COUNT"] / grouped["TOTAL_SHOTS"] * 100
        ).round(2)

        # Time deviation percentages
        grouped["FASTER_TIME_SAVINGS_PCT"] = np.where(
            grouped["USED_HOURS_FAST"] > 0,
            (
                (grouped["EXPECTED_HOURS_FAST"] - grouped["USED_HOURS_FAST"])
                / grouped["USED_HOURS_FAST"]
                * 100
            ).round(2),
            0,
        )

        grouped["SLOWER_TIME_OVERRUN_PCT"] = np.where(
            grouped["USED_HOURS_SLOW"] > 0,
            (
                (grouped["USED_HOURS_SLOW"] - grouped["EXPECTED_HOURS_SLOW"])
                / grouped["EXPECTED_HOURS_SLOW"]
                * 100
            ).round(2),
            0,
        )

        return grouped

    def _calculate_efficiency_metrics(self, grouped: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate efficiency metrics and status flags.

        Args:
            grouped: Grouped DataFrame with time metrics

        Returns:
            DataFrame with efficiency metrics added
        """
        # Main efficiency calculation
        grouped["TOOLING_EFFICIENCY"] = np.where(
            grouped["USED_HOURS"] > 0,
            (grouped["TOTAL_SHOTS"] * grouped["APPROVED_CT"])
            / (grouped["USED_HOURS"] * 3600)
            * 100,
            0,
        ).round(2)

        # Category-specific efficiencies
        grouped["FASTER_EFFICIENCY"] = (
            (grouped["FASTER_SHOT_COUNT"] * grouped["APPROVED_CT"])
            / (grouped["USED_HOURS"] * 3600)
            * 100
        ).round(2)

        grouped["SLOWER_EFFICIENCY"] = (
            (grouped["SLOWER_SHOT_COUNT"] * grouped["APPROVED_CT"])
            / (grouped["USED_HOURS"] * 3600)
            * 100
        ).round(2)

        grouped["WITHIN_EFFICIENCY"] = (
            (grouped["WITHIN_SHOT_COUNT"] * grouped["APPROVED_CT"])
            / (grouped["USED_HOURS"] * 3600)
            * 100
        ).round(2)

        # Relative efficiency gains/losses
        grouped["EFF_GAIN"] = np.where(
            grouped["TOOLING_EFFICIENCY"] > 0,
            (grouped["FASTER_EFFICIENCY"] / grouped["TOOLING_EFFICIENCY"] * 100).round(
                2
            ),
            0,
        )

        grouped["EFF_LOSS"] = np.where(
            grouped["TOOLING_EFFICIENCY"] > 0,
            (grouped["SLOWER_EFFICIENCY"] / grouped["TOOLING_EFFICIENCY"] * 100).round(
                2
            ),
            0,
        )

        # Status flag
        grouped["STATUS"] = np.where(
            grouped["TOOLING_EFFICIENCY"] < 100, "LOSS", "GAIN"
        )

        # Additional metrics
        grouped["DIFFERENCE"] = (grouped["APPROVED_CT"] - grouped["AVERAGE_CT"]).round(
            2
        )

        return grouped

    def _add_process_stability(
        self, df: pd.DataFrame, grouped: pd.DataFrame, time_col: str
    ) -> pd.DataFrame:
        """
        Add process stability metrics based on deviation from average CT.

        Args:
            df: Original DataFrame with individual records
            grouped: Grouped DataFrame
            time_col: Time aggregation column (DATE, WEEK, or MONTH)

        Returns:
            DataFrame with stability metrics added
        """
        # Merge average CT back to original data for stability calculation
        df_with_avg = df.merge(
            grouped[["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col, "AVERAGE_CT"]],
            on=["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col],
            how="left",
        )

        # Calculate stability based on deviation from average CT
        delta = self.config.delta_tolerance
        df_with_avg["CT_WITHIN_FROM_AVG"] = (
            np.abs(df_with_avg["CT"] - df_with_avg["AVERAGE_CT"])
            <= df_with_avg["AVERAGE_CT"] * delta
        )

        # Aggregate stability metrics
        within_from_avg = (
            df_with_avg.groupby(["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col])
            .agg(WITHIN_FROM_AVG_SHOT_COUNT=("CT_WITHIN_FROM_AVG", "sum"))
            .reset_index()
        )

        # Merge back to grouped data
        grouped = grouped.merge(
            within_from_avg,
            on=["SUPPLIER_NAME", "EQUIPMENT_CODE", time_col],
            how="left",
        )

        # Calculate process stability percentage
        grouped["PROCESS_STABILITY"] = (
            grouped["WITHIN_FROM_AVG_SHOT_COUNT"] / grouped["TOTAL_SHOTS"] * 100
        ).round(2)

        return grouped

    def filter_data(self, grouped: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Filter data into valid and suspicious datasets.

        Filters out data that doesn't meet quality thresholds:
        - Minimum shots threshold (per day)
        - Min/max efficiency thresholds

        Args:
            grouped: Grouped metrics DataFrame (daily level)

        Returns:
            Tuple of (valid_df, suspicious_df)
        """
        suspicious_condition = (
            (grouped["TOTAL_SHOTS"] < self.config.min_shots_threshold)
            | (grouped["TOOLING_EFFICIENCY"] < self.config.min_efficiency_threshold)
            | (grouped["TOOLING_EFFICIENCY"] > self.config.max_efficiency_threshold)
        )

        suspicious_df = grouped[suspicious_condition].copy()
        valid_df = grouped[~suspicious_condition].copy()

        logging.info(
            f"✅ Data filtering: {len(valid_df)} valid rows, {len(suspicious_df)} suspicious rows"
        )

        return valid_df, suspicious_df
