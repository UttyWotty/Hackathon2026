"""
Master Shot Table Pipeline
==========================

Foundation data pipeline that transforms raw shot data into the DEMO_TABLE.
Supports incremental (7-day overlap) and full historical processing modes.
"""

from .pipeline import MasterShotPipeline
from .sql_builder import build_optimized_shot_query

__all__ = ["MasterShotPipeline", "build_optimized_shot_query"]
