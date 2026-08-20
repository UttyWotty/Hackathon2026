"""Snowpark session helper for local and in-Snowflake execution.

Provides a single get_session() function that returns the active Snowpark
session when running inside Snowflake, or creates a local session using
environment variables when running locally.
"""

import os

from snowflake.snowpark import Session
from snowflake.snowpark.context import get_active_session

SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT", "")
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER", "")
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
DATABASE = os.getenv("SNOWFLAKE_DATABASE", "DEMO")
SCHEMA = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")

_local_session = None


def get_session() -> Session:
    """Get active Snowpark session, falling back to local connection."""
    global _local_session
    try:
        return get_active_session()
    except Exception:
        if _local_session is not None:
            return _local_session
        connection_params = {
            "account": SNOWFLAKE_ACCOUNT,
            "user": SNOWFLAKE_USER,
            "password": os.environ.get("SNOWFLAKE_PASSWORD", ""),
            "warehouse": SNOWFLAKE_WAREHOUSE,
            "database": DATABASE,
            "schema": SCHEMA,
        }
        _local_session = Session.builder.configs(connection_params).create()
        return _local_session
