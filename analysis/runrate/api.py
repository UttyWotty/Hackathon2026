"""
RunRate Analysis - Main Orchestrator (Refactored & Async-Ready).

This module serves as the main entry point for RunRate analysis,
orchestrating data loading, processing, session analysis, and reporting.

The refactored architecture separates concerns into:
- core/: Business logic (data loading, processing, session analysis)
- reporting/: Report generation (Excel, charts)
- utils/: Utility functions
- models/: Data models and configuration

Author: AI TEAM
Date: 2025-10-22 (Refactored)
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

# Import refactored core modules
from .core import load_data_async, preprocess_data, process_shots
from .models import RunRateConfig, RunRateResults

# Import reporting modules
from .reporting import create_excel_report_with_formulas, validate_data_for_excel
from .utils import format_time_readable, format_time_readable_seconds


async def run_analysis_async(
    equipment_code: str,
    supplier_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    output_dir: Optional[str] = None,
    schema: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run RunRate analysis asynchronously.

    This is the async entry point for RunRate analysis. It uses async I/O
    for database operations to improve performance when handling multiple
    concurrent requests.

    Args:
        equipment_code: Equipment code to analyze (REQUIRED)
        supplier_name: Optional supplier name filter
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
        output_dir: Optional directory for output files

    Returns:
        dict: Analysis results including metrics and file paths

    Raises:
        ValueError: If equipment_code is not provided
        Exception: If analysis fails

    Example:
        >>> results = await run_analysis_async("EMA-4104", supplier_name="SUPPLIER_A")
        >>> print(results["metrics"]["efficiency_percentage"])
        92.5
    """
    # Set default output directory (centralized)
    if output_dir is None:
        from analysis.shared import get_output_dir

        output_dir = str(get_output_dir("runrate"))

    # Validate configuration
    config = RunRateConfig(
        equipment_code=equipment_code,
        supplier_name=supplier_name,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
    )

    try:
        # Load data asynchronously
        print(f"📊 Loading data for {supplier_name}...")
        df = await load_data_async(
            config.supplier_name,
            config.equipment_code,
            config.start_date,
            config.end_date,
            schema,
        )

        # Check if data is empty
        if df.empty:
            return RunRateResults.empty_result(
                supplier_name=config.supplier_name,
                equipment_code=config.equipment_code,
                start_date=config.start_date,
                end_date=config.end_date,
            ).to_dict()

        records_loaded = len(df)
        print(f"✅ Loaded {records_loaded:,} records")

        # Process data (CPU-bound, run in executor if needed for large datasets)
        print("🔄 Processing data...")
        df_preprocessed = preprocess_data(df)
        # Test shot filtering removed - process all shots

        # Analyze sessions
        print("🔍 Analyzing sessions...")
        try:
            # Use include_groups=False for pandas 2.0+ compatibility
            df_result = (
                df_preprocessed.groupby(
                    ["EQUIPMENT_CODE", "SESSION_ID"], group_keys=False
                )
                .apply(process_shots, include_groups=False)
                .reset_index(drop=True)
            )
        except TypeError as te:
            # Fallback for older pandas versions that don't support include_groups
            if "include_groups" in str(te):
                df_result = (
                    df_preprocessed.groupby(
                        ["EQUIPMENT_CODE", "SESSION_ID"], group_keys=False
                    )
                    .apply(process_shots)
                    .reset_index(drop=True)
                )
            else:
                raise

        # Calculate aggregate metrics
        metrics = _calculate_aggregate_metrics(df_result, records_loaded)

        # Generate Excel report
        print("📝 Generating Excel report...")
        output_file = await _generate_report_async(
            df_result,
            config,
            metrics,
        )

        # Return structured results with session-level data for visualization
        result_dict = RunRateResults(
            status="completed",
            message="Analysis completed successfully",
            supplier_name=config.supplier_name,
            equipment_code=config.equipment_code,
            date_range=f"{config.start_date or 'No limit'} to {config.end_date or 'No limit'}",
            metrics=metrics,
            output_files=[output_file] if output_file else [],
        ).to_dict()

        # Add session-level dataframe for time-series visualization
        result_dict["dataframe"] = df_result

        return result_dict

    except Exception as e:
        return RunRateResults.error_result(
            supplier_name=config.supplier_name,
            error_message=str(e),
            equipment_code=config.equipment_code,
        ).to_dict()


def run_analysis_api(
    equipment_code: str,
    supplier_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    output_dir: Optional[str] = None,
    schema: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run RunRate analysis (synchronous wrapper).

    This is the synchronous entry point for RunRate analysis, compatible with
    existing FastAPI integration. It wraps the async implementation.

    Args:
        equipment_code: Equipment code to analyze (REQUIRED)
        supplier_name: Optional supplier name filter
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
        output_dir: Optional directory for output files

    Returns:
        dict: Analysis results including metrics and file paths

    Raises:
        ValueError: If equipment_code is not provided
        Exception: If analysis fails
    """
    # Check if we're already in an event loop
    try:
        asyncio.get_running_loop()
        # We're in an async context, but this is a sync function
        # Create a new thread to run the async code
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                run_analysis_async(
                    equipment_code,
                    supplier_name,
                    start_date,
                    end_date,
                    output_dir,
                    schema,
                ),
            )
            return future.result()
    except RuntimeError:
        # No event loop running, we can use asyncio.run
        return asyncio.run(
            run_analysis_async(
                equipment_code, supplier_name, start_date, end_date, output_dir, schema
            )
        )


# Alias for backward compatibility with FastAPI
analyze_runrate = run_analysis_api


def _calculate_aggregate_metrics(
    df_result: pd.DataFrame, records_loaded: int
) -> Dict[str, Any]:
    """
    Calculate aggregate metrics from processed session data.

    Args:
        df_result: Processed session data
        records_loaded: Number of records loaded from database

    Returns:
        dict: Aggregate metrics including efficiency, stops, production time, etc.
    """
    total_shots = len(df_result)
    total_sessions = df_result["SESSION_ID"].nunique()
    unique_equipment = df_result["EQUIPMENT_CODE"].nunique()

    # Calculate stops and efficiency
    total_stops = int(df_result["STOP"].sum())
    normal_shots = total_shots - total_stops
    efficiency = (normal_shots / total_shots * 100) if total_shots > 0 else 0.0

    # Calculate OEE metrics
    production_time_min = (
        df_result["CUMULATIVE_COUNT"].sum()
        if "CUMULATIVE_COUNT" in df_result.columns
        else 0.0
    )

    # Calculate downtime
    if "SHOT_DIFF_SEC" in df_result.columns and "STOP" in df_result.columns:
        downtime_sec = df_result[df_result["STOP"] == 1]["SHOT_DIFF_SEC"].sum()
        downtime_min = downtime_sec / 60
    else:
        downtime_min = 0.0

    # Calculate average stop duration
    if total_stops > 0 and downtime_sec > 0:
        avg_stop_duration_min = (downtime_sec / 60) / total_stops
    else:
        avg_stop_duration_min = 0.0

    return {
        "records_loaded": records_loaded,
        "total_shots": total_shots,
        "total_sessions": total_sessions,
        "unique_equipment": unique_equipment,
        "total_stops": total_stops,
        "normal_shots": normal_shots,
        "efficiency_percentage": round(efficiency, 2),
        "production_time_minutes": round(production_time_min, 2),
        "downtime_minutes": round(downtime_min, 2),
        "average_stop_duration_minutes": round(avg_stop_duration_min, 2),
    }


async def _generate_report_async(
    df_result: pd.DataFrame,
    config: RunRateConfig,
    metrics: Dict[str, Any],
) -> Optional[str]:
    """
    Generate Excel report asynchronously.

    Args:
        df_result: Processed session data
        config: RunRate configuration
        metrics: Calculated metrics

    Returns:
        Optional[str]: Path to generated Excel file, or None if generation failed
    """
    try:
        # Validate data before Excel generation
        validate_data_for_excel(df_result)

        # Determine date range for filename
        date_range = None
        if config.start_date and config.end_date:
            date_range = [config.start_date, config.end_date]
        elif config.start_date:
            date_range = [
                config.start_date,
                df_result["LOCAL_SHOT_TIME"].max().strftime("%Y-%m-%d"),
            ]
        elif config.end_date:
            date_range = [
                df_result["LOCAL_SHOT_TIME"].min().strftime("%Y-%m-%d"),
                config.end_date,
            ]

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if config.output_dir:
            filename = f"{config.output_dir}/runrate_report_{timestamp}.xlsx"
        else:
            filename = f"runrate_report_{timestamp}.xlsx"

        # Run Excel generation in thread pool (it's CPU/I-O bound)
        loop = asyncio.get_event_loop()
        output_file = await loop.run_in_executor(
            None,  # Use default executor
            create_excel_report_with_formulas,
            df_result,
            config.equipment_code or f"All_{config.supplier_name}",
            date_range,
            filename,
        )

        return output_file

    except Exception as e:
        print(f"⚠️ Excel generation failed: {e}")
        return None


# Re-export commonly used functions for backward compatibility
__all__ = [
    "run_analysis_async",
    "run_analysis_api",
    "analyze_runrate",
    "format_time_readable",
    "format_time_readable_seconds",
]
