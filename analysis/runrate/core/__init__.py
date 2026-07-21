"""
RunRate Core Module.

Provides core business logic for RunRate analysis:
- Data loading from Snowflake
- Data preprocessing and filtering
- Session analysis and metrics calculation
"""

from .data_loader import (
    cleanup_db_executor,
    get_equipment_codes,
    get_supplier_names,
    load_data,
    load_data_async,
)
from .data_processor import calculate_session_statistics, preprocess_data
from .session_analyzer import process_shots

__all__ = [
    # Data loading
    "get_supplier_names",
    "get_equipment_codes",
    "load_data",
    "load_data_async",
    "cleanup_db_executor",
    # Data processing
    "preprocess_data",
    "calculate_session_statistics",
    # Session analysis
    "process_shots",
]
