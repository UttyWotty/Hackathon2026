"""
Pytest configuration and fixtures.
"""

import pytest  # type: ignore[import-untyped]
from dotenv import load_dotenv  # type: ignore[import-untyped]
from fastapi.testclient import TestClient

load_dotenv()


@pytest.fixture(scope="session", autouse=True)
def initialize_database():
    """Create the SQLite schema and run migrations before any test runs.

    Mirrors the application lifespan startup so database-backed tests do not
    depend on a pre-existing data/manufacturing.db, which is absent in a clean
    checkout (e.g., CI). Safe to call repeatedly; create_all is idempotent.
    """
    # Import the app first so every model is registered on the metadata before
    # create_all runs (mirrors production, where main.py imports all routers
    # before the lifespan runs).
    import main  # noqa: F401
    from models.database import init_database

    init_database()


@pytest.fixture(scope="session")
def client():
    """
    FastAPI TestClient for in-process API testing.

    This avoids requiring an externally running server on localhost:3020 and keeps
    tests hermetic and fast.
    """
    from main import app

    return TestClient(app)
