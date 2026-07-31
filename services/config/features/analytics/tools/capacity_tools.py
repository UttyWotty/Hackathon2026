"""
Capacity Analysis MCP Tools.

Wraps the refactored capacity analyzer from analysis for MCP integration.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Add analysis to path
analysis_path = Path(__file__).parent.parent.parent.parent.parent / "analysis"
if str(analysis_path) not in sys.path:
    sys.path.insert(0, str(analysis_path))


async def run_capacity_analysis(
    equipment_codes: Optional[list] = None,
    supplier_names: Optional[list] = None,
    start_date: str = None,
    end_date: str = None,
    oee_targets: Optional[list] = None,
    client: Optional[str] = None,
    min_shots_per_session: int = 50,
) -> Dict[str, Any]:
    """
    Execute Capacity/OEE analysis for manufacturing operations.

    Analyzes production capacity with multi-target OEE scenarios (50%-100%),
    calculates Availability, Performance, Quality metrics, and generates
    comprehensive Excel reports with multiple OEE target sheets.

    Args:
        equipment_codes: Equipment identifier(s) - list (REQUIRED - at least one equipment)
        supplier_names: Supplier name(s) - list (optional)
        start_date: Analysis start date (YYYY-MM-DD)
        end_date: Analysis end date (YYYY-MM-DD)
        oee_targets: OEE target list (default: [0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
        client: Client name/schema (e.g., "NORDPLAST", "AURELIA", "MERIDIAN") - overrides .env

    Returns:
        dict: Analysis results with metrics and file paths
        {
            "status": "success"|"error",
            "job_id": str,
            "metrics": {
                "total_sessions": int,
                "avg_oee_100": float,
                "avg_availability": float,
                "avg_performance": float,
                "avg_quality": float,
                "total_actual_output": int,
                "total_optimal_output": int,
                "total_gap": int,
                ...
            },
            "output_files": {
                "excel": str,
                "sales_doc": str,
                "formulas_doc": str,
            }
        }
    """
    job_id = f"capacity_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Import capacity analyzer (function-based API)
        from analysis.capacity import run_analysis_api

        # Build filter parameters
        # The capacity API requires at least equipment_code
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
                "error": "At least 'equipment_codes' must be provided for Capacity analysis",
                "error_type": "ValueError",
            }

        # Run analysis using the refactored function-based API
        results = run_analysis_api(
            equipment_code=equipment_code,
            supplier_name=supplier_name,
            start_date=start_date,
            end_date=end_date,
            oee_targets=oee_targets,
            schema=client,
            min_shots_per_session=min_shots_per_session,
        )

        # The run_analysis_api returns a dict with:
        # - status: "success" or "error"
        # - metrics: dict with analysis results
        # - output_files: dict of generated file paths

        if results.get("status") == "error":
            return {
                "status": "error",
                "job_id": job_id,
                "error": results.get("error", "Unknown error"),
                "error_type": results.get("error_type", "UnknownError"),
            }

        # Extract metrics
        metrics = results.get("metrics", {})

        # Format output files
        output_files = results.get("output_files", {})

        return {
            "status": "success",
            "job_id": job_id,
            "date_range": results.get("date_range", f"{start_date} to {end_date}"),
            "equipment_codes": equipment_codes,
            "supplier_names": supplier_names,
            "oee_targets": results.get("oee_targets", [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]),
            "metrics": metrics,
            "output_files": output_files,
            "message": results.get(
                "message", "Capacity analysis completed successfully"
            ),
        }

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
CAPACITY_TOOLS = [
    {
        "name": "run_capacity_analysis",
        "description": "Analyze production capacity and OEE with multi-target scenarios (50%-100%), including Availability, Performance, and Quality metrics",
        "inputSchema": {
            "type": "object",
            "properties": {
                "equipment_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Equipment code(s) - REQUIRED - e.g., ['MX-7102']",
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
                "oee_targets": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "OEE targets (e.g., [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]) - default provided",
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
