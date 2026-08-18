"""
File Operations Utilities
=========================

File I/O, path management, and file handling utilities.

Author: Utku Gulbardak
Date: 2025-10-28
"""

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    """
    Get the manufacturing-api project root directory.

    Returns:
        Path: Absolute path to the project root

    Example:
        >>> root = get_project_root()
        >>> print(root)  # /path/to/manufacturing-api
    """
    # Go up from analysis/shared/ to manufacturing-api/
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent
    return project_root


def get_output_dir(module_name: str, create: bool = True) -> Path:
    """
    Get standardized output directory for a module.

    Outputs go to /tmp to avoid polluting the project directory.

    Args:
        module_name: Name of the analysis module (e.g., "roi", "deviation")
        create: Whether to create the directory if it doesn't exist

    Returns:
        Path: Absolute path to the module's output directory
    """
    output_dir = Path("/tmp/agent_output") / module_name

    if create:
        output_dir.mkdir(parents=True, exist_ok=True)

    return output_dir


def ensure_directory(directory: str) -> Path:
    """
    Ensure a directory exists, create if it doesn't.

    Args:
        directory: Directory path to create

    Returns:
        Path: Path object for the directory

    Example:
        >>> output_dir = ensure_directory("output/reports")
        >>> print(f"Directory ready: {output_dir}")
    """
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    logger.debug(f"✅ Directory ensured: {dir_path}")
    return dir_path


def generate_filename(
    prefix: str,
    extension: str,
    timestamp: bool = True,
    separator: str = "_",
) -> str:
    """
    Generate a standardized filename with optional timestamp.

    Args:
        prefix: Filename prefix (e.g., "ROI_Analysis")
        extension: File extension without dot (e.g., "xlsx")
        timestamp: Whether to include timestamp (default: True)
        separator: Separator between parts (default: "_")

    Returns:
        str: Generated filename

    Example:
        >>> filename = generate_filename("ROI_Analysis", "xlsx")
        >>> print(filename)  # ROI_Analysis_20241028_153045.xlsx
    """
    parts = [prefix]

    if timestamp:
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        parts.append(timestamp_str)

    filename = separator.join(parts) + f".{extension}"
    logger.debug(f"✅ Generated filename: {filename}")
    return filename


def generate_filepath(
    directory: str,
    prefix: str,
    extension: str,
    timestamp: bool = True,
    ensure_dir: bool = True,
) -> str:
    """
    Generate a complete filepath with directory creation.

    Args:
        directory: Output directory
        prefix: Filename prefix
        extension: File extension
        timestamp: Include timestamp in filename
        ensure_dir: Create directory if it doesn't exist

    Returns:
        str: Complete filepath

    Example:
        >>> filepath = generate_filepath("output", "report", "xlsx")
        >>> print(filepath)  # output/report_20241028_153045.xlsx
    """
    if ensure_dir:
        dir_path = ensure_directory(directory)
    else:
        dir_path = Path(directory)

    filename = generate_filename(prefix, extension, timestamp)
    filepath = dir_path / filename

    logger.debug(f"✅ Generated filepath: {filepath}")
    return str(filepath)


def safe_write_json(data: Dict[str, Any], filepath: str) -> bool:
    """
    Safely write JSON data to file with error handling.

    Args:
        data: Dictionary to write as JSON
        filepath: Output file path

    Returns:
        bool: True if successful, False otherwise

    Example:
        >>> data = {"status": "success", "count": 100}
        >>> safe_write_json(data, "output/results.json")
    """
    try:
        # Ensure directory exists
        dir_path = Path(filepath).parent
        ensure_directory(str(dir_path))

        # Write JSON with pretty printing
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ JSON written successfully: {filepath}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to write JSON to {filepath}: {e}")
        return False


def safe_read_json(filepath: str, default: Any = None) -> Any:
    """
    Safely read JSON data from file with error handling.

    Args:
        filepath: Input file path
        default: Default value if file doesn't exist or fails to parse

    Returns:
        Parsed JSON data or default value

    Example:
        >>> data = safe_read_json("config.json", default={})
        >>> print(data)
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        logger.debug(f"✅ JSON read successfully: {filepath}")
        return data

    except FileNotFoundError:
        logger.warning(f"⚠️  File not found: {filepath}, returning default value")
        return default
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse JSON from {filepath}: {e}")
        return default
    except Exception as e:
        logger.error(f"❌ Error reading {filepath}: {e}")
        return default


@contextmanager
def temporary_file(suffix: str = "", prefix: str = "tmp", dir: Optional[str] = None):
    """
    Context manager for temporary file that is automatically cleaned up.

    Args:
        suffix: File suffix/extension
        prefix: File prefix
        dir: Directory for temporary file

    Yields:
        str: Path to temporary file

    Example:
        >>> with temporary_file(suffix=".csv") as temp_path:
        ...     df.to_csv(temp_path)
        ...     # Use temp file
        ... # File is automatically deleted
    """
    temp_fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir)
    try:
        os.close(temp_fd)
        logger.debug(f"✅ Created temporary file: {temp_path}")
        yield temp_path
    finally:
        try:
            os.unlink(temp_path)
            logger.debug(f"🗑️  Deleted temporary file: {temp_path}")
        except Exception as e:
            logger.warning(f"⚠️  Could not delete temporary file {temp_path}: {e}")


def get_file_size_mb(filepath: str) -> float:
    """
    Get file size in megabytes.

    Args:
        filepath: Path to file

    Returns:
        float: File size in MB

    Example:
        >>> size = get_file_size_mb("report.xlsx")
        >>> print(f"File size: {size:.2f} MB")
    """
    try:
        size_bytes = os.path.getsize(filepath)
        size_mb = size_bytes / (1024 * 1024)
        return size_mb
    except Exception as e:
        logger.error(f"❌ Could not get file size for {filepath}: {e}")
        return 0.0


def file_exists(filepath: str) -> bool:
    """
    Check if a file exists.

    Args:
        filepath: Path to check

    Returns:
        bool: True if file exists

    Example:
        >>> if file_exists("config.json"):
        ...     print("Config found")
    """
    return Path(filepath).exists()


def clean_filename(filename: str, replacement: str = "_") -> str:
    """
    Clean filename by removing/replacing invalid characters.

    Args:
        filename: Original filename
        replacement: Character to replace invalid chars with

    Returns:
        str: Cleaned filename

    Example:
        >>> clean = clean_filename("my/file*name?.txt")
        >>> print(clean)  # my_file_name_.txt
    """
    invalid_chars = '<>:"/\\|?*'
    cleaned = filename
    for char in invalid_chars:
        cleaned = cleaned.replace(char, replacement)
    return cleaned


def get_absolute_path(relative_path: str, base_dir: Optional[str] = None) -> str:
    """
    Convert relative path to absolute path.

    Args:
        relative_path: Relative path
        base_dir: Base directory (defaults to current working directory)

    Returns:
        str: Absolute path

    Example:
        >>> abs_path = get_absolute_path("config/roi_key.p8")
        >>> print(abs_path)
    """
    if base_dir is None:
        base_dir = os.getcwd()

    return str(Path(base_dir) / relative_path)


def list_files_by_extension(
    directory: str,
    extension: str,
    recursive: bool = False,
) -> list:
    """
    List all files with specific extension in a directory.

    Args:
        directory: Directory to search
        extension: File extension (e.g., ".xlsx")
        recursive: Search recursively in subdirectories

    Returns:
        list: List of file paths

    Example:
        >>> excel_files = list_files_by_extension("output", ".xlsx")
        >>> print(f"Found {len(excel_files)} Excel files")
    """
    dir_path = Path(directory)

    if not dir_path.exists():
        logger.warning(f"⚠️  Directory not found: {directory}")
        return []

    if recursive:
        pattern = f"**/*{extension}"
    else:
        pattern = f"*{extension}"

    files = list(dir_path.glob(pattern))
    logger.debug(
        f"✅ Found {len(files)} files with extension '{extension}' in {directory}"
    )

    return [str(f) for f in files]


# Module metadata
__version__ = "1.0.0"
__author__ = "Utku Gulbardak"
__all__ = [
    "ensure_directory",
    "generate_filename",
    "generate_filepath",
    "safe_write_json",
    "safe_read_json",
    "temporary_file",
    "get_file_size_mb",
    "file_exists",
    "clean_filename",
    "get_absolute_path",
    "list_files_by_extension",
]
