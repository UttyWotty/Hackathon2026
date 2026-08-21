"""
Duration Efficiency Analysis MCP Tools.

This module provides MCP tool wrappers for the duration efficiency and supplier
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


EFFICIENCY_TOOLS = [
    {
        "name": "run_efficiency_analysis",
        "description": """Analyze duration efficiency and benchmark suppliers.
        
        This tool performs comprehensive efficiency analysis and supplier benchmarking:
        
        Key metrics:
        - Duration efficiency (actual vs approved duration)
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
        - "Which suppliers have the best duration efficiency?"
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
                "vendor_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of supplier names to analyze. Optional - analyzes all if not specified.",
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


def run_efficiency_analysis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    vendor_names: Optional[List[str]] = None,
    machine_ids: Optional[List[str]] = None,
    client: Optional[str] = None,
    output_dir: Optional[str] = None,
    save_csv: Optional[bool] = False,
    save_html: Optional[bool] = False,
    normalization_method: Optional[str] = "z_score",
) -> dict:
    """Execute duration efficiency and supplier benchmarking analysis.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        vendor_names: List of supplier names to analyze
        machine_ids: List of equipment codes (currently unused, reserved)
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
        from analysis.efficiency import run_analysis_api

        logger.info(
            "Running duration efficiency analysis: "
            "date_range=%s to %s, suppliers=%s, normalization=%s",
            start_date,
            end_date,
            vendor_names,
            normalization_method,
        )

        # Run analysis
        result = run_analysis_api(
            start_date=start_date,
            end_date=end_date,
            vendor_names=vendor_names,
            client=client,
            output_dir=output_dir,
            # Forced off for agent-driven runs; see deviation_tools for why.
            save_csv=False,
            save_html=False,
            normalization_method=normalization_method or "z_score",
        )

        logger.info(
            f"✅ duration efficiency analysis completed: {result.get('message', '')}"
        )
        return result

    except Exception as e:
        logger.error(f"❌ duration efficiency analysis failed: {e}", exc_info=True)
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
