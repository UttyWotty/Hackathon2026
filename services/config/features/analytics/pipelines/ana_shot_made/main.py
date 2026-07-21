"""Orchestrates ANA_SHOT_MADE pipeline building sessionized shot analytics from MASTER_SHOT_TABLE.
Thin subclass of BasePipeline that wires up ANA_SHOT_MADE-specific data fetcher, table manager, and uploader.
Supports full historical loads with truncation and incremental 7-day overlap updates.
"""

import pandas as pd

from ..base_pipeline import BasePipeline
from ..base_table_manager import BaseTableManager
from ..base_uploader import BaseUploader
from ..shared_config import OVERLAP_DAYS
from .config import setup_logging
from .data_fetcher import (
    fetch_full_data as _fetch_full,
    fetch_incremental_data as _fetch_incremental,
    validate_data as _validate,
)
from .table_manager import AnaShotMadeTableManager
from .uploader import AnaShotMadeUploader

setup_logging()


class AnaShotMadePipeline(BasePipeline):
    """Pipeline orchestrator for the ANA_SHOT_MADE_TABLE."""

    def __init__(self) -> None:
        super().__init__()
        self._table_manager: AnaShotMadeTableManager = AnaShotMadeTableManager()
        self._uploader: AnaShotMadeUploader = AnaShotMadeUploader()

    def get_pipeline_name(self) -> str:
        """Return the ANA_SHOT_MADE pipeline name."""
        return "ANA_SHOT_MADE"

    def get_table_manager(self) -> BaseTableManager:
        """Return the ANA_SHOT_MADE table manager."""
        return self._table_manager

    def get_uploader(self) -> BaseUploader:
        """Return the ANA_SHOT_MADE uploader."""
        return self._uploader

    def fetch_full_data(self, session: object) -> pd.DataFrame:
        """Fetch full historical ANA_SHOT_MADE data.

        Args:
            session: Snowflake Snowpark session

        Returns:
            DataFrame with all historical data.
        """
        return _fetch_full(session)

    def fetch_incremental_data(self, session: object, start_date: str) -> pd.DataFrame:
        """Fetch incremental ANA_SHOT_MADE data from start_date.

        Args:
            session: Snowflake Snowpark session
            start_date: Start date (YYYY-MM-DD) for incremental fetch

        Returns:
            DataFrame with incremental data.
        """
        return _fetch_incremental(session, start_date)

    def validate_data(self, df: pd.DataFrame) -> bool:
        """Validate fetched ANA_SHOT_MADE data.

        Args:
            df: DataFrame to validate

        Returns:
            True if validation passed.
        """
        return _validate(df)


_pipeline = AnaShotMadePipeline()


def run(
    full_historical_load: bool = False,
    overlap_days: int = OVERLAP_DAYS,
    schema_name: str = None,
) -> bool:
    """Main execution function for the ANA_SHOT_MADE pipeline.

    Args:
        full_historical_load: If True, process all historical data.
        overlap_days: Number of days to reprocess in incremental mode.
        schema_name: Optional schema override (e.g., CLIENT_A, CLIENT_B)

    Returns:
        True if processing succeeded.
    """
    return _pipeline.run(
        full_historical_load=full_historical_load,
        overlap_days=overlap_days,
        schema_name=schema_name,
    )


if __name__ == "__main__":
    FULL_HISTORICAL_LOAD: bool = False
    run(full_historical_load=FULL_HISTORICAL_LOAD, overlap_days=OVERLAP_DAYS)
