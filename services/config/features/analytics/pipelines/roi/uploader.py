"""Handles DataFrame preparation and chunked uploads to the Snowflake ROI table as a thin subclass of BaseUploader.
Transforms lowercase column names to uppercase and formats LOCAL_SHOT_TIME with millisecond precision.
Disables quote_identifiers for write_pandas to match the ROI table's uppercase column scheme.
"""

import pandas as pd

from ..base_uploader import BaseUploader

LOGGER_NAME: str = "ROI"
TABLE_NAME: str = "ROI"

EXPECTED_COLUMNS: list[str] = [
    "supplier_name",
    "equipment_code",
    "ct",
    "approved_ct",
    "average_ct",
    "local_shot_time",
    "total_shot_count",
    "part_id",
    "mold_id",
    "supplier_id",
    "counter_id",
    "volume",
]

NUMERIC_COLUMNS: list[str] = [
    "ct",
    "approved_ct",
    "average_ct",
    "total_shot_count",
    "volume",
    "supplier_id",
    "counter_id",
]

TIMESTAMP_FORMAT: str = "%Y-%m-%d %H:%M:%S.%f"
MILLISECOND_TRIM: int = -3


class RoiUploader(BaseUploader):
    """Uploader for the ROI pipeline.

    Disables quote_identifiers since ROI uses uppercase columns
    without quoting.
    """

    quote_identifiers: bool = False

    def get_table_name(self) -> str:
        """Return the ROI table name."""
        return TABLE_NAME

    def get_logger_name(self) -> str:
        """Return the ROI logger name."""
        return LOGGER_NAME

    def prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare DataFrame for ROI upload.

        Selects and orders expected columns, converts LOCAL_SHOT_TIME
        to string with millisecond precision, and uppercases all column
        names to match the Snowflake schema.

        Args:
            df: DataFrame with lowercase column names from the data fetcher.

        Returns:
            DataFrame ready for upload.
        """
        self.logger.info("Preparing DataFrame for upload...")

        missing_columns: list[str] = [
            col for col in EXPECTED_COLUMNS if col not in df.columns
        ]
        if missing_columns:
            raise ValueError(
                "Missing required columns for upload: %s" % missing_columns
            )

        df = df[EXPECTED_COLUMNS].copy()

        for col in NUMERIC_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["local_shot_time"] = (
            pd.to_datetime(df["local_shot_time"])
            .dt.strftime(TIMESTAMP_FORMAT)
            .str[:MILLISECOND_TRIM]
        )

        df.columns = [c.upper() for c in df.columns]

        self.logger.info(
            "DataFrame prepared: %s rows, %d columns",
            f"{len(df):,}",
            len(df.columns),
        )
        return df


roi_uploader = RoiUploader()

prepare_dataframe_for_upload = roi_uploader.prepare_dataframe
upload_to_snowflake = roi_uploader.upload_to_snowflake
validate_upload = roi_uploader.validate_upload
