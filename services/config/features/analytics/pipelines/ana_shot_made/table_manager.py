"""Manages the Snowflake ANA_SHOT_MADE_TABLE lifecycle as a thin subclass of BaseTableManager.
Defines the 41-column schema for sessionized shot analytics including cycle time thresholds and time dimensions.
Delegates all shared logic (creation, truncation, incremental detection, overlap deletion) to the base class.
"""

from ..base_table_manager import BaseTableManager

LOGGER_NAME: str = "ANA_SHOT_MADE"
TABLE_NAME: str = "ANA_SHOT_MADE_TABLE"


class AnaShotMadeTableManager(BaseTableManager):
    """Table manager for the ANA_SHOT_MADE pipeline."""

    def get_table_name(self) -> str:
        """Return the ANA_SHOT_MADE table name."""
        return TABLE_NAME

    def get_logger_name(self) -> str:
        """Return the ANA_SHOT_MADE logger name."""
        return LOGGER_NAME

    def get_schema_columns(self) -> str:
        """Return the ANA_SHOT_MADE_TABLE column definitions."""
        return """
            COMPANY_NAME STRING,
            PLANT_NAME STRING,
            EQUIPMENT_CODE STRING,
            COUNTER_CODE STRING,
            CYCLE_TIME_STATUS STRING,
            LOCAL_SHOT_TIME TIMESTAMP,
            CYCLE_TIME_LIMIT1 FLOAT,
            CYCLE_TIME_LIMIT1UNIT STRING,
            CYCLE_TIME_LIMIT2 FLOAT,
            CYCLE_TIME_LIMIT2UNIT STRING,
            L1_ABOVE_ADJUSTED FLOAT,
            L2_ABOVE_ADJUSTED FLOAT,
            L1_BELOW_ADJUSTED FLOAT,
            L2_BELOW_ADJUSTED FLOAT,
            CONTRACTED_CYCLE_TIME FLOAT,
            ABOVE_COUNT FLOAT,
            WITHIN_COUNT FLOAT,
            BELOW_COUNT FLOAT,
            CT FLOAT,
            TEMPERATURE FLOAT,
            ABOVE_AVG_CT FLOAT,
            WITHIN_AVG_CT FLOAT,
            BELOW_AVG_CT FLOAT,
            SHOTS_MADE FLOAT,
            ROWNUM FLOAT,
            NEWSESSIONFLAGRENAMED FLOAT,
            SESSIONID FLOAT,
            SESSIONSTARTTIME TIMESTAMP,
            SESSIONENDTIME TIMESTAMP,
            PRODUCTION_TIME FLOAT,
            TOTAL_RUNTIME FLOAT,
            IDLE_TIME FLOAT,
            UPTIME_PERCENTAGE FLOAT,
            ISODAY FLOAT,
            ISOYEAR FLOAT,
            ISOWEEK FLOAT,
            ISOMONTH FLOAT,
            DAY STRING,
            MONTH STRING,
            YEAR STRING,
            WEEK STRING,
            QUARTER STRING,
            UPLOAD_TIME TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
        """


ana_shot_made_table_manager = AnaShotMadeTableManager()

create_ana_shot_made_table = ana_shot_made_table_manager.create_table
truncate_ana_shot_made_table = ana_shot_made_table_manager.truncate_table
get_incremental_start_date = ana_shot_made_table_manager.get_incremental_start_date
delete_overlap_data = ana_shot_made_table_manager.delete_overlap_data
get_table_statistics = ana_shot_made_table_manager.get_table_statistics
