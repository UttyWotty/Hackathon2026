"""Orchestrates the run rate pipeline calculating run efficiency metrics per session for equipment performance analysis.
Thin subclass of BasePipeline that wires up run_rate components and overrides process_data with the 6-step calculation pipeline.
Coordinates session detection, mode CT calculation, stop detection, stop metrics, run efficiency, and time dimensions.
"""

import time

import pandas as pd

from ..base_pipeline import BasePipeline
from ..base_table_manager import BaseTableManager
from ..base_uploader import BaseUploader
from ..shared_config import OVERLAP_DAYS
from .calculations import (
    calculate_mode_ct,
    calculate_run_efficiency,
    calculate_stop_metrics,
    detect_stops,
    validate_calculations,
)
from .config import setup_logging
from .data_fetcher import (
    fetch_full_data as _fetch_full,
    fetch_incremental_data as _fetch_incremental,
    validate_data as _validate,
)
from .session_processor import (
    detect_sessions,
    get_session_statistics,
    validate_sessions,
)
from .table_manager import RunRateTableManager
from .time_utils import (
    extract_time_dimensions,
    get_time_range_summary,
    validate_time_dimensions,
)
from .uploader import RunRateUploader

setup_logging()

SEPARATOR_WIDTH: int = 80
TOTAL_PIPELINE_STEPS: int = 6


class RunRatePipeline(BasePipeline):
    """Pipeline orchestrator for the RUNRATE table.

    Overrides process_data to run the full 6-step calculation pipeline:
    session detection, mode CT, stop detection, stop metrics,
    run efficiency, and time dimensions.
    """

    def __init__(self) -> None:
        super().__init__()
        self._table_manager: RunRateTableManager = RunRateTableManager()
        self._uploader: RunRateUploader = RunRateUploader()

    def get_pipeline_name(self) -> str:
        """Return the RUNRATE pipeline name."""
        return "RUNRATE"

    def get_table_manager(self) -> BaseTableManager:
        """Return the RUNRATE table manager."""
        return self._table_manager

    def get_uploader(self) -> BaseUploader:
        """Return the RUNRATE uploader."""
        return self._uploader

    def fetch_full_data(self, session: object) -> pd.DataFrame:
        """Fetch full historical RUNRATE data.

        Args:
            session: Snowflake Snowpark session

        Returns:
            DataFrame with all historical data.
        """
        return _fetch_full(session)

    def fetch_incremental_data(self, session: object, start_date: str) -> pd.DataFrame:
        """Fetch incremental RUNRATE data from start_date.

        Args:
            session: Snowflake Snowpark session
            start_date: Start date (YYYY-MM-DD) for incremental fetch

        Returns:
            DataFrame with incremental data.
        """
        return _fetch_incremental(session, start_date)

    def validate_data(self, df: pd.DataFrame) -> bool:
        """Validate fetched RUNRATE data.

        Args:
            df: DataFrame to validate

        Returns:
            True if validation passed.
        """
        return _validate(df)

    def process_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process data through the 6-step calculation pipeline.

        Steps:
            1. Session detection (8-hour gap logic)
            2. Mode CT calculation
            3. Stop detection (3 criteria)
            4. Stop metrics (MTTR, MTBF, stop events, total stops)
            5. Run efficiency calculation
            6. Time dimension extraction

        Args:
            df: Raw data from MASTER_SHOT_TABLE

        Returns:
            Processed data ready for upload.
        """
        self.logger.info("=" * SEPARATOR_WIDTH)
        self.logger.info("PROCESSING DATA THROUGH CALCULATION PIPELINE")
        self.logger.info("=" * SEPARATOR_WIDTH)

        pipeline_start: float = time.time()

        self.logger.info("Step 1/%d: Session Detection", TOTAL_PIPELINE_STEPS)
        df = detect_sessions(df)
        validate_sessions(df)
        session_stats: dict = get_session_statistics(df)
        self.logger.info(
            "-> %s sessions detected (%.1f avg shots/session)",
            f"{session_stats['total_sessions']:,}",
            session_stats["avg_shots_per_session"],
        )

        self.logger.info("Step 2/%d: Mode CT Calculation", TOTAL_PIPELINE_STEPS)
        df = calculate_mode_ct(df)

        self.logger.info("Step 3/%d: Stop Detection", TOTAL_PIPELINE_STEPS)
        df = detect_stops(df)

        self.logger.info("Step 4/%d: Stop Metrics Calculation", TOTAL_PIPELINE_STEPS)
        df = calculate_stop_metrics(df)

        self.logger.info("Step 5/%d: Run Efficiency Calculation", TOTAL_PIPELINE_STEPS)
        df = calculate_run_efficiency(df)
        validate_calculations(df)

        self.logger.info("Step 6/%d: Time Dimension Extraction", TOTAL_PIPELINE_STEPS)
        df = extract_time_dimensions(df)
        validate_time_dimensions(df)
        time_summary: dict = get_time_range_summary(df)
        self.logger.info(
            "-> Time range: %s to %s (%d unique dates)",
            time_summary["min_date"],
            time_summary["max_date"],
            time_summary["unique_dates"],
        )

        pipeline_elapsed: float = round(time.time() - pipeline_start, 2)
        self.logger.info("=" * SEPARATOR_WIDTH)
        self.logger.info("Pipeline processing completed in %ss", pipeline_elapsed)
        self.logger.info(
            "Final dataset: %s rows x %d columns",
            f"{len(df):,}",
            len(df.columns),
        )
        self.logger.info("=" * SEPARATOR_WIDTH)
        return df


_pipeline = RunRatePipeline()


def run(
    full_historical_load: bool = False,
    overlap_days: int = OVERLAP_DAYS,
    schema_name: str = None,
) -> bool:
    """Main execution function for the run rate pipeline.

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
    FULL_HISTORICAL_LOAD: bool = True
    run(full_historical_load=FULL_HISTORICAL_LOAD, overlap_days=OVERLAP_DAYS)
