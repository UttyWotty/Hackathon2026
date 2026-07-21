"""
ANA_SHOT_MADE Pipeline Package
===============================

Modular pipeline for building ANA_SHOT_MADE_TABLE from MASTER_SHOT_TABLE with sessionization logic.

Modules:
- config: Snowflake connection and constants
- data_fetcher: Extract data from MASTER_SHOT_TABLE with complex sessionization SQL
- table_manager: ANA_SHOT_MADE_TABLE creation and management
- uploader: Chunked data upload to Snowflake
- main: Main pipeline orchestration and execution

Usage:
    from ana_shot_made import run

    # Run incremental processing
    run(full_historical_load=False, overlap_days=7)

    # Run full historical load
    run(full_historical_load=True)
"""

__version__ = "1.0.0"

# Expose main run function for easy import
from .main import run

__all__ = ["run"]
