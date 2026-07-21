"""
Analytics Pipelines - Data Processing Pipelines.

Contains data pipelines that feed the analysis modules:
- Master Shot Table Pipeline: Foundation data processing
"""

from .master_shot_table.pipeline import MasterShotPipeline
from .shared_config import PipelineConfig

# Legacy alias for backwards compatibility
OptimizedMasterShotPipeline = MasterShotPipeline
ProcessingConfig = PipelineConfig

__all__ = [
    "MasterShotPipeline",
    "PipelineConfig",
    # Legacy aliases
    "OptimizedMasterShotPipeline",
    "ProcessingConfig",
]
