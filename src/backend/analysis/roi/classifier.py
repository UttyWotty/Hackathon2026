"""
ROI Duration Classifier
==========================

Classifies durations as WITHIN, FASTER, or SLOWER based on approved duration.

Author: Utku Gulbardak
Date: 2025-10-24
"""

import numpy as np
import pandas as pd

from .config import ROIAnalysisConfig


class CycleTimeClassifier:
    """
    Classifies durations based on deviation from approved duration.

    Classification categories:
    - WITHIN: Within tolerance of approved duration (±delta_tolerance)
    - FASTER: Faster than approved duration (below tolerance)
    - SLOWER: Slower than approved duration (above tolerance)
    """

    def __init__(self, config: ROIAnalysisConfig):
        """
        Initialize classifier with configuration.

        Args:
            config: ROI analysis configuration
        """
        self.config = config

    def classify(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Classify durations as WITHIN, FASTER, or SLOWER based on approved duration.

        Args:
            df: DataFrame with DURATION and TARGET_DURATION columns

        Returns:
            DataFrame with DURATION_CATEGORY column added
        """
        delta = self.config.delta_tolerance

        conditions = [
            np.abs(df["DURATION"] - df["TARGET_DURATION"])
            <= df["TARGET_DURATION"] * delta,
            df["DURATION"] > df["TARGET_DURATION"] * (1 + delta),
            df["DURATION"] < df["TARGET_DURATION"] * (1 - delta),
        ]
        choices = ["WITHIN", "SLOWER", "FASTER"]
        df["DURATION_CATEGORY"] = np.select(conditions, choices, default="OTHER")

        return df
