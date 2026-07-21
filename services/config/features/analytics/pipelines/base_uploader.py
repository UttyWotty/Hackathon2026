"""Abstract base class for chunked DataFrame uploads to Snowflake analytics tables.
Provides shared logic for chunked write_pandas uploads with progress logging and post-upload row count validation.
Subclasses override table name and DataFrame preparation to handle pipeline-specific column transformations.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd
from snowflake.connector.pandas_tools import write_pandas

from .shared_config import CHUNK_SIZE

TIME_COLUMN: str = "LOCAL_SHOT_TIME"


class BaseUploader(ABC):
    """Base class for pipeline upload operations.

    Subclasses must implement get_table_name(), get_logger_name(), and
    prepare_dataframe() to define their specific upload behavior.

    Attributes:
        quote_identifiers: Passed to write_pandas. Defaults to True.
            ROI overrides to False for its uppercase column scheme.
    """

    quote_identifiers: bool = True

    def __init__(self) -> None:
        self.logger: logging.Logger = logging.getLogger(self.get_logger_name())

    @abstractmethod
    def get_table_name(self) -> str:
        """Return the Snowflake table name (e.g., 'ROI', 'RUNRATE')."""

    @abstractmethod
    def get_logger_name(self) -> str:
        """Return the logger name for this pipeline."""

    @abstractmethod
    def prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare DataFrame for upload with pipeline-specific transformations.

        Args:
            df: Raw or processed DataFrame.

        Returns:
            DataFrame ready for Snowflake upload.
        """

    def upload_to_snowflake(
        self,
        connector_conn: object,
        df: pd.DataFrame,
        chunk_size: int = CHUNK_SIZE,
        overwrite: bool = False,
    ) -> bool:
        """Upload DataFrame to Snowflake table in chunks.

        Args:
            connector_conn: Snowflake connector connection
            df: DataFrame to upload
            chunk_size: Number of rows per chunk
            overwrite: Whether to overwrite on first chunk

        Returns:
            True if upload succeeded, False otherwise.
        """
        if df.empty:
            self.logger.warning("DataFrame is empty, skipping upload")
            return True

        total_rows: int = len(df)
        db: str = (connector_conn.database or "").strip('"')
        schema: str = (connector_conn.schema or "").strip('"')
        table: str = self.get_table_name()
        self.logger.info(
            "Uploading %s rows to %s.%s.%s in chunks of %s...",
            f"{total_rows:,}",
            db,
            schema,
            table,
            f"{chunk_size:,}",
        )

        is_first_chunk: bool = True

        try:
            for start in range(0, total_rows, chunk_size):
                end: int = min(start + chunk_size, total_rows)
                chunk: pd.DataFrame = df.iloc[start:end]

                self.logger.info(
                    "Uploading chunk: rows %s to %s...",
                    f"{start:,}",
                    f"{end:,}",
                )

                write_pandas(
                    conn=connector_conn,
                    df=chunk,
                    table_name=table,
                    schema=schema,
                    database=db,
                    overwrite=overwrite and is_first_chunk,
                    auto_create_table=False,
                    quote_identifiers=self.quote_identifiers,
                )

                is_first_chunk = False

                progress: float = end / total_rows * 100
                self.logger.info(
                    "Progress: %.1f%% (%s/%s rows)",
                    progress,
                    f"{end:,}",
                    f"{total_rows:,}",
                )

            self.logger.info(
                "Upload completed successfully: %s rows uploaded",
                f"{total_rows:,}",
            )
            return True

        except Exception as e:
            self.logger.error("Upload failed: %s", e, exc_info=True)
            return False

    def validate_upload_extras(self, session: object) -> bool:
        """Hook for subclasses to run additional upload validation checks.

        Override in subclasses that need null-checks or other validation
        beyond row count.

        Args:
            session: Snowflake Snowpark session

        Returns:
            True if extra validation passed.
        """
        return True

    def validate_upload(
        self,
        session: object,
        expected_row_count: Optional[int] = None,
    ) -> bool:
        """Validate data was uploaded correctly.

        Args:
            session: Snowflake Snowpark session
            expected_row_count: Expected number of rows (optional)

        Returns:
            True if validation passed.
        """
        db: str = session.get_current_database().strip('"')
        schema: str = session.get_current_schema().strip('"')
        table: str = self.get_table_name()
        try:
            count_query: str = (
                f"SELECT COUNT(*) as row_count FROM {db}.{schema}.{table}"
            )
            result = session.sql(count_query).collect()
            actual_row_count: int = result[0][0] if result else 0

            self.logger.info(
                "%s table now contains %s rows",
                table,
                f"{actual_row_count:,}",
            )

            if expected_row_count is not None:
                if actual_row_count < expected_row_count:
                    self.logger.warning(
                        "Row count mismatch: expected %s, got %s",
                        f"{expected_row_count:,}",
                        f"{actual_row_count:,}",
                    )
                    return False

            if not self.validate_upload_extras(session):
                return False

            self.logger.info("Upload validation passed")
            return True

        except Exception as e:
            self.logger.error("Validation failed: %s", e)
            return False
