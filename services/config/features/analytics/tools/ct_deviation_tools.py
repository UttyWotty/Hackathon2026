"""
CT Deviation Analysis MCP Tools.

This module provides MCP tool wrappers for the CT deviation analysis module.

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


CT_DEVIATION_TOOLS = [
    {
        "name": "run_ct_deviation_analysis",
        "description": """Analyze cycle time (CT) deviations from approved specifications.
        
        This tool analyzes how actual cycle times deviate from approved/target cycle times,
        providing insights into process stability, efficiency, and equipment performance.
        
        Key metrics:
        - Deviation percentage from approved CT
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
        - "What's the CT deviation for equipment MX-7110?"
        - "Which equipment has the best cycle time stability?"
        - "Show me equipment with critical CT deviations"
        - "Compare CT performance across suppliers"
        - "Analyze CT efficiency for Q1 2025"
        
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
                "equipment_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of equipment codes to analyze. Optional - analyzes all if not specified.",
                },
                "supplier_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of supplier names to filter by. Optional.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for reports. Optional, defaults to 'ct_deviation_results'.",
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


def run_ct_deviation_analysis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    equipment_codes: Optional[List[str]] = None,
    supplier_names: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    save_csv: Optional[bool] = True,
    save_html: Optional[bool] = True,
    create_charts: Optional[bool] = True,
) -> dict:
    """Execute CT deviation analysis.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        equipment_codes: List of equipment codes
        supplier_names: List of supplier names
        output_dir: Output directory path
        save_csv: Save CSV results
        save_html: Save HTML report
        create_charts: Create visualizations

    Returns:
        dict: Analysis results with metrics, summary, and file paths
    """
    try:
        # Import here to avoid import errors during module initialization
        from analysis.ct_deviation import run_analysis_api

        logger.info(
            f"🔧 Running CT deviation analysis: "
            f"date_range={start_date} to {end_date}, "
            f"equipment={equipment_codes}, "
            f"suppliers={supplier_names}"
        )

        # Run analysis
        result = run_analysis_api(
            start_date=start_date,
            end_date=end_date,
            equipment_codes=equipment_codes,
            supplier_names=supplier_names,
            output_dir=output_dir,
            save_csv=save_csv if save_csv is not None else True,
            save_html=save_html if save_html is not None else True,
            create_charts=create_charts if create_charts is not None else True,
        )

        logger.info(f"✅ CT deviation analysis completed: {result.get('message', '')}")
        return result

    except Exception as e:
        logger.error(f"❌ CT deviation analysis failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "metrics": [],
            "summary": {},
            "output_files": {},
            "message": f"Analysis failed: {str(e)}",
        }
