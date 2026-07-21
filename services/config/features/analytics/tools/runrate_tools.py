"""
RunRate Analysis MCP Tools.

Wraps the refactored runrate analyzer from analysis for MCP integration.

Author: Utku Gulbardak
Date: 2025-10-26
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np


def _convert_numpy_types(obj: Any) -> Any:
    """Convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_numpy_types(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    return obj


# Add analysis to path
analysis_path = Path(__file__).parent.parent.parent.parent.parent / "analysis"
if str(analysis_path) not in sys.path:
    sys.path.insert(0, str(analysis_path))


async def run_runrate_analysis(
    equipment_codes: Optional[list] = None,
    supplier_names: Optional[list] = None,
    start_date: str = None,
    end_date: str = None,
    client: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute RunRate analysis for manufacturing operations with MTTR/MTBF tracking.

    Analyzes production sessions, detects stops, calculates efficiency metrics,
    and generates comprehensive Excel reports with formulas and charts.

    Args:
        equipment_codes: Equipment identifier(s) - list (REQUIRED - at least one equipment)
        supplier_names: Supplier name(s) - list (optional)
        start_date: Analysis start date (YYYY-MM-DD)
        end_date: Analysis end date (YYYY-MM-DD)
        client: Client name/schema (e.g., "NORDPLAST", "AURELIA", "MERIDIAN") - overrides .env

    Returns:
        dict: Analysis results with metrics and Excel file path
        {
            "status": "success"|"error",
            "job_id": str,
            "metrics": {
                "total_shots": int,
                "total_sessions": int,
                "total_stops": int,
                "efficiency": float,
                "mttr": float,
                "mtbf": float,
                "time_to_first_downtime": float,
                ...
            },
            "output_files": {
                "excel": str,
                "filename": str,
            }
        }
    """
    job_id = f"runrate_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Import runrate analyzer (function-based API)
        from analysis.runrate import run_analysis_api

        # Build filter parameters
        # The runrate API requires at least equipment_code
        equipment_code = (
            equipment_codes[0] if equipment_codes and len(equipment_codes) > 0 else None
        )
        supplier_name = (
            supplier_names[0] if supplier_names and len(supplier_names) > 0 else None
        )

        # Validate: at least equipment_code is required
        if not equipment_code:
            return {
                "status": "error",
                "job_id": job_id,
                "error": "At least 'equipment_codes' must be provided for RunRate analysis",
                "error_type": "ValueError",
            }

        # Run analysis using the refactored function-based API
        results = run_analysis_api(
            equipment_code=equipment_code,
            supplier_name=supplier_name,
            start_date=start_date,
            end_date=end_date,
            schema=client,
        )

        # The run_analysis_api returns a dict with:
        # - status: "success" or "error"
        # - metrics: dict with analysis results
        # - output_files: list of generated file paths
        # - dataframe: the processed session data

        if results.get("status") == "error":
            return {
                "status": "error",
                "job_id": job_id,
                "error": results.get("error", "Unknown error"),
                "error_type": results.get("error_type", "UnknownError"),
            }

        # Extract metrics
        metrics = results.get("metrics", {})

        # Extract session-level data for time-series visualization
        session_data = None
        if results.get("dataframe") is not None:
            import pandas as pd

            df_result = results["dataframe"]

            # Aggregate to session-level time-series
            if not df_result.empty and "SESSION_ID" in df_result.columns:
                # Get session-level metrics (one record per session)
                session_metrics = []
                for (equipment, session_id), session_df in df_result.groupby(
                    ["EQUIPMENT_CODE", "SESSION_ID"]
                ):
                    session_start = pd.to_datetime(session_df["LOCAL_SHOT_TIME"]).min()
                    session_end = pd.to_datetime(session_df["LOCAL_SHOT_TIME"]).max()

                    # Get session-level KPIs if available
                    efficiency = (
                        session_df["EFFICIENCY"].iloc[0]
                        if "EFFICIENCY" in session_df.columns
                        else None
                    )
                    downtime_minutes = (
                        session_df["TOTAL_DOWN_TIME"].iloc[0]
                        if "TOTAL_DOWN_TIME" in session_df.columns
                        else 0.0
                    )
                    total_shots = len(session_df)
                    total_stops = (
                        int(session_df["STOP"].sum())
                        if "STOP" in session_df.columns
                        else 0
                    )

                    session_metrics.append(
                        {
                            "session_id": int(session_id),  # Convert numpy.int64 to int
                            "equipment_code": str(equipment),
                            "session_start_time": (
                                session_start.isoformat()
                                if pd.notna(session_start)
                                else None
                            ),
                            "session_end_time": (
                                session_end.isoformat()
                                if pd.notna(session_end)
                                else None
                            ),
                            "date": (
                                session_start.date().isoformat()
                                if pd.notna(session_start)
                                else None
                            ),
                            "efficiency_percentage": (
                                float(efficiency) if efficiency is not None else None
                            ),
                            "downtime_minutes": float(downtime_minutes),
                            "total_shots": int(total_shots),
                            "total_stops": int(total_stops),
                        }
                    )

                session_data = session_metrics

        # Format output files
        output_files = {}
        if results.get("output_files"):
            excel_path = (
                results["output_files"][0]
                if isinstance(results["output_files"], list)
                else results["output_files"]
            )
            output_files["excel"] = excel_path
            output_files["filename"] = Path(excel_path).name

        # Convert all numpy types to native Python types for JSON serialization
        response = {
            "status": "success",
            "job_id": job_id,
            "date_range": f"{start_date} to {end_date}",
            "equipment_codes": equipment_codes,
            "supplier_names": supplier_names,
            "metrics": _convert_numpy_types(metrics),
            "session_metrics": session_data,  # Already converted above
            "output_files": output_files,
            "message": f"RunRate analysis completed successfully with {metrics.get('total_shots', 0)} shots across {metrics.get('total_sessions', 0)} sessions",
        }
        return response

    except Exception as e:
        import traceback

        return {
            "status": "error",
            "job_id": job_id,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }


# Tool metadata for MCP registration
RUNRATE_TOOLS = [
    {
        "name": "run_runrate_analysis",
        "description": "Analyze production run rate with MTTR/MTBF metrics, stop detection, and efficiency tracking",
        "inputSchema": {
            "type": "object",
            "properties": {
                "equipment_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Equipment code(s) - REQUIRED - e.g., ['EMA-4104', 'EMA-4110']",
                },
                "supplier_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Supplier name(s) - e.g., ['Vantis industries SCS']",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "client": {
                    "type": "string",
                    "description": "Client name/schema (e.g., 'NORDPLAST', 'ARCWELD', 'MERIDIAN', 'CALDERA') - overrides .env setting",
                },
            },
            "required": ["start_date", "end_date", "equipment_codes"],
        },
    }
]
