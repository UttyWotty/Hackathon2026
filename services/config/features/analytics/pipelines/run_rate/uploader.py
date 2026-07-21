"""Handles DataFrame preparation and chunked uploads to the Snowflake RUNRATE table as a thin subclass of BaseUploader.
Orders 21 expected columns, converts timestamps and DATE to string format, and replaces NaN with None for Snowflake NULLs.
Extends upload validation with null-checks on critical columns (EQUIPMENT_CODE, SESSION_ID, MODE_CT, RUN_EFFICIENCY).
"""

import pandas as pd

from ..base_uploader import BaseUploader

LOGGER_NAME: str = "RUNRATE"
TABLE_NAME: str = "RUNRATE"

EXPECTED_COLUMNS: list[str] = [
    "EQUIPMENT_CODE",
    "SUPPLIER_NAME",
    "LOCAL_SHOT_TIME",
    "CT",
    "APPROVED_CT",
    "SESSION_ID",
    "SHOT_DIFF_SEC",
    "MODE_CT",
    "STOP",
    "RUN_EFFICIENCY",
    "TOTAL_RUN_TIME",
    "TOTAL_STOPS",
    "DOWNTIME",
    "PRODUCTION_TIME",
    "STOP_EVENTS",
    "MTTR",
    "MTBF",
    "DAY",
    "WEEK",
    "MONTH",
    "YEAR",
    "DATE",
]

TIMESTAMP_FORMAT: str = "%Y-%m-%d %H:%M:%S.%f"
DATE_FORMAT: str = "%Y-%m-%d"

CRITICAL_NULL_COLUMNS: list[str] = [
    "EQUIPMENT_CODE",
    "SESSION_ID",
    "MODE_CT",
    "RUN_EFFICIENCY",
]


class RunRateUploader(BaseUploader):
    """Uploader for the RUNRATE pipeline.

    Adds null-checks on critical columns during upload validation.
    """

    def get_table_name(self) -> str:
        """Return the RUNRATE table name."""
        return TABLE_NAME

    def get_logger_name(self) -> str:
        """Return the RUNRATE logger name."""
        return LOGGER_NAME

    def prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare DataFrame for RUNRATE upload.

        Selects and orders expected columns, converts LOCAL_SHOT_TIME
        and DATE to string format, and replaces NaN in SHOT_DIFF_SEC
        with None (NULL in Snowflake).

        Args:
            df: Processed DataFrame with all calculation results.

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

        df["LOCAL_SHOT_TIME"] = pd.to_datetime(df["LOCAL_SHOT_TIME"]).dt.strftime(
            TIMESTAMP_FORMAT
        )

        df["DATE"] = pd.to_datetime(df["DATE"]).dt.strftime(DATE_FORMAT)

        df["SHOT_DIFF_SEC"] = df["SHOT_DIFF_SEC"].where(
            pd.notna(df["SHOT_DIFF_SEC"]), None
        )

        self.logger.info(
            "DataFrame prepared: %s rows, %d columns",
            f"{len(df):,}",
            len(df.columns),
        )
        return df

    def validate_upload_extras(self, session: object) -> bool:
        """Check for null values in critical RUNRATE columns.

        Args:
            session: Snowflake Snowpark session

        Returns:
            True if no critical nulls found.
        """
        db: str = session.get_current_database().strip('"')
        schema: str = session.get_current_schema().strip('"')
        table: str = self.get_table_name()

        null_cases: str = ", ".join(
            f"SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END)"
            for col in CRITICAL_NULL_COLUMNS
        )
        null_check_query: str = f"SELECT {null_cases} FROM {db}.{schema}.{table}"
        null_result = session.sql(null_check_query).collect()
        if null_result:
            null_counts: list[int] = [
                null_result[0][i] for i in range(len(CRITICAL_NULL_COLUMNS))
            ]
            if any(null_counts):
                null_report: str = ", ".join(
                    f"{col}={count}"
                    for col, count in zip(CRITICAL_NULL_COLUMNS, null_counts)
                )
                self.logger.warning("Found null values: %s", null_report)
                return False
        return True


run_rate_uploader = RunRateUploader()

prepare_dataframe_for_upload = run_rate_uploader.prepare_dataframe
upload_to_snowflake = run_rate_uploader.upload_to_snowflake
validate_upload = run_rate_uploader.validate_upload
