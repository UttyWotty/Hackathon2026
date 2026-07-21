"""
ROI Cycle Time Classifier
==========================

Classifies cycle times as WITHIN, FASTER, or SLOWER based on approved CT.

Author: Utku Gulbardak
Date: 2025-10-24
"""

import numpy as np
import pandas as pd

from .config import ROIAnalysisConfig


class CycleTimeClassifier:
    """
    Classifies cycle times based on deviation from approved CT.

    Classification categories:
    - WITHIN: Within tolerance of approved CT (±delta_tolerance)
    - FASTER: Faster than approved CT (below tolerance)
    - SLOWER: Slower than approved CT (above tolerance)
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
        Classify cycle times as WITHIN, FASTER, or SLOWER based on approved CT.

        Args:
            df: DataFrame with CT and APPROVED_CT columns

        Returns:
            DataFrame with CT_CATEGORY column added
        """
        delta = self.config.delta_tolerance

        conditions = [
            np.abs(df["CT"] - df["APPROVED_CT"]) <= df["APPROVED_CT"] * delta,
            df["CT"] > df["APPROVED_CT"] * (1 + delta),
            df["CT"] < df["APPROVED_CT"] * (1 - delta),
        ]
        choices = ["WITHIN", "SLOWER", "FASTER"]
        df["CT_CATEGORY"] = np.select(conditions, choices, default="OTHER")

        return df
