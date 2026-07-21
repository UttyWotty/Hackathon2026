"""
Run Rate Pipeline Package
=========================

Modular pipeline for calculating run efficiency metrics per session.

Modules:
- config: Snowflake connection and constants
- data_fetcher: Extract data from MASTER_SHOT_TABLE
- session_processor: Session detection based on 8-hour gaps
- calculations: Mode CT, stop detection, run efficiency calculations
- time_utils: Time dimension extraction (day, week, month, year)
- table_manager: RUNRATE table creation and management
- uploader: Chunked data upload to Snowflake
- main: Main pipeline orchestration and execution

Usage:
    from run_rate import run

    # Run incremental processing
    run(full_historical_load=False, overlap_days=7)

    # Run full historical load
    run(full_historical_load=True)
"""

__version__ = "1.0.0"

# Expose main run function for easy import
from .main import run

__all__ = ["run"]
