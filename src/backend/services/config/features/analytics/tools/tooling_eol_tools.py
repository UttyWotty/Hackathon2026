"""
Tooling EOL Analysis MCP Tool.

This module provides MCP tool wrappers for tooling end-of-life prediction analysis.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add analysis to path
analysis_path = Path(__file__).parent.parent.parent.parent.parent / "analysis"
if str(analysis_path) not in sys.path:
    sys.path.insert(0, str(analysis_path))

from analysis.tooling_eol import run_analysis_api  # noqa: E402

logger = logging.getLogger(__name__)


async def run_tooling_eol_analysis(
    type_category: Optional[str] = None,
    output_dir: Optional[str] = None,
    save_csv: Optional[bool] = False,
    save_html: Optional[bool] = False,
    disable_maintenance: Optional[bool] = False,
) -> Dict[str, Any]:
    """Run tooling end-of-life prediction analysis.

    This tool predicts when manufacturing tools/molds will reach end-of-life based on:
    - Historical shot data and production rates
    - Current utilization levels
    - Design life specifications
    - Maintenance history (optional)

    Args:
        type_category: Tooling family type for family-specific config
            ("Injection Molding", "Die Casting", "Stamping")
        output_dir: Directory to save output files
        save_csv: Whether to save CSV report (default: True)
        save_html: Whether to save HTML report (default: False)
        disable_maintenance: Skip maintenance integration (default: False)

    Returns:
        Dict containing:
            - status: 'success' or 'error'
            - num_molds: Number of molds analyzed
            - summary: Dict with key metrics
            - output_files: Dict of generated file paths
            - message: Status message
            - error: Error details (if failed)
    """
    try:
        logger.info(
            f"Running tooling EOL analysis with type_category={type_category}, "
            f"save_csv={save_csv}, save_html={save_html}"
        )

        # Run analysis
        result = run_analysis_api(
            output_dir=output_dir,
            # Forced off for agent-driven runs; see deviation_tools for why.
            save_csv=False,
            save_html=False,
            disable_maintenance=disable_maintenance,
            type_category=type_category,
        )

        if result["status"] == "success":
            df = result["predictions"]

            # Calculate summary metrics
            total_molds = len(df)

            # High confidence predictions
            high_confidence = (
                len(df[df["CONFIDENCE"] == "High"]) if "CONFIDENCE" in df.columns else 0
            )

            # Critical tools (remaining days < 90)
            critical_tools = 0
            avg_remaining_days = None
            if "REMAINING_DAYS" in df.columns:
                valid_days = df["REMAINING_DAYS"].dropna()
                if len(valid_days) > 0:
                    critical_tools = len(df[df["REMAINING_DAYS"] < 90])
                    avg_remaining_days = round(valid_days.mean(), 1)

            # High utilization tools
            high_util = 0
            if "UTILIZATION_CATEGORY" in df.columns:
                high_util = len(
                    df[df["UTILIZATION_CATEGORY"].isin(["High", "Overutilized"])]
                )

            # Overutilized tools
            overutilized = 0
            if "UTILIZATION_CATEGORY" in df.columns:
                overutilized = len(df[df["UTILIZATION_CATEGORY"] == "Overutilized"])

            # Tools with warnings
            with_warnings = 0
            if "WARNINGS" in df.columns:
                with_warnings = len(df[df["WARNINGS"].notna()])

            # Build summary
            summary = {
                "total_molds": total_molds,
                "high_confidence_predictions": high_confidence,
                "critical_tools_90_days": critical_tools,
                "avg_remaining_days": avg_remaining_days,
                "high_utilization_tools": high_util,
                "overutilized_tools": overutilized,
                "tools_with_warnings": with_warnings,
            }

            # Convert DataFrame to list of dicts for LLM analysis
            predictions_data = []
            if not df.empty:
                predictions_data = df.to_dict("records")

            return {
                "status": "success",
                "num_molds": total_molds,
                "summary": summary,
                "predictions": predictions_data,  # Add detailed predictions for LLM analysis
                "output_files": result.get("output_files", {}),
                "message": f"Successfully predicted EOL for {total_molds} molds. "
                f"{critical_tools} tools critical (< 90 days), "
                f"{overutilized} overutilized.",
                "timestamp": result.get("timestamp"),
            }

        return result

    except Exception as exc:
        logger.error(f"Error in tooling EOL analysis: {exc}", exc_info=True)
        return {
            "status": "error",
            "error": str(exc),
            "message": f"Tooling EOL analysis failed: {exc}",
        }


# MCP Tool Definition
TOOLING_EOL_TOOLS = [
    {
        "name": "run_tooling_eol_analysis",
        "description": (
            "Predict end-of-life (EOL) for manufacturing tools and molds. "
            "Analyzes historical production data to predict when tools will reach "
            "their design life limit. Calculates utilization, remaining shots, "
            "remaining days, and confidence levels. Identifies critical tools, "
            "overutilization, and potential maintenance needs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "type_category": {
                    "type": "string",
                    "description": (
                        "Tooling family type for family-specific OEE and utilization bins. "
                        "Options: 'Injection Molding', 'Die Casting', 'Stamping'. "
                        "Leave empty for default values."
                    ),
                    "enum": ["Injection Molding", "Die Casting", "Stamping"],
                },
                "disable_maintenance": {
                    "type": "boolean",
                    "description": "Skip maintenance event integration. Default: false.",
                    "default": False,
                },
            },
            "required": [],
        },
    }
]
