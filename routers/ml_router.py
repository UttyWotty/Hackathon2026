"""
ML Router - AI-Powered Manufacturing Insights

Provides machine learning capabilities:
- Anomaly detection (cycle times, defects, metrics)
- Production forecasting
- Predictive maintenance
- Pattern recognition

Uses: services/infrastructure/ml/
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator

from services.infrastructure.ml.anomaly_detector import AnomalyDetector
from services.infrastructure.ml.forecaster import Forecaster
from services.infrastructure.ml.predictor import Predictor
from utils.error_handling import sanitize_error_message

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize ML components
detector = AnomalyDetector()
forecaster = Forecaster()
predictor = Predictor()


# Request Models
class AnomalyDetectionRequest(BaseModel):
    data: List[Dict[str, Any]] = Field(..., description="Data to analyze for anomalies")
    columns: List[str] = Field(..., description="Columns to check for anomalies")
    method: str = Field(
        "zscore", description="Detection method: 'zscore', 'iqr', or 'isolation_forest'"
    )
    threshold: float = Field(
        3.0, description="Threshold for statistical methods (default: 3.0)"
    )

    @validator("method")
    def validate_method(cls, v):
        allowed = ["zscore", "iqr", "isolation_forest"]
        if v not in allowed:
            raise ValueError(f"method must be one of: {allowed}")
        return v

    @validator("threshold")
    def validate_threshold(cls, v):
        if v < 0 or v > 100:
            raise ValueError("threshold must be between 0 and 100")
        return v

    @validator("data")
    def validate_data_size(cls, v):
        if len(v) > 100000:
            raise ValueError("Data too large (max 100,000 rows)")
        if len(v) == 0:
            raise ValueError("Data cannot be empty")
        return v

    @validator("columns")
    def validate_columns(cls, v):
        if len(v) == 0:
            raise ValueError("At least one column must be specified")
        if len(v) > 50:
            raise ValueError("Too many columns (max 50)")
        return v


class ForecastRequest(BaseModel):
    data: List[Dict[str, Any]] = Field(
        ..., description="Historical data for forecasting"
    )
    target_column: str = Field(..., description="Column to forecast")
    periods: int = Field(30, description="Number of periods to forecast")
    frequency: str = Field(
        "D", description="Data frequency: 'D' (daily), 'H' (hourly), 'W' (weekly)"
    )

    @validator("periods")
    def validate_periods(cls, v):
        if v < 1 or v > 365:
            raise ValueError("periods must be between 1 and 365")
        return v

    @validator("frequency")
    def validate_frequency(cls, v):
        allowed = ["D", "H", "W", "M"]
        if v not in allowed:
            raise ValueError(f"frequency must be one of: {allowed}")
        return v

    @validator("data")
    def validate_data_size(cls, v):
        if len(v) > 100000:
            raise ValueError("Data too large (max 100,000 rows)")
        if len(v) == 0:
            raise ValueError("Data cannot be empty")
        return v


class PredictionRequest(BaseModel):
    data: List[Dict[str, Any]] = Field(..., description="Input data for prediction")
    target: str = Field(
        ..., description="What to predict (e.g., 'downtime', 'quality')"
    )
    features: List[str] = Field(..., description="Feature columns to use")

    @validator("data")
    def validate_data_size(cls, v):
        if len(v) > 100000:
            raise ValueError("Data too large (max 100,000 rows)")
        if len(v) == 0:
            raise ValueError("Data cannot be empty")
        return v

    @validator("features")
    def validate_features(cls, v):
        if len(v) == 0:
            raise ValueError("At least one feature must be specified")
        if len(v) > 100:
            raise ValueError("Too many features (max 100)")
        return v


@router.get("/", summary="ML Service Info")
async def ml_info():
    """Get information about the ML service and available models."""
    return {
        "service": "ML Service",
        "description": "AI-powered manufacturing insights",
        "capabilities": [
            "Anomaly Detection (cycle times, defects, production metrics)",
            "Time Series Forecasting (production volumes, demand)",
            "Predictive Maintenance (equipment failure prediction)",
            "Pattern Recognition (quality issues, process deviations)",
        ],
        "models": {
            "anomaly_detector": {
                "methods": ["zscore", "iqr", "isolation_forest"],
                "use_cases": [
                    "Detect unusual cycle times",
                    "Find quality issues",
                    "Identify process anomalies",
                ],
            },
            "forecaster": {
                "algorithms": ["ARIMA", "Exponential Smoothing", "Prophet"],
                "use_cases": [
                    "Production planning",
                    "Demand forecasting",
                    "Capacity planning",
                ],
            },
            "predictor": {
                "algorithms": ["Random Forest", "Gradient Boosting", "Neural Network"],
                "use_cases": [
                    "Predict downtime",
                    "Quality prediction",
                    "Maintenance scheduling",
                ],
            },
        },
    }


@router.post("/detect-anomalies", summary="Detect Anomalies")
async def detect_anomalies(request: AnomalyDetectionRequest):
    """
    Detect anomalies in manufacturing data using ML algorithms.

    Supports multiple methods:
    - **zscore**: Statistical method using standard deviations
    - **iqr**: Interquartile range method (robust to outliers)
    - **isolation_forest**: ML-based unsupervised detection

    Returns identified anomalies with scores and statistics.
    """
    start_time = time.time()

    try:
        # Convert to DataFrame
        df = pd.DataFrame(request.data)

        if df.empty:
            raise HTTPException(status_code=400, detail="Input data is empty")

        # Validate columns exist
        missing_cols = [col for col in request.columns if col not in df.columns]
        if missing_cols:
            raise HTTPException(
                status_code=400,
                detail=f"Columns not found in data: {missing_cols}. Available: {list(df.columns)}",
            )

        # Detect anomalies
        result_df, stats = detector.detect_statistical_anomalies(
            df=df,
            columns=request.columns,
            method=request.method,
            threshold=request.threshold,
        )

        # Extract anomalies
        anomalies = (
            result_df[result_df["is_anomaly"]].to_dict("records")
            if "is_anomaly" in result_df.columns
            else []
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "method": request.method,
            "threshold": request.threshold,
            "total_records": len(df),
            "anomalies_found": stats.get("anomaly_count", len(anomalies)),
            "anomaly_percentage": stats.get("anomaly_percentage", 0),
            "statistics": stats,
            "anomalies": anomalies,
            "execution_time_ms": round(execution_time_ms, 2),
            "message": f"Found {len(anomalies)} anomalies using {request.method} method",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Anomaly detection error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Anomaly detection failed. Please check your input data."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/forecast", summary="Forecast Time Series")
async def forecast_production(request: ForecastRequest):
    """
    Forecast future values using time series analysis.

    Perfect for:
    - Production volume forecasting
    - Demand prediction
    - Capacity planning
    - Resource allocation

    Uses ARIMA, Exponential Smoothing, or Prophet based on data characteristics.
    """
    start_time = time.time()

    try:
        # Convert to DataFrame
        df = pd.DataFrame(request.data)

        if df.empty:
            raise HTTPException(status_code=400, detail="Input data is empty")

        if request.target_column not in df.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Target column '{request.target_column}' not found. Available: {list(df.columns)}",
            )

        # Prepare time series data
        if "timestamp" not in df.columns and "date" not in df.columns:
            # Create dummy timestamps if not provided
            df["timestamp"] = pd.date_range(
                start="2025-01-01", periods=len(df), freq=request.frequency
            )

        time_col = "timestamp" if "timestamp" in df.columns else "date"

        # Forecast
        forecast_result = forecaster.forecast_timeseries(
            df=df,
            target_column=request.target_column,
            periods=request.periods,
            time_column=time_col,
            frequency=request.frequency,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "target": request.target_column,
            "periods_forecasted": request.periods,
            "frequency": request.frequency,
            "forecast": forecast_result["forecast"],
            "confidence_intervals": forecast_result.get("confidence_intervals", {}),
            "model_info": forecast_result.get("model_info", {}),
            "execution_time_ms": round(execution_time_ms, 2),
            "message": f"Forecasted {request.periods} periods for {request.target_column}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forecasting error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Forecasting failed. Please check your input data."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/predict", summary="Make Predictions")
async def predict(request: PredictionRequest):
    """
    Make predictions using trained ML models.

    Use cases:
    - Predict equipment downtime
    - Quality prediction
    - Maintenance scheduling
    - Process optimization

    Uses ensemble methods (Random Forest, Gradient Boosting) for robust predictions.
    """
    start_time = time.time()

    try:
        # Convert to DataFrame
        df = pd.DataFrame(request.data)

        if df.empty:
            raise HTTPException(status_code=400, detail="Input data is empty")

        # Validate features exist
        missing_features = [f for f in request.features if f not in df.columns]
        if missing_features:
            raise HTTPException(
                status_code=400,
                detail=f"Features not found: {missing_features}. Available: {list(df.columns)}",
            )

        # Make predictions
        predictions = predictor.predict(
            df=df, target=request.target, features=request.features
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "target": request.target,
            "features_used": request.features,
            "predictions": predictions["predictions"],
            "probabilities": predictions.get("probabilities", []),
            "confidence": predictions.get("confidence", 0),
            "model_info": predictions.get("model_info", {}),
            "execution_time_ms": round(execution_time_ms, 2),
            "message": f"Generated {len(predictions['predictions'])} predictions for {request.target}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Prediction failed. Please check your input data."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/health", summary="ML Service Health Check")
async def health_check():
    """Check if ML service and models are ready."""
    try:
        # Test if models are initialized
        models_status = {
            "anomaly_detector": "ready" if detector else "not_initialized",
            "forecaster": "ready" if forecaster else "not_initialized",
            "predictor": "ready" if predictor else "not_initialized",
        }

        overall_status = (
            "healthy"
            if all(s == "ready" for s in models_status.values())
            else "degraded"
        )

        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "models": models_status,
            "dependencies": {
                "pandas": "available",
                "sklearn": "available",
                "numpy": "available",
            },
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }
