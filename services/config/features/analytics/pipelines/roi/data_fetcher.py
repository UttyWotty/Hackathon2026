"""Extracts ROI-relevant shot data from MASTER_SHOT_TABLE with filters for CT < 999.9, non-null equipment codes, and positive volumes.
Supports both full historical data fetches and incremental date-filtered queries, returning validated pandas DataFrames.
Builds fully qualified table names from the active Snowpark session for cross-schema compatibility.
"""

import logging
import time

from utils.sql_validation import validate_date_param

logger = logging.getLogger("ROI")


def _get_fq_table(session, table_name):
    """Build fully qualified table name from the active session."""
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')
    return f"{db}.{schema}.{table_name}"


def _build_roi_query(fq_table, start_date=None):
    """Build the SQL query for ROI data extraction.

    Args:
        fq_table: Fully qualified table name
        start_date: Optional start date for incremental filtering (YYYY-MM-DD)

    Returns:
        str: SQL query string
    """
    date_filter = (
        f"\n    AND DATE(LOCAL_SHOT_TIME) >= '{validate_date_param(start_date)}'::DATE"
        if start_date
        else ""
    )

    return f"""SELECT
    SUPPLIER_NAME AS supplier_name,
    EQUIPMENT_CODE AS equipment_code,
    CT AS ct,
    APPROVED_CT AS approved_ct,
    CT AS average_ct,
    LOCAL_SHOT_TIME AS local_shot_time,
    1 AS total_shot_count,
    PART_ID AS part_id,
    MOLD_ID AS mold_id,
    COMPANY_ID AS supplier_id,
    COUNTER_ID AS counter_id,
    VOLUME AS volume
    FROM {fq_table}
    WHERE CT < 999.9
    AND EQUIPMENT_CODE IS NOT NULL
    AND VOLUME > 0{date_filter}
    ORDER BY EQUIPMENT_CODE, LOCAL_SHOT_TIME
    """


def fetch_full_data(session):
    """Fetch all historical ROI data from MASTER_SHOT_TABLE.

    Filters:
        - CT < 999.9 (exclude idle/stopped shots)
        - EQUIPMENT_CODE IS NOT NULL (must have equipment identifier)
        - VOLUME > 0 (must have volume data)

    Args:
        session: Snowflake Snowpark session

    Returns:
        pd.DataFrame: DataFrame with all historical ROI data
    """
    fq_table = _get_fq_table(session, "MASTER_SHOT_TABLE")
    logger.info(f"Fetching full historical data from {fq_table}...")

    sql_query = _build_roi_query(fq_table)
    start_time = time.time()
    df = session.sql(sql_query).to_pandas()
    elapsed = round(time.time() - start_time, 2)

    df.columns = [c.lower() for c in df.columns]
    logger.info(f"Retrieved {len(df):,} rows in {elapsed}s")
    return df


def fetch_incremental_data(session, start_date: str):
    """Fetch incremental ROI data from MASTER_SHOT_TABLE starting from start_date.

    Uses same filters as fetch_full_data() plus date filter.

    Args:
        session: Snowflake Snowpark session
        start_date: Start date for incremental processing (YYYY-MM-DD)

    Returns:
        pd.DataFrame: DataFrame with incremental ROI data
    """
    fq_table = _get_fq_table(session, "MASTER_SHOT_TABLE")
    logger.info(
        f"Fetching incremental data from {fq_table} (start_date: {start_date})..."
    )

    sql_query = _build_roi_query(fq_table, start_date=start_date)
    start_time = time.time()
    df = session.sql(sql_query).to_pandas()
    elapsed = round(time.time() - start_time, 2)

    df.columns = [c.lower() for c in df.columns]
    logger.info(f"Retrieved {len(df):,} incremental rows in {elapsed}s")
    return df


def validate_data(df):
    """Validate fetched data has all required columns.

    Args:
        df (pd.DataFrame): DataFrame to validate

    Raises:
        ValueError: If any required columns are missing
    """
    required_columns = [
        "supplier_name",
        "equipment_code",
        "ct",
        "approved_ct",
        "average_ct",
        "local_shot_time",
        "total_shot_count",
        "part_id",
        "mold_id",
        "supplier_id",
        "counter_id",
        "volume",
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    logger.info("Data validation passed - all required columns present")
