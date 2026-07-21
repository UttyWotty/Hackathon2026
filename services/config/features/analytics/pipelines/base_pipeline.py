"""Abstract base class for analytics pipeline orchestration with full and incremental load modes.
Provides the shared run/process flow: session lifecycle, table management, data fetching, upload, and statistics logging.
Subclasses wire up their specific table manager, uploader, and data fetcher, and optionally override process_data for calculations.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from .base_table_manager import BaseTableManager
from .base_uploader import BaseUploader
from .shared_config import OVERLAP_DAYS, get_snowflake_connector, get_snowflake_session

SEPARATOR_WIDTH: int = 80


class BasePipeline(ABC):
    """Base class for analytics pipeline orchestration.

    Subclasses must implement abstract methods to wire up their specific
    table manager, uploader, data fetcher, and data validator.

    The run() method dispatches to process_full_historical_data() or
    process_incremental_data() based on the mode flag.
    """

    def __init__(self) -> None:
        self.logger: logging.Logger = logging.getLogger(self.get_pipeline_name())

    @abstractmethod
    def get_pipeline_name(self) -> str:
        """Return the pipeline name for logging (e.g., 'ROI', 'RUNRATE')."""

    @abstractmethod
    def get_table_manager(self) -> BaseTableManager:
        """Return the table manager instance for this pipeline."""

    @abstractmethod
    def get_uploader(self) -> BaseUploader:
        """Return the uploader instance for this pipeline."""

    @abstractmethod
    def fetch_full_data(self, session: object) -> pd.DataFrame:
        """Fetch full historical data from the source table.

        Args:
            session: Snowflake Snowpark session

        Returns:
            DataFrame with fetched data.
        """

    @abstractmethod
    def fetch_incremental_data(self, session: object, start_date: str) -> pd.DataFrame:
        """Fetch incremental data from the source table.

        Args:
            session: Snowflake Snowpark session
            start_date: Start date (YYYY-MM-DD) for incremental fetch

        Returns:
            DataFrame with fetched data.
        """

    @abstractmethod
    def validate_data(self, df: pd.DataFrame) -> bool:
        """Validate fetched data before processing.

        Args:
            df: DataFrame to validate

        Returns:
            True if validation passed.
        """

    def process_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process data through pipeline-specific calculations.

        Default implementation returns the DataFrame unchanged. Override
        in subclasses that need calculation steps (e.g., run_rate).

        Args:
            df: Validated DataFrame

        Returns:
            Processed DataFrame ready for upload preparation.
        """
        return df

    def _log_statistics(self, stats: dict) -> None:
        """Log final table statistics after upload.

        Handles both base fields (total_rows, min_date, max_date) and
        any extras returned by get_statistics_extras.

        Args:
            stats: Dictionary of statistics from get_table_statistics.
        """
        self.logger.info("=" * SEPARATOR_WIDTH)
        self.logger.info("FINAL STATISTICS:")
        self.logger.info("Total rows: %s", f"{stats['total_rows']:,}")
        if "total_sessions" in stats:
            self.logger.info("Total sessions: %s", f"{stats['total_sessions']:,}")
        if "total_equipment" in stats:
            self.logger.info("Total equipment: %s", f"{stats['total_equipment']:,}")
        self.logger.info("Date range: %s to %s", stats["min_date"], stats["max_date"])
        self.logger.info("=" * SEPARATOR_WIDTH)

    def process_full_historical_data(self, schema_name: Optional[str] = None) -> bool:
        """Process full historical data from the source table.

        Steps:
            1. Create table (force_recreate if configured, else truncate)
            2. Fetch all historical data
            3. Validate and process data
            4. Prepare and upload to target table
            5. Validate upload and log statistics

        Args:
            schema_name: Optional schema override (e.g., CLIENT_A)

        Returns:
            True if processing succeeded.
        """
        self.logger.info("=" * SEPARATOR_WIDTH)
        self.logger.info("FULL HISTORICAL LOAD MODE - Processing all historical data")
        self.logger.info("=" * SEPARATOR_WIDTH)

        start_time: float = time.time()
        session = None
        connector_conn = None
        try:
            session = get_snowflake_session(schema=schema_name)
            connector_conn = get_snowflake_connector(schema=schema_name)

            tm: BaseTableManager = self.get_table_manager()
            up: BaseUploader = self.get_uploader()

            if tm.force_recreate_on_full_load:
                tm.create_table(session, force_recreate=True)
            else:
                tm.create_table(session)
                self.logger.info(
                    "Full load mode: Truncating table to prevent duplicates"
                )
                tm.truncate_table(session)

            df: pd.DataFrame = self.fetch_full_data(session)
            if df.empty:
                self.logger.warning("No historical data to process")
                return False

            self.validate_data(df)
            df = self.process_data(df)
            df = up.prepare_dataframe(df)

            success: bool = up.upload_to_snowflake(connector_conn, df, overwrite=True)
            if success:
                up.validate_upload(session, expected_row_count=len(df))
                stats = tm.get_table_statistics(session)
                if stats:
                    self._log_statistics(stats)

                elapsed: float = round(time.time() - start_time, 2)
                self.logger.info("Full historical load completed in %ss", elapsed)
                return True

            self.logger.error("Full historical load failed during upload")
            return False

        except Exception as e:
            self.logger.error("Full historical load failed: %s", e, exc_info=True)
            return False
        finally:
            if session is not None:
                session.close()
            if connector_conn is not None:
                connector_conn.close()

    def process_incremental_data(
        self,
        overlap_days: int = OVERLAP_DAYS,
        schema_name: Optional[str] = None,
    ) -> bool:
        """Process incremental data -- replaces only the last N days.

        Steps:
            1. Create table if not exists
            2. Get incremental start date and delete overlap
            3. Fetch incremental data
            4. Validate, process, prepare, and upload
            5. Validate upload and log statistics

        Args:
            overlap_days: Number of days to reprocess
            schema_name: Optional schema override (e.g., CLIENT_A)

        Returns:
            True if processing succeeded.
        """
        self.logger.info("=" * SEPARATOR_WIDTH)
        self.logger.info("INCREMENTAL MODE - Replacing last %d days only", overlap_days)
        self.logger.info("=" * SEPARATOR_WIDTH)

        start_time: float = time.time()
        session = None
        connector_conn = None
        try:
            session = get_snowflake_session(schema=schema_name)
            connector_conn = get_snowflake_connector(schema=schema_name)

            tm: BaseTableManager = self.get_table_manager()
            up: BaseUploader = self.get_uploader()

            tm.create_table(session)

            start_date: Optional[str] = tm.get_incremental_start_date(
                session, overlap_days
            )
            if start_date is None:
                self.logger.warning(
                    "No existing data - falling back to full historical load"
                )
                return self.process_full_historical_data(schema_name=schema_name)

            tm.delete_overlap_data(session, start_date)

            df: pd.DataFrame = self.fetch_incremental_data(session, start_date)
            if df.empty:
                self.logger.warning("No incremental data to process")
                return True

            self.validate_data(df)
            df = self.process_data(df)
            df = up.prepare_dataframe(df)

            success: bool = up.upload_to_snowflake(connector_conn, df, overwrite=False)
            if success:
                up.validate_upload(session)
                stats = tm.get_table_statistics(session)
                if stats:
                    self._log_statistics(stats)

                elapsed: float = round(time.time() - start_time, 2)
                self.logger.info("Incremental processing completed in %ss", elapsed)
                self.logger.info(
                    "Historical data before %s has been preserved",
                    start_date,
                )
                return True

            self.logger.error("Incremental processing failed during upload")
            return False

        except Exception as e:
            self.logger.error("Incremental processing failed: %s", e, exc_info=True)
            return False
        finally:
            if session is not None:
                session.close()
            if connector_conn is not None:
                connector_conn.close()

    def run(
        self,
        full_historical_load: bool = False,
        overlap_days: int = OVERLAP_DAYS,
        schema_name: Optional[str] = None,
    ) -> bool:
        """Main execution entry point for the pipeline.

        Args:
            full_historical_load: If True, process all historical data.
                If False, run incremental mode.
            overlap_days: Number of days to reprocess in incremental mode.
            schema_name: Optional schema override (e.g., CLIENT_A)

        Returns:
            True if processing succeeded.
        """
        try:
            if full_historical_load:
                success: bool = self.process_full_historical_data(
                    schema_name=schema_name
                )
                if success:
                    self.logger.info(
                        "Full historical data processing completed " "successfully"
                    )
                else:
                    self.logger.error("Full historical data processing failed")
                return success

            success = self.process_incremental_data(
                overlap_days=overlap_days, schema_name=schema_name
            )
            if success:
                self.logger.info("Incremental processing completed successfully")
            else:
                self.logger.error("Incremental processing failed")
            return success

        except Exception as e:
            self.logger.error("Pipeline execution failed: %s", e, exc_info=True)
            raise
