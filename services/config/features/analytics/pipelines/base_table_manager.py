"""Abstract base class for Snowflake table lifecycle management across analytics pipelines.
Provides shared logic for table creation, truncation, incremental date detection, and overlap deletion with 20% safety checks.
Subclasses override table name, schema columns, and optional statistics extras to specialize behavior.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional

from utils.sql_validation import sanitize_sql_identifier, validate_date_param

from .shared_config import OVERLAP_DAYS

MAX_DELETE_FRACTION: float = 0.2
DATETIME_PARSE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT: str = "%Y-%m-%d"
TIME_COLUMN: str = "SHOT_TIME"


class BaseTableManager(ABC):
    """Base class for pipeline table management operations.

    Subclasses must implement get_table_name(), get_logger_name(), and
    get_schema_columns() to define their specific table structure.

    Attributes:
        force_recreate_on_full_load: When True, full loads drop and recreate
            the table instead of truncating. Defaults to False.
    """

    force_recreate_on_full_load: bool = False

    def __init__(self) -> None:
        self.logger: logging.Logger = logging.getLogger(self.get_logger_name())

    @abstractmethod
    def get_table_name(self) -> str:
        """Return the Snowflake table name (e.g., 'ROI', 'DEVIATION')."""

    @abstractmethod
    def get_logger_name(self) -> str:
        """Return the logger name for this pipeline."""

    @abstractmethod
    def get_schema_columns(self) -> str:
        """Return the CREATE TABLE column definitions as a SQL fragment."""

    def _get_db_schema(self, session: object) -> tuple[str, str]:
        """Resolve database and schema from the active Snowpark session.

        Args:
            session: Snowflake Snowpark session

        Returns:
            Tuple of (database_name, schema_name).
        """
        db: str = session.get_current_database().strip('"')
        schema: str = session.get_current_schema().strip('"')
        return db, schema

    def create_table(self, session: object, force_recreate: bool = False) -> None:
        """Create the table in Snowflake if it does not exist.

        Args:
            session: Snowflake Snowpark session
            force_recreate: If True, drop and recreate the table
        """
        db, schema = self._get_db_schema(session)
        table: str = self.get_table_name()
        schema_cols: str = self.get_schema_columns()

        if force_recreate:
            self.logger.info(
                "Force recreating %s table to ensure correct schema...", table
            )
            session.sql(
                f"CREATE OR REPLACE TABLE {db}.{schema}.{table} ({schema_cols})"
            ).collect()
            self.logger.info("Recreated table: %s with correct schema", table)
            return

        safe_schema: str = sanitize_sql_identifier(schema)
        exists_query: str = (
            f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            f"WHERE TABLE_SCHEMA = '{safe_schema}' AND TABLE_NAME = '{table}'"
        )
        result = session.sql(exists_query).collect()
        if result[0][0] == 0:
            session.sql(f"CREATE TABLE {db}.{schema}.{table} ({schema_cols})").collect()
            self.logger.info("Created table: %s", table)
        else:
            self.logger.info("Table %s already exists", table)

    def truncate_table(self, session: object) -> None:
        """Truncate the table to remove all existing data.

        Args:
            session: Snowflake Snowpark session
        """
        db, schema = self._get_db_schema(session)
        table: str = self.get_table_name()
        try:
            session.sql(f"TRUNCATE TABLE IF EXISTS {db}.{schema}.{table}").collect()
            self.logger.info("Truncated table %s - removed all existing data", table)
        except Exception as e:
            self.logger.error("Error truncating table: %s", e)
            raise

    def get_incremental_start_date(
        self, session: object, overlap_days: int = OVERLAP_DAYS
    ) -> Optional[str]:
        """Get the start date for incremental processing using global max-date.

        Queries MAX(SHOT_TIME) from the table, then subtracts
        overlap_days for safety.

        Args:
            session: Snowflake Snowpark session
            overlap_days: Extra days to subtract for safety overlap

        Returns:
            Start date string (YYYY-MM-DD) or None if table is empty.
        """
        db, schema = self._get_db_schema(session)
        table: str = self.get_table_name()
        query: str = f"SELECT MAX({TIME_COLUMN}) FROM {db}.{schema}.{table}"
        result = session.sql(query).collect()
        if result and result[0][0] is not None:
            raw_max = result[0][0]
            if isinstance(raw_max, str):
                global_max = datetime.strptime(raw_max[:19], DATETIME_PARSE_FORMAT)
            else:
                global_max = raw_max
            start_date: str = (global_max - timedelta(days=overlap_days)).strftime(
                DATE_FORMAT
            )
            self.logger.info(
                "Global MAX(%s): %s, incremental start: %s",
                TIME_COLUMN,
                global_max.strftime(DATE_FORMAT),
                start_date,
            )
            return start_date
        self.logger.warning("%s table is empty - no data found", table)
        return None

    def delete_overlap_data(self, session: object, start_date: str) -> None:
        """Delete existing data from start_date to today to prevent duplicates.

        Safety check validates deletion will not exceed 20% of total data.

        Args:
            session: Snowflake Snowpark session
            start_date: Start date for deletion window (YYYY-MM-DD)
        """
        db, schema = self._get_db_schema(session)
        table: str = self.get_table_name()
        try:
            delete_end_date: str = datetime.now().date().strftime(DATE_FORMAT)

            total_count_result = session.sql(
                f"SELECT COUNT(*) FROM {db}.{schema}.{table}"
            ).collect()
            total_rows: int = total_count_result[0][0] if total_count_result else 0

            safe_start: str = validate_date_param(start_date)
            safe_end: str = validate_date_param(delete_end_date)

            count_before_result = session.sql(f"""
                SELECT COUNT(*) FROM {db}.{schema}.{table}
                WHERE DATE({TIME_COLUMN}) >= '{safe_start}'::DATE
                AND DATE({TIME_COLUMN}) <= '{safe_end}'::DATE
            """).collect()
            rows_to_delete: int = (
                count_before_result[0][0] if count_before_result else 0
            )

            if total_rows > 0 and rows_to_delete > (total_rows * MAX_DELETE_FRACTION):
                raise ValueError(
                    "Cannot delete more than 20%% of total data. "
                    "Would delete: %d / %d rows" % (rows_to_delete, total_rows)
                )

            self.logger.info(
                "Deleting %d rows from %s to %s",
                rows_to_delete,
                start_date,
                delete_end_date,
            )

            session.sql(f"""
                DELETE FROM {db}.{schema}.{table}
                WHERE DATE({TIME_COLUMN}) >= '{safe_start}'::DATE
                AND DATE({TIME_COLUMN}) <= '{safe_end}'::DATE
            """).collect()

            self.logger.info("Deleted %d rows", rows_to_delete)

            count_after_result = session.sql(
                f"SELECT COUNT(*) FROM {db}.{schema}.{table}"
            ).collect()
            remaining_rows: int = count_after_result[0][0] if count_after_result else 0
            self.logger.info("Remaining rows in %s: %d", table, remaining_rows)
        except Exception as e:
            self.logger.error("Error deleting overlap data: %s", e)
            raise

    def get_statistics_extras(self, session: object, db: str, schema: str) -> dict:
        """Hook for subclasses to add extra statistics fields.

        Override in subclasses that need additional metrics (e.g., session
        or equipment counts).

        Args:
            session: Snowflake Snowpark session
            db: Database name
            schema: Schema name

        Returns:
            Dictionary of additional statistics.
        """
        return {}

    def get_table_statistics(self, session: object) -> Optional[dict]:
        """Get statistics about the table.

        Args:
            session: Snowflake Snowpark session

        Returns:
            Dictionary with table statistics or None.
        """
        db, schema = self._get_db_schema(session)
        table: str = self.get_table_name()
        result = session.sql(
            f"SELECT COUNT(*), MIN({TIME_COLUMN}), MAX({TIME_COLUMN}) "
            f"FROM {db}.{schema}.{table}"
        ).collect()
        if result:
            stats: dict = {
                "total_rows": result[0][0],
                "min_date": result[0][1],
                "max_date": result[0][2],
            }
            extras: dict = self.get_statistics_extras(session, db, schema)
            stats.update(extras)
            return stats
        return None
