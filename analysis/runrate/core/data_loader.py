"""
Data loading functions for RunRate analysis.

Provides both async and sync versions for flexible integration.
Uses connection pooling and async I/O for optimal performance.
"""

import os

# CRITICAL: Set OCSP fail-open BEFORE importing Snowflake modules
# This ensures it's respected during S3 result fetching
if "SF_OCSP_FAIL_OPEN" not in os.environ:
    os.environ["SF_OCSP_FAIL_OPEN"] = os.getenv(
        "SNOWFLAKE_OCSP_FAIL_OPEN", "true"
    ).lower()

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import pandas as pd
import snowflake.connector

# Import shared utilities
from analysis.shared import (
    get_snowflake_connection_params,
    get_snowflake_connection_params_with_schema,
)

# Thread pool for database operations
_db_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="snowflake_")


async def get_supplier_names_async() -> List[str]:
    """
    Get list of available suppliers from database (async).

    Returns:
        List[str]: Sorted list of unique supplier names

    Raises:
        Exception: If database connection fails
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_db_executor, _get_supplier_names_sync)


def _get_supplier_names_sync() -> List[str]:
    """Synchronous implementation of get_supplier_names."""
    try:
        conn = snowflake.connector.connect(**get_snowflake_connection_params())
        supplier_df = pd.read_sql(
            "SELECT DISTINCT SUPPLIER_NAME FROM MASTER_SHOT_TABLE WHERE SUPPLIER_NAME IS NOT NULL",
            conn,
        )
        conn.close()
        return sorted(supplier_df["SUPPLIER_NAME"].dropna().unique().tolist())
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return []


def get_supplier_names() -> List[str]:
    """
    Get list of available suppliers from database (sync).

    Returns:
        List[str]: Sorted list of unique supplier names
    """
    return _get_supplier_names_sync()


async def get_equipment_codes_async(supplier: str) -> List[str]:
    """
    Get list of equipment codes for a supplier (async).

    Args:
        supplier: Supplier name to filter by

    Returns:
        List[str]: List of equipment codes for the supplier

    Raises:
        Exception: If database query fails
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_db_executor, _get_equipment_codes_sync, supplier)


def _get_equipment_codes_sync(supplier: str) -> List[str]:
    """Synchronous implementation of get_equipment_codes."""
    try:
        conn = snowflake.connector.connect(**get_snowflake_connection_params())
        query = """
        SELECT DISTINCT EQUIPMENT_CODE
        FROM MASTER_SHOT_TABLE
        WHERE SUPPLIER_NAME = %s
        AND EQUIPMENT_CODE IS NOT NULL
        ORDER BY EQUIPMENT_CODE
        """
        equipment_df = pd.read_sql(query, conn, params=[supplier])
        conn.close()
        return equipment_df["EQUIPMENT_CODE"].tolist()
    except Exception as e:
        print(f"Error getting equipment codes: {e}")
        return []


def get_equipment_codes(supplier: str) -> List[str]:
    """
    Get list of equipment codes for a supplier (sync).

    Args:
        supplier: Supplier name to filter by

    Returns:
        List[str]: List of equipment codes for the supplier
    """
    return _get_equipment_codes_sync(supplier)


async def load_data_async(
    supplier: Optional[str] = None,
    equipment_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    schema: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load production data from Snowflake (async).

    Args:
        supplier: Optional supplier name filter (use "All" for all suppliers)
        equipment_code: Optional equipment code filter
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
        schema: Optional schema/client override (e.g., "NORDPLAST", "AURELIA")

    Returns:
        pd.DataFrame: Production data with columns:
            - SUPPLIER_NAME
            - EQUIPMENT_CODE
            - LOCAL_SHOT_TIME
            - ACTUAL_CT
            - APPROVED_CT

    Raises:
        Exception: If database query fails
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _db_executor,
        _load_data_sync,
        supplier,
        equipment_code,
        start_date,
        end_date,
        schema,
    )


def _load_data_sync(
    supplier: Optional[str] = None,
    equipment_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    schema: Optional[str] = None,
) -> pd.DataFrame:
    """Synchronous implementation of load_data with retry logic."""
    params = (
        get_snowflake_connection_params_with_schema(schema)
        if schema
        else get_snowflake_connection_params()
    )

    # Log which schema we're using
    active_schema = params.get("schema", "UNKNOWN")
    database = params.get("database", "MMS")
    print(f"🔍 Querying: {database}.{active_schema}.MASTER_SHOT_TABLE")

    # Build query with proper parameterization
    # Note: Inputs are validated at API level, but we still use safe query building
    query = """
    SELECT SUPPLIER_NAME, EQUIPMENT_CODE, LOCAL_SHOT_TIME, CT AS ACTUAL_CT, APPROVED_CT
    FROM MASTER_SHOT_TABLE
    WHERE LOCAL_SHOT_TIME IS NOT NULL
        AND VOLUME > 0
    """

    query_params = []

    # Add supplier filter if provided (and not "All")
    # Input is validated at API level, but we escape single quotes for safety
    if supplier and supplier != "All":
        # Escape single quotes by doubling them (SQL standard)
        safe_supplier = supplier.replace("'", "''")
        query += " AND SUPPLIER_NAME = %s"
        query_params.append(safe_supplier)

    # Add equipment filter if provided
    if equipment_code:
        # Equipment codes are validated at API level (any format allowed)
        safe_equipment = equipment_code.replace("'", "''")
        query += " AND EQUIPMENT_CODE = %s"
        query_params.append(safe_equipment)

    # Add date filters if provided
    # Include shots that overlap with the date range:
    # - Shots that end after range starts (catches cross-day shots from previous day)
    # - Shots that start before range ends
    # Dates are validated at API level (format: YYYY-MM-DD)
    if start_date:
        query += " AND DATEADD(SECOND, CASE WHEN CT >= 999.9 THEN 0 ELSE CT END, LOCAL_SHOT_TIME) >= %s"
        query_params.append(f"{start_date} 00:00:00")

    if end_date:
        query += " AND LOCAL_SHOT_TIME <= %s"
        query_params.append(f"{end_date} 23:59:59")

    print(f"🔍 SQL Query: {query}")  # Debug logging
    if query_params:
        print(f"🔍 Query Parameters: {query_params}")  # Debug logging

    # Calculate date range for logging and retry strategy
    date_diff = None
    if start_date and end_date:
        from datetime import datetime

        date_diff = (
            datetime.strptime(end_date, "%Y-%m-%d")
            - datetime.strptime(start_date, "%Y-%m-%d")
        ).days
        print(f"📅 Date range: {date_diff} days")
        if date_diff > 3:
            print(
                f"⚠️ Large date range ({date_diff} days) - using enhanced retry logic"
            )

    # Retry configuration
    max_retries = int(os.getenv("SNOWFLAKE_MAX_RETRIES", "5"))
    retry_delay = int(os.getenv("SNOWFLAKE_RETRY_DELAY", "10"))

    conn = None
    for attempt in range(1, max_retries + 1):
        cursor = None
        try:
            # Recreate connection on retry attempts (fresh SSL handshake)
            if attempt > 1:
                print(
                    f"🔄 Retry attempt {attempt}/{max_retries} - recreating connection..."
                )
                if conn:
                    try:
                        conn.close()
                    except Exception as close_error:
                        print(f"   Warning closing old connection: {close_error}")
                time.sleep(retry_delay * (attempt - 1))  # Exponential backoff

            # Create fresh connection
            conn = snowflake.connector.connect(**params)

            # Set statement timeout to prevent default 71s timeout
            statement_timeout = int(os.getenv("SNOWFLAKE_STATEMENT_TIMEOUT", "7200"))
            cursor = conn.cursor()
            cursor.execute(
                f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {statement_timeout}"
            )
            if attempt == 1:
                print(f"⏱️ Statement timeout set to: {statement_timeout}s")

            # Set schema context
            cursor.execute(f"USE SCHEMA {database}.{active_schema}")
            cursor.close()
            cursor = None

            # Execute query and fetch data
            print(f"📥 Fetching data (attempt {attempt}/{max_retries})...")
            start_time = time.time()

            # Use parameterized query execution for security
            # Snowflake connector supports parameterized queries
            if query_params:
                # Use cursor.execute with parameters, then convert to DataFrame
                cursor = conn.cursor()
                cursor.execute(query, query_params)
                # Fetch column names
                columns = [desc[0] for desc in cursor.description]
                # Fetch all rows
                rows = cursor.fetchall()
                cursor.close()
                # Convert to DataFrame
                df = pd.DataFrame(rows, columns=columns)
            else:
                # No parameters, safe to use pd.read_sql directly
                df = pd.read_sql(query, conn)

            elapsed_time = time.time() - start_time

            conn.close()
            conn = None

            print(f"✅ Loaded {len(df)} records from Snowflake in {elapsed_time:.2f}s")

            # Success! Return the dataframe
            return df

        except Exception as e:
            error_msg = str(e)
            print(f"❌ Attempt {attempt}/{max_retries} failed: {error_msg}")

            # Close cursor/connection on error
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            conn = None

            # Check if this is a certificate error
            is_cert_error = "254007" in error_msg or "certificate" in error_msg.lower()

            # If last attempt, raise the error
            if attempt >= max_retries:
                print(f"💥 All {max_retries} attempts failed!")
                raise Exception(
                    f"Snowflake query failed after {max_retries} attempts: {error_msg}"
                )

            # Log retry info
            if is_cert_error:
                print("   Certificate error detected - will recreate connection")
            print(f"   Waiting {retry_delay * attempt}s before retry...")

        finally:
            # Ensure cleanup (but only if we're not returning successfully)
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass

    # Should never reach here
    raise Exception("Unexpected error in retry loop")


def load_data(
    supplier: Optional[str] = None,
    equipment_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load production data from Snowflake (sync).

    Args:
        supplier: Optional supplier name filter (use "All" for all suppliers)
        equipment_code: Optional equipment code filter
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)

    Returns:
        pd.DataFrame: Production data
    """
    return _load_data_sync(supplier, equipment_code, start_date, end_date)


def cleanup_db_executor():
    """Cleanup the database thread pool executor. Call this on shutdown."""
    global _db_executor
    if _db_executor:
        _db_executor.shutdown(wait=True)
