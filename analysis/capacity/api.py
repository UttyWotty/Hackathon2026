"""
API entry point for Capacity Analysis.

Provides run_analysis_api() function for MCP/LLM integration.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import os
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]

from .core import (
    add_shot_diffs,
    build_session_metrics,
    fetch_equipment_data,
    filter_sessions_by_shot_count,
)

# Import from refactored modules
from .models.config import DEFAULT_OEE_TARGETS, CapacityConfig
from .reporting import (
    create_multi_oee_excel,
    generate_formulas_doc_daily,
    generate_sales_doc_daily,
)


def _create_config(
    equipment_code: str,
    supplier_name: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    oee_targets: Optional[List[float]],
    min_shots_per_session: int,
) -> CapacityConfig:
    """Create and return CapacityConfig instance."""
    if oee_targets is None:
        oee_targets = DEFAULT_OEE_TARGETS

    return CapacityConfig(
        equipment_code=equipment_code,
        supplier_name=supplier_name,
        start_date=start_date,
        end_date=end_date,
        oee_targets=oee_targets,
        min_shots_per_session=min_shots_per_session,
    )


def _fetch_and_validate_data(
    config: CapacityConfig, schema: Optional[str]
) -> pd.DataFrame:
    """Fetch equipment data and validate it's not empty."""
    start_ts = pd.Timestamp(config.start_date) if config.start_date else None
    end_ts = pd.Timestamp(config.end_date) if config.end_date else None

    shots = fetch_equipment_data(
        equipment_code=config.equipment_code,
        supplier_name=config.supplier_name,
        start_ts=start_ts,
        end_ts=end_ts,
        schema=schema,
    )

    if shots.empty:
        raise ValueError(f"No data found for equipment {config.equipment_code}")

    return shots


def _process_shot_data(shots: pd.DataFrame, config: CapacityConfig) -> pd.DataFrame:
    """Process shot data: add diffs, filter sessions."""
    shots = add_shot_diffs(shots)
    shots = filter_sessions_by_shot_count(shots, min_shots=config.min_shots_per_session)
    return shots


def _build_all_oee_metrics(
    shots: pd.DataFrame, config: CapacityConfig
) -> Dict[float, pd.DataFrame]:
    """Build metrics for all OEE targets."""
    all_daily_data = {}
    for oee_target in config.oee_targets:
        daily = build_session_metrics(df=shots, oee_target=oee_target)
        all_daily_data[oee_target] = daily
    return all_daily_data


def _generate_output_files(
    all_daily_data: Dict[float, pd.DataFrame],
    config: CapacityConfig,
    shots: pd.DataFrame,
) -> Dict[str, str]:
    """Generate Excel and HTML output files."""
    from analysis.shared import get_output_dir

    results_dir = str(get_output_dir("capacity"))

    # Generate Excel report
    excel_file = os.path.join(
        results_dir, f"{config.equipment_code}_capacity_report.xlsx"
    )
    create_multi_oee_excel(all_daily_data, excel_file)

    # Generate HTML docs
    main_daily = all_daily_data.get(1.0, list(all_daily_data.values())[0])
    sales_doc_file = os.path.join(results_dir, "sales_notes.html")
    formulas_doc_file = os.path.join(results_dir, "formulas_doc.html")

    generate_sales_doc_daily(
        daily=main_daily,
        equipment_code=config.equipment_code,
        supplier_name=config.supplier_name,
        start=config.start_date,
        end=config.end_date,
        output_path=sales_doc_file,
    )

    # Get approved CT from first session
    approved_ct = None
    if not shots.empty and "APPROVED_CT" in shots.columns:
        approved_ct_series = shots["APPROVED_CT"]
        valid_cts = approved_ct_series[approved_ct_series > 0]
        if not valid_cts.empty:
            approved_ct = valid_cts.iloc[0]

    generate_formulas_doc_daily(
        equipment_code=config.equipment_code,
        approved_ct_sec=approved_ct,
        output_path=formulas_doc_file,
    )

    return {
        "excel": excel_file,
        "sales_doc": sales_doc_file,
        "formulas_doc": formulas_doc_file,
    }


def _calculate_summary_metrics(
    main_daily: pd.DataFrame, shots: pd.DataFrame
) -> Dict[str, Any]:
    """Calculate summary metrics from daily data."""
    if main_daily is None or main_daily.empty:
        return {}

    def safe_sum(column: str, default: int = 0) -> int:
        """Safely sum column values."""
        if column in main_daily.columns:
            return int(main_daily[column].sum())
        return default

    def safe_mean(column: str, default: float = 0.0) -> float:
        """Safely calculate mean of column."""
        if column in main_daily.columns:
            return float(main_daily[column].mean())
        return default

    total_sessions = (
        len(shots["SESSION_ID"].unique()) if "SESSION_ID" in shots.columns else 0
    )

    return {
        "total_sessions": total_sessions,
        "total_days": len(main_daily),
        "avg_oee_100": safe_mean("OEE_SCORE"),
        "avg_availability": safe_mean("AVAILABILITY"),
        "avg_performance": safe_mean("PERFORMANCE"),
        "avg_quality": safe_mean("QUALITY"),
        "total_actual_output": safe_sum("ACTUAL_OUTPUT"),
        "total_optimal_output": safe_sum("OPTIMAL_OUTPUT"),
        "total_gap": safe_sum("GAP"),
    }


def run_analysis_api(
    equipment_code: str,
    supplier_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    oee_targets: Optional[List[float]] = None,
    schema: Optional[str] = None,
    min_shots_per_session: int = 10,
) -> Dict[str, Any]:
    """
    API entry point for capacity analysis (for LLM integration).

    Args:
        equipment_code: Equipment identifier (REQUIRED)
        supplier_name: Supplier name (optional)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        oee_targets: OEE target list (default: [0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

    Returns:
        dict: {
            "status": "success"|"error",
            "date_range": "2025-01-01 to 2025-12-31",
            "equipment_code": "MX-7102",
            "supplier_name": "Vantis industries",
            "metrics": {
                "total_sessions": 123,
                "avg_oee_100": 0.87,
                "avg_availability": 0.95,
                "avg_performance": 0.92,
                "total_actual_output": 50000,
                "total_optimal_output": 57000,
                "total_gap": 7000
            },
            "output_files": {
                "excel": "capacity_report.xlsx",
                "dashboard": "dashboard.html",
                "sales_doc": "sales_notes.html",
                "formulas_doc": "formulas_doc.html"
            },
            "message": "Capacity analysis completed successfully"
        }
    """
    try:
        # Create configuration
        config = _create_config(
            equipment_code=equipment_code,
            supplier_name=supplier_name,
            start_date=start_date,
            end_date=end_date,
            oee_targets=oee_targets,
            min_shots_per_session=min_shots_per_session,
        )

        # Fetch and validate data
        shots = _fetch_and_validate_data(config, schema)

        # Process shot data
        shots = _process_shot_data(shots, config)

        # Build metrics for all OEE targets
        all_daily_data = _build_all_oee_metrics(shots, config)

        # Generate output files
        output_files = _generate_output_files(all_daily_data, config, shots)

        # Calculate summary metrics (using 100% OEE data)
        main_daily = all_daily_data.get(1.0)
        metrics = _calculate_summary_metrics(main_daily, shots)

        return {
            "status": "success",
            "date_range": f"{config.start_date} to {config.end_date}",
            "equipment_code": config.equipment_code,
            "supplier_name": config.supplier_name,
            "oee_targets": config.oee_targets,
            "metrics": metrics,
            "output_files": output_files,
            "message": f"Capacity analysis completed successfully for {len(config.oee_targets)} OEE targets",
        }

    except Exception as e:
        import traceback

        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }
