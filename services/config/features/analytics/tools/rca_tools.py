"""
Root Cause Analysis (RCA) MCP Tools.

Wraps the RCA analyzer from analysis for MCP integration.

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


async def run_rca_analysis(
    equipment_codes: Optional[list] = None,
    supplier_names: Optional[list] = None,
    snowflake_schema: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute Root Cause Analysis for manufacturing issues.

    Performs comprehensive analysis including:
    - Pareto analysis to identify top 20% of issues causing 80% of problems
    - 5 Whys methodology for root cause identification
    - Downtime and scrap pattern analysis
    - Time-based pattern detection (shifts, days, seasonality)
    - Actionable recommendations with priority levels

    Args:
        equipment_codes: Equipment identifier(s) - list (optional - analyzes all if not provided)
        supplier_names: Supplier name(s) - list (optional)
        snowflake_schema: Snowflake schema (e.g., "NORDPLAST", "KESTREL") - overrides .env

    Returns:
        dict: Analysis results with root causes and recommendations
        {
            "status": "success"|"error",
            "job_id": str,
            "equipment_code": str,
            "analysis_summary": {
                "total_shots": int,
                "issue_rate": float (percentage),
                "downtime_rate": float (percentage),
                "scrap_rate": float (percentage),
                "top_equipment": list,
                "top_parts": list
            },
            "top_issues": [
                {
                    "equipment": str,
                    "issue_rate": float,
                    "impact": "High"|"Medium"|"Low"
                }
            ],
            "root_causes": [
                {
                    "category": str,
                    "root_cause": str,
                    "severity": "High"|"Medium"|"Low"
                }
            ],
            "recommendations": [
                {
                    "category": str,
                    "action": str,
                    "expected_impact": str,
                    "priority": "High"|"Medium"|"Low"
                }
            ],
            "output_files": {
                "html_reports": list,
                "json_data": str
            }
        }
    """
    job_id = f"rca_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Import RCA analyzer
        from analysis.rca import run_analysis_api

        # Extract parameters
        equipment_code = (
            equipment_codes[0] if equipment_codes and len(equipment_codes) > 0 else None
        )
        supplier_name = (
            supplier_names[0] if supplier_names and len(supplier_names) > 0 else None
        )

        # Run analysis
        results = run_analysis_api(
            equipment_code=equipment_code,
            supplier_name=supplier_name,
        )

        if results.get("status") == "error":
            return {
                "status": "error",
                "job_id": job_id,
                "error": results.get("error", "Unknown error"),
                "error_type": results.get("error_type", "UnknownError"),
            }

        return {
            "status": "success",
            "job_id": job_id,
            "equipment_code": equipment_code or "All Equipment",
            "supplier_name": supplier_name,
            "analysis_summary": results.get("analysis_summary", {}),
            "top_issues": results.get("top_issues", []),
            "root_causes": results.get("root_causes", []),
            "recommendations": results.get("recommendations", []),
            "output_files": results.get("output_files", {}),
            "message": results.get(
                "message", "Root cause analysis completed successfully"
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
RCA_TOOLS = [
    {
        "name": "run_rca_analysis",
        "description": "Perform root cause analysis using Pareto + 5 Whys methodology to identify top manufacturing issues, root causes, and actionable recommendations",
        "inputSchema": {
            "type": "object",
            "properties": {
                "equipment_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Equipment code(s) - optional - e.g., ['EMA-4110']. Analyzes all equipment if not provided.",
                },
                "supplier_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Supplier name(s) - optional",
                },
                "snowflake_schema": {
                    "type": "string",
                    "description": "Snowflake schema (e.g., 'NORDPLAST', 'KESTREL') - overrides .env setting",
                },
            },
            "required": [],
        },
    }
]
