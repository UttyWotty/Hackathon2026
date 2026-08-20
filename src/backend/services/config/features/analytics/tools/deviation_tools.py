"""
Duration Deviation Analysis MCP Tools.

This module provides MCP tool wrappers for the duration deviation analysis module.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional

# Add analysis to Python path
analysis_path = Path(__file__).parent.parent.parent.parent.parent / "analysis"
sys.path.insert(0, str(analysis_path))

logger = logging.getLogger(__name__)


# ==================== Tool Definitions ==================== #


DEVIATION_TOOLS = [
    {
        "name": "run_deviation_analysis",
        "description": """Analyze duration deviations from approved specifications.
        
        This tool analyzes how actual durations deviate from approved/target durations,
        providing insights into process stability, efficiency, and equipment performance.
        
        Key metrics:
        - Deviation percentage from approved duration
        - Efficiency score (shots within tolerance)
        - Stability score (process consistency)
        - Performance categorization (Excellent to Critical)
        
        Categories:
        - Excellent: ≤5% deviation
        - Good: 5-10% deviation
        - Acceptable: 10-15% deviation
        - Poor: 15-20% deviation
        - Critical: >20% deviation
        
        Use cases:
        - "What's the duration deviation for equipment MX-7110?"
        - "Which equipment has the best duration stability?"
        - "Show me equipment with critical duration deviations"
        - "Compare CT performance across suppliers"
        - "Analyze duration efficiency for Q1 2025"
        
        Returns comprehensive metrics, HTML reports, and visualizations.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date for analysis (YYYY-MM-DD format). Optional.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date for analysis (YYYY-MM-DD format). Optional.",
                },
                "machine_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of equipment codes to analyze. Optional - analyzes all if not specified.",
                },
                "vendor_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of supplier names to filter by. Optional.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for reports. Optional, defaults to 'deviation_results'.",
                },
                "save_csv": {
                    "type": "boolean",
                    "description": "Whether to save CSV results. Default: true.",
                },
                "save_html": {
                    "type": "boolean",
                    "description": "Whether to save HTML report with visualizations. Default: true.",
                },
                "create_charts": {
                    "type": "boolean",
                    "description": "Whether to create visualizations. Default: true.",
                },
            },
            "required": [],
        },
    }
]


# ==================== Tool Implementation ==================== #


DEVIATION_DEFAULT_START = "2026-07-01"
DEVIATION_DEFAULT_END = "2026-08-20"


def run_deviation_analysis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    machine_ids: Optional[List[str]] = None,
    vendor_names: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    save_csv: Optional[bool] = True,
    save_html: Optional[bool] = True,
    create_charts: Optional[bool] = True,
) -> dict:
    """Execute duration deviation analysis.

    Args:
        start_date: Start date (YYYY-MM-DD). Defaults to 2026-07-01.
        end_date: End date (YYYY-MM-DD). Defaults to 2026-08-20.
        machine_ids: List of equipment codes
        vendor_names: List of supplier names
        output_dir: Output directory path
        save_csv: Save CSV results
        save_html: Save HTML report
        create_charts: Create visualizations

    Returns:
        dict: Analysis results with metrics, summary, and file paths
    """
    try:
        # Import here to avoid import errors during module initialization
        from analysis.deviation import run_analysis_api

        start_date = start_date or DEVIATION_DEFAULT_START
        end_date = end_date or DEVIATION_DEFAULT_END

        logger.info(
            "Running duration deviation analysis: "
            "date_range=%s to %s, equipment=%s, suppliers=%s",
            start_date, end_date, machine_ids, vendor_names,
        )

        # Run analysis
        result = run_analysis_api(
            start_date=start_date,
            end_date=end_date,
            machine_ids=machine_ids,
            vendor_names=vendor_names,
            output_dir=output_dir,
            save_csv=save_csv if save_csv is not None else True,
            save_html=save_html if save_html is not None else True,
            create_charts=create_charts if create_charts is not None else True,
        )

        logger.info(
            f"✅ duration deviation analysis completed: {result.get('message', '')}"
        )
        return result

    except Exception as e:
        logger.error(f"❌ duration deviation analysis failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "metrics": [],
            "summary": {},
            "output_files": {},
            "message": f"Analysis failed: {str(e)}",
        }
