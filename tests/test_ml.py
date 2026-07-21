"""
Test ML functionality.
"""


def test_ml_anomaly_detection_endpoint(client):
    """Test anomaly detection endpoint accepts valid data."""
    request_data = {
        "data": [
            {"value": 100},
            {"value": 102},
            {"value": 98},
            {"value": 101},
            {"value": 200},  # Anomaly
        ],
        "columns": ["value"],
        "method": "zscore",
        "threshold": 3.0,
    }

    response = client.post("/ml/detect-anomalies", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "anomalies_found" in data
    assert data["method"] == "zscore"


def test_ml_forecast_endpoint_structure(client):
    """Test forecast endpoint accepts valid data structure."""
    import pandas as pd  # type: ignore[import-untyped]

    # Generate simple time series
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    request_data = {
        "data": [
            {"timestamp": str(d.date()), "value": i * 10 + 100}
            for i, d in enumerate(dates)
        ],
        "target_column": "value",
        "periods": 7,
        "frequency": "D",
    }

    response = client.post("/ml/forecast", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "forecast" in data


def test_ml_health_check(client):
    """Test ML service health check."""
    response = client.get("/ml/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "models" in data
