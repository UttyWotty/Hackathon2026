"""
ROI Database Manager
====================

Handles Snowflake connections and data fetching for ROI analysis.

Author: Utku Gulbardak
Date: 2025-10-24
"""

import logging
import os
import time
from typing import Dict, Optional

# CRITICAL: Set OCSP fail-open BEFORE importing Snowflake modules
# This ensures it's respected during S3 result fetching
if "SF_OCSP_FAIL_OPEN" not in os.environ:
    os.environ["SF_OCSP_FAIL_OPEN"] = os.getenv(
        "SNOWFLAKE_OCSP_FAIL_OPEN", "true"
    ).lower()

import pandas as pd
import snowflake.connector
from snowflake.snowpark import Session

# Import shared utilities
from analysis.shared import get_logger, get_snowflake_connection_params_with_schema

logger = get_logger(__name__)


class ROIDatabase:
    """
    Manages Snowflake connections and data fetching for ROI analysis.

    Attributes:
        session: Snowflake Snowpark session
        sf_conn: Snowflake connector connection
        connection_parameters: Connection configuration dictionary
    """

    def __init__(self, schema: Optional[str] = None):
        """
        Initialize database connection manager.

        Args:
            schema: Snowflake schema to use (overrides .env if provided)
        """
        self.schema = schema
        self.session: Optional[Session] = None
        self.sf_conn: Optional[snowflake.connector.SnowflakeConnection] = None
        self.connection_parameters: Dict[str, str] = {}

        self._load_environment()
        self._connect()

    def _load_environment(self) -> None:
        """Load Snowflake credentials from environment variables."""
        self.connection_parameters = get_snowflake_connection_params_with_schema(
            schema=self.schema
        )

    def _connect(self) -> None:
        """
        Establish Snowflake connections with timeout settings for long-running queries.

        Configures extended timeouts and OCSP fail-open mode to handle:
        - Long-running queries (>1 day date ranges)
        - Certificate validation issues during extended operations
        """
        try:
            # Ensure timeout settings are present for long-running queries
            if "network_timeout" not in self.connection_parameters:
                self.connection_parameters["network_timeout"] = 3600  # 1 hour
            if "login_timeout" not in self.connection_parameters:
                self.connection_parameters["login_timeout"] = 60  # 1 minute
            if "ocsp_fail_open" not in self.connection_parameters:
                self.connection_parameters["ocsp_fail_open"] = (
                    True  # Allow connection even if OCSP fails
                )

            # Ensure OCSP fail-open is set (already set at module level, but ensure it's True)
            ocsp_fail_open = self.connection_parameters.get("ocsp_fail_open", True)
            os.environ["SF_OCSP_FAIL_OPEN"] = str(ocsp_fail_open).lower()

            # Snowpark session (uses same connection parameters)
            self.session = Session.builder.configs(self.connection_parameters).create()

            # CRITICAL: Set statement timeout via ALTER SESSION (Snowpark requires this)
            # Default is often 60 seconds, which causes failures around 71 seconds
            # This must be set AFTER session creation via ALTER SESSION command
            statement_timeout = int(
                os.getenv("SNOWFLAKE_STATEMENT_TIMEOUT", "7200")
            )  # 2 hours default
            try:
                self.session.sql(
                    f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {statement_timeout}"
                ).collect()
                logging.info(f"   Statement timeout set to: {statement_timeout}s")
            except Exception as e:
                logging.warning(f"   Could not set statement timeout: {e}")

            # Snowflake connector
            self.sf_conn = snowflake.connector.connect(**self.connection_parameters)

            logging.info("✅ Connected to Snowflake successfully")
            logging.info(
                f"   Network timeout: {self.connection_parameters.get('network_timeout', 3600)}s"
            )
            logging.info(
                f"   OCSP fail-open: {self.connection_parameters.get('ocsp_fail_open', True)}"
            )

        except Exception as e:
            logging.error(f"❌ Failed to connect to Snowflake: {e}")
            raise

    def fetch_data(
        self,
        supplier_names: Optional[list] = None,
        equipment_codes: Optional[list] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch ROI data from Snowflake with optional filtering.

        Args:
            supplier_names: Filter by supplier name(s) - list of names (optional)
            equipment_codes: Filter by equipment code(s) - list of codes (optional)
            start_date: Start date in YYYY-MM-DD format (optional)
            end_date: End date in YYYY-MM-DD format (optional)

        Returns:
            DataFrame with ROI data
        """
        # Build dynamic WHERE clause
        where_conditions = ["volume > 0", "local_shot_time is not null"]

        if supplier_names and len(supplier_names) > 0:
            # Validate and sanitize supplier names
            import re

            sanitized_suppliers = []
            for name in supplier_names:
                # Validate format (alphanumeric, spaces, hyphens, underscores)
                if not re.match(r"^[a-zA-Z0-9\s\-_]+$", name):
                    raise ValueError(f"Invalid supplier name format: {name}")
                # Escape single quotes
                sanitized_suppliers.append(name.replace("'", "''"))
            supplier_list = "', '".join(sanitized_suppliers)
            where_conditions.append(f"supplier_name IN ('{supplier_list}')")

        if equipment_codes and len(equipment_codes) > 0:
            # Equipment codes are validated at API level - just sanitize for SQL injection
            sanitized_equipment = []
            for code in equipment_codes:
                # Escape single quotes for SQL safety
                sanitized_equipment.append(code.replace("'", "''"))
            equipment_list = "', '".join(sanitized_equipment)
            where_conditions.append(f"equipment_code IN ('{equipment_list}')")

        if start_date:
            # Validate date format
            import re

            if not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date):
                raise ValueError(
                    f"Invalid start_date format: {start_date}. Expected YYYY-MM-DD"
                )
            safe_start_date = start_date.replace("'", "''")
            where_conditions.append(f"local_shot_time >= '{safe_start_date} 00:00:00'")
        if end_date:
            # Validate date format
            import re

            if not re.match(r"^\d{4}-\d{2}-\d{2}$", end_date):
                raise ValueError(
                    f"Invalid end_date format: {end_date}. Expected YYYY-MM-DD"
                )
            safe_end_date = end_date.replace("'", "''")
            where_conditions.append(f"local_shot_time <= '{safe_end_date} 23:59:59'")

        where_clause = " AND ".join(where_conditions)

        # Get MASTER_SHOT_TABLE location from env or session
        shots_db = os.getenv("SHOT_DB") or self.session.get_current_database()
        shots_schema = os.getenv("SHOT_SCHEMA") or self.session.get_current_schema()
        master_table = f"{shots_db}.{shots_schema}.MASTER_SHOT_TABLE"

        sql_query = f"""
        SELECT 
            SUPPLIER_NAME,
            EQUIPMENT_CODE,
            MOLD_ID,
            COMPANY_ID AS SUPPLIER_ID,
            COUNTER_ID,
            1 AS TOTAL_SHOT_COUNT,
            VOLUME,
            APPROVED_CT,
            CT,
            LOCAL_SHOT_TIME
        FROM {master_table}
        WHERE CT < 999.9 
            AND VOLUME > 0
            AND {where_clause}
        ORDER BY EQUIPMENT_CODE, LOCAL_SHOT_TIME
        """

        # Calculate date range for logging
        date_diff = None
        if start_date and end_date:
            from datetime import datetime

            date_diff = (
                datetime.strptime(end_date, "%Y-%m-%d")
                - datetime.strptime(start_date, "%Y-%m-%d")
            ).days
            logging.info(
                f"📅 Fetching data for {date_diff} day(s): {start_date} to {end_date}"
            )
            if date_diff > 30:
                logging.warning(
                    f"⚠️ Large date range ({date_diff} days) - query may take several minutes"
                )

        start_time = time.time()
        max_retries = int(os.getenv("SNOWFLAKE_MAX_RETRIES", "5"))  # Increased from 3
        retry_delay = int(
            os.getenv("SNOWFLAKE_RETRY_DELAY", "10")
        )  # Start with 10 seconds

        # For date ranges >3 days, use connector instead of Snowpark
        # Connector has better retry logic for S3 certificate errors
        # Threshold lowered from 30 to 3 days due to hangs with 1.4K+ rows
        use_connector = date_diff is not None and date_diff > 3

        if use_connector:
            logging.info(
                f"📥 Using Snowflake connector for large query ({date_diff} days) - better S3 retry handling"
            )

        for attempt in range(1, max_retries + 1):
            cursor = None
            try:
                if use_connector:
                    # Use Snowflake connector for large queries (better S3 retry handling)
                    # Recreate connection on retry if previous attempt failed
                    if attempt > 1:
                        logging.info(
                            f"🔄 Recreating connector connection for retry attempt {attempt}"
                        )
                        try:
                            if self.sf_conn:
                                self.sf_conn.close()
                        except Exception as close_error:
                            logging.warning(
                                f"   Warning closing old connection: {close_error}"
                            )
                        # Recreate connection with fresh state
                        self.sf_conn = snowflake.connector.connect(
                            **self.connection_parameters
                        )
                        logging.info("   ✅ Connection recreated successfully")

                    cursor = self.sf_conn.cursor()

                    # Set statement timeout for this connection
                    statement_timeout = int(
                        os.getenv("SNOWFLAKE_STATEMENT_TIMEOUT", "7200")
                    )
                    try:
                        cursor.execute(
                            f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {statement_timeout}"
                        )
                        if attempt == 1:
                            logging.info(
                                f"   Statement timeout set to: {statement_timeout}s"
                            )
                    except Exception as e:
                        logging.warning(f"   Could not set statement timeout: {e}")

                    cursor.execute(sql_query)
                    df = cursor.fetch_pandas_all()
                    cursor.close()
                    cursor = None  # Mark as closed
                else:
                    # Use Snowpark for smaller queries
                    df = self.session.sql(sql_query).to_pandas()

                duration = round(time.time() - start_time, 2)

                logging.info(
                    f"✅ Retrieved {len(df)} rows from Snowflake in {duration} seconds"
                )

                return df

            except Exception as e:
                duration = round(time.time() - start_time, 2)
                error_msg = str(e)

                # Clean up cursor if it exists
                if cursor:
                    try:
                        cursor.close()
                    except Exception:
                        pass

                # Check if it's a certificate error that might be retryable
                is_certificate_error = (
                    "certificate" in error_msg.lower() or "254007" in error_msg
                )
                is_timeout_error = "timeout" in error_msg.lower()

                if is_certificate_error and attempt < max_retries:
                    logging.warning(
                        f"⚠️ Certificate error on attempt {attempt}/{max_retries} after {duration}s - Retrying in {retry_delay}s..."
                    )
                    logging.warning(f"   Error: {error_msg[:200]}")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                elif is_certificate_error or is_timeout_error:
                    logging.error(
                        f"❌ Query failed after {duration}s ({attempt} attempts) - Certificate/timeout error: {error_msg}"
                    )
                    logging.warning(
                        "💡 Tip: For large date ranges, try:\n"
                        "   1) Using weekly/monthly aggregation_level\n"
                        "   2) Splitting into smaller date ranges (e.g., weekly chunks)\n"
                        "   3) Checking SNOWFLAKE_NETWORK_TIMEOUT and SNOWFLAKE_OCSP_FAIL_OPEN settings"
                    )
                else:
                    logging.error(f"❌ Query failed after {duration}s: {error_msg}")

                # If we've exhausted retries or it's not a certificate error, raise
                raise

    def close(self) -> None:
        """Close Snowflake connections."""
        try:
            if self.session:
                self.session.close()
            if self.sf_conn:
                self.sf_conn.close()
            logging.info("✅ Snowflake connections closed")

        except Exception as e:
            logging.warning(f"⚠️ Error closing connections: {e}")
