"""
CT Efficiency Analysis MCP Tools.

This module provides MCP tool wrappers for the CT efficiency and supplier
benchmarking analysis module.

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


CT_EFFICIENCY_TOOLS = [
    {
        "name": "run_ct_efficiency_analysis",
        "description": """Analyze cycle time efficiency and benchmark suppliers.
        
        This tool performs comprehensive efficiency analysis and supplier benchmarking:
        
        Key metrics:
        - Cycle time efficiency (actual vs approved CT)
        - Supplier performance ranking
        - Tool consistency scores
        - Confidence intervals for statistical rigor
        - Multi-dimensional supplier scoring
        
        Supplier Tiers:
        - Excellent: Top 20% performers
        - Good: 60-80th percentile
        - Average: 40-60th percentile
        - Needs Improvement: 20-40th percentile
        - Poor: Bottom 20%
        
        Scoring Methodology:
        - Adjusted Score = 70% efficiency + 30% consistency
        - Consistency = inverse coefficient of variation across tools
        - Normalized efficiency for cross-supplier comparison
        
        Use cases:
        - "Which suppliers have the best cycle time efficiency?"
        - "Compare supplier performance for Q1 2025"
        - "Show me supplier rankings with consistency scores"
        - "What's the efficiency tier of Supplier X?"
        - "Benchmark all suppliers this year"
        
        Returns supplier rankings, efficiency metrics, tier classifications, and comprehensive reports.""",
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
                "supplier_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of supplier names to analyze. Optional - analyzes all if not specified.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for reports. Optional, defaults to 'ct_efficiency_results'.",
                },
                "save_csv": {
                    "type": "boolean",
                    "description": "Whether to save CSV results. Default: true.",
                },
                "save_html": {
                    "type": "boolean",
                    "description": "Whether to save HTML report with supplier rankings. Default: true.",
                },
                "normalization_method": {
                    "type": "string",
                    "description": "Score normalization method: 'z_score' (default), 'min_max', or 'percentile'.",
                    "enum": ["z_score", "min_max", "percentile"],
                },
            },
            "required": [],
        },
    }
]


# ==================== Tool Implementation ==================== #


def run_ct_efficiency_analysis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    supplier_names: Optional[List[str]] = None,
    equipment_codes: Optional[List[str]] = None,
    client: Optional[str] = None,
    output_dir: Optional[str] = None,
    save_csv: Optional[bool] = True,
    save_html: Optional[bool] = True,
    normalization_method: Optional[str] = "z_score",
) -> dict:
    """Execute CT efficiency and supplier benchmarking analysis.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        supplier_names: List of supplier names to analyze
        equipment_codes: List of equipment codes (currently unused, reserved)
        client: Client name (currently unused, reserved)
        output_dir: Output directory path
        save_csv: Save CSV results
        save_html: Save HTML report
        normalization_method: Normalization method for efficiency scores

    Returns:
        dict: Analysis results with efficiency metrics, supplier benchmarks, and file paths
    """
    try:
        # Import here to avoid import errors during module initialization
        from analysis.ct_efficiency import run_analysis_api

        logger.info(
            "Running CT efficiency analysis: "
            "date_range=%s to %s, suppliers=%s, normalization=%s",
            start_date,
            end_date,
            supplier_names,
            normalization_method,
        )

        # Run analysis
        result = run_analysis_api(
            start_date=start_date,
            end_date=end_date,
            supplier_names=supplier_names,
            client=client,
            output_dir=output_dir,
            save_csv=save_csv if save_csv is not None else True,
            save_html=save_html if save_html is not None else True,
            normalization_method=normalization_method or "z_score",
        )

        logger.info(f"✅ CT efficiency analysis completed: {result.get('message', '')}")
        return result

    except Exception as e:
        logger.error(f"❌ CT efficiency analysis failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "efficiency_summary": {},
            "supplier_summary": {},
            "supplier_benchmarks": [],
            "top_suppliers": [],
            "output_files": {},
            "message": f"Analysis failed: {str(e)}",
        }
