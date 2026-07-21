"""
ROI Data Preprocessor
=====================

Handles data preprocessing and transformation for ROI analysis.

Author: Utku Gulbardak
Date: 2025-10-24
"""

import numpy as np
import pandas as pd

from analysis.shared.constants import SessionDetection


class ROIPreprocessor:
    """
    Preprocesses raw Snowflake data for ROI analysis.

    Handles data type conversions, cleaning, and time dimension creation.
    """

    @staticmethod
    def preprocess(df: pd.DataFrame) -> pd.DataFrame:
        """
        Preprocess raw data for analysis.

        Performs:
        - Data type corrections
        - String cleaning
        - Time dimension creation (DAY, WEEK, MONTH, YEAR, QUARTER)

        Args:
            df: Raw data from Snowflake

        Returns:
            Preprocessed DataFrame with additional columns
        """
        # Data type corrections
        df["EQUIPMENT_CODE"] = df["EQUIPMENT_CODE"].astype(str).str.strip()
        df["LOCAL_SHOT_TIME"] = pd.to_datetime(df["LOCAL_SHOT_TIME"])

        # Add time dimension columns
        df["DATE"] = df[
            "LOCAL_SHOT_TIME"
        ].dt.date  # Human-readable date for daily aggregations
        df["DAY"] = df["LOCAL_SHOT_TIME"].dt.strftime("%Y%m%d").astype(int)
        df["WEEK"] = df["LOCAL_SHOT_TIME"].dt.strftime("%G%V").astype(int)
        df["MONTH"] = df["LOCAL_SHOT_TIME"].dt.strftime("%Y%m").astype(int)
        df["YEAR"] = df["LOCAL_SHOT_TIME"].dt.year
        df["QUARTER"] = df["LOCAL_SHOT_TIME"].dt.quarter

        return df

    @staticmethod
    def calculate_uptime_metrics(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate uptime metrics with proper sessionization from MASTER_SHOT_TABLE.

        Based on ANA_SHOT_MADE logic with session detection:
        - Sessions break on gaps > 8 hours (28,800 seconds) or ISO week changes
        - Production time = sum of CT values (excluding idle shots CT >= 999.9)
        - Idle time = gaps WITHIN sessions only (not overnight/weekend gaps)
        - Uptime = (Production time / Total runtime) × 100

        Args:
            df: Preprocessed DataFrame with shots data

        Returns:
            DataFrame with uptime metrics added (PRODUCTION_SECONDS, IDLE_SECONDS)
        """
        # Sort by equipment and time for gap calculation
        df = df.sort_values(["SUPPLIER_NAME", "EQUIPMENT_CODE", "LOCAL_SHOT_TIME"])

        # Calculate time to next shot within same equipment
        df["NEXT_SHOT_TIME"] = df.groupby(["SUPPLIER_NAME", "EQUIPMENT_CODE"])[
            "LOCAL_SHOT_TIME"
        ].shift(-1)
        df["GAP_SECONDS"] = (
            df["NEXT_SHOT_TIME"] - df["LOCAL_SHOT_TIME"]
        ).dt.total_seconds()

        # Extract ISO week/year for session detection
        df["ISO_WEEK"] = df["LOCAL_SHOT_TIME"].dt.isocalendar().week
        df["ISO_YEAR"] = df["LOCAL_SHOT_TIME"].dt.isocalendar().year

        # Get previous shot's week/year for comparison
        df["PREV_WEEK"] = df.groupby(["SUPPLIER_NAME", "EQUIPMENT_CODE"])[
            "ISO_WEEK"
        ].shift(1)
        df["PREV_YEAR"] = df.groupby(["SUPPLIER_NAME", "EQUIPMENT_CODE"])[
            "ISO_YEAR"
        ].shift(1)

        # Mark new sessions based on:
        # 1. Gap from previous shot > 8 hours (28,800 seconds)
        # 2. ISO week changed
        # 3. ISO year changed
        # 4. First shot per equipment
        df["PREV_GAP"] = df["GAP_SECONDS"].shift(1)

        df["NEW_SESSION"] = (
            (df["PREV_GAP"] > SessionDetection.SESSION_GAP_SECONDS)
            | (df["ISO_WEEK"] != df["PREV_WEEK"])
            | (df["ISO_YEAR"] != df["PREV_YEAR"])
            | (df.groupby(["SUPPLIER_NAME", "EQUIPMENT_CODE"]).cumcount() == 0)
        ).astype(int)

        # Assign session IDs
        df["SESSION_ID"] = df.groupby(["SUPPLIER_NAME", "EQUIPMENT_CODE"])[
            "NEW_SESSION"
        ].cumsum()

        # Get next shot's session ID to detect session boundaries
        df["NEXT_SESSION_ID"] = df.groupby(["SUPPLIER_NAME", "EQUIPMENT_CODE"])[
            "SESSION_ID"
        ].shift(-1)

        # Production time per shot (exclude idle shots CT >= 999.9)
        df["PRODUCTION_SECONDS"] = np.where(df["CT"] >= 999.9, 0, df["CT"])

        # Idle time per shot:
        # ONLY count gaps WITHIN the same session (not across session breaks)
        # Conditions:
        # 1. Next shot exists
        # 2. Gap <= 8 hours (within session threshold)
        # 3. Next shot is in SAME session
        df["IDLE_SECONDS"] = np.where(
            (df["NEXT_SHOT_TIME"].notna())
            & (df["GAP_SECONDS"] <= SessionDetection.SESSION_GAP_SECONDS)
            & (df["SESSION_ID"] == df["NEXT_SESSION_ID"]),
            np.maximum(df["GAP_SECONDS"] - df["CT"], 0),
            0,
        )

        # Clean up temporary columns
        df = df.drop(
            columns=[
                "NEXT_SHOT_TIME",
                "GAP_SECONDS",
                "ISO_WEEK",
                "ISO_YEAR",
                "PREV_WEEK",
                "PREV_YEAR",
                "PREV_GAP",
                "NEW_SESSION",
                "SESSION_ID",
                "NEXT_SESSION_ID",
            ]
        )

        return df
