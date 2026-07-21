"""Data Fetcher Module
===================

Handles data extraction from MASTER_SHOT_TABLE with complex sessionization logic.
"""

import logging
import os
import time

from utils.sql_validation import validate_date_param

from .config import SESSION_GAP_HOURS

logger = logging.getLogger("ANA_SHOT_MADE")

SESSION_GAP_SECONDS = SESSION_GAP_HOURS * 3600


def _build_sessionization_sql(
    master_fq: str, include_date_filter: bool = False, start_date: str = None
):
    """Build the complex SQL query for sessionization and performance metrics.

    Sessionization logic:
        - 8-hour gap between shots starts new session
        - ISO week change starts new session
        - Equipment-centric sessionization (COUNTER_CODE changes don't break sessions)
        - Includes idle shots (CT >= 999.9) in total count but excludes from performance metrics

    Args:
        master_fq: Fully qualified table name for MASTER_SHOT_TABLE
        include_date_filter: Whether to include incremental date filter
        start_date: Start date for incremental processing (YYYY-MM-DD)

    Returns:
        str: Complete SQL query
    """
    date_filter = (
        f"AND DATE(ms.LOCAL_SHOT_TIME) >= '{validate_date_param(start_date)}'::DATE"
        if include_date_filter and start_date
        else ""
    )
    return f"""WITH Base AS (
        SELECT
        co.name AS COMPANY_NAME,
        lo.name AS PLANT_NAME,
        ms.EQUIPMENT_CODE,
        ms.COUNTER_CODE,
        ms.CT,
        ms.TEMPERATURE,
        ms.LOCAL_SHOT_TIME,
        ms.MOLD_ID,
        ms.COMPANY_ID,
        ms.VOLUME,
        m.cycle_time_limit1,
        m.cycle_time_limit1unit,
        m.cycle_time_limit2,
        m.cycle_time_limit2unit,
        (m.contracted_cycle_time / 10) AS CONTRACTED_CYCLE_TIME
        FROM {master_fq} ms
        LEFT JOIN MOLD m ON m.ID = ms.MOLD_ID
        LEFT JOIN COMPANY co ON co.ID = ms.COMPANY_ID
        LEFT JOIN LOCATION lo ON lo.ID = m.location_id
        WHERE ms.EQUIPMENT_CODE IS NOT NULL
        AND ms.VOLUME > 0
        {date_filter}
    ),
    AdjustedLimits AS (
        SELECT
        b.*,
        CASE WHEN b.CT >= 999.9 THEN 'idle' ELSE 'active' END AS CYCLE_TIME_STATUS,
        CASE WHEN b.cycle_time_limit1unit = 'PERCENTAGE'
            THEN (b.CONTRACTED_CYCLE_TIME * (1 + (b.cycle_time_limit1 / 100)))
            ELSE (b.CONTRACTED_CYCLE_TIME + b.cycle_time_limit1) END AS L1_ABOVE_ADJUSTED,
        CASE WHEN b.cycle_time_limit2unit = 'PERCENTAGE'
            THEN (b.CONTRACTED_CYCLE_TIME * (1 + (b.cycle_time_limit2 / 100)))
            ELSE (b.CONTRACTED_CYCLE_TIME + b.cycle_time_limit2) END AS L2_ABOVE_ADJUSTED,
        CASE WHEN b.cycle_time_limit1unit = 'PERCENTAGE'
            THEN (b.CONTRACTED_CYCLE_TIME * (1 - (b.cycle_time_limit1 / 100)))
            ELSE (b.CONTRACTED_CYCLE_TIME - b.cycle_time_limit1) END AS L1_BELOW_ADJUSTED,
        CASE WHEN b.cycle_time_limit2unit = 'PERCENTAGE'
            THEN (b.CONTRACTED_CYCLE_TIME * (1 - (b.cycle_time_limit2 / 100)))
            ELSE (b.CONTRACTED_CYCLE_TIME - b.cycle_time_limit2) END AS L2_BELOW_ADJUSTED
        FROM Base b
    ),
    Enriched AS (
        SELECT
        a.*,
        -- Performance metrics: reference pre-computed adjusted limits
        CASE WHEN a.CT >= 999.9 THEN 0
            WHEN a.CT > a.L1_ABOVE_ADJUSTED THEN 1
            ELSE 0 END AS ABOVE_COUNT,
        CASE WHEN a.CT >= 999.9 THEN 0
            WHEN a.CT BETWEEN a.L1_BELOW_ADJUSTED AND a.L1_ABOVE_ADJUSTED THEN 1
            ELSE 0 END AS WITHIN_COUNT,
        CASE WHEN a.CT >= 999.9 THEN 0
            WHEN a.CT < a.L1_BELOW_ADJUSTED THEN 1
            ELSE 0 END AS BELOW_COUNT,
        -- Average CT calculations: reference pre-computed adjusted limits
        ROUND(CASE WHEN a.CT >= 999.9 THEN NULL
            WHEN a.CT > a.L1_ABOVE_ADJUSTED THEN a.CT END, 2) AS ABOVE_AVG_CT,
        ROUND(CASE WHEN a.CT >= 999.9 THEN NULL
            WHEN a.CT BETWEEN a.L1_BELOW_ADJUSTED AND a.L1_ABOVE_ADJUSTED THEN a.CT END, 2) AS WITHIN_AVG_CT,
        ROUND(CASE WHEN a.CT >= 999.9 THEN NULL
            WHEN a.CT < a.L1_BELOW_ADJUSTED THEN a.CT END, 2) AS BELOW_AVG_CT,
        -- Total shot count: include all shots (including idle)
        1 AS SHOTS_MADE
        FROM AdjustedLimits a
    ),
    DistinctShots AS (
        SELECT e.*
        FROM Enriched e
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY e.COMPANY_NAME, e.PLANT_NAME, e.EQUIPMENT_CODE, e.COUNTER_CODE, e.LOCAL_SHOT_TIME
            ORDER BY e.CT DESC
        ) = 1
    ),
    SortedData AS (
        SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY e.COMPANY_NAME, e.PLANT_NAME, e.EQUIPMENT_CODE
            ORDER BY e.LOCAL_SHOT_TIME
        ) AS ROWNUM
        FROM DistinctShots e
    ),
    SessionGroups AS (
        SELECT
        t1.*,
        CASE
            WHEN DATEDIFF('SECOND', LAG(t1.LOCAL_SHOT_TIME) OVER (
                PARTITION BY t1.COMPANY_NAME, t1.PLANT_NAME, t1.EQUIPMENT_CODE
                ORDER BY t1.LOCAL_SHOT_TIME
            ), t1.LOCAL_SHOT_TIME) > {SESSION_GAP_SECONDS}  -- {SESSION_GAP_HOURS} hours
            THEN 1
            WHEN DATE_PART('WEEKISO', LAG(t1.LOCAL_SHOT_TIME) OVER (
                PARTITION BY t1.COMPANY_NAME, t1.PLANT_NAME, t1.EQUIPMENT_CODE
                ORDER BY t1.LOCAL_SHOT_TIME
            )) <> DATE_PART('WEEKISO', t1.LOCAL_SHOT_TIME)
            THEN 1
            ELSE 0
        END AS NEWSESSIONFLAGRENAMED
        FROM SortedData t1
    ),
    SessionIDAssign AS (
        SELECT
        sg.*,
        SUM(sg.NEWSESSIONFLAGRENAMED) OVER (
            PARTITION BY sg.COMPANY_NAME, sg.PLANT_NAME, sg.EQUIPMENT_CODE
            ORDER BY sg.LOCAL_SHOT_TIME
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) + 1 AS SESSIONID
        FROM SessionGroups sg
    ),
    SessionWithLastCT AS (
        SELECT
        s.*,
        LAST_VALUE(s.CT) OVER (
            PARTITION BY s.COMPANY_NAME, s.PLANT_NAME, s.EQUIPMENT_CODE, s.SESSIONID
            ORDER BY s.LOCAL_SHOT_TIME
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS last_CT,
        LEAD(s.LOCAL_SHOT_TIME) OVER (
            PARTITION BY s.COMPANY_NAME, s.PLANT_NAME, s.EQUIPMENT_CODE, s.SESSIONID
            ORDER BY s.LOCAL_SHOT_TIME
        ) AS next_time
        FROM SessionIDAssign s
    ),
    PerInterval AS (
        SELECT
        p.*,
        DATEDIFF('SECOND', p.LOCAL_SHOT_TIME, p.next_time) AS gap_sec,
        -- Production time: exclude idle shots (CT >= 999.9)
        CASE
            WHEN p.CT >= 999.9 THEN 0 -- Idle shots contribute 0 to production time
            WHEN p.next_time IS NULL THEN p.last_CT
            ELSE LEAST(GREATEST(DATEDIFF('SECOND', p.LOCAL_SHOT_TIME, p.next_time), 0), p.CT)
        END AS prod_sec,
        CASE
            WHEN p.next_time IS NULL THEN 0
            ELSE GREATEST(DATEDIFF('SECOND', p.LOCAL_SHOT_TIME, p.next_time) - p.CT, 0)
        END AS idle_sec
        FROM SessionWithLastCT p
    ),
    AggregatedSessions AS (
        SELECT
        COMPANY_NAME, PLANT_NAME, EQUIPMENT_CODE, SESSIONID,
        MIN(LOCAL_SHOT_TIME) AS SESSIONSTARTTIME,
        MAX(LOCAL_SHOT_TIME) AS SESSIONENDTIME,
        SUM(prod_sec) AS PRODUCTION_TIME,
        SUM(idle_sec) AS IDLE_TIME,
        SUM(prod_sec) + SUM(idle_sec) AS TOTAL_RUNTIME
        FROM PerInterval
        GROUP BY 1,2,3,4
    )

    SELECT
    sa.COMPANY_NAME,
    sa.PLANT_NAME,
    sa.EQUIPMENT_CODE,
    sa.COUNTER_CODE,
    sa.CYCLE_TIME_STATUS,
    sa.LOCAL_SHOT_TIME,
    sa.CYCLE_TIME_LIMIT1,
    sa.CYCLE_TIME_LIMIT1UNIT,
    sa.CYCLE_TIME_LIMIT2,
    sa.CYCLE_TIME_LIMIT2UNIT,
    sa.L1_ABOVE_ADJUSTED,
    sa.L2_ABOVE_ADJUSTED,
    sa.L1_BELOW_ADJUSTED,
    sa.L2_BELOW_ADJUSTED,
    sa.CONTRACTED_CYCLE_TIME,
    sa.ABOVE_COUNT,
    sa.WITHIN_COUNT,
    sa.BELOW_COUNT,
    sa.CT,
    sa.TEMPERATURE,
    sa.ABOVE_AVG_CT,
    sa.WITHIN_AVG_CT,
    sa.BELOW_AVG_CT,
    sa.SHOTS_MADE,
    sa.ROWNUM,
    sa.NEWSESSIONFLAGRENAMED,
    sa.SESSIONID,
    a.SESSIONSTARTTIME,
    a.SESSIONENDTIME,
    a.PRODUCTION_TIME,
    a.TOTAL_RUNTIME,
    GREATEST(a.TOTAL_RUNTIME - a.PRODUCTION_TIME, 0) AS IDLE_TIME,
    LEAST(100.0, 100.0 * (a.PRODUCTION_TIME / NULLIF(a.TOTAL_RUNTIME, 0))) AS UPTIME_PERCENTAGE,
    DAYOFWEEKISO(sa.LOCAL_SHOT_TIME) AS ISODAY,
    YEAROFWEEKISO(sa.LOCAL_SHOT_TIME) AS ISOYEAR,
    WEEKISO(sa.LOCAL_SHOT_TIME) AS ISOWEEK,
    MONTH(sa.LOCAL_SHOT_TIME) AS ISOMONTH,
    TO_VARCHAR(sa.LOCAL_SHOT_TIME, 'YYYYMMDD') AS DAY,
    TO_VARCHAR(DATE_TRUNC('month', sa.LOCAL_SHOT_TIME), 'YYYYMM') AS MONTH,
    TO_VARCHAR(DATE_TRUNC('year', sa.LOCAL_SHOT_TIME), 'YYYY') AS YEAR,
    TO_VARCHAR(YEAROFWEEKISO(sa.LOCAL_SHOT_TIME)) || LPAD(TO_VARCHAR(WEEKISO(sa.LOCAL_SHOT_TIME)), 2, '0') AS WEEK,
    TO_VARCHAR(DATE_TRUNC('quarter', sa.LOCAL_SHOT_TIME), 'YYYY') || LPAD(TO_VARCHAR(DATE_PART('quarter', sa.LOCAL_SHOT_TIME)), 1, '0') AS QUARTER
    FROM AggregatedSessions a
    JOIN SessionIDAssign sa
    ON a.COMPANY_NAME = sa.COMPANY_NAME
    AND a.PLANT_NAME = sa.PLANT_NAME
    AND a.EQUIPMENT_CODE = sa.EQUIPMENT_CODE
    AND a.SESSIONID = sa.SESSIONID
    ORDER BY a.EQUIPMENT_CODE, a.SESSIONID
    """


def fetch_full_data(session):
    """Fetch all historical data from MASTER_SHOT_TABLE with sessionization logic.

    Builds ANA_SHOT_MADE_TABLE directly from MASTER_SHOT_TABLE by:
        - Sessionizing per (COMPANY_NAME, PLANT_NAME, EQUIPMENT_CODE)
        - Dedup per exact LOCAL_SHOT_TIME within the group
        - 8-hour gap or ISO week change starts a new session
        - Equipment-centric sessionization (COUNTER_CODE changes don't break sessions)
        - Includes idle shots (CT >= 999.9) in total shot count
        - Excludes idle shots from performance metrics
        - Computes per-shot threshold flags and session KPIs

    Args:
        session: Snowflake Snowpark session

    Returns:
        pd.DataFrame: DataFrame with all historical data
    """
    shots_db = (os.getenv("SHOT_DB") or session.get_current_database()).strip('"')
    shots_schema = (os.getenv("SHOT_SCHEMA") or session.get_current_schema()).strip('"')
    master_fq = f"{shots_db}.{shots_schema}.MASTER_SHOT_TABLE"
    logger.info(f"Fetching full historical data from {master_fq}...")

    sql_query = _build_sessionization_sql(master_fq, include_date_filter=False)

    start_time = time.time()
    df = session.sql(sql_query).to_pandas()
    elapsed = round(time.time() - start_time, 2)

    logger.info(f"Retrieved {len(df):,} rows in {elapsed}s")
    logger.info(f"Columns: {df.columns.tolist()}")
    return df


def fetch_incremental_data(session, start_date: str):
    """Fetch incremental data from MASTER_SHOT_TABLE starting from start_date.

    Uses same sessionization logic as fetch_full_data() plus date filter:
        - DATE(LOCAL_SHOT_TIME) >= start_date

    Args:
        session: Snowflake Snowpark session
        start_date: Start date for incremental processing (YYYY-MM-DD)

    Returns:
        pd.DataFrame: DataFrame with incremental data
    """
    shots_db = (os.getenv("SHOT_DB") or session.get_current_database()).strip('"')
    shots_schema = (os.getenv("SHOT_SCHEMA") or session.get_current_schema()).strip('"')
    master_fq = f"{shots_db}.{shots_schema}.MASTER_SHOT_TABLE"
    logger.info(
        f"Fetching incremental data from {master_fq} (start_date: {start_date})..."
    )

    sql_query = _build_sessionization_sql(
        master_fq, include_date_filter=True, start_date=start_date
    )

    start_time = time.time()
    df = session.sql(sql_query).to_pandas()
    elapsed = round(time.time() - start_time, 2)

    logger.info(f"Retrieved {len(df):,} incremental rows in {elapsed}s")
    return df


def validate_data(df):
    """Validate fetched data has all required columns.

    Required columns:
        - 41 columns including COMPANY_NAME, PLANT_NAME, EQUIPMENT_CODE, etc.

    Args:
        df (pd.DataFrame): DataFrame to validate

    Raises:
        ValueError: If any required columns are missing
    """
    required_columns = [
        "COMPANY_NAME",
        "PLANT_NAME",
        "EQUIPMENT_CODE",
        "COUNTER_CODE",
        "CYCLE_TIME_STATUS",
        "LOCAL_SHOT_TIME",
        "CYCLE_TIME_LIMIT1",
        "CYCLE_TIME_LIMIT1UNIT",
        "CYCLE_TIME_LIMIT2",
        "CYCLE_TIME_LIMIT2UNIT",
        "L1_ABOVE_ADJUSTED",
        "L2_ABOVE_ADJUSTED",
        "L1_BELOW_ADJUSTED",
        "L2_BELOW_ADJUSTED",
        "CONTRACTED_CYCLE_TIME",
        "ABOVE_COUNT",
        "WITHIN_COUNT",
        "BELOW_COUNT",
        "CT",
        "TEMPERATURE",
        "ABOVE_AVG_CT",
        "WITHIN_AVG_CT",
        "BELOW_AVG_CT",
        "SHOTS_MADE",
        "ROWNUM",
        "NEWSESSIONFLAGRENAMED",
        "SESSIONID",
        "SESSIONSTARTTIME",
        "SESSIONENDTIME",
        "PRODUCTION_TIME",
        "TOTAL_RUNTIME",
        "IDLE_TIME",
        "UPTIME_PERCENTAGE",
        "ISODAY",
        "ISOYEAR",
        "ISOWEEK",
        "ISOMONTH",
        "DAY",
        "MONTH",
        "YEAR",
        "WEEK",
        "QUARTER",
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    logger.info("Data validation passed - all required columns present")
