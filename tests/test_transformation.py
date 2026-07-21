"""
Test data transformation functionality.
"""


def test_transformation_clean_endpoint(client):
    """Test data cleaning endpoint."""
    request_data = {
        "data": [
            {"value": 100, "name": "A"},
            {"value": 100, "name": "A"},  # Duplicate
            {"value": 200, "name": "B"},
        ],
        "remove_duplicates": True,
        "handle_nulls": "drop",
    }

    response = client.post("/transformation/clean", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "cleaned_data" in data
    assert data["statistics"]["duplicates_removed"] >= 1


def test_transformation_validate_endpoint(client):
    """Test data validation endpoint."""
    request_data = {
        "data": [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ],
        "required_columns": ["name", "age"],
        "check_nulls": True,
        "check_duplicates": True,
    }

    response = client.post("/transformation/validate", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert "validation" in data
    assert "quality_score" in data["validation"]
    assert data["validation"]["quality_score"] >= 0


def test_transformation_health_check(client):
    """Test transformation service health check."""
    response = client.get("/transformation/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "components" in data
