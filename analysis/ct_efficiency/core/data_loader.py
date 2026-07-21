"""
CT Efficiency Data Loader.

This module handles Snowflake connection and data fetching for CT efficiency analysis.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import os
import time
from typing import Optional

import pandas as pd  # type: ignore[import-untyped]
import snowflake.connector  # type: ignore[import-untyped]
from snowflake.snowpark import Session  # type: ignore[import-untyped]

# Import shared utilities
from analysis.shared import get_logger, get_snowflake_connection_params

logger = get_logger(__name__)


# ==================== Snowflake Connection ==================== #


def create_snowpark_session() -> Session:
    """Create and return a Snowpark session using P8 authentication.

    Returns:
        Session: Configured Snowpark session

    Raises:
        ValueError: If required environment variables are missing
        Exception: If connection fails
    """
    try:
        # Use shared utilities for P8 authentication (same as RCA, ROI, etc.)
        connection_parameters = get_snowflake_connection_params(
            include_private_key=True
        )

        # Validate required environment variables
        missing_vars = [
            key for key, value in connection_parameters.items() if not value
        ]
        if missing_vars:
            raise ValueError(
                f"Missing required Snowflake environment variables: {missing_vars}"
            )

        session = Session.builder.configs(connection_parameters).create()

        # CRITICAL: Set statement timeout via ALTER SESSION (Snowpark requires this)
        # Default is often 60 seconds, which causes failures around 71 seconds
        statement_timeout = int(
            os.getenv("SNOWFLAKE_STATEMENT_TIMEOUT", "7200")
        )  # 2 hours default
        try:
            session.sql(
                f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {statement_timeout}"
            ).collect()
            logger.info(f"   Statement timeout set to: {statement_timeout}s")
        except Exception as e:
            logger.warning(f"   Could not set statement timeout: {e}")

        logger.info("✅ Connected to Snowflake successfully")

        return session

    except Exception as e:
        logger.error(f"❌ Failed to connect to Snowflake: {e}")
        raise


def create_snowflake_connector() -> snowflake.connector.SnowflakeConnection:
    """Create and return a standard Snowflake connector.

    Returns:
        SnowflakeConnection: Connected Snowflake connector

    Raises:
        ValueError: If required environment variables are missing
        Exception: If connection fails
    """
    try:
        connection_parameters = {
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
            "user": os.getenv("SNOWFLAKE_USER"),
            "password": os.getenv("SNOWFLAKE_PASSWORD"),
            "role": os.getenv("SNOWFLAKE_ROLE"),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
            "database": os.getenv("SNOWFLAKE_DATABASE"),
            "schema": os.getenv("SNOWFLAKE_SCHEMA"),
        }

        # Validate required environment variables
        missing_vars = [
            key for key, value in connection_parameters.items() if not value
        ]
        if missing_vars:
            raise ValueError(
                f"Missing required Snowflake environment variables: {missing_vars}"
            )

        connector = snowflake.connector.connect(**connection_parameters)
        logger.info("✅ Snowflake connector created successfully")

        return connector

    except Exception as e:
        logger.error(f"❌ Failed to create Snowflake connector: {e}")
        raise


# ==================== Data Fetching ==================== #


def fetch_efficiency_data(
    session: Session,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    supplier_names: Optional[list] = None,
    client: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch cycle time data from MASTER_SHOT_TABLE for efficiency analysis.

    Args:
        session: Snowpark session
        start_date: Start date in 'YYYY-MM-DD' format (optional)
        end_date: End date in 'YYYY-MM-DD' format (optional)
        supplier_names: List of supplier names to filter (optional)
        client: Client/schema name (e.g. 'KESTREL', 'VANTIS'). Switches Snowflake schema.

    Returns:
        pd.DataFrame: Shot data with CT and approved CT

    Raises:
        Exception: If query fails
    """
    try:
        # Switch schema if client specified
        if client:
            schema = client.upper()
            session.sql(f"USE SCHEMA {schema}").collect()
            logger.info("Switched to schema: %s", schema)

        # Build the query
        query = """
        SELECT
            SUPPLIER_NAME,
            CT,
            APPROVED_CT,
            EQUIPMENT_CODE,
            TOOLING_TYPE,
            LOCAL_SHOT_TIME,
            PART_ID,
            PART_NAME
        FROM MASTER_SHOT_TABLE
        WHERE CT IS NOT NULL
        AND APPROVED_CT IS NOT NULL
        AND CT > 0
        AND APPROVED_CT > 0
        AND CT < 999.9
        """

        # Add date filters if provided
        if start_date:
            query += f" AND LOCAL_SHOT_TIME >= '{start_date}'"
        if end_date:
            query += f" AND LOCAL_SHOT_TIME <= '{end_date}'"

        # Add supplier filter
        if supplier_names:
            supplier_list = "', '".join(supplier_names)
            query += f" AND SUPPLIER_NAME IN ('{supplier_list}')"

        query += " ORDER BY LOCAL_SHOT_TIME"

        logger.info("Fetching CT efficiency data from Snowflake...")
        start_time = time.time()

        df = session.sql(query).to_pandas()

        fetch_time = time.time() - start_time
        logger.info("Retrieved %d rows in %.2f seconds", len(df), fetch_time)

        return df

    except Exception as e:
        logger.error(f"❌ Error fetching CT efficiency data: {e}")
        raise


# ==================== Data Preparation ==================== #


def prepare_efficiency_data(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare and clean data for efficiency analysis.

    Args:
        df: Raw data from Snowflake

    Returns:
        pd.DataFrame: Cleaned and prepared data

    Raises:
        ValueError: If data is invalid
    """
    if df.empty:
        logger.warning("⚠️ No data to prepare")
        return df

    try:
        logger.info("Preparing data for benchmarking analysis...")

        # Create tool_id from equipment_code
        df["tool_id"] = df["EQUIPMENT_CODE"].astype(str)

        # Ensure tooling_type is present, default to Injection for molding clients
        if "TOOLING_TYPE" not in df.columns:
            df["TOOLING_TYPE"] = "Injection"
        else:
            df["TOOLING_TYPE"] = df["TOOLING_TYPE"].fillna("Injection")

        # Ensure LOCAL_SHOT_TIME is datetime for session detection
        if "LOCAL_SHOT_TIME" in df.columns:
            df["LOCAL_SHOT_TIME"] = pd.to_datetime(df["LOCAL_SHOT_TIME"])

        initial_count = len(df)

        # Filter valid production shots (already done in query, but double-check)
        df = df[df["CT"] < 999.9]  # Exclude warm-up/paused shots
        df = df[df["CT"] > 0]
        df = df[df["APPROVED_CT"] > 0]

        # Filter out extreme outliers (1st to 99th percentile)
        q1 = df["CT"].quantile(0.01)
        q3 = df["CT"].quantile(0.99)
        df = df[(df["CT"] >= q1) & (df["CT"] <= q3)]

        filtered_count = len(df)
        logger.info(
            f"Data filtering: {initial_count} → {filtered_count} records "
            f"({filtered_count / initial_count * 100:.1f}% retained)"
        )

        return df

    except Exception as e:
        logger.error(f"❌ Error preparing efficiency data: {e}")
        raise
