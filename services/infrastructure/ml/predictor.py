"""
Predictive Models Module.

Features:
- Tooling End-of-Life prediction (enhanced)
- Quality prediction
- Failure prediction
- Performance degradation detection

Author: Utku Gulbardak
Date: 2025-11-12
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# Generic predictor defaults. A target with at most this many distinct values (or
# a non-numeric target) is treated as classification, otherwise regression.
RF_ESTIMATORS = 100
RF_RANDOM_STATE = 42
CLASSIFICATION_MAX_CLASSES = 10


class Predictor:
    """
    Predictive Models for Manufacturing.

    Predicts equipment failures, quality issues, and EOL.
    """

    def __init__(self):
        """Initialize Predictor."""
        self.models = {}
        self.scalers = {}
        logger.info("✅ Predictor initialized")

    def predict(
        self, df: pd.DataFrame, target: str, features: List[str]
    ) -> Dict[str, Any]:
        """
        Train a Random Forest on the provided rows and return in-sample predictions.

        General-purpose supervised predictor backing POST /ml/predict: uses a
        classifier for categorical/low-cardinality targets and a regressor
        otherwise. Predictions are in-sample (fit and scored on the same rows),
        intended for quick what-if analysis, not a persisted production model.

        Args:
            df: Rows containing the target and feature columns.
            target: Column to predict.
            features: Numeric feature columns to train on.

        Returns:
            Dict with predictions, confidence, optional probabilities, model_info.
        """
        if target not in df.columns:
            raise ValueError("Target column '%s' not found in data" % target)
        feature_frame = df[features].apply(pd.to_numeric, errors="coerce")
        if feature_frame.isnull().any().any():
            raise ValueError("Feature columns must be numeric and non-null")

        y = df[target]
        # Continuous (float) targets are always regression; only non-numeric or
        # low-cardinality integer targets are treated as classification.
        is_classification = not pd.api.types.is_numeric_dtype(y) or (
            pd.api.types.is_integer_dtype(y)
            and y.nunique() <= CLASSIFICATION_MAX_CLASSES
        )
        model_cls = (
            RandomForestClassifier if is_classification else RandomForestRegressor
        )
        model = model_cls(n_estimators=RF_ESTIMATORS, random_state=RF_RANDOM_STATE)
        model.fit(feature_frame, y)

        result: Dict[str, Any] = {
            "predictions": model.predict(feature_frame).tolist(),
            "confidence": round(float(model.score(feature_frame, y)), 4),
            "model_info": {
                "model_type": type(model).__name__,
                "task": "classification" if is_classification else "regression",
                "n_estimators": RF_ESTIMATORS,
                "n_features": len(features),
                "n_samples": int(len(feature_frame)),
            },
        }
        if is_classification:
            result["probabilities"] = (
                model.predict_proba(feature_frame).max(axis=1).round(4).tolist()
            )
        return result

    def predict_tooling_eol(
        self,
        df: pd.DataFrame,
        current_shots: int,
        target_confidence: float = 0.95,
    ) -> Dict[str, Any]:
        """
        Predict when tooling will reach end-of-life (enhanced).

        Uses historical data to predict remaining shots.

        Args:
            df: Historical shot data (with CT, quality metrics)
            current_shots: Current total shots
            target_confidence: Confidence level for prediction

        Returns:
            dict: EOL prediction
        """
        # Simple EOL prediction based on cycle time degradation
        df_sorted = df.sort_values("SHOT_TIME").copy()

        # Calculate CT increase over time
        df_sorted["shot_index"] = range(len(df_sorted))

        # Fit linear model to CT trend
        X = df_sorted[["shot_index"]].values
        y = df_sorted["CT"].values

        from sklearn.linear_model import LinearRegression

        model = LinearRegression()
        model.fit(X, y)

        ct_increase_per_shot = model.coef_[0]

        # Predict when CT will exceed threshold (e.g., 1.2x baseline)
        baseline_ct = df_sorted["CT"].iloc[:100].mean()  # First 100 shots
        ct_threshold = baseline_ct * 1.2

        if ct_increase_per_shot > 0:
            current_ct = model.predict([[current_shots]])[0]
            shots_until_threshold = (ct_threshold - current_ct) / ct_increase_per_shot
            predicted_eol_shots = current_shots + max(0, shots_until_threshold)
        else:
            # CT not increasing, use historical EOL if available
            predicted_eol_shots = current_shots + 100000  # Default 100k more shots

        return {
            "current_shots": current_shots,
            "predicted_eol_shots": int(predicted_eol_shots),
            "remaining_shots": int(predicted_eol_shots - current_shots),
            "confidence": target_confidence,
            "ct_increase_per_shot": float(ct_increase_per_shot),
            "baseline_ct": float(baseline_ct),
            "ct_threshold": float(ct_threshold),
            "method": "ct_degradation_model",
        }

    def predict_quality_issues(
        self,
        df: pd.DataFrame,
        features: List[str],
        quality_col: str = "QUALITY_OK",
        train: bool = True,
        model_name: str = "quality_predictor",
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Predict quality issues based on process parameters.

        Args:
            df: Process data with quality labels
            features: Feature columns (CT, temperature, pressure, etc.)
            quality_col: Quality label column (1=OK, 0=defect)
            train: Whether to train new model or use cached
            model_name: Model name for caching

        Returns:
            tuple: (DataFrame with predictions, statistics)
        """
        df_clean = df[features + [quality_col]].dropna().copy()

        X = df_clean[features].values
        y = df_clean[quality_col].values

        if train:
            # Train Random Forest classifier
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            model = RandomForestClassifier(
                n_estimators=100, random_state=42, max_depth=10
            )
            model.fit(X_scaled, y)

            # Cache model
            self.models[model_name] = model
            self.scalers[model_name] = scaler

            logger.info(f"✅ Trained quality prediction model: {model_name}")
        else:
            if model_name not in self.models:
                raise ValueError(f"Model '{model_name}' not found. Train model first.")

            model = self.models[model_name]
            scaler = self.scalers[model_name]
            X_scaled = scaler.transform(X)

        # Predict
        predictions = model.predict(X_scaled)
        probabilities = model.predict_proba(X_scaled)[:, 1]  # Probability of quality OK

        df_result = df_clean.copy()
        df_result["quality_prediction"] = predictions
        df_result["quality_probability"] = probabilities
        df_result["defect_risk"] = 1 - probabilities

        # Feature importance
        feature_importance = dict(zip(features, model.feature_importances_))

        defect_count = int((predictions == 0).sum())

        return df_result, {
            "model": model_name,
            "predicted_defects": defect_count,
            "defect_rate": round(defect_count / len(df_result) * 100, 2),
            "features_used": features,
            "feature_importance": {
                k: float(v)
                for k, v in sorted(
                    feature_importance.items(), key=lambda x: x[1], reverse=True
                )
            },
            "accuracy": float(model.score(X_scaled, y)) if train else None,
        }

    def predict_failure_probability(
        self,
        df: pd.DataFrame,
        features: List[str],
        lookback_window: int = 100,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Predict probability of equipment failure.

        Uses recent performance metrics to assess failure risk.

        Args:
            df: Equipment performance data
            features: Feature columns
            lookback_window: Number of recent records to consider

        Returns:
            tuple: (DataFrame with failure predictions, statistics)
        """
        # Take recent data
        df_recent = df.tail(lookback_window).copy()

        # Calculate degradation indicators
        for feature in features:
            if pd.api.types.is_numeric_dtype(df_recent[feature]):
                # Calculate trend (increasing or decreasing)
                df_recent[f"{feature}_trend"] = (
                    df_recent[feature].rolling(window=10).mean()
                )

        # Simple failure probability based on CT increase
        if "CT" in features:
            baseline_ct = df["CT"].head(100).mean()
            current_ct = df_recent["CT"].mean()
            ct_increase = (current_ct - baseline_ct) / baseline_ct

            # Failure probability increases with CT increase
            failure_probability = min(1.0, max(0.0, ct_increase * 5))  # Scale to 0-1
        else:
            failure_probability = 0.1  # Default low risk

        risk_level = (
            "high"
            if failure_probability > 0.7
            else "medium" if failure_probability > 0.3 else "low"
        )

        return df_recent, {
            "failure_probability": float(failure_probability),
            "risk_level": risk_level,
            "lookback_window": lookback_window,
            "features_analyzed": features,
            "recommendation": (
                "Schedule maintenance"
                if failure_probability > 0.7
                else (
                    "Monitor closely"
                    if failure_probability > 0.3
                    else "Normal operation"
                )
            ),
        }

    def predict_performance_degradation(
        self, df: pd.DataFrame, metric_col: str, baseline_window: int = 100
    ) -> Dict[str, Any]:
        """
        Detect performance degradation over time.

        Args:
            df: Historical performance data
            metric_col: Performance metric column (e.g., OEE, efficiency)
            baseline_window: Number of records for baseline

        Returns:
            dict: Degradation analysis
        """
        df_sorted = df.sort_values(
            "SHOT_TIME" if "SHOT_TIME" in df.columns else df.columns[0]
        ).copy()

        # Calculate baseline performance
        baseline_perf = df_sorted[metric_col].head(baseline_window).mean()

        # Calculate recent performance
        recent_perf = df_sorted[metric_col].tail(baseline_window).mean()

        # Calculate degradation
        degradation_pct = (
            ((baseline_perf - recent_perf) / baseline_perf * 100)
            if baseline_perf > 0
            else 0
        )

        degradation_status = (
            "severe"
            if degradation_pct > 20
            else (
                "moderate"
                if degradation_pct > 10
                else "minor" if degradation_pct > 5 else "none"
            )
        )

        return {
            "baseline_performance": float(baseline_perf),
            "recent_performance": float(recent_perf),
            "degradation_percentage": float(degradation_pct),
            "degradation_status": degradation_status,
            "metric": metric_col,
            "baseline_window": baseline_window,
            "recommendation": (
                "Investigate and address issues"
                if degradation_pct > 10
                else (
                    "Continue monitoring" if degradation_pct > 5 else "No action needed"
                )
            ),
        }

    def predict_optimal_maintenance_timing(
        self,
        current_shots: int,
        eol_prediction: Dict[str, Any],
        maintenance_cost: float = 1000,
        failure_cost: float = 10000,
    ) -> Dict[str, Any]:
        """
        Predict optimal maintenance timing to minimize costs.

        Args:
            current_shots: Current shot count
            eol_prediction: EOL prediction from predict_tooling_eol()
            maintenance_cost: Cost of planned maintenance
            failure_cost: Cost of unplanned failure

        Returns:
            dict: Optimal maintenance timing
        """
        predicted_eol = eol_prediction["predicted_eol_shots"]
        remaining_shots = predicted_eol - current_shots

        # Optimal timing: Maintain before 90% of EOL to avoid failure
        optimal_shots = current_shots + int(remaining_shots * 0.9)

        # Calculate expected cost
        failure_probability = 0.1  # 10% chance of premature failure
        expected_cost = maintenance_cost + failure_probability * failure_cost

        return {
            "current_shots": current_shots,
            "optimal_maintenance_at_shots": optimal_shots,
            "shots_until_maintenance": optimal_shots - current_shots,
            "predicted_eol_shots": predicted_eol,
            "expected_cost": float(expected_cost),
            "maintenance_cost": maintenance_cost,
            "failure_cost": failure_cost,
            "recommendation": f"Schedule maintenance at {optimal_shots:,} shots",
        }


# Global predictor instance
_predictor: Optional[Predictor] = None


def get_predictor() -> Predictor:
    """
    Get global predictor instance.

    Returns:
        Predictor: Global predictor instance
    """
    global _predictor
    if _predictor is None:
        _predictor = Predictor()
    return _predictor
