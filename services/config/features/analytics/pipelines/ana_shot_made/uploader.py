"""Handles DataFrame preparation and chunked uploads to the Snowflake ANA_SHOT_MADE_TABLE as a thin subclass of BaseUploader.
Converts timestamp columns to string format and count columns to integers for Snowflake compatibility.
Delegates chunked upload logic, progress logging, and row count validation to the base class.
"""

import pandas as pd

from ..base_uploader import BaseUploader

LOGGER_NAME: str = "ANA_SHOT_MADE"
TABLE_NAME: str = "ANA_SHOT_MADE_TABLE"

TIMESTAMP_COLUMNS: list[str] = [
    "LOCAL_SHOT_TIME",
    "SESSIONSTARTTIME",
    "SESSIONENDTIME",
]

INT_COLUMNS: list[str] = [
    "ABOVE_COUNT",
    "WITHIN_COUNT",
    "BELOW_COUNT",
    "SHOTS_MADE",
]

TIMESTAMP_FORMAT: str = "%Y-%m-%d %H:%M:%S"
INT_FILL_VALUE: int = 0


class AnaShotMadeUploader(BaseUploader):
    """Uploader for the ANA_SHOT_MADE pipeline."""

    def get_table_name(self) -> str:
        """Return the ANA_SHOT_MADE table name."""
        return TABLE_NAME

    def get_logger_name(self) -> str:
        """Return the ANA_SHOT_MADE logger name."""
        return LOGGER_NAME

    def prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare DataFrame for ANA_SHOT_MADE upload.

        Converts timestamp columns to string format and count columns
        to integers for Snowflake compatibility.

        Args:
            df: DataFrame from the data fetcher with sessionization results.

        Returns:
            DataFrame ready for upload.
        """
        self.logger.info("Preparing DataFrame for upload...")

        for col in TIMESTAMP_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col]).dt.strftime(TIMESTAMP_FORMAT)

        for col_name in INT_COLUMNS:
            if col_name in df.columns:
                df[col_name] = df[col_name].fillna(INT_FILL_VALUE).astype(int)

        self.logger.info(
            "DataFrame prepared: %s rows, %d columns",
            f"{len(df):,}",
            len(df.columns),
        )
        return df


ana_shot_made_uploader = AnaShotMadeUploader()

prepare_dataframe_for_upload = ana_shot_made_uploader.prepare_dataframe
upload_to_snowflake = ana_shot_made_uploader.upload_to_snowflake
validate_upload = ana_shot_made_uploader.validate_upload
