"""
Standardized Logging Utilities
===============================

Provides consistent logging setup across all analysis modules.
Eliminates code duplication and ensures uniform log formatting.

Author: Utku Gulbardak
Date: 2025-10-28
"""

import logging
import sys
import time
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Optional


def setup_module_logger(
    module_name: str,
    log_dir: str = "logs",
    log_level: int = logging.INFO,
    console_output: bool = True,
    file_output: bool = True,
) -> logging.Logger:
    """
    Set up a standardized logger for analysis modules.

    Creates a logger with both file and optional console output,
    using a consistent format across all analysis modules.

    Args:
        module_name: Name for the log file and logger (e.g., "ROI_Analysis")
        log_dir: Directory to store log files (default: "logs")
        log_level: Logging level (default: logging.INFO)
        console_output: Whether to also output logs to console (default: True)
        file_output: Whether to write logs to file (default: True)

    Returns:
        logging.Logger: Configured logger instance

    Example:
        >>> logger = setup_module_logger("ROI_Analysis")
        >>> logger.info("Starting ROI analysis")
    """
    # Create logger
    logger = logging.getLogger(module_name)
    logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    if file_output:
        # Create log directory if it doesn't exist
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # Create log file path with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_path / f"{module_name}_{timestamp}.log"

        file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    logger.info(f"Logger initialized for {module_name}")
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger for a specific module.

    Args:
        name: Module name (usually __name__)

    Returns:
        logging.Logger: Logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing data")
    """
    return logging.getLogger(name)


def log_execution_time(logger: Optional[logging.Logger] = None):
    """
    Decorator to log function execution time.

    Args:
        logger: Optional logger instance (creates one if not provided)

    Example:
        >>> @log_execution_time()
        ... def process_data(df):
        ...     # Process data
        ...     return df
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = get_logger(func.__module__)

            start_time = time.time()
            logger.info(f"⏱️  Starting {func.__name__}...")

            try:
                result = func(*args, **kwargs)
                elapsed_time = time.time() - start_time
                logger.info(
                    f"✅ {func.__name__} completed in {elapsed_time:.2f} seconds"
                )
                return result

            except Exception as e:
                elapsed_time = time.time() - start_time
                logger.error(
                    f"❌ {func.__name__} failed after {elapsed_time:.2f} seconds: {e}"
                )
                raise

        return wrapper

    return decorator


def log_dataframe_info(
    df, name: str = "DataFrame", logger: Optional[logging.Logger] = None
):
    """
    Log DataFrame information for debugging.

    Args:
        df: pandas DataFrame to log
        name: Name to identify the DataFrame
        logger: Optional logger instance

    Example:
        >>> log_dataframe_info(df, "Production Data")
    """
    if logger is None:
        logger = get_logger(__name__)

    logger.info(f"📊 {name} Info:")
    logger.info(f"   - Shape: {df.shape}")
    logger.info(f"   - Columns: {list(df.columns)}")
    logger.info(f"   - Memory: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

    if df.empty:
        logger.warning(f"⚠️  {name} is empty!")
    else:
        logger.info(f"   - First row date: {df.iloc[0].get('DATE', 'N/A')}")
        logger.info(f"   - Last row date: {df.iloc[-1].get('DATE', 'N/A')}")


def log_analysis_start(
    analysis_name: str, parameters: dict, logger: Optional[logging.Logger] = None
):
    """
    Log the start of an analysis with parameters.

    Args:
        analysis_name: Name of the analysis
        parameters: Dictionary of analysis parameters
        logger: Optional logger instance

    Example:
        >>> log_analysis_start("ROI Analysis", {
        ...     "machine_id": "MX-7110",
        ...     "date_range": "2024-01-01 to 2024-12-31"
        ... })
    """
    if logger is None:
        logger = get_logger(__name__)

    logger.info("=" * 70)
    logger.info(f"🚀 Starting {analysis_name}")
    logger.info("=" * 70)
    logger.info("Parameters:")
    for key, value in parameters.items():
        logger.info(f"   - {key}: {value}")
    logger.info("=" * 70)


def log_analysis_complete(
    analysis_name: str, results_summary: dict, logger: Optional[logging.Logger] = None
):
    """
    Log the completion of an analysis with summary.

    Args:
        analysis_name: Name of the analysis
        results_summary: Dictionary of key results
        logger: Optional logger instance

    Example:
        >>> log_analysis_complete("ROI Analysis", {
        ...     "total_records": 1000,
        ...     "efficiency": "85.5%"
        ... })
    """
    if logger is None:
        logger = get_logger(__name__)

    logger.info("=" * 70)
    logger.info(f"✅ {analysis_name} Complete")
    logger.info("=" * 70)
    logger.info("Summary:")
    for key, value in results_summary.items():
        logger.info(f"   - {key}: {value}")
    logger.info("=" * 70)


# Module metadata
__version__ = "1.0.0"
__author__ = "Utku Gulbardak"
__all__ = [
    "setup_module_logger",
    "get_logger",
    "log_execution_time",
    "log_dataframe_info",
    "log_analysis_start",
    "log_analysis_complete",
]
