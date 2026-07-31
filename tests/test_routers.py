"""
Test the remaining routers are accessible and respond correctly.

Only scheduler and MCP routers survive the hackathon trim; analytics, chat, email,
config, and monitoring were removed because the agent calls tools directly.
"""


def test_root_endpoint(client):
    """Test root endpoint returns API info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "surfaces" in data
    assert "agent_entry_point" in data


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_scheduler_router_info(client):
    """Test scheduler router is accessible."""
    response = client.get("/scheduler/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Scheduler Service"
