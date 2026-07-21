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


def test_ml_router_info(client):
    """Test ML router is accessible."""
    response = client.get("/ml/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "ML Service"
    assert "capabilities" in data
    assert len(data["capabilities"]) >= 3


def test_transformation_router_info(client):
    """Test transformation router is accessible."""
    response = client.get("/transformation/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Transformation Service"
    assert "capabilities" in data


def test_backup_router_info(client):
    """Test backup router is accessible."""
    response = client.get("/backup/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Backup Service"
    assert "backup_types" in data


def test_auth_router_info(client):
    """Test auth router is accessible (even when disabled)."""
    response = client.get("/auth/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Authentication Service"
    assert "enabled" in data


def test_monitoring_router_health(client):
    """Test monitoring router health check."""
    response = client.get("/monitoring/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["healthy", "degraded"]


def test_cache_router_info(client):
    """Test cache router is accessible."""
    response = client.get("/cache/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Unified Cache Service"


def test_visualization_router_info(client):
    """Test visualization router is accessible."""
    response = client.get("/visualization/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Visualization Service"


def test_scheduler_router_info(client):
    """Test scheduler router is accessible."""
    response = client.get("/scheduler/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Scheduler Service"


def test_audit_router_info(client):
    """Test audit router is accessible."""
    response = client.get("/audit/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Audit Service"
