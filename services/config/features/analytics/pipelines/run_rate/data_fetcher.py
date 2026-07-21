"""Data Fetcher Module
===================

Handles data extraction from MASTER_SHOT_TABLE for run rate analysis.
"""

import logging
import time

import pandas as pd

from utils.sql_validation import validate_date_param

logger = logging.getLogger("RUNRATE")


def _get_fq_table(session, table_name):
    """Build fully qualified table name from the active session."""
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')
    return f"{db}.{schema}.{table_name}"


def fetch_full_data(session):
    """Fetch full historical data from MASTER_SHOT_TABLE.

    Args:
        session: Snowflake Snowpark session

    Returns:
        pd.DataFrame: DataFrame with equipment_code, supplier_name, local_shot_time,
            ct, approved_ct columns
    """
    fq_table = _get_fq_table(session, "MASTER_SHOT_TABLE")
    sql_query = f"""
        SELECT
            EQUIPMENT_CODE,
            SUPPLIER_NAME,
            LOCAL_SHOT_TIME,
            CT,
            APPROVED_CT
        FROM {fq_table}
        WHERE
            EQUIPMENT_CODE IS NOT NULL
            AND SUPPLIER_NAME IS NOT NULL
            AND CT IS NOT NULL
            AND APPROVED_CT IS NOT NULL
            AND VOLUME > 0
        ORDER BY EQUIPMENT_CODE, LOCAL_SHOT_TIME
    """
    logger.info(f"Fetching full historical data from {fq_table}...")
    start_time = time.time()

    df = session.sql(sql_query).to_pandas()

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"Retrieved {len(df):,} rows from MASTER_SHOT_TABLE in {elapsed}s")
    return df


def fetch_incremental_data(session, start_date: str):
    """Fetch incremental data from MASTER_SHOT_TABLE starting from start_date.

    Args:
        session: Snowflake Snowpark session
        start_date: Start date for incremental processing (YYYY-MM-DD format)

    Returns:
        pd.DataFrame: DataFrame with equipment_code, supplier_name, local_shot_time,
            ct, approved_ct columns
    """
    fq_table = _get_fq_table(session, "MASTER_SHOT_TABLE")
    sql_query = f"""
        SELECT
            EQUIPMENT_CODE,
            SUPPLIER_NAME,
            LOCAL_SHOT_TIME,
            CT,
            APPROVED_CT
        FROM {fq_table}
        WHERE
            EQUIPMENT_CODE IS NOT NULL
            AND SUPPLIER_NAME IS NOT NULL
            AND CT IS NOT NULL
            AND APPROVED_CT IS NOT NULL
            AND VOLUME > 0
            AND DATE(LOCAL_SHOT_TIME) >= '{validate_date_param(start_date)}'::DATE
        ORDER BY EQUIPMENT_CODE, LOCAL_SHOT_TIME
    """
    logger.info(f"Fetching incremental data from {fq_table} (from {start_date})...")
    start_time = time.time()

    df = session.sql(sql_query).to_pandas()

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"Retrieved {len(df):,} incremental rows in {elapsed}s")
    return df


def validate_data(df):
    """Validate fetched data for required columns and data types.

    Args:
        df (pd.DataFrame): DataFrame to validate

    Returns:
        bool: True if valid, raises ValueError otherwise
    """
    required_columns = [
        "EQUIPMENT_CODE",
        "SUPPLIER_NAME",
        "LOCAL_SHOT_TIME",
        "CT",
        "APPROVED_CT",
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    if df.empty:
        logger.warning("DataFrame is empty after fetch")
        return False

    # Ensure LOCAL_SHOT_TIME is datetime
    if not pd.api.types.is_datetime64_any_dtype(df["LOCAL_SHOT_TIME"]):
        df["LOCAL_SHOT_TIME"] = pd.to_datetime(df["LOCAL_SHOT_TIME"])

    logger.info(f"Data validation passed for {len(df):,} rows")
    return True
