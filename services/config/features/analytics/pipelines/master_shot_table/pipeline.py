"""Pipeline Module
===============

Core pipeline class for Master Shot Table processing with chunking, parallel processing,
deduplication, incremental logic, and safety checks.
"""

import concurrent.futures
import random
import time
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pandas as pd
from snowflake.connector.pandas_tools import write_pandas

from utils.sql_validation import sanitize_sql_identifier, validate_date_param

from ..shared_config import PipelineConfig, get_database_schema, setup_pipeline_logging
from .sql_builder import build_optimized_shot_query

logger = setup_pipeline_logging("MASTER_SHOT")


def _normalize_datetime_column(df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    """Find a column by case-insensitive match, convert to datetime, and rename to target_col."""
    actual_col = None
    for col in df.columns:
        if col.upper() == target_col:
            actual_col = col
            break

    if actual_col and actual_col in df.columns:
        df[actual_col] = pd.to_datetime(df[actual_col], errors="coerce").astype(
            "datetime64[ns]"
        )
        if actual_col != target_col:
            df = df.rename(columns={actual_col: target_col})
    return df


class MasterShotPipeline:
    """Optimized pipeline for generating master shot table with chunked processing."""

    def __init__(self, session, sf_conn, config: Optional[PipelineConfig] = None):
        """Initialize the pipeline.

        Args:
            session: Snowflake Snowpark session
            sf_conn: Snowflake connector connection
            config: Processing configuration
        """
        self.session = session
        self.sf_conn = sf_conn
        self.config = config or PipelineConfig()
        self.database, default_schema = get_database_schema()
        # Use config schema_name if provided, otherwise use default from environment
        self.schema = self.config.schema_name or default_schema
        logger.info(
            f"Pipeline initialized: database={self.database}, schema={self.schema}"
        )

    def _get_global_max_shot_date(self) -> Optional[str]:
        """Find the global MAX(LOCAL_SHOT_TIME) across the entire table.

        Returns the most recent shot timestamp in the table so that
        incremental processing only covers the trailing window
        (max_date - overlap_days) to today.

        Returns:
            Date string (YYYY-MM-DD) or None if table is empty.
        """
        query = f"""
        SELECT MAX(LOCAL_SHOT_TIME)
        FROM {self.database}.{self.schema}.MASTER_SHOT_TABLE
        """
        result = self.session.sql(query).collect()
        if result and result[0][0] is not None:
            global_max = result[0][0]
            date_str = global_max.strftime("%Y-%m-%d")
            logger.info("Global MAX(LOCAL_SHOT_TIME): %s", date_str)
            return date_str
        logger.warning("MASTER_SHOT_TABLE is empty - no data found")
        return None

    def get_date_chunks(self) -> List[Tuple[str, str]]:
        """Generate date chunks for processing.

        Returns:
            List of (start_date, end_date) tuples for each chunk.
        """
        if self.config.start_date and self.config.end_date:
            start_dt = datetime.strptime(self.config.start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(self.config.end_date, "%Y-%m-%d")
        else:
            end_dt = datetime.now().date()
            start_dt = end_dt - timedelta(days=self.config.overlap_days)
            end_dt = datetime.combine(end_dt, datetime.min.time())
            start_dt = datetime.combine(start_dt, datetime.min.time())

        chunks = []
        current_date = start_dt

        while current_date < end_dt:
            chunk_end = min(
                current_date + timedelta(days=self.config.chunk_size_days), end_dt
            )
            chunks.append(
                (current_date.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d"))
            )
            current_date = chunk_end

        logger.info(
            f"Generated {len(chunks)} date chunks of {self.config.chunk_size_days} days each"
        )
        return chunks

    def process_chunk(
        self, start_date: str, end_date: str, max_retries: int = 3
    ) -> pd.DataFrame:
        """Process a single date chunk with automatic retry logic.

        Args:
            start_date: Start date for chunk
            end_date: End date for chunk
            max_retries: Maximum number of retry attempts

        Returns:
            DataFrame with processed data for the chunk
        """
        logger.info(f"Processing chunk: {start_date} to {end_date}")

        query = build_optimized_shot_query(
            self.database, self.schema, start_date, end_date
        )

        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()
                df = self.session.sql(query).to_pandas()
                duration = time.time() - start_time

                # Normalize datetime columns (case-insensitive match + convert)
                df = _normalize_datetime_column(df, "LOCAL_SHOT_TIME")
                df = _normalize_datetime_column(df, "UTC_TIME_ZONE")

                logger.info(
                    f"Chunk {start_date}-{end_date}: {len(df)} rows in {duration:.2f}s"
                )
                return df

            except Exception as e:
                if attempt < max_retries:
                    base_wait = 2**attempt
                    jitter = base_wait * 0.25 * (2 * random.random() - 1)
                    wait_time = base_wait + jitter
                    logger.warning(
                        f"Chunk {start_date}-{end_date} failed (attempt {attempt + 1}/{max_retries + 1}). "
                        f"Retrying in {wait_time:.1f}s... Error: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Error processing chunk {start_date}-{end_date} after {max_retries + 1} attempts: {e}"
                    )
                    raise

    def create_result_table(self):
        """Create the MASTER_SHOT_TABLE if it doesn't exist."""
        table_name = "MASTER_SHOT_TABLE"
        safe_schema = sanitize_sql_identifier(self.schema)
        exists_query = f"""SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = '{safe_schema}' AND TABLE_NAME = '{table_name}'"""
        result = self.session.sql(exists_query).collect()
        if result[0][0] == 0:
            create_query = f"""CREATE TABLE {self.database}.{self.schema}.{table_name} (
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
            LOCAL_SHOT_TIME TIMESTAMP_NTZ(3),
            UTC_TIME_ZONE TIMESTAMP_NTZ(3),
            VOLUME NUMBER,
            COUNTER_ID NUMBER,
            MOLD_ID NUMBER,
            COMPANY_ID NUMBER,
            PART_ID STRING,
            UPLOAD_TIME TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            PROCESSING_DATE STRING
            )
            """
            self.session.sql(create_query).collect()
            logger.info(f"Created table: {table_name}")
        else:
            logger.info(f"Table {table_name} already exists")

    def truncate_table(self):
        """Truncate the MASTER_SHOT_TABLE."""
        table_name = "MASTER_SHOT_TABLE"
        try:
            truncate_query = f"""TRUNCATE TABLE IF EXISTS {self.database}.{self.schema}.{table_name}
            """
            self.session.sql(truncate_query).collect()
            logger.info(f"Truncated table {table_name}")
        except Exception as e:
            logger.error(f"Error truncating table: {e}")
            raise

    def deduplicate_final_table(self):
        """Deduplicate MASTER_SHOT_TABLE based on all data columns."""
        table_name = "MASTER_SHOT_TABLE"
        try:
            dup_check_query = f"""SELECT COUNT(*) as duplicate_count
            FROM (
            SELECT COUNTER_CODE, LOCAL_SHOT_TIME, COUNT(*) as dup_count
            FROM {self.database}.{self.schema}.{table_name}
            GROUP BY COUNTER_CODE, LOCAL_SHOT_TIME
            HAVING COUNT(*) > 1
            )
            """
            dup_result = self.session.sql(dup_check_query).collect()
            duplicate_count = dup_result[0][0] if dup_result else 0

            if duplicate_count == 0:
                logger.info("No duplicates found")
                return

            logger.info(
                f"Found {duplicate_count:,} duplicate combinations - deduplicating..."
            )

            temp_table = f"{table_name}_TEMP"
            dedupe_query = f"""CREATE OR REPLACE TABLE {self.database}.{self.schema}.{temp_table} AS
            SELECT *
            FROM {self.database}.{self.schema}.{table_name}
            QUALIFY ROW_NUMBER() OVER (
            PARTITION BY
            COUNTER_CODE, LOCAL_SHOT_TIME, CT, TEMPERATURE, VOLUME,
            PART_ID, PART_NAME, SUPPLIER_NAME, EQUIPMENT_CODE
            ORDER BY PROCESSING_DATE DESC
            ) = 1
            """
            self.session.sql(dedupe_query).collect()

            count_before = self.session.sql(
                f"SELECT COUNT(*) FROM {self.database}.{self.schema}.{table_name}"
            ).collect()[0][0]
            count_after = self.session.sql(
                f"SELECT COUNT(*) FROM {self.database}.{self.schema}.{temp_table}"
            ).collect()[0][0]
            removed = count_before - count_after

            logger.info(
                f"Before: {count_before:,} | After: {count_after:,} | Removed: {removed:,}"
            )

            self.session.sql(
                f"DROP TABLE {self.database}.{self.schema}.{table_name}"
            ).collect()
            self.session.sql(
                f"ALTER TABLE {self.database}.{self.schema}.{temp_table} RENAME TO {table_name}"
            ).collect()
            logger.info(f"Deduplication complete - removed {removed:,} duplicates")
        except Exception as e:
            logger.error(f"Error during deduplication: {e}")
            raise

    def upload_chunk_data(
        self, df: pd.DataFrame, chunk_id: str, overwrite: bool = False
    ):
        """Upload chunk data to Snowflake."""
        if df.empty:
            logger.warning(f"Chunk {chunk_id}: No data to upload")
            return True

        df.columns = [c.upper() for c in df.columns]

        if "LOCAL_SHOT_TIME" in df.columns:
            df["LOCAL_SHOT_TIME"] = pd.to_datetime(
                df["LOCAL_SHOT_TIME"], errors="coerce"
            )
            initial_len = len(df)
            df = df.dropna(subset=["LOCAL_SHOT_TIME"]).copy()
            if len(df) < initial_len:
                logger.warning(
                    f"Dropped {initial_len - len(df)} rows with invalid timestamps"
                )
        else:
            raise ValueError("LOCAL_SHOT_TIME column missing")

        df["PROCESSING_DATE"] = chunk_id
        df["PART_ID"] = df["PART_ID"].astype(str).replace("nan", None)
        df["PART_NAME"] = df["PART_NAME"].astype(str).replace("nan", None)

        total_rows = len(df)
        if total_rows == 0:
            return True

        logger.info(f"Uploading chunk {chunk_id}: {total_rows} rows...")
        try:
            if overwrite:
                self.create_result_table()

            for start in range(0, total_rows, self.config.batch_upload_size):
                end = min(start + self.config.batch_upload_size, total_rows)
                batch = df.iloc[start:end].copy()
                if "LOCAL_SHOT_TIME" in batch.columns:
                    batch["LOCAL_SHOT_TIME"] = (
                        batch["LOCAL_SHOT_TIME"]
                        .dt.strftime("%Y-%m-%d %H:%M:%S.%f")
                        .str[:-3]
                    )
                if "UTC_TIME_ZONE" in batch.columns:
                    batch["UTC_TIME_ZONE"] = (
                        batch["UTC_TIME_ZONE"]
                        .dt.strftime("%Y-%m-%d %H:%M:%S.%f")
                        .str[:-3]
                    )

                write_pandas(
                    conn=self.sf_conn,
                    df=batch,
                    table_name="MASTER_SHOT_TABLE",
                    schema=self.schema,
                    database=self.database,
                    overwrite=False,
                    auto_create_table=False,
                    quote_identifiers=False,
                )

            logger.info(f"Chunk {chunk_id}: Upload completed")
            return True
        except Exception as e:
            logger.error(f"Chunk {chunk_id}: Upload failed: {e}")
            return False

    def delete_overlap_data(self, start_date: str, end_date: str):
        """Delete existing data for date range with safety checks."""
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            days_span = (end_dt - start_dt).days

            if days_span > self.config.max_delete_days:
                raise ValueError(
                    "Cannot delete more than %d days. Requested: %d days"
                    % (self.config.max_delete_days, days_span)
                )

            safe_start = validate_date_param(start_date)
            safe_end = validate_date_param(end_date)

            total_count_query = f"""SELECT COUNT(*) FROM {self.database}.{self.schema}.MASTER_SHOT_TABLE
            """
            total_rows = self.session.sql(total_count_query).collect()[0][0]

            count_query = f"""SELECT COUNT(*) FROM {self.database}.{self.schema}.MASTER_SHOT_TABLE
            WHERE LOCAL_SHOT_TIME >= '{safe_start}'::TIMESTAMP
            AND LOCAL_SHOT_TIME < '{safe_end}'::TIMESTAMP
            """
            rows_to_delete = self.session.sql(count_query).collect()[0][0]

            if total_rows > 0 and rows_to_delete > (total_rows * 0.2):
                raise ValueError(
                    f"Cannot delete more than 20% of data. Would delete: {rows_to_delete:,}/{total_rows:,}"
                )

            logger.info(
                f"Deleting {rows_to_delete:,} rows from {start_date} to {end_date}"
            )

            delete_query = f"""DELETE FROM {self.database}.{self.schema}.MASTER_SHOT_TABLE
            WHERE LOCAL_SHOT_TIME >= '{safe_start}'::TIMESTAMP
            AND LOCAL_SHOT_TIME < '{safe_end}'::TIMESTAMP
            """
            self.session.sql(delete_query).collect()
            logger.info(f"Deleted {rows_to_delete:,} rows")
        except Exception as e:
            logger.error(f"Error deleting overlap data: {e}")
            raise

    def process_all_chunks(
        self, parallel: bool = True, full_load: bool = False
    ) -> bool:
        """Process all date chunks."""
        date_chunks = self.get_date_chunks()
        if not date_chunks:
            return True

        logger.info(f"Starting processing of {len(date_chunks)} chunks")

        self.create_result_table()
        if full_load:
            logger.info("Full load mode: Truncating table")
            self.truncate_table()

        success_count = 0

        if parallel and len(date_chunks) > 1:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.config.max_workers
            ) as executor:
                future_to_chunk = {
                    executor.submit(
                        self._process_and_upload_chunk,
                        start_date,
                        end_date,
                        full_load and i == 0,
                    ): (start_date, end_date)
                    for i, (start_date, end_date) in enumerate(date_chunks)
                }

                for future in concurrent.futures.as_completed(future_to_chunk):
                    try:
                        if future.result():
                            success_count += 1
                    except Exception as e:
                        logger.error(f"Chunk failed: {e}")
        else:
            for i, (start_date, end_date) in enumerate(date_chunks):
                try:
                    if self._process_and_upload_chunk(
                        start_date, end_date, full_load and i == 0
                    ):
                        success_count += 1
                except Exception as e:
                    logger.error(f"Chunk {start_date}-{end_date} failed: {e}")

        logger.info(
            f"Processing complete: {success_count}/{len(date_chunks)} successful"
        )
        if success_count > 0:
            logger.info("Running final deduplication...")
            try:
                self.deduplicate_final_table()
            except Exception as e:
                logger.warning(f"Deduplication failed: {e}")

        return success_count == len(date_chunks)

    def _process_and_upload_chunk(
        self, start_date: str, end_date: str, is_first: bool
    ) -> bool:
        """Helper to process and upload a single chunk."""
        chunk_id = f"{start_date}_to_{end_date}"
        try:
            df = self.process_chunk(start_date, end_date)
            return self.upload_chunk_data(df, chunk_id, overwrite=is_first)
        except Exception as e:
            logger.error(f"Failed chunk {chunk_id}: {e}")
            return False

    def process_incremental(self, overlap_days: int = 7) -> bool:
        """Process incremental data using global max-date detection.

        Finds the global MAX(LOCAL_SHOT_TIME) in the table, then deletes
        and re-fetches from (max_date - overlap_days) to today. This keeps
        the incremental window small and predictable.

        Falls back to full load if MASTER_SHOT_TABLE is empty.

        Args:
            overlap_days: Extra days to subtract for safety overlap.

        Returns:
            True if processing succeeded.
        """
        logger.info("Starting incremental processing with global max-date detection")

        self.create_result_table()

        global_max = self._get_global_max_shot_date()
        if global_max is None:
            logger.warning("No existing data found - falling back to full load")
            return self.process_all_chunks(parallel=True, full_load=True)

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (
            datetime.strptime(global_max, "%Y-%m-%d") - timedelta(days=overlap_days)
        ).strftime("%Y-%m-%d")

        days_span = (datetime.now() - datetime.strptime(start_date, "%Y-%m-%d")).days
        self.config.max_delete_days = days_span
        logger.info(
            "Incremental range: %s to %s (%d days)", start_date, end_date, days_span
        )

        self.config.start_date = start_date
        self.config.end_date = end_date

        self.delete_overlap_data(start_date, end_date)

        success = self.process_all_chunks(parallel=True)
        if success:
            logger.info("Incremental processing completed")
        else:
            logger.error("Incremental processing completed with errors")
        return success

    # Alias for compatibility
    process_incremental_with_overlap = process_incremental
