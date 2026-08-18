"""
ROI Analysis MCP Tools.

Wraps the existing ROI analyzer from analysis for MCP integration.

Author: Utku Gulbardak
Date: 2025-10-22
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Add analysis to path
analysis_path = Path(__file__).parent.parent.parent.parent.parent / "analysis"
if str(analysis_path) not in sys.path:
    sys.path.insert(0, str(analysis_path))

# FileManager removed - not used in this file


async def run_roi_analysis(
    machine_ids: Optional[list] = None,
    vendor_names: Optional[list] = None,
    start_date: str = None,
    end_date: str = None,
    delta_tolerance: float = 0.05,
    client: Optional[str] = None,
    aggregation_level: str = "daily",
) -> Dict[str, Any]:
    """
    Execute ROI (Return on Investment) analysis for manufacturing duration efficiency.

    Calculates efficiency metrics, time savings/losses, and generates Excel reports.

    Args:
        machine_ids: Equipment identifier(s) - list (optional)
        vendor_names: Supplier name(s) - list (optional)
        start_date: Analysis start date (YYYY-MM-DD)
        end_date: Analysis end date (YYYY-MM-DD)
        delta_tolerance: CT tolerance percentage (default: 0.05 = 5%)
        client: Client name/schema (e.g., "PUBLIC", "AURELIA", "MERIDIAN") - overrides .env
        aggregation_level: Time aggregation - "daily", "weekly", or "monthly" (default: "daily")

    Returns:
        dict: Analysis results with metrics and Excel file path
        {
            "status": "success"|"error",
            "job_id": str,
            "metrics": {
                "total_records": int,
                "suspicious_records": int,
                "efficiency_avg": float,
                ...
            },
            "output_files": {
                "excel": str,
                "filename": str,
            }
        }
    """
    job_id = f"roi_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Import ROI analyzer
        from analysis.roi.api import ROIAnalyzer
        from analysis.roi.config import ROIAnalysisConfig

        # Create configuration
        config = ROIAnalysisConfig(delta_tolerance=delta_tolerance)

        # Initialize analyzer with schema override
        analyzer = ROIAnalyzer(config=config, schema=client)

        # Run analysis with aggregation level
        valid_results, suspicious_results = analyzer.analyze(
            vendor_names=vendor_names,
            machine_ids=machine_ids,
            start_date=start_date,
            end_date=end_date,
            aggregation_level=aggregation_level,
        )

        # Extract metrics
        metrics = {
            "total_records": len(valid_results) if valid_results is not None else 0,
            "suspicious_records": (
                len(suspicious_results) if suspicious_results is not None else 0
            ),
        }

        # Add summary statistics if data available
        if valid_results is not None and len(valid_results) > 0:
            metrics.update(
                {
                    # Efficiency metrics (use avg_efficiency to match summary generator)
                    "avg_efficiency": (
                        float(valid_results["TOOLING_EFFICIENCY"].mean())
                        if "TOOLING_EFFICIENCY" in valid_results.columns
                        else 0.0
                    ),
                    "efficiency_avg": (
                        float(valid_results["TOOLING_EFFICIENCY"].mean())
                        if "TOOLING_EFFICIENCY" in valid_results.columns
                        else 0.0
                    ),  # Keep for backward compatibility
                    # Uptime metrics
                    "avg_uptime_percentage": (
                        float(valid_results["UPTIME_PERCENTAGE"].mean())
                        if "UPTIME_PERCENTAGE" in valid_results.columns
                        else 0.0
                    ),
                    # CT performance
                    "within_ct_percentage": (
                        float(valid_results["WITHIN_SHOT_PCT"].mean())
                        if "WITHIN_SHOT_PCT" in valid_results.columns
                        else 0.0
                    ),
                    # Production volume
                    "total_shots": (
                        int(valid_results["TOTAL_SHOTS"].sum())
                        if "TOTAL_SHOTS" in valid_results.columns
                        else 0
                    ),
                }
            )

        # Generate Excel report if we have valid data
        output_files = {}
        if valid_results is not None and len(valid_results) > 0:
            # Use centralized output directory
            import sys
            from pathlib import Path

            analysis_shared_path = (
                Path(__file__).parent.parent.parent.parent.parent / "analysis"
            )
            if str(analysis_shared_path) not in sys.path:
                sys.path.insert(0, str(analysis_shared_path))
            from analysis.shared import get_output_dir

            output_dir = str(get_output_dir("roi"))

            # Get first supplier name for filename (if provided)
            supplier_filter = (
                vendor_names[0]
                if vendor_names and len(vendor_names) > 0
                else None
            )

            # Generate Excel report
            report_path = analyzer.generate_excel_report(
                valid_results, suspicious_results, output_dir, supplier_filter
            )

            output_files["excel"] = report_path
            output_files["filename"] = Path(report_path).name

            # Generate Executive Summary HTML
            analysis_result = {
                "machine_ids": machine_ids,
                "vendor_names": vendor_names,
                "date_range": f"{start_date} to {end_date}",
                "aggregation_level": aggregation_level,
                "metrics": metrics,
            }

            summary_result = analyzer.generate_executive_summary(
                analysis_result=analysis_result, output_dir=output_dir
            )

            if summary_result.get("status") == "success":
                summary_path = summary_result.get("summary_html_path")
                output_files["executive_summary_html"] = summary_path

                # Generate PDF from summary HTML (optional - skip if libraries unavailable)
                try:
                    pdf_result = analyzer.generate_pdf_report(
                        html_path=summary_path, output_dir=output_dir
                    )

                    if pdf_result.get("status") == "success":
                        output_files["executive_summary_pdf"] = pdf_result.get(
                            "pdf_path"
                        )
                except (OSError, ImportError) as e:
                    # PDF generation requires system libraries (libgobject, cairo)
                    # Skip PDF if not available, HTML summary is still generated
                    logger.warning(
                        f"PDF generation skipped (missing system libraries): {str(e)[:100]}"
                    )
                    pass

        # Close connections
        analyzer.close_connections()

        # Create success message with context
        records_desc = (
            "daily records"
            if aggregation_level == "daily"
            else f"{aggregation_level} records"
        )
        total_shots_desc = (
            f" ({metrics['total_shots']} total shots)"
            if metrics.get("total_shots")
            else ""
        )

        success_message = (
            f"✅ ROI analysis completed successfully! "
            f"Generated Excel report with {metrics['total_records']} {records_desc}{total_shots_desc}. "
            f"Files: {', '.join(output_files.keys())}"
        )

        return {
            "status": "success",
            "job_id": job_id,
            "date_range": f"{start_date} to {end_date}",
            "machine_ids": machine_ids,
            "vendor_names": vendor_names,
            "aggregation_level": aggregation_level,
            "metrics": metrics,
            "output_files": output_files,
            "message": success_message,
        }

    except Exception as e:
        return {
            "status": "error",
            "job_id": job_id,
            "error": str(e),
            "error_type": type(e).__name__,
        }


# Tool metadata for MCP registration
ROI_TOOLS = [
    {
        "name": "run_roi_analysis",
        "description": "Calculate ROI and duration efficiency metrics for manufacturing operations",
        "inputSchema": {
            "type": "object",
            "properties": {
                "machine_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Equipment code(s) - e.g., ['MX-7104', 'MX-7110']",
                },
                "vendor_names": {
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
                "delta_tolerance": {
                    "type": "number",
                    "description": "CT tolerance as decimal (default: 0.05 = 5%)",
                    "default": 0.05,
                },
                "client": {
                    "type": "string",
                    "description": "Client name/schema (e.g., 'PUBLIC', 'ARCWELD', 'MERIDIAN') - overrides .env setting",
                },
            },
            "required": ["start_date", "end_date"],
        },
    }
]
