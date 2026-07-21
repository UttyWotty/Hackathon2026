"""
Advanced analysis orchestrator for manufacturing root cause analysis.
Coordinates downtime pattern classification, risk scoring, ML prediction,
and visualization generation across extracted sub-modules.
This module delegates ML work to risk_classifier and charts to rca_visualizations.
"""

import json
import logging
import os
import warnings
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from analysis.rca.core_analysis.rca_visualizations import (
    create_day_of_week_heatmap,
    create_downtime_classification_summary,
)
from analysis.rca.core_analysis.risk_classifier import (
    PATTERN_GRADUAL_DECREASE,
    PATTERN_GRADUAL_INCREASE,
    PATTERN_HIGH_VARIABILITY,
    PATTERN_NORMAL,
    PATTERN_SUDDEN_SPIKE,
    build_prediction_model,
    calculate_risk_scores,
    predict_risk,
)
from analysis.shared.constants import ShiftBoundaries

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore")

# CT pattern analysis constants
MIN_PATTERN_DATAPOINTS = 5
SUDDEN_SPIKE_PCT_THRESHOLD = 50
GRADUAL_CHANGE_PCT_THRESHOLD = 10
VARIABILITY_COEFFICIENT = 0.3

# Downtime classification lookback
MIN_DOWNTIME_LOOKBACK = 3

# Alert thresholds
DEFAULT_ALERT_THRESHOLD = 0.7
HIGH_SEVERITY_THRESHOLD = 0.8
ALERT_LOOKBACK_HOURS = 24


class AdvancedAnalysis:
    """Advanced analysis features for manufacturing root cause analysis."""

    def __init__(self, df: pd.DataFrame) -> None:
        """Initialize with processed manufacturing data.

        Args:
            df: DataFrame with CT_ISSUE_FLAG, DOWNTIME_EVENT, etc.
        """
        self.df = df.copy()
        self.setup_advanced_features()

    def setup_advanced_features(self) -> None:
        """Set up advanced analysis features including time columns and patterns."""
        logger.info("Setting up advanced analysis features...")

        required_columns = ["LOCAL_SHOT_TIME", "CT", "EQUIPMENT_CODE", "PART_NAME"]
        missing_columns = [
            col for col in required_columns if col not in self.df.columns
        ]

        if missing_columns:
            logger.warning("Missing required columns: %s", missing_columns)
            return

        self.df["HOUR"] = self.df["LOCAL_SHOT_TIME"].dt.hour
        self.df["DAY_OF_WEEK"] = self.df["LOCAL_SHOT_TIME"].dt.day_name()
        self.df["WEEK_OF_YEAR"] = self.df["LOCAL_SHOT_TIME"].dt.isocalendar().week
        self.df["MONTH"] = self.df["LOCAL_SHOT_TIME"].dt.month
        self.df["SHIFT"] = self.df["HOUR"].apply(self._determine_shift)

        self.classify_downtime_patterns()

        logger.info("Advanced features setup complete")

    def _determine_shift(self, hour: int) -> str:
        """Determine shift based on hour.

        Args:
            hour: Hour of day (0-23).

        Returns:
            Shift name string.
        """
        if (
            ShiftBoundaries.DAY_START_HOUR
            <= hour
            < ShiftBoundaries.AFTERNOON_START_HOUR
        ):
            return "Morning"
        elif (
            ShiftBoundaries.AFTERNOON_START_HOUR
            <= hour
            < ShiftBoundaries.NIGHT_START_HOUR
        ):
            return "Afternoon"
        else:
            return "Night"

    def classify_downtime_patterns(self) -> None:
        """Classify downtime patterns based on CT shapes for all equipment."""
        logger.info("Classifying downtime patterns...")

        self.df["DOWNTIME_TYPE"] = "None"
        self.df["CT_PATTERN"] = PATTERN_NORMAL
        self.df["RISK_SCORE"] = 0.0

        for equipment in self.df["EQUIPMENT_CODE"].unique():
            equipment_data = self.df[self.df["EQUIPMENT_CODE"] == equipment].copy()
            equipment_data = equipment_data.sort_values("LOCAL_SHOT_TIME")

            equipment_data["CT_CHANGE"] = equipment_data["CT"].diff()
            equipment_data["CT_CHANGE_PCT"] = (
                equipment_data["CT_CHANGE"] / equipment_data["CT"].shift(1)
            ) * 100

            equipment_data["CT_PATTERN"] = self._classify_ct_pattern(equipment_data)
            equipment_data["DOWNTIME_TYPE"] = self._classify_downtime_type(
                equipment_data
            )
            equipment_data["RISK_SCORE"] = calculate_risk_scores(equipment_data)

            mask = self.df["EQUIPMENT_CODE"] == equipment
            self.df.loc[mask, "CT_PATTERN"] = equipment_data["CT_PATTERN"]
            self.df.loc[mask, "DOWNTIME_TYPE"] = equipment_data["DOWNTIME_TYPE"]
            self.df.loc[mask, "RISK_SCORE"] = equipment_data["RISK_SCORE"]

        logger.info("Downtime pattern classification complete")

    def _classify_ct_pattern(self, data: pd.DataFrame) -> List[str]:
        """Classify CT patterns based on recent change history.

        Args:
            data: Equipment-level DataFrame with CT and CT_CHANGE_PCT columns.

        Returns:
            List of pattern classification strings.
        """
        patterns: List[str] = []

        for i in range(len(data)):
            if i < MIN_PATTERN_DATAPOINTS:
                patterns.append(PATTERN_NORMAL)
                continue

            recent_ct = data["CT"].iloc[i - MIN_PATTERN_DATAPOINTS : i + 1].values
            recent_changes = (
                data["CT_CHANGE_PCT"].iloc[i - MIN_PATTERN_DATAPOINTS : i + 1].values
            )

            if np.any(np.abs(recent_changes) > SUDDEN_SPIKE_PCT_THRESHOLD):
                patterns.append(PATTERN_SUDDEN_SPIKE)
            elif np.all(recent_changes > GRADUAL_CHANGE_PCT_THRESHOLD):
                patterns.append(PATTERN_GRADUAL_INCREASE)
            elif np.all(recent_changes < -GRADUAL_CHANGE_PCT_THRESHOLD):
                patterns.append(PATTERN_GRADUAL_DECREASE)
            elif np.std(recent_ct) > np.mean(recent_ct) * VARIABILITY_COEFFICIENT:
                patterns.append(PATTERN_HIGH_VARIABILITY)
            else:
                patterns.append(PATTERN_NORMAL)

        return patterns

    def _classify_downtime_type(self, data: pd.DataFrame) -> List[str]:
        """Classify downtime types based on CT patterns.

        Args:
            data: Equipment-level DataFrame with CT_PATTERN and optionally
                  DOWNTIME_EVENT columns.

        Returns:
            List of downtime type classification strings.
        """
        downtime_types: List[str] = []

        for i in range(len(data)):
            if i < MIN_DOWNTIME_LOOKBACK:
                downtime_types.append("None")
                continue

            has_downtime = (
                data["DOWNTIME_EVENT"].iloc[i]
                if "DOWNTIME_EVENT" in data.columns
                else False
            )

            if has_downtime:
                pattern = data["CT_PATTERN"].iloc[i]
                downtime_types.append(self._map_pattern_to_downtime(pattern))
            else:
                downtime_types.append("None")

        return downtime_types

    def _map_pattern_to_downtime(self, pattern: str) -> str:
        """Map a CT pattern to its corresponding downtime type.

        Args:
            pattern: CT pattern classification string.

        Returns:
            Downtime type string.
        """
        pattern_to_downtime = {
            PATTERN_SUDDEN_SPIKE: "Equipment Jam",
            PATTERN_GRADUAL_INCREASE: "Tool Wear",
            PATTERN_HIGH_VARIABILITY: "Process Instability",
            PATTERN_GRADUAL_DECREASE: "Process Optimization",
        }
        return pattern_to_downtime.get(pattern, "Scheduled Downtime")

    def create_day_of_week_heatmap(
        self, save_path: Optional[str] = None
    ) -> pd.DataFrame:
        """Create day-of-week heatmap for issue rates.

        Args:
            save_path: Optional path to save the heatmap image.

        Returns:
            Pivot table DataFrame of issue rates.
        """
        return create_day_of_week_heatmap(self.df, save_path)

    def create_downtime_classification_summary(self) -> pd.DataFrame:
        """Create summary of downtime classifications.

        Returns:
            Summary DataFrame sorted by Issue_Rate descending.
        """
        return create_downtime_classification_summary(self.df)

    def build_prediction_model(
        self, save_model: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Build predictive model for high-risk shifts/tools.

        Args:
            save_model: Whether to persist the model to disk.

        Returns:
            Model data dictionary or None if insufficient data.
        """
        return build_prediction_model(self.df, save_model)

    def predict_risk(
        self, model_data: Optional[Dict[str, Any]], new_data: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:
        """Predict risk for new data.

        Args:
            model_data: Dictionary returned by build_prediction_model.
            new_data: DataFrame with required feature columns.

        Returns:
            Dictionary with risk_probability and high_risk_prediction.
        """
        return predict_risk(model_data, new_data)

    def generate_real_time_alerts(
        self, threshold: float = DEFAULT_ALERT_THRESHOLD
    ) -> List[Dict[str, Any]]:
        """Generate real-time alerts based on current risk scores.

        Args:
            threshold: Risk score threshold for generating alerts.

        Returns:
            List of alert dictionaries.
        """
        logger.info("Generating real-time alerts...")

        recent_cutoff = datetime.now() - timedelta(hours=ALERT_LOOKBACK_HOURS)
        recent_data = self.df[self.df["LOCAL_SHOT_TIME"] > recent_cutoff].copy()

        if len(recent_data) == 0:
            logger.warning("No recent data available for alerts")
            return []

        high_risk = recent_data[recent_data["RISK_SCORE"] > threshold].copy()

        alerts: List[Dict[str, Any]] = []
        for _, row in high_risk.iterrows():
            alert = {
                "timestamp": row["LOCAL_SHOT_TIME"],
                "equipment": row["EQUIPMENT_CODE"],
                "part": row["PART_NAME"],
                "risk_score": row["RISK_SCORE"],
                "ct_pattern": row["CT_PATTERN"],
                "downtime_type": row["DOWNTIME_TYPE"],
                "severity": (
                    "High" if row["RISK_SCORE"] > HIGH_SEVERITY_THRESHOLD else "Medium"
                ),
                "message": "High risk detected on %s - %s pattern"
                % (row["EQUIPMENT_CODE"], row["CT_PATTERN"]),
            }
            alerts.append(alert)

        logger.info("Generated %d alerts", len(alerts))

        return alerts

    def run_complete_advanced_analysis(
        self, save_outputs: bool = True
    ) -> Dict[str, Any]:
        """Run complete advanced analysis pipeline.

        Args:
            save_outputs: Whether to save output files to disk.

        Returns:
            Dictionary with heatmap_data, downtime_summary, model_data, and alerts.
        """
        logger.info("Starting Advanced Analysis")

        if save_outputs:
            from analysis.shared import get_output_dir

            output_dir = get_output_dir("rca")
            os.chdir(str(output_dir.parent.parent))

        heatmap_path = (
            "advanced_analysis_outputs/day_of_week_heatmap.png"
            if save_outputs
            else None
        )
        heatmap_data = self.create_day_of_week_heatmap(heatmap_path)

        downtime_summary = self.create_downtime_classification_summary()

        model_data = self.build_prediction_model(save_model=save_outputs)

        alerts = self.generate_real_time_alerts()

        if save_outputs:
            self._save_advanced_analysis_report(
                heatmap_data, downtime_summary, model_data, alerts
            )

        logger.info("Advanced analysis complete")

        return {
            "heatmap_data": heatmap_data,
            "downtime_summary": downtime_summary,
            "model_data": model_data,
            "alerts": alerts,
        }

    def _save_advanced_analysis_report(
        self,
        heatmap_data: Optional[pd.DataFrame],
        downtime_summary: Optional[pd.DataFrame],
        model_data: Optional[Dict[str, Any]],
        alerts: List[Dict[str, Any]],
    ) -> None:
        """Save advanced analysis report to JSON.

        Args:
            heatmap_data: Pivot table from heatmap generation.
            downtime_summary: Summary DataFrame from downtime classification.
            model_data: Model training results dictionary.
            alerts: List of alert dictionaries.
        """
        report = {
            "analysis_date": datetime.now().isoformat(),
            "heatmap_data": (
                heatmap_data.to_dict() if heatmap_data is not None else None
            ),
            "downtime_summary": (
                downtime_summary.to_dict() if downtime_summary is not None else None
            ),
            "model_performance": {
                "risk_threshold": model_data["risk_threshold"] if model_data else None,
                "feature_importance": (
                    model_data["feature_importance"].to_dict() if model_data else None
                ),
            },
            "alerts": alerts,
            "summary_stats": {
                "total_shots": len(self.df),
                "high_risk_shots": int(
                    (self.df["RISK_SCORE"] > DEFAULT_ALERT_THRESHOLD).sum()
                ),
                "downtime_events": self.df["DOWNTIME_TYPE"].value_counts().to_dict(),
            },
        }

        report_path = "advanced_analysis_outputs/advanced_analysis_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info("Advanced analysis report saved to %s", report_path)


def main() -> None:
    """Entry point for standalone testing of the advanced analysis module."""
    logger.info("Advanced Analysis Module")
    logger.info("This module provides advanced features for root cause analysis.")
    logger.info("Use it with processed data from the main pipeline.")


if __name__ == "__main__":
    main()
