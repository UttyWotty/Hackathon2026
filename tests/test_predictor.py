"""Unit tests for the generic Predictor.predict backing POST /ml/predict.

Covers the regression path for a continuous target and the classification path
for a low-cardinality integer target, plus input-validation errors, so the
endpoint's dispatch cannot regress to the AttributeError it shipped with.
"""

import pandas as pd
import pytest  # type: ignore[import-untyped]

from services.infrastructure.ml.predictor import Predictor


def _predictor() -> Predictor:
    return Predictor()


def test_continuous_target_uses_regression() -> None:
    df = pd.DataFrame(
        {
            "temperature": [180, 181, 182, 183, 184, 185],
            "ct": [10.0, 10.1, 10.2, 10.3, 10.4, 10.5],
        }
    )
    result = _predictor().predict(df, target="ct", features=["temperature"])
    assert result["model_info"]["model_type"] == "RandomForestRegressor"
    assert result["model_info"]["task"] == "regression"
    assert len(result["predictions"]) == len(df)
    assert 0.0 <= result["confidence"] <= 1.0
    assert "probabilities" not in result


def test_low_cardinality_integer_target_uses_classification() -> None:
    df = pd.DataFrame(
        {"temperature": [180, 220, 181, 221, 182, 222], "faulty": [0, 1, 0, 1, 0, 1]}
    )
    result = _predictor().predict(df, target="faulty", features=["temperature"])
    assert result["model_info"]["model_type"] == "RandomForestClassifier"
    assert result["model_info"]["task"] == "classification"
    assert len(result["probabilities"]) == len(df)


def test_missing_target_raises_value_error() -> None:
    df = pd.DataFrame({"temperature": [180, 181]})
    with pytest.raises(ValueError):
        _predictor().predict(df, target="ct", features=["temperature"])


def test_non_numeric_feature_raises_value_error() -> None:
    df = pd.DataFrame({"machine": ["a", "b", "c"], "ct": [10.0, 10.1, 10.2]})
    with pytest.raises(ValueError):
        _predictor().predict(df, target="ct", features=["machine"])
