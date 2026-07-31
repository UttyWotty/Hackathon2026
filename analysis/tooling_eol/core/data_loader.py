"""
Tooling EOL Data Loader.

This module handles all data loading from Snowflake for tooling end-of-life prediction.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from __future__ import annotations

import os
import re
from typing import Tuple

import pandas as pd
from snowflake.snowpark import Session

# Import shared utilities
from analysis.shared import get_logger, get_snowflake_connection_params

# Configure logging
logger = get_logger(__name__)


# ==================== Helper Functions ==================== #


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with all column names uppercased.

    Args:
        df: Input dataframe.

    Returns:
        DataFrame with uppercased column names.

    Note:
        This prevents KeyError when upstream tables deliver different cases
        (e.g., 'mold_id' vs 'MOLD_ID').
    """
    if df is None or df.empty:
        return df
    renamed = df.copy()
    renamed.columns = [str(c).upper() for c in renamed.columns]
    return renamed


def ensure_time_column(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure a 'LOCAL_SHOT_TIME' column exists, using common fallbacks.

    If 'LOCAL_SHOT_TIME' is missing, tries to use 'SHOT_TIME'.

    Args:
        df: Input dataframe

    Returns:
        DataFrame with LOCAL_SHOT_TIME column
    """
    if df is None or df.empty:
        return df
    if "LOCAL_SHOT_TIME" not in df.columns:
        if "SHOT_TIME" in df.columns:
            df = df.rename(columns={"SHOT_TIME": "LOCAL_SHOT_TIME"})
    return df


# ==================== Snowflake Connection ==================== #


def create_snowpark_session() -> Session:
    """Create and return a Snowpark session using P8 authentication.

    Returns:
        Session: Configured Snowpark session, or None in local data mode.

    Raises:
        ValueError: If required environment variables are missing
        Exception: If connection fails
    """
    from analysis.shared.local_source import is_local_data_enabled

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

        # Create session
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

        logger.info("✅ Connected to Snowflake using P8 authentication")
        return session

    except Exception as e:
        logger.error(f"❌ Failed to create Snowpark session: {e}")
        raise


def get_db_schema(session: Session) -> Tuple[str, str]:
    """Helper to get current database and schema from session.

    Args:
        session: Active Snowpark session

    Returns:
        Tuple of (database, schema)
    """
    return session.get_current_database(), session.get_current_schema()


# ==================== Data Loading Functions ==================== #


def read_master_shot_table(session: Session) -> pd.DataFrame:
    """Read essential fields from MASTER_SHOT_TABLE into a pandas DataFrame.

    The query keeps columns necessary for weekly rate, utilization, and EOL logic.

    Args:
        session: Active Snowflake Snowpark Session (None in local mode).

    Returns:
        pd.DataFrame with shot data including SHOT_COUNT column.
    """
    from analysis.shared.local_source import is_local_data_enabled

    if is_local_data_enabled():
        from analysis.shared.local_source import query_tooling_eol_shots

        logger.info("Reading MASTER_SHOT_TABLE from local dataset")
        return query_tooling_eol_shots()
    # Build fully qualified table name (allow cross-database via env)
    shots_db = os.getenv("SHOT_DB") or session.get_current_database() or "AI"
    shots_schema = os.getenv("SHOT_SCHEMA") or session.get_current_schema()
    fq_table = f"{shots_db}.{shots_schema}.MASTER_SHOT_TABLE"

    sql = f"""
        SELECT 
            SUPPLIER_NAME,
            EQUIPMENT_CODE,
            COUNTER_CODE,
            CT,
            APPROVED_CT,
            LOCAL_SHOT_TIME,
            VOLUME,
            COUNTER_ID,
            MOLD_ID,
            COMPANY_ID,
            PART_ID,
            TOOLING_TYPE,
            CT_STATUS
        FROM {fq_table}
        WHERE LOCAL_SHOT_TIME IS NOT NULL
    """

    logger.info(f"Reading MASTER_SHOT_TABLE from {fq_table}")
    df = session.sql(sql).to_pandas()
    df = normalize_columns(df)
    df = ensure_time_column(df)

    # Normalize dtypes
    if "LOCAL_SHOT_TIME" in df.columns:
        df["LOCAL_SHOT_TIME"] = pd.to_datetime(df["LOCAL_SHOT_TIME"], errors="coerce")

    # Ensure core numeric fields are numeric
    # Note: PART_ID is now STRING (part_code format like "218-155"), not numeric
    for col in [
        "CT",
        "APPROVED_CT",
        "VOLUME",
        "COUNTER_ID",
        "MOLD_ID",
        "COMPANY_ID",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Shots proxy: one row equals one shot
    df["SHOT_COUNT"] = 1

    return df


def read_maintenance_events(session: Session) -> pd.DataFrame:
    """Read optional maintenance events from WORK_ORDER and MOLD_MAINTENANCE.

    Only WORK_ORDER rows with STATUS='completed' are used. If tables/columns
    are missing, returns an empty DataFrame and caller can warn accordingly.

    Args:
        session: Active Snowpark session (None in local mode).

    Returns:
        pd.DataFrame with columns ['MOLD_ID','EVENT_TS','SOURCE'] when available.
    """
    from analysis.shared.local_source import is_local_data_enabled

    if is_local_data_enabled():
        from analysis.shared.local_source import query_tooling_eol_maintenance

        logger.info("Reading maintenance events from local dataset")
        return query_tooling_eol_maintenance()
    # Maintenance in MMS by default; overridable via env
    database = os.getenv("MAINT_DB", "MMS")
    schema = os.getenv("MAINT_SCHEMA", session.get_current_schema())

    # Validate database/schema names to prevent SQL injection
    # SQL identifiers must be alphanumeric, underscore, or quoted
    if not re.match(r"^[a-zA-Z0-9_]+$", database):
        raise ValueError(f"Invalid database name format: {database}")
    if not re.match(r"^[a-zA-Z0-9_]+$", schema):
        raise ValueError(f"Invalid schema name format: {schema}")

    candidates: list[pd.DataFrame] = []

    # WORK_ORDER (completed only)
    try:
        wo_sql = f"SELECT MOLD_ID, COMPLETED_AT FROM {database}.{schema}.WORK_ORDER WHERE STATUS ILIKE 'completed'"
        wo = session.sql(wo_sql).to_pandas()
        wo = normalize_columns(wo)
        if "MOLD_ID" in wo.columns:
            # Identify timestamp column
            ts_col = None
            for c in [
                "COMPLETED_AT",
                "COMPLETION_TIME",
                "END_AT",
                "UPDATED_AT",
                "FINISHED_AT",
            ]:
                if c in wo.columns:
                    ts_col = c
                    break
            if ts_col is not None:
                out = pd.DataFrame(
                    {
                        "MOLD_ID": wo["MOLD_ID"],
                        "EVENT_TS": pd.to_datetime(wo[ts_col], errors="coerce"),
                        "SOURCE": "WORK_ORDER",
                    }
                ).dropna(subset=["EVENT_TS"])
                candidates.append(out)
    except Exception as exc:
        logger.warning(f"WORK_ORDER read skipped: {exc}")

    # MOLD_MAINTENANCE (use all events; filterable if STATUS exists)
    try:
        mm_sql = f"SELECT * FROM {database}.{schema}.MOLD_MAINTENANCE"
        mm = session.sql(mm_sql).to_pandas()
        mm = normalize_columns(mm)
        if "MOLD_ID" in mm.columns:
            # Prefer rows with STATUS='completed' if STATUS exists
            if "STATUS" in mm.columns:
                mm = mm[mm["STATUS"].astype(str).str.lower() == "completed"]
            # Identify timestamp column
            ts_col = None
            for c in [
                "MAINTENANCE_DATE",
                "EVENT_TS",
                "COMPLETED_AT",
                "DATE",
                "TIMESTAMP",
            ]:
                if c in mm.columns:
                    ts_col = c
                    break
            if ts_col is not None:
                out = pd.DataFrame(
                    {
                        "MOLD_ID": mm["MOLD_ID"],
                        "EVENT_TS": pd.to_datetime(mm[ts_col], errors="coerce"),
                        "SOURCE": "MOLD_MAINTENANCE",
                    }
                ).dropna(subset=["EVENT_TS"])
                candidates.append(out)
    except Exception as exc:
        logger.warning(f"MOLD_MAINTENANCE read skipped: {exc}")

    if not candidates:
        return pd.DataFrame(columns=["MOLD_ID", "EVENT_TS", "SOURCE"])

    events = pd.concat(candidates, axis=0, ignore_index=True)
    events = events.dropna(subset=["MOLD_ID", "EVENT_TS"])
    # Ensure types
    events["MOLD_ID"] = pd.to_numeric(events["MOLD_ID"], errors="coerce")
    events = events.dropna(subset=["MOLD_ID"])
    events["MOLD_ID"] = events["MOLD_ID"].astype(int)
    return events


def read_mold_table(session: Session) -> pd.DataFrame:
    """Read essential fields from MOLD table for enrichment.

    Pulls designed shots and capacity-related fields to complement MASTER_SHOT_TABLE.

    Args:
        session: Active Snowflake Snowpark Session (None in local mode).

    Returns:
        pd.DataFrame with mold reference columns.
    """
    from analysis.shared.local_source import is_local_data_enabled

    if is_local_data_enabled():
        from analysis.shared.local_source import query_tooling_eol_mold

        logger.info("Reading MOLD table from local dataset")
        return query_tooling_eol_mold()
    mold_db = os.getenv("MOLD_DB", "MMS")
    mold_schema = os.getenv("MOLD_SCHEMA", session.get_current_schema())
    fq_mold = f"{mold_db}.{mold_schema}.MOLD"
    sql = f"""
        SELECT
            ID AS MOLD_ID,
            EQUIPMENT_CODE,
            DESIGNED_SHOT,
            DAILY_MAX_CAPACITY,
            PRODUCTION_DAYS,
            SHIFTS_PER_DAY
        FROM {fq_mold}
    """
    logger.info(f"Reading MOLD table from {fq_mold}")
    mold = session.sql(sql).to_pandas()
    mold = normalize_columns(mold)

    # Ensure numeric types where appropriate
    for col in [
        "MOLD_ID",
        "DESIGNED_SHOT",
        "DAILY_MAX_CAPACITY",
        "PRODUCTION_DAYS",
        "SHIFTS_PER_DAY",
    ]:
        if col in mold.columns:
            mold[col] = pd.to_numeric(mold[col], errors="coerce")

    return mold
