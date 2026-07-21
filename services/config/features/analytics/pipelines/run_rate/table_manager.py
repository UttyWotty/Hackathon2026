"""Manages the Snowflake RUNRATE table lifecycle as a thin subclass of BaseTableManager.
Defines the 22-column schema for run efficiency metrics and overrides statistics to include session and equipment counts.
Delegates all shared logic (creation, truncation, incremental detection, overlap deletion) to the base class.
"""

from ..base_table_manager import BaseTableManager

LOGGER_NAME: str = "RUNRATE"
TABLE_NAME: str = "RUNRATE"


class RunRateTableManager(BaseTableManager):
    """Table manager for the RUNRATE pipeline.

    Adds session and equipment counts to table statistics.
    """

    def get_table_name(self) -> str:
        """Return the RUNRATE table name."""
        return TABLE_NAME

    def get_logger_name(self) -> str:
        """Return the RUNRATE logger name."""
        return LOGGER_NAME

    def get_schema_columns(self) -> str:
        """Return the RUNRATE table column definitions."""
        return """
            EQUIPMENT_CODE STRING,
            SUPPLIER_NAME STRING,
            LOCAL_SHOT_TIME TIMESTAMP,
            CT FLOAT,
            APPROVED_CT FLOAT,
            SESSION_ID STRING,
            SHOT_DIFF_SEC FLOAT,
            MODE_CT FLOAT,
            STOP INTEGER,
            RUN_EFFICIENCY FLOAT,
            TOTAL_RUN_TIME FLOAT,
            TOTAL_STOPS INTEGER,
            DOWNTIME FLOAT,
            PRODUCTION_TIME FLOAT,
            STOP_EVENTS INTEGER,
            MTTR FLOAT,
            MTBF FLOAT,
            DAY INTEGER,
            WEEK INTEGER,
            MONTH INTEGER,
            YEAR INTEGER,
            DATE DATE,
            UPLOAD_TIME TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
        """

    def get_statistics_extras(self, session: object, db: str, schema: str) -> dict:
        """Add session and equipment counts to statistics.

        Args:
            session: Snowflake Snowpark session
            db: Database name
            schema: Schema name

        Returns:
            Dictionary with total_sessions and total_equipment counts.
        """
        table: str = self.get_table_name()
        result = session.sql(
            f"SELECT COUNT(DISTINCT SESSION_ID), "
            f"COUNT(DISTINCT EQUIPMENT_CODE) "
            f"FROM {db}.{schema}.{table}"
        ).collect()
        if result:
            return {
                "total_sessions": result[0][0],
                "total_equipment": result[0][1],
            }
        return {}


run_rate_table_manager = RunRateTableManager()

create_runrate_table = run_rate_table_manager.create_table
truncate_runrate_table = run_rate_table_manager.truncate_table
get_incremental_start_date = run_rate_table_manager.get_incremental_start_date
delete_overlap_data = run_rate_table_manager.delete_overlap_data
get_table_statistics = run_rate_table_manager.get_table_statistics
