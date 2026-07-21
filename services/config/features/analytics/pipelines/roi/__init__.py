"""
ROI Pipeline Package
====================

Modular pipeline for extracting and uploading ROI data from MASTER_SHOT_TABLE.

Modules:
- config: Snowflake connection and constants
- data_fetcher: Extract data from MASTER_SHOT_TABLE with filters
- table_manager: ROI table creation and management
- uploader: Chunked data upload to Snowflake
- main: Main pipeline orchestration and execution

Usage:
    from roi import run

    # Run incremental processing
    run(full_historical_load=False, overlap_days=7)

    # Run full historical load
    run(full_historical_load=True)
"""

__version__ = "1.0.0"

# Expose main run function for easy import
from .main import run

__all__ = ["run"]
