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
        (e.g., 'tool_id' vs 'TOOL_ID').
    """
    if df is None or df.empty:
        return df
    renamed = df.copy()
    renamed.columns = [str(c).upper() for c in renamed.columns]
    return renamed


def ensure_time_column(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure a 'SHOT_TIME' column exists, using common fallbacks.

    If 'SHOT_TIME' is missing, tries to use 'SHOT_TIME'.

    Args:
        df: Input dataframe

    Returns:
        DataFrame with SHOT_TIME column
    """
    if df is None or df.empty:
        return df
    if "SHOT_TIME" not in df.columns:
        if "SHOT_TIME" in df.columns:
            df = df.rename(columns={"SHOT_TIME": "SHOT_TIME"})
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


def read_shot_data(session: Session) -> pd.DataFrame:
    """Read essential fields from SHOT_DATA into a pandas DataFrame.

    The query keeps columns necessary for weekly rate, utilization, and EOL logic.

    Args:
        session: Active Snowflake Snowpark Session (None in local mode).

    Returns:
        pd.DataFrame with shot data including SHOT_COUNT column.
    """
    from analysis.shared.local_source import is_local_data_enabled

    if is_local_data_enabled():
        from analysis.shared.local_source import query_tooling_eol_shots

        logger.info("Reading SHOT_DATA from local dataset")
        return query_tooling_eol_shots()
    # Build fully qualified table name (allow cross-database via env)
    shots_db = os.getenv("SHOT_DB") or session.get_current_database() or "AI"
    shots_schema = os.getenv("SHOT_SCHEMA") or session.get_current_schema()
    fq_table = f"{shots_db}.{shots_schema}.SHOT_DATA"

    sql = f"""
        SELECT 
            VENDOR_NAME,
            MACHINE_ID,
            SENSOR_CODE,
            duration,
            TARGET_DURATION,
            SHOT_TIME,
            VOLUME,
            SENSOR_ID,
            TOOL_ID,
            VENDOR_ID,
            PRODUCT_ID,
            TYPE,
            STATUS
        FROM {fq_table}
        WHERE SHOT_TIME IS NOT NULL
    """

    logger.info(f"Reading SHOT_DATA from {fq_table}")
    df = session.sql(sql).to_pandas()
    df = normalize_columns(df)
    df = ensure_time_column(df)

    # Normalize dtypes
    if "SHOT_TIME" in df.columns:
        df["SHOT_TIME"] = pd.to_datetime(df["SHOT_TIME"], errors="coerce")

    # Ensure core numeric fields are numeric
    # Note: PRODUCT_ID is now STRING (product_code format like "218-155"), not numeric
    for col in [
        "DURATION",
        "TARGET_DURATION",
        "VOLUME",
        "SENSOR_ID",
        "TOOL_ID",
        "VENDOR_ID",
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
        pd.DataFrame with columns ['TOOL_ID','EVENT_TS','SOURCE'] when available.
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
        wo_sql = f"SELECT TOOL_ID, COMPLETED_AT FROM {database}.{schema}.WORK_ORDER WHERE STATUS ILIKE 'completed'"
        wo = session.sql(wo_sql).to_pandas()
        wo = normalize_columns(wo)
        if "TOOL_ID" in wo.columns:
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
                        "TOOL_ID": wo["TOOL_ID"],
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
        if "TOOL_ID" in mm.columns:
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
                        "TOOL_ID": mm["TOOL_ID"],
                        "EVENT_TS": pd.to_datetime(mm[ts_col], errors="coerce"),
                        "SOURCE": "MOLD_MAINTENANCE",
                    }
                ).dropna(subset=["EVENT_TS"])
                candidates.append(out)
    except Exception as exc:
        logger.warning(f"MOLD_MAINTENANCE read skipped: {exc}")

    if not candidates:
        return pd.DataFrame(columns=["TOOL_ID", "EVENT_TS", "SOURCE"])

    events = pd.concat(candidates, axis=0, ignore_index=True)
    events = events.dropna(subset=["TOOL_ID", "EVENT_TS"])
    # Ensure types
    events["TOOL_ID"] = pd.to_numeric(events["TOOL_ID"], errors="coerce")
    events = events.dropna(subset=["TOOL_ID"])
    events["TOOL_ID"] = events["TOOL_ID"].astype(int)
    return events


def read_tool_table(session: Session) -> pd.DataFrame:
    """Read essential fields from TOOL table for enrichment.

    Pulls designed shots and capacity-related fields to complement SHOT_DATA.

    Args:
        session: Active Snowflake Snowpark Session (None in local mode).

    Returns:
        pd.DataFrame with mold reference columns.
    """
    from analysis.shared.local_source import is_local_data_enabled

    if is_local_data_enabled():
        from analysis.shared.local_source import query_tooling_eol_mold

        logger.info("Reading TOOL table from local dataset")
        return query_tooling_eol_mold()
    mold_db = os.getenv("MOLD_DB", "MMS")
    mold_schema = os.getenv("MOLD_SCHEMA", session.get_current_schema())
    fq_mold = f"{mold_db}.{mold_schema}.MOLD"
    sql = f"""
        SELECT
            ID AS TOOL_ID,
            MACHINE_ID,
            DESIGNED_SHOT,
            MAX_DAILY_OUTPUT,
            PRODUCTION_DAYS,
            SHIFTS_PER_DAY
        FROM {fq_mold}
    """
    logger.info(f"Reading TOOL table from {fq_mold}")
    mold = session.sql(sql).to_pandas()
    mold = normalize_columns(mold)

    # Ensure numeric types where appropriate
    for col in [
        "TOOL_ID",
        "DESIGNED_SHOT",
        "MAX_DAILY_OUTPUT",
        "PRODUCTION_DAYS",
        "SHIFTS_PER_DAY",
    ]:
        if col in mold.columns:
            mold[col] = pd.to_numeric(mold[col], errors="coerce")

    return mold
