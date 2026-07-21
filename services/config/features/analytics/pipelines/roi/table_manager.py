"""Manages the Snowflake ROI table lifecycle as a thin subclass of BaseTableManager.
Defines the ROI-specific 12-column schema and enables force_recreate_on_full_load for correct schema enforcement.
Delegates all shared logic (creation, truncation, incremental detection, overlap deletion) to the base class.
"""

from ..base_table_manager import BaseTableManager

LOGGER_NAME: str = "ROI"
TABLE_NAME: str = "ROI"


class RoiTableManager(BaseTableManager):
    """Table manager for the ROI pipeline.

    Sets force_recreate_on_full_load to True so full loads drop and
    recreate the table instead of truncating, ensuring uppercase column
    schema correctness.
    """

    force_recreate_on_full_load: bool = True

    def get_table_name(self) -> str:
        """Return the ROI table name."""
        return TABLE_NAME

    def get_logger_name(self) -> str:
        """Return the ROI logger name."""
        return LOGGER_NAME

    def get_schema_columns(self) -> str:
        """Return the ROI table column definitions."""
        return """
            SUPPLIER_NAME STRING,
            EQUIPMENT_CODE STRING,
            CT FLOAT,
            APPROVED_CT FLOAT,
            AVERAGE_CT FLOAT,
            LOCAL_SHOT_TIME TIMESTAMP_NTZ(3),
            TOTAL_SHOT_COUNT NUMBER,
            PART_ID STRING,
            MOLD_ID NUMBER,
            SUPPLIER_ID NUMBER,
            COUNTER_ID NUMBER,
            VOLUME NUMBER,
            UPLOAD_TIME TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
        """


roi_table_manager = RoiTableManager()

create_roi_table = roi_table_manager.create_table
truncate_roi_table = roi_table_manager.truncate_table
get_incremental_start_date = roi_table_manager.get_incremental_start_date
delete_overlap_data = roi_table_manager.delete_overlap_data
get_table_statistics = roi_table_manager.get_table_statistics
