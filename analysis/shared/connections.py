"""
Snowflake Connection Management
================================

Centralized connection management for Snowflake database operations.
Provides connection pooling, retry logic, and private key authentication.

Author: Utku Gulbardak
Date: 2025-10-28
"""

from __future__ import annotations

import logging
import os
import time
from functools import lru_cache
from typing import Any, Dict, Optional

# CRITICAL: Set OCSP fail-open BEFORE importing Snowflake modules
# This ensures it's respected during S3 result fetching
if "SF_OCSP_FAIL_OPEN" not in os.environ:
    os.environ["SF_OCSP_FAIL_OPEN"] = os.getenv(
        "SNOWFLAKE_OCSP_FAIL_OPEN", "true"
    ).lower()

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class SnowflakeConnectionError(Exception):
    """Custom exception for Snowflake connection errors."""


def load_private_key(key_path: str, password: Optional[str] = None) -> bytes:
    """
    Load private key for Snowflake key-pair authentication.

    Args:
        key_path: Path to the private key file (.p8)
        password: Optional password for the private key

    Returns:
        bytes: The private key in DER format for Snowflake

    Raises:
        FileNotFoundError: If key file doesn't exist
        ValueError: If key cannot be decoded

    Example:
        >>> key = load_private_key("config/roi_key.p8", "mypassword")
        >>> # Use key in Snowflake connection
    """
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"Private key file not found: {key_path}")

    try:
        with open(key_path, "rb") as key_file:
            p_key = key_file.read()

        password_bytes = password.encode() if password else None

        private_key = serialization.load_pem_private_key(
            p_key, password=password_bytes, backend=default_backend()
        )

        private_key_der = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        logger.debug(f"✅ Successfully loaded private key from {key_path}")
        return private_key_der

    except Exception as e:
        logger.error(f"❌ Failed to load private key from {key_path}: {e}")
        raise ValueError(f"Could not decode private key: {e}")


@lru_cache(maxsize=1)
def get_snowflake_connection_params(include_private_key: bool = True) -> Dict[str, Any]:
    """
    Get Snowflake connection parameters from environment variables.

    Supports both private key and password authentication, with automatic
    fallback from private key to password if key loading fails.

    Results are cached to avoid repeated environment variable lookups.

    Args:
        include_private_key: Whether to attempt private key authentication

    Returns:
        dict: Connection parameters ready for snowflake.connector.connect()

    Raises:
        SnowflakeConnectionError: If required environment variables are missing

    Example:
        >>> params = get_snowflake_connection_params()
        >>> conn = snowflake.connector.connect(**params)
    """
    # Load environment variables
    load_dotenv()

    # Build base connection parameters
    params = {
        "user": os.getenv("SNOWFLAKE_USER"),
        "account": os.getenv("SNOWFLAKE_ACCOUNT"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
        "database": os.getenv("SNOWFLAKE_DATABASE"),
        "schema": os.getenv("SNOWFLAKE_SCHEMA"),
        "role": os.getenv("SNOWFLAKE_ROLE"),
    }

    # Add timeout settings for long-running queries
    # network_timeout: Timeout for network operations (default: 600 seconds = 10 minutes)
    # login_timeout: Timeout for login (default: 60 seconds)
    # ocsp_fail_open: Allow connection even if OCSP certificate validation fails (for long queries)
    params["network_timeout"] = int(
        os.getenv("SNOWFLAKE_NETWORK_TIMEOUT", "3600")
    )  # 1 hour default
    params["login_timeout"] = int(
        os.getenv("SNOWFLAKE_LOGIN_TIMEOUT", "60")
    )  # 1 minute default
    ocsp_fail_open = (
        os.getenv("SNOWFLAKE_OCSP_FAIL_OPEN", "True").lower() == "true"
    )  # Default: True
    params["ocsp_fail_open"] = ocsp_fail_open

    # Insecure mode: Completely disable SSL/TLS certificate verification
    # Use with caution - bypasses all certificate validation
    # Useful when corporate firewalls/proxies interfere with SSL handshakes
    insecure_mode = os.getenv("SNOWFLAKE_INSECURE_MODE", "False").lower() == "true"
    params["insecure_mode"] = insecure_mode

    # CRITICAL: Set OCSP fail-open as environment variable for Python connector
    # This ensures it's respected during S3 result fetching (where certificate errors occur)
    os.environ["SF_OCSP_FAIL_OPEN"] = str(ocsp_fail_open).lower()

    # Try private key authentication first, fall back to password
    if include_private_key:
        key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
        if key_path and os.path.exists(key_path):
            try:
                key_password = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSWORD")
                params["private_key"] = load_private_key(key_path, key_password)
                logger.info("✅ Using private key authentication")
            except Exception as e:
                logger.warning(
                    f"⚠️  Could not load private key: {e}, falling back to password"
                )
                password = os.getenv("SNOWFLAKE_PASSWORD")
                if password:
                    params["password"] = password
        else:
            password = os.getenv("SNOWFLAKE_PASSWORD")
            if password:
                params["password"] = password
    else:
        password = os.getenv("SNOWFLAKE_PASSWORD")
        if password:
            params["password"] = password

    # Validate required parameters
    required_keys = ["account", "user", "warehouse", "database", "schema", "role"]
    missing = [key for key in required_keys if not params.get(key)]
    if missing:
        raise SnowflakeConnectionError(
            f"Missing required Snowflake credentials: {missing}"
        )

    # Ensure we have either private_key or password
    if "private_key" not in params and "password" not in params:
        raise SnowflakeConnectionError(
            "Either SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PASSWORD must be set"
        )

    return params


def get_snowflake_connection_params_with_schema(
    schema: Optional[str] = None, include_private_key: bool = True
) -> Dict[str, Any]:
    """
    Get Snowflake connection parameters with optional schema override.

    Args:
        schema: Override schema (if None, uses environment variable)
        include_private_key: Whether to attempt private key authentication

    Returns:
        dict: Connection parameters ready for snowflake.connector.connect()

    Example:
        >>> params = get_snowflake_connection_params_with_schema("PRODUCTION")
        >>> conn = snowflake.connector.connect(**params)
    """
    params = dict(get_snowflake_connection_params(include_private_key))

    # Override schema if provided
    if schema:
        params["schema"] = schema
        logger.info(f"🔄 Using schema override: {schema}")

    return params


def create_snowflake_connection(
    max_retries: int = 3, retry_delay: int = 2, schema: Optional[str] = None
) -> snowflake.connector.SnowflakeConnection:
    """
    Create and return a Snowflake database connection with retry logic.

    Automatically retries connection on failure with exponential backoff.

    Args:
        max_retries: Maximum number of connection attempts (default: 3)
        retry_delay: Initial delay between retries in seconds (default: 2)
        schema: Optional schema override

    Returns:
        SnowflakeConnection: Active Snowflake connection

    Raises:
        SnowflakeConnectionError: If connection fails after all retries

    Example:
        >>> conn = create_snowflake_connection(max_retries=5)
        >>> cursor = conn.cursor()
        >>> cursor.execute("SELECT * FROM my_table LIMIT 10")
    """
    params = (
        get_snowflake_connection_params_with_schema(schema)
        if schema
        else get_snowflake_connection_params()
    )

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"🔌 Attempting Snowflake connection (attempt {attempt}/{max_retries})"
            )
            conn = snowflake.connector.connect(**params)
            logger.info("✅ Successfully connected to Snowflake")
            return conn

        except Exception as e:
            if attempt == max_retries:
                logger.error(
                    f"❌ Failed to connect to Snowflake after {max_retries} attempts: {e}"
                )
                raise SnowflakeConnectionError(
                    f"Could not connect to Snowflake after {max_retries} attempts: {e}"
                )

            wait_time = retry_delay * (2 ** (attempt - 1))  # Exponential backoff
            logger.warning(
                f"⚠️  Connection attempt {attempt} failed: {e}. "
                f"Retrying in {wait_time} seconds..."
            )
            time.sleep(wait_time)


def test_snowflake_connection() -> bool:
    """
    Test Snowflake connection health.

    Returns:
        bool: True if connection is healthy, False otherwise

    Example:
        >>> if test_snowflake_connection():
        ...     print("Connection is healthy")
    """
    try:
        conn = create_snowflake_connection(max_retries=1)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if result and result[0] == 1:
            logger.info("✅ Snowflake connection health check passed")
            return True
        return False

    except Exception as e:
        logger.error(f"❌ Snowflake connection health check failed: {e}")
        return False


def get_schema_name() -> str:
    """
    Get Snowflake schema name from environment variables.

    Returns:
        str: Schema name (defaults to "PUBLIC" if not set)

    Example:
        >>> schema = get_schema_name()
        >>> print(f"Using schema: {schema}")
    """
    load_dotenv()
    return os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")


def create_snowpark_session(schema: Optional[str] = None):
    """
    Create a Snowpark Session for DataFrame operations.

    Snowpark Sessions provide a higher-level API for working with Snowflake
    data using DataFrame operations similar to PySpark.

    Args:
        schema: Optional schema override (if None, uses environment variable)

    Returns:
        snowflake.snowpark.Session: Active Snowpark session

    Raises:
        SnowflakeConnectionError: If session creation fails

    Example:
        >>> session = create_snowpark_session()
        >>> df = session.table("my_table")
        >>> df.show()
    """
    from snowflake.snowpark import Session

    load_dotenv()

    # Build connection parameters for Snowpark
    connection_params = {
        "user": os.getenv("SNOWFLAKE_USER"),
        "account": os.getenv("SNOWFLAKE_ACCOUNT"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
        "database": os.getenv("SNOWFLAKE_DATABASE"),
        "schema": schema or os.getenv("SNOWFLAKE_SCHEMA"),
        "role": os.getenv("SNOWFLAKE_ROLE"),
    }

    # Try private key authentication first
    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if key_path and os.path.exists(key_path):
        try:
            key_password = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSWORD")
            connection_params["private_key"] = load_private_key(key_path, key_password)
            logger.info("Using private key authentication for Snowpark session")
        except Exception as e:
            logger.warning(f"Could not load private key: {e}, falling back to password")
            password = os.getenv("SNOWFLAKE_PASSWORD")
            if password:
                connection_params["password"] = password
    else:
        password = os.getenv("SNOWFLAKE_PASSWORD")
        if password:
            connection_params["password"] = password

    try:
        session = Session.builder.configs(connection_params).create()
        logger.info("Snowpark session created successfully")
        return session
    except Exception as e:
        logger.error(f"Failed to create Snowpark session: {e}")
        raise SnowflakeConnectionError(f"Could not create Snowpark session: {e}")


# Module metadata
__version__ = "1.0.0"
__author__ = "Utku Gulbardak"
__all__ = [
    "SnowflakeConnectionError",
    "load_private_key",
    "get_snowflake_connection_params",
    "get_snowflake_connection_params_with_schema",
    "create_snowflake_connection",
    "create_snowpark_session",
    "test_snowflake_connection",
    "get_schema_name",
]
