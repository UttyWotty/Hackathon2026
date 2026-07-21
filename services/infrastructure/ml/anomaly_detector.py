"""
Anomaly Detection Module.

Features:
- Statistical anomaly detection (Z-score, IQR)
- Isolation Forest (unsupervised ML)
- Time series anomaly detection
- Multi-variate anomaly detection
- Anomaly scoring and ranking

Author: Utku Gulbardak
Date: 2025-11-12
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """
    Anomaly Detection for Manufacturing Data.

    Detects unusual patterns in cycle times, production metrics, etc.
    """

    def __init__(self):
        """Initialize Anomaly Detector."""
        self.models = {}
        self.scalers = {}
        logger.info("✅ Anomaly Detector initialized")

    def detect_statistical_anomalies(
        self,
        df: pd.DataFrame,
        columns: List[str],
        method: str = "zscore",
        threshold: float = 3.0,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Detect anomalies using statistical methods.

        Args:
            df: Input DataFrame
            columns: Columns to check for anomalies
            method: 'zscore' or 'iqr'
            threshold: Z-score threshold (default 3) or IQR multiplier (default 1.5)

        Returns:
            tuple: (DataFrame with anomaly flags, statistics)
        """
        df_result = df.copy()
        anomaly_stats = {}

        for col in columns:
            if col not in df.columns:
                logger.warning(f"Column '{col}' not found, skipping")
                continue

            if not pd.api.types.is_numeric_dtype(df[col]):
                logger.warning(f"Column '{col}' is not numeric, skipping")
                continue

            if method == "zscore":
                mean = df[col].mean()
                std = df[col].std()

                if std == 0:
                    anomalies = pd.Series([False] * len(df), index=df.index)
                else:
                    z_scores = np.abs((df[col] - mean) / std)
                    anomalies = z_scores > threshold

                anomaly_stats[col] = {
                    "method": "zscore",
                    "anomaly_count": int(anomalies.sum()),
                    "anomaly_percentage": round(anomalies.sum() / len(df) * 100, 2),
                    "mean": float(mean),
                    "std": float(std),
                    "threshold": threshold,
                }

            elif method == "iqr":
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - threshold * IQR
                upper_bound = Q3 + threshold * IQR

                anomalies = (df[col] < lower_bound) | (df[col] > upper_bound)

                anomaly_stats[col] = {
                    "method": "iqr",
                    "anomaly_count": int(anomalies.sum()),
                    "anomaly_percentage": round(anomalies.sum() / len(df) * 100, 2),
                    "lower_bound": float(lower_bound),
                    "upper_bound": float(upper_bound),
                    "Q1": float(Q1),
                    "Q3": float(Q3),
                    "IQR": float(IQR),
                }

            else:
                raise ValueError(f"Unknown method: {method}")

            df_result[f"{col}_anomaly"] = anomalies
            df_result[f"{col}_anomaly_score"] = (
                np.abs((df[col] - df[col].mean()) / df[col].std())
                if df[col].std() > 0
                else 0
            )

        total_anomalies = sum(
            stats["anomaly_count"] for stats in anomaly_stats.values()
        )

        return df_result, {
            "total_anomalies": total_anomalies,
            "columns_checked": len(columns),
            "anomaly_details": anomaly_stats,
        }

    def detect_ml_anomalies(
        self,
        df: pd.DataFrame,
        features: List[str],
        contamination: float = 0.1,
        model_name: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Detect anomalies using Isolation Forest (ML).

        Args:
            df: Input DataFrame
            features: Feature columns for anomaly detection
            contamination: Expected proportion of anomalies (0.1 = 10%)
            model_name: Optional name to cache model

        Returns:
            tuple: (DataFrame with anomaly predictions, statistics)
        """
        # Prepare features
        X = df[features].copy()

        # Handle missing values
        X = X.fillna(X.mean())

        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Train Isolation Forest
        model = IsolationForest(
            contamination=contamination, random_state=42, n_estimators=100
        )
        predictions = model.fit_predict(X_scaled)

        # Get anomaly scores (lower = more anomalous)
        anomaly_scores = model.score_samples(X_scaled)

        # Convert predictions (-1 = anomaly, 1 = normal) to boolean
        is_anomaly = predictions == -1

        # Add results to dataframe
        df_result = df.copy()
        df_result["ml_anomaly"] = is_anomaly
        df_result["ml_anomaly_score"] = (
            -anomaly_scores
        )  # Negate so higher = more anomalous

        # Cache model if name provided
        if model_name:
            self.models[model_name] = model
            self.scalers[model_name] = scaler
            logger.info(f"✅ Cached Isolation Forest model: {model_name}")

        anomaly_count = int(is_anomaly.sum())

        return df_result, {
            "model": "isolation_forest",
            "anomaly_count": anomaly_count,
            "anomaly_percentage": round(anomaly_count / len(df) * 100, 2),
            "contamination": contamination,
            "features_used": features,
            "model_cached": model_name is not None,
        }

    def predict_anomalies(
        self, df: pd.DataFrame, features: List[str], model_name: str
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Predict anomalies using cached model.

        Args:
            df: Input DataFrame
            features: Feature columns
            model_name: Name of cached model

        Returns:
            tuple: (DataFrame with predictions, statistics)
        """
        if model_name not in self.models:
            raise ValueError(
                f"Model '{model_name}' not found. Train model first using detect_ml_anomalies()."
            )

        model = self.models[model_name]
        scaler = self.scalers[model_name]

        # Prepare features
        X = df[features].copy()
        X = X.fillna(X.mean())
        X_scaled = scaler.transform(X)

        # Predict
        predictions = model.predict(X_scaled)
        anomaly_scores = model.score_samples(X_scaled)

        is_anomaly = predictions == -1

        df_result = df.copy()
        df_result["ml_anomaly"] = is_anomaly
        df_result["ml_anomaly_score"] = -anomaly_scores

        anomaly_count = int(is_anomaly.sum())

        return df_result, {
            "model": model_name,
            "anomaly_count": anomaly_count,
            "anomaly_percentage": round(anomaly_count / len(df) * 100, 2),
            "features_used": features,
        }

    def detect_time_series_anomalies(
        self,
        df: pd.DataFrame,
        time_col: str,
        value_col: str,
        window: int = 10,
        threshold: float = 3.0,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Detect anomalies in time series data.

        Uses rolling statistics to detect sudden changes.

        Args:
            df: Input DataFrame
            time_col: Time column name
            value_col: Value column name
            window: Rolling window size
            threshold: Standard deviation threshold

        Returns:
            tuple: (DataFrame with anomaly flags, statistics)
        """
        df_sorted = df.sort_values(time_col).copy()

        # Calculate rolling mean and std
        rolling_mean = df_sorted[value_col].rolling(window=window, center=True).mean()
        rolling_std = df_sorted[value_col].rolling(window=window, center=True).std()

        # Detect anomalies (values outside mean ± threshold * std)
        upper_bound = rolling_mean + threshold * rolling_std
        lower_bound = rolling_mean - threshold * rolling_std

        anomalies = (df_sorted[value_col] > upper_bound) | (
            df_sorted[value_col] < lower_bound
        )

        df_sorted["ts_anomaly"] = anomalies
        df_sorted["rolling_mean"] = rolling_mean
        df_sorted["upper_bound"] = upper_bound
        df_sorted["lower_bound"] = lower_bound

        anomaly_count = int(anomalies.sum())

        return df_sorted, {
            "anomaly_count": anomaly_count,
            "anomaly_percentage": round(anomaly_count / len(df) * 100, 2),
            "window": window,
            "threshold": threshold,
            "time_column": time_col,
            "value_column": value_col,
        }

    def get_top_anomalies(
        self, df: pd.DataFrame, score_col: str = "ml_anomaly_score", top_n: int = 10
    ) -> pd.DataFrame:
        """
        Get top N most anomalous records.

        Args:
            df: DataFrame with anomaly scores
            score_col: Anomaly score column name
            top_n: Number of top anomalies to return

        Returns:
            DataFrame: Top N anomalies
        """
        if score_col not in df.columns:
            raise ValueError(f"Score column '{score_col}' not found in DataFrame")

        return df.nlargest(top_n, score_col)

    def list_cached_models(self) -> List[str]:
        """Get list of cached model names."""
        return list(self.models.keys())

    def remove_cached_model(self, model_name: str) -> bool:
        """
        Remove cached model.

        Args:
            model_name: Name of model to remove

        Returns:
            bool: Success status
        """
        if model_name in self.models:
            del self.models[model_name]
            del self.scalers[model_name]
            logger.info(f"🗑️  Removed cached model: {model_name}")
            return True
        return False


# Global anomaly detector instance
_anomaly_detector: Optional[AnomalyDetector] = None


def get_anomaly_detector() -> AnomalyDetector:
    """
    Get global anomaly detector instance.

    Returns:
        AnomalyDetector: Global detector instance
    """
    global _anomaly_detector
    if _anomaly_detector is None:
        _anomaly_detector = AnomalyDetector()
    return _anomaly_detector
