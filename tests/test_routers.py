"""
Test all routers are accessible and respond correctly.
"""


def test_root_endpoint(client):
    """Test root endpoint returns API info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "features" in data
    assert len(data["features"]) >= 12


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_analytics_router_info(client):
    """Test analytics router is accessible."""
    response = client.get("/analytics/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Manufacturing Analytics"
    assert "available_tools" in data


def test_monitoring_router_health(client):
    """Test monitoring router health check."""
    response = client.get("/monitoring/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["healthy", "degraded"]


def test_scheduler_router_info(client):
    """Test scheduler router is accessible."""
    response = client.get("/scheduler/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Scheduler Service"
