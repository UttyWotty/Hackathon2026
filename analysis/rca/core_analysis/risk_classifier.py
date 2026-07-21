"""
Risk classification and predictive modeling for manufacturing root cause analysis.
Provides ML-based risk prediction using RandomForest on CT pattern features,
along with composite risk scoring from pattern, deviation, time, and day factors.
This module is extracted from advanced_analysis.py for single-responsibility compliance.
"""

import logging
from typing import Any, Dict, List, Optional

import joblib  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
from sklearn.ensemble import RandomForestClassifier  # type: ignore[import-untyped]
from sklearn.metrics import classification_report  # type: ignore[import-untyped]
from sklearn.model_selection import train_test_split  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Pattern classification constants
PATTERN_SUDDEN_SPIKE = "Sudden Spike"
PATTERN_GRADUAL_INCREASE = "Gradual Increase"
PATTERN_GRADUAL_DECREASE = "Gradual Decrease"
PATTERN_HIGH_VARIABILITY = "High Variability"
PATTERN_NORMAL = "Normal"

# Risk scoring thresholds
DEVIATION_HIGH_THRESHOLD = 50
DEVIATION_MEDIUM_THRESHOLD = 25
DEVIATION_LOW_THRESHOLD = 10

NIGHT_SHIFT_HOURS = [0, 1, 2, 3, 4, 5]
HIGH_RISK_DAYS = ["Sunday", "Friday"]

# Model training constants
MIN_SAMPLES_FOR_TRAINING = 100
RISK_QUANTILE_THRESHOLD = 0.8
TEST_SIZE_FRACTION = 0.2
RANDOM_STATE = 42
N_ESTIMATORS = 100
MIN_SAMPLES_LEAF = 1
MAX_FEATURES = "sqrt"

# Model persistence paths
DEFAULT_MODEL_PATH = "prediction_model.pkl"
DEFAULT_SCALER_PATH = "feature_scaler.pkl"

# Feature columns used for model training
NUMERIC_FEATURE_COLUMNS = [
    "HOUR",
    "MONTH",
    "WEEK_OF_YEAR",
    "CT_DEVIATION_PCT",
    "OUTLIER_SCORE",
    "RISK_SCORE",
]

CATEGORICAL_FEATURE_COLUMNS = [
    "DAY_OF_WEEK",
    "SHIFT",
    "CT_PATTERN",
    "DOWNTIME_TYPE",
]


def get_pattern_risk_score(pattern: str) -> float:
    """Get base risk score from CT pattern.

    Args:
        pattern: The classified CT pattern string.

    Returns:
        A float risk score between 0.0 and 0.4.
    """
    pattern_scores = {
        PATTERN_SUDDEN_SPIKE: 0.4,
        PATTERN_HIGH_VARIABILITY: 0.3,
        PATTERN_GRADUAL_INCREASE: 0.2,
        PATTERN_GRADUAL_DECREASE: 0.1,
    }
    return pattern_scores.get(pattern, 0.0)


def get_deviation_risk_score(deviation: float) -> float:
    """Get risk score from CT deviation percentage.

    Args:
        deviation: Absolute CT deviation percentage value.

    Returns:
        A float risk score between 0.0 and 0.3.
    """
    if deviation > DEVIATION_HIGH_THRESHOLD:
        return 0.3
    elif deviation > DEVIATION_MEDIUM_THRESHOLD:
        return 0.2
    elif deviation > DEVIATION_LOW_THRESHOLD:
        return 0.1
    return 0.0


def get_time_risk_score(hour: int) -> float:
    """Get risk score from hour of day (night shift has higher risk).

    Args:
        hour: Hour of day (0-23).

    Returns:
        A float risk score of 0.0 or 0.1.
    """
    if hour in NIGHT_SHIFT_HOURS:
        return 0.1
    return 0.0


def get_day_risk_score(day: str) -> float:
    """Get risk score from day of week.

    Args:
        day: Day name string (e.g. "Monday").

    Returns:
        A float risk score of 0.0 or 0.1.
    """
    if day in HIGH_RISK_DAYS:
        return 0.1
    return 0.0


def calculate_risk_scores(data: pd.DataFrame) -> List[float]:
    """Calculate composite risk score based on multiple factors.

    Combines pattern risk, deviation risk, time risk, and day risk
    into a single score capped at 1.0.

    Args:
        data: DataFrame with CT_PATTERN, HOUR, DAY_OF_WEEK columns
              and optionally CT_DEVIATION_PCT.

    Returns:
        List of float risk scores, one per row.
    """
    risk_scores: List[float] = []

    for i in range(len(data)):
        score = 0.0

        pattern = data["CT_PATTERN"].iloc[i]
        score += get_pattern_risk_score(pattern)

        if "CT_DEVIATION_PCT" in data.columns:
            deviation = abs(data["CT_DEVIATION_PCT"].iloc[i])
            score += get_deviation_risk_score(deviation)

        hour = data["HOUR"].iloc[i]
        score += get_time_risk_score(hour)

        day = data["DAY_OF_WEEK"].iloc[i]
        score += get_day_risk_score(day)

        risk_scores.append(min(score, 1.0))

    return risk_scores


def _prepare_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Build the feature matrix with numeric and one-hot encoded categorical columns.

    Args:
        df: Source DataFrame containing all feature columns.

    Returns:
        Feature matrix DataFrame ready for model training.
    """
    x = df[NUMERIC_FEATURE_COLUMNS].copy()

    for col in CATEGORICAL_FEATURE_COLUMNS:
        if col in df.columns:
            dummies = pd.get_dummies(df[col], prefix=col, drop_first=True)
            x = pd.concat([x, dummies], axis=1)

    return x


def build_prediction_model(
    df: pd.DataFrame, save_model: bool = True
) -> Optional[Dict[str, Any]]:
    """Build predictive model for high-risk shifts/tools.

    Trains a RandomForest classifier on CT pattern features to predict
    high-risk situations (top 20% risk score quantile).

    Args:
        df: DataFrame with all required feature columns.
        save_model: Whether to persist the model and scaler to disk.

    Returns:
        Dictionary with model, scaler, feature_importance, X_columns,
        and risk_threshold. Returns None if insufficient data.
    """
    logger.info("Building predictive model...")

    x = _prepare_feature_matrix(df)

    risk_threshold = df["RISK_SCORE"].quantile(RISK_QUANTILE_THRESHOLD)
    y = (df["RISK_SCORE"] > risk_threshold).astype(int)

    valid_mask = x.notna().all(axis=1) & y.notna()
    x = x[valid_mask]
    y = y[valid_mask]

    if len(x) < MIN_SAMPLES_FOR_TRAINING:
        logger.warning(
            "Insufficient data for prediction model: %d samples (need %d)",
            len(x),
            MIN_SAMPLES_FOR_TRAINING,
        )
        return None

    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=TEST_SIZE_FRACTION, random_state=RANDOM_STATE, stratify=y
    )

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_test_scaled = scaler.transform(x_test)

    model = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        min_samples_leaf=MIN_SAMPLES_LEAF,
        max_features=MAX_FEATURES,
        random_state=RANDOM_STATE,
    )
    model.fit(x_train_scaled, y_train)

    y_pred = model.predict(x_test_scaled)

    logger.info("Model performance report:\n%s", classification_report(y_test, y_pred))

    feature_importance = pd.DataFrame(
        {"feature": x.columns, "importance": model.feature_importances_}
    ).sort_values("importance", ascending=False)

    _log_top_features(feature_importance)

    if save_model:
        _persist_model(model, scaler)

    return {
        "model": model,
        "scaler": scaler,
        "feature_importance": feature_importance,
        "X_columns": x.columns.tolist(),
        "risk_threshold": risk_threshold,
    }


def _log_top_features(feature_importance: pd.DataFrame, top_n: int = 10) -> None:
    """Log the top N most important features.

    Args:
        feature_importance: DataFrame with feature and importance columns.
        top_n: Number of top features to log.
    """
    logger.info("Top %d most important features:", top_n)
    for _, row in feature_importance.head(top_n).iterrows():
        logger.info("  %s: %.3f", row["feature"], row["importance"])


def _persist_model(model: RandomForestClassifier, scaler: StandardScaler) -> None:
    """Save model and scaler to disk.

    Args:
        model: Trained RandomForest model.
        scaler: Fitted StandardScaler.
    """
    joblib.dump(model, DEFAULT_MODEL_PATH)
    joblib.dump(scaler, DEFAULT_SCALER_PATH)
    logger.info("Model saved to: %s", DEFAULT_MODEL_PATH)
    logger.info("Scaler saved to: %s", DEFAULT_SCALER_PATH)


def predict_risk(
    model_data: Dict[str, Any], new_data: pd.DataFrame
) -> Optional[Dict[str, Any]]:
    """Predict risk for new data using a trained model.

    Args:
        model_data: Dictionary returned by build_prediction_model.
        new_data: DataFrame with the same feature columns used during training.

    Returns:
        Dictionary with risk_probability and high_risk_prediction arrays.
        Returns None if model_data is None.
    """
    if model_data is None:
        logger.error("No trained model available for prediction")
        return None

    x_new = new_data[model_data["X_columns"]].copy()
    x_new_scaled = model_data["scaler"].transform(x_new)

    risk_prob = model_data["model"].predict_proba(x_new_scaled)[:, 1]
    risk_pred = model_data["model"].predict(x_new_scaled)

    return {"risk_probability": risk_prob, "high_risk_prediction": risk_pred}
