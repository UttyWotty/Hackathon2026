"""
CT Deviation Data Loader.

This module handles Snowflake connection and data fetching for CT deviation analysis.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import os
import re
from datetime import datetime
from typing import List, Optional

import pandas as pd  # type: ignore[import-untyped]
import snowflake.connector  # type: ignore[import-untyped]
from snowflake.snowpark import Session  # type: ignore[import-untyped]

# Import shared utilities
from analysis.shared import get_logger, get_snowflake_connection_params
from analysis.shared.local_source import is_local_data_enabled, query_shots

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
    # In local mode no session is needed: fetch_ct_deviation_data serves from
    # CSV and ignores this argument. Returning None rather than connecting keeps
    # the api layer working, since it builds the session before fetching.
    if is_local_data_enabled():
        logger.info("Local data mode: skipping Snowpark session creation")
        return None  # type: ignore[return-value]

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
    """Create and return a standard Snowflake connector (for write operations).

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


def _validate_and_sanitize_date(date_str: str, field_name: str) -> str:
    """Validate date format and sanitize for SQL injection."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise ValueError(
            f"Invalid {field_name} format: {date_str}. Expected YYYY-MM-DD"
        )
    return date_str.replace("'", "''")


def _sanitize_equipment_codes(equipment_codes: List[str]) -> str:
    """Sanitize equipment codes for SQL IN clause."""
    safe_codes = [code.replace("'", "''") for code in equipment_codes]
    return "', '".join(safe_codes)


def _validate_and_sanitize_supplier_names(supplier_names: List[str]) -> str:
    """Validate and sanitize supplier names for SQL IN clause."""
    for name in supplier_names:
        if not re.match(r"^[a-zA-Z0-9\s\-_]+$", name):
            raise ValueError(f"Invalid supplier name format: {name}")
    safe_names = [name.replace("'", "''") for name in supplier_names]
    return "', '".join(safe_names)


def _build_date_filters(
    query: str, start_date: Optional[str], end_date: Optional[str]
) -> str:
    """Add date filters to SQL query."""
    if start_date:
        safe_start_date = _validate_and_sanitize_date(start_date, "start_date")
        query += f" AND LOCAL_SHOT_TIME >= '{safe_start_date} 00:00:00'"
    if end_date:
        safe_end_date = _validate_and_sanitize_date(end_date, "end_date")
        query += f" AND LOCAL_SHOT_TIME <= '{safe_end_date} 23:59:59'"
    return query


def _build_equipment_filter(query: str, equipment_codes: Optional[List[str]]) -> str:
    """Add equipment code filter to SQL query."""
    if equipment_codes:
        codes_list = _sanitize_equipment_codes(equipment_codes)
        query += f" AND EQUIPMENT_CODE IN ('{codes_list}')"
    return query


def _build_supplier_filter(query: str, supplier_names: Optional[List[str]]) -> str:
    """Add supplier name filter to SQL query."""
    if supplier_names:
        names_list = _validate_and_sanitize_supplier_names(supplier_names)
        query += f" AND SUPPLIER_NAME IN ('{names_list}')"
    return query


def _execute_query_and_process_results(session: Session, query: str) -> pd.DataFrame:
    """Execute SQL query and process results."""
    logger.info("🔄 Fetching CT deviation data from Snowflake...")
    start_time = datetime.now()

    df = session.sql(query).to_pandas()

    fetch_time = (datetime.now() - start_time).total_seconds()
    logger.info(f"✅ Retrieved {len(df)} rows in {fetch_time:.2f} seconds")

    # Ensure CT column exists
    if not df.empty and "CT" not in df.columns:
        logger.warning("⚠️ CT column not found, attempting to use CYCLE_TIME")
        if "CYCLE_TIME" in df.columns:
            df["CT"] = df["CYCLE_TIME"]
        else:
            raise ValueError("Neither CT nor CYCLE_TIME column found in data")

    return df


def fetch_ct_deviation_data(
    session: Session,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    equipment_codes: Optional[List[str]] = None,
    supplier_names: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Fetch cycle time data from DEMO_TABLE with optional filters.

    Args:
        session: Snowpark session
        start_date: Start date in 'YYYY-MM-DD' format (optional)
        end_date: End date in 'YYYY-MM-DD' format (optional)
        equipment_codes: List of equipment codes to filter (optional)
        supplier_names: List of supplier names to filter (optional)

    Returns:
        pd.DataFrame: Filtered shot data with CT and approved CT

    Raises:
        Exception: If query fails
    """
    # Development path: serve the synthetic CSVs instead of querying Snowflake.
    # Inactive unless LOCAL_DATA_DIR is set, so production behaviour is unchanged.
    if is_local_data_enabled():
        logger.info("Serving CT deviation data from the local dataset")
        return query_shots(
            start_date=start_date,
            end_date=end_date,
            equipment_codes=equipment_codes,
            supplier_names=supplier_names,
        )

    try:
        # Build the base query
        # Note: Snowpark doesn't support parameterized queries like the connector
        # We validate inputs at API level and escape properly for security
        query = """
        SELECT 
            SUPPLIER_NAME,
            CT,
            LOCAL_SHOT_TIME,
            TEMPERATURE,
            VOLUME,
            APPROVED_CT,
            EQUIPMENT_CODE,
            COUNTER_ID,
            COUNTER_CODE,
            MOLD_ID,
            COMPANY_ID,
            PART_ID,
            PART_NAME,
            TOOLING_TYPE
        FROM DEMO_TABLE
        WHERE CT IS NOT NULL 
        AND APPROVED_CT IS NOT NULL
        AND CT > 0
        AND APPROVED_CT > 0
        AND CT < 999.9
        """

        # Add filters
        query = _build_date_filters(query, start_date, end_date)
        query = _build_equipment_filter(query, equipment_codes)
        query = _build_supplier_filter(query, supplier_names)
        query += " ORDER BY LOCAL_SHOT_TIME"

        # Execute query and process results
        df = _execute_query_and_process_results(session, query)

        return df

    except Exception as e:
        logger.error(f"❌ Error fetching CT deviation data: {e}")
        raise


def validate_ct_data(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and clean CT data.

    Args:
        df: Raw data from Snowflake

    Returns:
        pd.DataFrame: Validated and cleaned data

    Raises:
        ValueError: If data is invalid
    """
    if df.empty:
        logger.warning("⚠️ No data to validate")
        return df

    # Check required columns
    required_cols = ["CT", "APPROVED_CT", "EQUIPMENT_CODE", "LOCAL_SHOT_TIME"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Remove any remaining invalid values
    original_len = len(df)
    df = df[
        (df["CT"].notna())
        & (df["APPROVED_CT"].notna())
        & (df["CT"] > 0)
        & (df["APPROVED_CT"] > 0)
        & (df["CT"] < 999.9)
    ]

    removed = original_len - len(df)
    if removed > 0:
        logger.info(f"🧹 Removed {removed} invalid records during validation")

    return df
