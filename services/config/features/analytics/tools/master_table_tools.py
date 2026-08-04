"""
Master Shot Table Refresh Tool - Foundation Data Pipeline.

Refreshes the DEMO_TABLE that serves as the canonical data source
for all analysis modules (ROI, RCA, etc.).

This tool wraps the OptimizedMasterShotPipeline which provides:
- Incremental processing with overlap detection
- Memory-efficient chunked processing
- Full historical loads for initial setup
- Smart date range handling

Author: Utku Gulbardak
Date: 2025-10-30
"""

import glob
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def refresh_demo_table(
    mode: str = "incremental",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    overlap_days: int = 7,
    chunk_size_days: int = 7,
    delete_overlap: bool = True,
    schemas: Optional[list] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Refresh DEMO_TABLE with latest production data.

    This is the foundation table used by all analysis modules:
    - ROI Analysis
    -  Analysis (MTTR/MTBF)

    - CT Deviation
    - CT Efficiency
    - Root Cause Analysis
    - Tooling EOL Prediction

    Args:
        mode: Processing mode - "incremental" (default) or "full"
              - incremental: Only process new data with overlap (recommended for scheduled jobs)
              - full: Reprocess all historical data (use for initial setup or recovery)
        start_date: Start date for processing (YYYY-MM-DD format, optional)
                   Only used in "full" mode. Defaults to 2022-01-01 if not specified.
        end_date: End date for processing (YYYY-MM-DD format, optional)
                 Only used in "full" mode. Defaults to current date if not specified.
        overlap_days: Number of days to overlap when processing incrementally (default: 7)
                     This catches late-arriving data and prevents gaps.
        chunk_size_days: Number of days to process in each chunk (default: 7)
        delete_overlap: If True, delete overlap period before processing (default: True)
                       If False, append new data without deleting (may create duplicates)
        schemas: List of client schemas to process (e.g., ["NORDPLAST", "ARCWELD"])
                If None, uses SNOWFLAKE_SCHEMA from .env
        job_id: Optional job ID for progress tracking (used by async execution)

    Returns:
        dict: Refresh results with row counts, timing, and processing details
              If multiple schemas, returns combined results for all schemas

    Example Response (single schema):
        {
          "status": "success",
          "schema": "NORDPLAST",
          "mode": "incremental",
          "rows_processed": 1500000,
          "chunks_processed": 1,
          "execution_time_seconds": 45.2,
          "timestamp": "2025-10-30T10:00:00"
        }

    Example Response (multiple schemas):
        {
          "status": "success",
          "schemas_processed": 2,
          "total_execution_time_seconds": 120.5,
          "results": [
            {"schema": "NORDPLAST", "status": "success", ...},
            {"schema": "ARCWELD", "status": "success", ...}
          ]
        }

    Usage Examples:
        # Single client
        refresh_demo_table(mode="incremental", schemas=["NORDPLAST"])

        # Multiple clients
        refresh_demo_table(mode="incremental", schemas=["NORDPLAST", "ARCWELD"])

        # Use .env default (no schema specified)
        refresh_demo_table(mode="incremental")
    """
    try:
        overall_start_time = datetime.now()

        # Import the optimized pipeline from the pipelines module
        from services.config.features.analytics.pipelines import (
            OptimizedMasterShotPipeline,
            ProcessingConfig,
        )

        # If no schemas provided, use .env default (None means use environment variable)
        schemas_to_process = schemas if schemas else [None]
        all_results = []

        # Process each schema
        for schema in schemas_to_process:
            schema_name = schema or "default (.env)"
            start_time = datetime.now()

            logger.info("=" * 70)
            logger.info(f"🔄 Starting DEMO_TABLE refresh for: {schema_name}")
            logger.info(f"   Mode: {mode}")
            logger.info(f"   Overlap days: {overlap_days}")
            logger.info(f"   Chunk size: {chunk_size_days} days")
            logger.info(f"   Delete overlap: {delete_overlap}")
            logger.info("=" * 70)

            # Configure based on mode
            if mode.lower() == "full":
                # Full historical load
                if not start_date:
                    start_date = "2022-01-01"  # Default historical start
                if not end_date:
                    end_date = datetime.now().strftime("%Y-%m-%d")

                logger.info(f"📅 Full load: {start_date} to {end_date}")

                config = ProcessingConfig(
                    chunk_size_days=chunk_size_days,
                    max_workers=3,
                    batch_upload_size=200000,
                    enable_incremental=True,
                    start_date=start_date,
                    end_date=end_date,
                    schema=schema,
                )

                pipeline = OptimizedMasterShotPipeline(config)
                success = pipeline.process_all_chunks(parallel=True)

                # Get processing stats
                total_rows = getattr(pipeline, "total_rows_processed", 0)
                chunks_count = getattr(pipeline, "chunks_processed", 0)

            else:
                # Incremental processing (default)
                logger.info(
                    f"⚡ Incremental processing with {overlap_days}-day overlap"
                )

                config = ProcessingConfig(
                    chunk_size_days=chunk_size_days,
                    max_workers=3,
                    batch_upload_size=200000,
                    enable_incremental=True,
                    start_date=None,  # Auto-detected
                    end_date=None,  # Auto-detected
                    schema=schema,
                )

                pipeline = OptimizedMasterShotPipeline(config)
                success = pipeline.process_incremental_with_overlap(
                    overlap_days=overlap_days, delete_overlap=delete_overlap
                )

                # Get processing stats
                total_rows = getattr(pipeline, "total_rows_processed", 0)
                chunks_count = getattr(pipeline, "chunks_processed", 0)

            # Close connections
            pipeline.close_connections()

            elapsed_time = (datetime.now() - start_time).total_seconds()

            if success:
                logger.info("=" * 70)
                logger.info(f"✅ DEMO_TABLE refresh completed for {schema_name}")
                logger.info(f"   Rows processed: {total_rows:,}")
                logger.info(f"   Chunks: {chunks_count}")
                logger.info(f"   Time: {elapsed_time:.1f}s")
                logger.info("=" * 70)

                result = {
                    "status": "success",
                    "schema": schema_name,
                    "mode": mode,
                    "rows_processed": total_rows,
                    "chunks_processed": chunks_count,
                    "execution_time_seconds": round(elapsed_time, 2),
                    "timestamp": datetime.now().isoformat(),
                    "date_range": {
                        "start": start_date if mode == "full" else "auto-detected",
                        "end": end_date if mode == "full" else "auto-detected",
                    },
                    "config": {
                        "chunk_size_days": chunk_size_days,
                        "overlap_days": overlap_days if mode == "incremental" else None,
                    },
                }
            else:
                logger.error(f"❌ DEMO_TABLE refresh failed for {schema_name}")
                result = {
                    "status": "error",
                    "schema": schema_name,
                    "error": "Pipeline processing failed - check logs for details",
                    "mode": mode,
                    "rows_processed": total_rows,
                    "execution_time_seconds": round(elapsed_time, 2),
                }

            all_results.append(result)

        # Return combined results
        total_elapsed = (datetime.now() - overall_start_time).total_seconds()

        if len(all_results) == 1:
            # Single schema - return simple result
            return all_results[0]
        else:
            # Multiple schemas - return combined results
            success_count = sum(1 for r in all_results if r["status"] == "success")
            return {
                "status": "success" if success_count == len(all_results) else "partial",
                "schemas_processed": len(all_results),
                "successful": success_count,
                "failed": len(all_results) - success_count,
                "total_execution_time_seconds": round(total_elapsed, 2),
                "timestamp": datetime.now().isoformat(),
                "results": all_results,
            }

    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return {
            "status": "error",
            "error": "Failed to import pipeline module: " + str(e),
            "error_type": "ImportError",
        }

    except Exception as e:
        logger.error(f"❌ DEMO_TABLE refresh failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }


def get_latest_log_file() -> Optional[str]:
    """
    Get the path to the most recent master shot table log file.

    Returns:
        str: Path to latest log file or None
    """
    log_files = glob.glob("logs/DEMO_TABLE_*.log")
    if not log_files:
        return None
    return max(log_files, key=os.path.getctime)


def get_log_progress(lines: int = 50) -> Dict[str, Any]:
    """
    Get progress information from the latest log file.

    Args:
        lines: Number of recent log lines to return

    Returns:
        dict: Progress information including recent logs and status
    """
    log_file = get_latest_log_file()
    if not log_file:
        return {"status": "no_active_process", "message": "No log file found"}

    try:
        with open(log_file, "r") as f:
            all_lines = f.readlines()
            recent_lines = [line.strip() for line in all_lines[-lines:]]

        # Parse for progress indicators
        total_chunks = 0  # Sum across all schemas
        completed_chunks = 0
        schemas_detected = 0

        for line in all_lines:
            if "Generated" in line and "chunks" in line:
                # Extract: "📅 Generated 200 date chunks"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "Generated" and i + 1 < len(parts):
                        try:
                            # Sum all "Generated X chunks" lines for multi-schema support
                            chunks_in_this_batch = int(parts[i + 1])
                            total_chunks += chunks_in_this_batch
                            schemas_detected += 1
                        except (ValueError, IndexError):
                            # Skip if can't parse chunk count
                            pass
            if "✅ Chunk" in line and "Upload completed" in line:
                completed_chunks += 1

        progress_pct = 0
        if total_chunks and total_chunks > 0:
            progress_pct = round((completed_chunks / total_chunks) * 100, 1)
            # Cap at 100% (sometimes completed can slightly exceed due to timing)
            progress_pct = min(progress_pct, 100.0)

        # Check if completed
        is_complete = any(
            "Processing complete" in line or "pipeline completed" in line.lower()
            for line in all_lines[-20:]
        )

        return {
            "status": "completed" if is_complete else "processing",
            "log_file": log_file,
            "recent_lines": recent_lines,
            "progress": {
                "completed_chunks": completed_chunks,
                "total_chunks": total_chunks,
                "percentage": progress_pct,
                "schemas_detected": schemas_detected if schemas_detected > 0 else 1,
            },
            "last_update": datetime.fromtimestamp(
                os.path.getmtime(log_file)
            ).isoformat(),
        }

    except Exception as e:
        return {"status": "error", "error": str(e), "log_file": log_file}


# Tool definition for MCP
MASTER_TABLE_TOOLS = [
    {
        "name": "refresh_demo_table",
        "description": """Refresh DEMO_TABLE with latest production data from Snowflake.

This is the FOUNDATION TABLE used by all 7 analysis modules:
• ROI Analysis - Cycle time efficiency metrics
•  Analysis - MTTR/MTBF tracking

• CT Deviation - Process stability monitoring
• CT Efficiency - Supplier benchmarking
• Root Cause Analysis - Pareto and Five Whys
• Tooling EOL - End-of-life prediction

Run this periodically (daily/hourly) to ensure analyses use fresh data.

Processing Modes:
• "incremental" (default): Smart processing of only new data with 7-day overlap
  - Recommended for scheduled jobs
  - Fast and efficient
  - Catches late-arriving data
  
• "full": Reprocess all historical data
  - Use for initial setup
  - Use for data recovery
  - More time-consuming

The pipeline uses optimized chunked processing to handle millions of shots efficiently.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "description": "Processing mode: 'incremental' (default) or 'full'",
                    "enum": ["incremental", "full"],
                    "default": "incremental",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date for full mode (YYYY-MM-DD). Defaults to 2022-01-01.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date for full mode (YYYY-MM-DD). Defaults to current date.",
                },
                "overlap_days": {
                    "type": "integer",
                    "description": "Days to overlap in incremental mode (default: 7)",
                    "default": 7,
                },
                "chunk_size_days": {
                    "type": "integer",
                    "description": "Days per processing chunk (default: 7)",
                    "default": 7,
                },
                "delete_overlap": {
                    "type": "boolean",
                    "description": "Delete overlap period before processing (default: false). If false, appends new data without deletion.",
                    "default": False,
                },
            },
        },
    },
    {
        "name": "get_master_table_progress",
        "description": """Get real-time progress of the current master shot table refresh operation.
        
        Returns progress percentage, completed chunks, and recent log lines.
        Useful for monitoring long-running operations.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lines": {
                    "type": "integer",
                    "description": "Number of recent log lines to return (default: 50)",
                    "default": 50,
                }
            },
        },
    },
]
