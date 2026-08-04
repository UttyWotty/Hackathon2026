# Imports
"""
Imports necessary modules for Snowflake connection, environment handling,
data processing with pandas and numpy, and timing.
"""

import os
import time

import pandas as pd
from dotenv import load_dotenv
from snowflake.connector.pandas_tools import write_pandas
from snowflake.snowpark import Session

# Import shared utilities
from analysis.shared import create_snowflake_connection

# Use shared logging utility (module-specific logger, no root-logger pollution)
from analysis.shared.error_handling import ProcessingError
from analysis.shared.logging import setup_module_logger

logger = setup_module_logger("DEMO_TABLE")

# ---------------------------------------------------------------------
# Load Snowflake credentials from .env


"""
Loads Snowflake connection using shared utilities.
Connection is created lazily when needed.
"""
load_dotenv()

# Module-level connection variables (created lazily)
session = None
sf_conn = None


def get_connection():
    """Get or create Snowflake connection using shared utilities."""
    global sf_conn
    if sf_conn is None:
        sf_conn = create_snowflake_connection()
        logger.info("✅ Connected to Snowflake")
    return sf_conn


def get_session():
    """Get or create Snowflake Snowpark session using shared connection."""
    global session
    if session is None:
        # Get connection using shared utilities
        conn = get_connection()

        # Create Snowpark session from existing connection
        session = Session.builder.configs({"connection": conn}).create()

        # CRITICAL: Set statement timeout via ALTER SESSION (Snowpark requires this)
        # Default is often 60 seconds, which causes failures around 71 seconds
        import os

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

        logger.info("✅ Created Snowflake Snowpark session")
    return session


# -------------------------------------------------------
def fetch_data_from_snowflake(session=None):
    """
    Fetches data from the existing DEMO_TABLE in Snowflake.

    Args:
        session (snowflake.snowpark.Session): Active Snowflake session (optional - created if None).

    Returns:
        pd.DataFrame: DataFrame containing shot records with tooling info.
    """
    logger.info("=" * 80)
    logger.info("🚀 Starting fetch_data_from_snowflake")
    logger.info("=" * 80)

    # Get session if not provided
    if session is None:
        logger.info("📡 Creating new Snowflake session...")
        session = get_session()
        logger.info("✅ Session created successfully")

    # Query DEMO_TABLE directly (RCA uses raw data)
    # RCA needs the full shot-level data for root cause analysis
    # Get database and schema from environment
    database = os.getenv("SNOWFLAKE_DATABASE", "MMS")
    schema = os.getenv("SNOWFLAKE_SCHEMA", "NORDPLAST")

    # Validate database/schema names to prevent SQL injection
    # SQL identifiers must be alphanumeric, underscore, or quoted
    import re

    if not re.match(r"^[a-zA-Z0-9_]+$", database):
        raise ValueError(f"Invalid database name format: {database}")
    if not re.match(r"^[a-zA-Z0-9_]+$", schema):
        raise ValueError(f"Invalid schema name format: {schema}")

    logger.info("Environment variables:")
    logger.info(f"   Database: {database}")
    logger.info(f"   Schema: {schema}")
    logger.info(f"   Target table: {database}.{schema}.DEMO_TABLE")

    # First, check if table exists and has data
    try:
        check_query = (
            f"SELECT COUNT(*) as ROW_COUNT FROM {database}.{schema}.DEMO_TABLE"
        )
        logger.info(f"🔍 Checking table existence: {check_query}")

        count_df = session.sql(check_query).to_pandas()

        # Debug: Log the DataFrame info
        logger.info(f"DataFrame columns: {count_df.columns.tolist()}")
        logger.info(f"DataFrame shape: {count_df.shape}")
        logger.info(f"DataFrame dtypes: {count_df.dtypes.to_dict()}")
        logger.info(f"DataFrame head:\n{count_df.head()}")

        # Snowflake returns uppercase column names by default
        total_rows = count_df["ROW_COUNT"].iloc[0] if not count_df.empty else 0
        logger.info(f"📊 DEMO_TABLE has {total_rows:,} total rows")

        if total_rows == 0:
            logger.error("❌ DEMO_TABLE exists but is empty!")
            return pd.DataFrame()
    except Exception as e:
        logger.error(f"❌ Error checking DEMO_TABLE: {str(e)}")
        logger.error(f"❌ Error type: {type(e).__name__}")
        logger.error("💡 Table might not exist or you don't have access")
        import traceback

        full_traceback = traceback.format_exc()
        logger.error(f"Full traceback:\n{full_traceback}")
        return pd.DataFrame()

    sql_query = f"""
    SELECT 
        SUPPLIER_NAME,
        EQUIPMENT_CODE,
        COUNTER_CODE,
        CT,
        APPROVED_CT,
        TEMPERATURE,
        PART_NAME,
        TOOLING_TYPE,
        TOOLING_TYPE AS TOOLING_FAMILY,
        CT_STATUS,
        LOCAL_SHOT_TIME,
        VOLUME,
        COUNTER_ID,
        MOLD_ID,
        COMPANY_ID,
        PART_ID
    FROM {database}.{schema}.DEMO_TABLE
    WHERE SUPPLIER_NAME IS NOT NULL 
    AND PART_NAME IS NOT NULL
    ORDER BY LOCAL_SHOT_TIME DESC
    LIMIT 100000
    """
    start_time = time.time()
    logger.info("🔍 Executing main data query...")
    logger.info(f"Full query: {sql_query}")
    logger.info(f"🔍 Querying: {database}.{schema}.DEMO_TABLE")

    try:
        df = session.sql(sql_query).to_pandas()
        elapsed = round(time.time() - start_time, 2)
        logger.info(f"✅ Query executed in {elapsed} seconds")
        logger.info(f"✅ Retrieved {len(df)} rows from DEMO_TABLE")
        logger.info(f"📊 DataFrame shape: {df.shape}")
        logger.info(f"📊 DataFrame columns: {df.columns.tolist()}")
        logger.info(
            f"✅ Retrieved {len(df):,} rows from DEMO_TABLE in {elapsed}s"
        )
    except Exception as e:
        logger.error(f"❌ Error executing main query: {str(e)}")
        raise ProcessingError(f"DEMO_TABLE query failed: {e}") from e

    if len(df) > 0:
        logger.info(
            f"Sample equipment codes in data: {df['EQUIPMENT_CODE'].unique()[:10].tolist()}"
        )
        logger.info(
            f"🔧 Available equipment: {df['EQUIPMENT_CODE'].nunique()} unique codes"
        )
        logger.info(f"📦 Available parts: {df['PART_NAME'].nunique()} unique parts")
        logger.info(
            f"📅 Date range: {df['LOCAL_SHOT_TIME'].min()} to {df['LOCAL_SHOT_TIME'].max()}"
        )
    else:
        logger.warning("⚠️ No data returned from query after applying filters!")
        logger.warning(
            "💡 Check if SUPPLIER_NAME and PART_NAME columns have NULL values"
        )

    return df


# -------------------------------------------------------
def create_result_table(session):
    """
    Creates the DEMO_TABLE result table in Snowflake if it does not already exist.

    Args:
        session (snowflake.snowpark.Session): Active Snowflake session.

    Returns:
        None
    """
    exists_query = """
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'CALDERA' AND TABLE_NAME = 'DEMO_TABLE'
    """
    result = session.sql(exists_query).collect()
    if result[0][0] == 0:
        create_query = """
        CREATE TABLE MMS.CALDERA.DEMO_TABLE (
            SUPPLIER_NAME STRING,
            EQUIPMENT_CODE STRING,
            COUNTER_CODE STRING,
            CT FLOAT,
            APPROVED_CT FLOAT,
            TEMPERATURE FLOAT,
            PART_NAME STRING,
            TOOLING_TYPE STRING,
            TOOLING_FAMILY STRING,
            CT_STATUS STRING,
            LOCAL_SHOT_TIME TIMESTAMP,
            VOLUME NUMBER,
            COUNTER_ID NUMBER,
            MOLD_ID NUMBER,
            COMPANY_ID NUMBER,
            PART_ID STRING,
            UPLOAD_TIME TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
        )
        """
        session.sql(create_query).collect()
        logger.info("✅ Created table: DEMO_TABLE")
    else:
        logger.warning("ℹ️ Table already exists")


# -------------------------------------------------------


def upload_data_to_snowflake(connector_conn, df, chunk_size=500000):
    """
    Uploads the processed DEMO_TABLE DataFrame to the Snowflake DEMO_TABLE table in chunks.

    Args:
        connector_conn (snowflake.connector.SnowflakeConnection): Snowflake connector connection.
        df (pd.DataFrame): DataFrame containing processed DEMO_TABLE data.
        chunk_size (int, optional): Number of rows per upload chunk. Defaults to 500000.

    Returns:
        bool: True if upload succeeded, False otherwise.
    """

    if df.empty:
        logger.warning("DataFrame is empty, skipping upload.")
        return True

    logger.info("DataFrame info before upload:")
    logger.info(df.info())
    logger.info(df.head())

    total_rows = len(df)
    logger.info(
        f"Uploading {total_rows} rows to Snowflake in chunks of {chunk_size}..."
    )

    overwrite_done = False

    try:
        for start in range(0, total_rows, chunk_size):
            end = min(start + chunk_size, total_rows)
            chunk = df.iloc[start:end]
            logger.info(f"Uploading rows {start} to {end}...")

            write_pandas(
                conn=connector_conn,
                df=chunk,
                table_name="DEMO_TABLE",
                schema="CALDERA",
                database="MMS",
                overwrite=not overwrite_done,
                auto_create_table=False,
            )
            overwrite_done = True  # After first chunk, switch to append

        logger.info("✅ Upload succeeded.")
        return True
    except Exception as e:
        logger.error("❌ Upload failed:", exc_info=e)
        return False


# -------------------------------------------------------
if __name__ == "__main__":
    """
    Main entry point: Runs data fetching, processing, table creation,
    and data upload to Snowflake.
    """
    df = fetch_data_from_snowflake(session)

    if not df.empty:
        df["LOCAL_SHOT_TIME"] = pd.to_datetime(df["LOCAL_SHOT_TIME"]).dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        create_result_table(session)
        success = upload_data_to_snowflake(sf_conn, df)
        if success:
            logger.info("✅ Data upload process completed successfully.")
        else:
            logger.error("❌ Data upload process failed.")
    else:
        logger.warning("⚠️ No data to upload: DataFrame is empty.")

    sf_conn.close()
    session.close()
