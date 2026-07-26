"""
Data Loading for Capacity Analysis.

Handles Snowflake connections and data fetching for capacity/OEE analysis.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import os
from typing import List, Optional

import pandas as pd  # type: ignore[import-untyped]

# Import shared utilities
from analysis.shared import create_snowflake_connection
from analysis.shared.local_source import is_local_data_enabled, query_capacity_shots


def init_env() -> None:
    """Load environment variables required for Snowflake connection (deprecated)."""
    # Environment variables now loaded automatically by shared utilities


def snowflake_connect(schema: Optional[str] = None):
    """
    Create a Snowflake connection using shared utilities.

    Args:
        schema: Optional schema/client override (e.g., "NORDPLAST", "AURELIA")

    Returns:
        Connection object for Snowflake database
    """
    return create_snowflake_connection(schema=schema)


def get_schema_name() -> str:
    """
    Get schema name from environment variables.

    Returns:
        str: Schema name (defaults to 'PUBLIC' if not set)
    """
    return os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")


def fetch_available_suppliers() -> List[str]:
    """
    Fetch available supplier names from the database.

    Returns:
        List[str]: Sorted list of available supplier names

    Example:
        >>> suppliers = fetch_available_suppliers()
        >>> print(suppliers[:3])
        ['Vantis industries SCS', 'Ford Motor Company', ...]
    """
    try:
        conn = snowflake_connect()
        query = """
        SELECT DISTINCT SUPPLIER_NAME 
        FROM MASTER_SHOT_TABLE 
        WHERE SUPPLIER_NAME IS NOT NULL 
            AND SUPPLIER_NAME != ''
        ORDER BY SUPPLIER_NAME
        """
        df = pd.read_sql(query, conn)
        conn.close()

        if not df.empty:
            suppliers = df["SUPPLIER_NAME"].tolist()
            print(f"✅ Found {len(suppliers)} suppliers")
            return suppliers
        else:
            print("⚠️ No suppliers found")
            return []

    except Exception as e:
        print(f"❌ Error fetching suppliers: {e}")
        return []


def fetch_available_equipment_codes(supplier_filter: Optional[str] = None) -> List[str]:
    """
    Fetch available equipment codes from the database.

    Args:
        supplier_filter: Optional supplier name to filter equipment codes

    Returns:
        List[str]: Sorted list of available equipment codes

    Example:
        >>> equipment = fetch_available_equipment_codes("Vantis industries SCS")
        >>> print(equipment[:3])
        ['EMA-4102', 'EMA-4101', ...]
    """
    try:
        conn = snowflake_connect()

        if supplier_filter:
            query = """
            SELECT DISTINCT EQUIPMENT_CODE 
            FROM MASTER_SHOT_TABLE 
            WHERE SUPPLIER_NAME = %s
                AND EQUIPMENT_CODE IS NOT NULL 
                AND EQUIPMENT_CODE != ''
            ORDER BY EQUIPMENT_CODE
            """
            df = pd.read_sql(query, conn, params=[supplier_filter])
        else:
            query = """
            SELECT DISTINCT EQUIPMENT_CODE 
            FROM MASTER_SHOT_TABLE 
            WHERE EQUIPMENT_CODE IS NOT NULL 
                AND EQUIPMENT_CODE != ''
            ORDER BY EQUIPMENT_CODE
            LIMIT 100
            """
            df = pd.read_sql(query, conn)

        conn.close()

        if not df.empty:
            equipment_codes = df["EQUIPMENT_CODE"].tolist()
            filter_msg = f" for supplier '{supplier_filter}'" if supplier_filter else ""
            print(f"✅ Found {len(equipment_codes)} equipment codes{filter_msg}")
            return equipment_codes
        else:
            print("⚠️ No equipment codes found")
            return []

    except Exception as e:
        print(f"❌ Error fetching equipment codes: {e}")
        return []


def fetch_equipment_data(
    equipment_code: str,
    supplier_name: Optional[str] = None,
    supplier_like: Optional[str] = None,
    start_ts: Optional[pd.Timestamp] = None,
    end_ts: Optional[pd.Timestamp] = None,
    schema: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch shot-level data for equipment and optional supplier/date filters.

    Args:
        equipment_code: Equipment code to fetch data for (REQUIRED)
        supplier_name: Exact supplier name match (optional)
        supplier_like: Partial supplier name match (optional)
        start_ts: Start timestamp for data range (optional)
        end_ts: End timestamp for data range (optional)
        schema: Optional schema/client override (e.g., "NORDPLAST", "AURELIA")

    Returns:
        pd.DataFrame: Shot-level data with columns:
            - SUPPLIER_NAME
            - EQUIPMENT_CODE
            - LOCAL_SHOT_TIME
            - ACTUAL_CT
            - APPROVED_CT

    Example:
        >>> df = fetch_equipment_data(
        ...     equipment_code="EMA-4102",
        ...     supplier_name="Vantis industries SCS",
        ...     start_ts=pd.Timestamp("2025-01-01"),
        ...     end_ts=pd.Timestamp("2025-12-31")
        ... )
        >>> print(df.head())
    """
    # Development path: serve the synthetic CSVs instead of querying Snowflake.
    if is_local_data_enabled():
        return query_capacity_shots(
            equipment_code=equipment_code,
            supplier_name=supplier_name,
            supplier_like=supplier_like,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    conn = snowflake_connect(schema=schema)

    # Explicitly set schema context if provided
    if schema:
        cursor = conn.cursor()
        cursor.execute(f"USE SCHEMA MMS.{schema}")
        cursor.close()
        print(f"🔍 Querying: MMS.{schema}.MASTER_SHOT_TABLE")

    try:
        query = (
            "SELECT SUPPLIER_NAME, EQUIPMENT_CODE, LOCAL_SHOT_TIME, CT AS ACTUAL_CT, APPROVED_CT "
            "FROM MASTER_SHOT_TABLE WHERE LOCAL_SHOT_TIME IS NOT NULL AND EQUIPMENT_CODE = %s "
            "AND CT < 999.9 AND VOLUME > 0"
        )
        params: List[object] = [equipment_code]

        if supplier_name:
            query += " AND UPPER(SUPPLIER_NAME) = UPPER(%s)"
            params.append(supplier_name)
        elif supplier_like:
            query += " AND SUPPLIER_NAME ILIKE %s"
            params.append(f"%{supplier_like}%")

        if start_ts is not None:
            query += " AND LOCAL_SHOT_TIME >= TO_TIMESTAMP(%s)"
            params.append(pd.to_datetime(start_ts).strftime("%Y-%m-%d %H:%M:%S"))
        if end_ts is not None:
            # Add 1 day to include the entire end date (00:00:00 to 23:59:59)
            end_ts_inclusive = pd.to_datetime(end_ts) + pd.Timedelta(days=1)
            query += " AND LOCAL_SHOT_TIME < TO_TIMESTAMP(%s)"
            params.append(end_ts_inclusive.strftime("%Y-%m-%d %H:%M:%S"))

        df = pd.read_sql(query, conn, params=params)
        df["LOCAL_SHOT_TIME"] = pd.to_datetime(df["LOCAL_SHOT_TIME"], errors="coerce")
        df = (
            df.dropna(subset=["LOCAL_SHOT_TIME"])
            .sort_values("LOCAL_SHOT_TIME")
            .reset_index(drop=True)
        )

        print(f"✅ Fetched {len(df)} shots for equipment {equipment_code}")
        return df
    finally:
        conn.close()
