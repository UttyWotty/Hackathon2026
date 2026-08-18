"""
API entry point for Root Cause Analysis (RCA).

Provides run_analysis_api() function for MCP/LLM integration.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from typing import Any, Dict, Optional

from .core_analysis.root_cause_analysis_pipeline import RootCauseAnalysisPipeline


def run_analysis_api(
    machine_id: Optional[str] = None,
    vendor_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    API entry point for Root Cause Analysis (for LLM integration).

    Performs comprehensive root cause analysis including:
    - Pareto analysis to identify top issues
    - 5 Whys methodology for deep dive
    - Downtime and scrap analysis
    - Time pattern detection
    - Actionable recommendations

    Args:
        machine_id: Equipment identifier (optional - analyzes specific equipment)
        vendor_name: Supplier name (optional - for supplier-level analysis)

    Returns:
        dict: {
            "status": "success"|"error",
            "machine_id": str,
            "analysis_summary": {
                "total_shots": int,
                "issue_rate": float,
                "downtime_rate": float,
                "scrap_rate": float,
                "top_issues": list,
                "root_causes": list,
            },
            "pareto_results": dict,
            "five_whys_results": dict,
            "recommendations": list,
            "output_files": {
                "html_reports": list,
                "json_data": str,
            },
            "message": str
        }
    """
    import logging

    logging.info("=" * 100)
    logging.info("RCA API ENTRY POINT")
    logging.info("=" * 100)
    logging.info(f"Parameters: machine_id={machine_id}, vendor_name={vendor_name}")
    print("=" * 100)
    print("RCA API ENTRY POINT")
    print("=" * 100)
    print(f"Parameters: machine_id={machine_id}, vendor_name={vendor_name}")

    try:
        # Ensure environment is loaded (same as other analysis modules)
        import os

        from dotenv import load_dotenv

        logging.info("Loading environment variables...")
        print("Loading environment variables...")
        load_dotenv()

        # Log critical env vars (without sensitive data)
        logging.info(
            f"   SNOWFLAKE_DATABASE: {os.getenv('SNOWFLAKE_DATABASE', 'NOT SET')}"
        )
        logging.info(f"   SNOWFLAKE_SCHEMA: {os.getenv('SNOWFLAKE_SCHEMA', 'NOT SET')}")
        logging.info(f"   SNOWFLAKE_USER: {os.getenv('SNOWFLAKE_USER', 'NOT SET')}")
        logging.info(
            f"   SNOWFLAKE_ACCOUNT: {os.getenv('SNOWFLAKE_ACCOUNT', 'NOT SET')}"
        )
        print(f"   SNOWFLAKE_DATABASE: {os.getenv('SNOWFLAKE_DATABASE', 'NOT SET')}")
        print(f"   SNOWFLAKE_SCHEMA: {os.getenv('SNOWFLAKE_SCHEMA', 'NOT SET')}")

        # Create and run pipeline
        logging.info(
            f"Creating RootCauseAnalysisPipeline with equipment_filter={machine_id}"
        )
        print(f"Creating RootCauseAnalysisPipeline with equipment_filter={machine_id}")
        pipeline = RootCauseAnalysisPipeline(equipment_filter=machine_id)

        # Run complete analysis
        logging.info("Running complete pipeline...")
        print("Running complete pipeline...")
        results = pipeline.run_complete_pipeline()

        if not results:
            return {
                "status": "error",
                "error": f"No data found or analysis failed for equipment {machine_id}",
                "error_type": "DataNotFoundError",
            }

        # Extract key metrics
        summary = {
            "total_shots": pipeline.pareto_results.get("total_shots", 0),
            "issue_rate": pipeline.pareto_results.get("issue_rate", 0),
            "downtime_rate": pipeline.pareto_results.get("downtime_rate", 0),
            "scrap_rate": pipeline.pareto_results.get("scrap_rate", 0),
            "top_equipment": pipeline.pareto_results.get("top_equipment", [])[:5],
            "top_parts": pipeline.pareto_results.get("top_parts", [])[:5],
        }

        # Extract top issues
        top_issues = []
        if pipeline.pareto_results.get("top_equipment"):
            for eq in pipeline.pareto_results["top_equipment"][:3]:
                top_issues.append(
                    {
                        "equipment": eq.get("equipment", "N/A"),
                        "issue_rate": eq.get("issue_rate", 0),
                        "impact": "High" if eq.get("issue_rate", 0) > 10 else "Medium",
                    }
                )

        # Extract root causes from 5 Whys
        root_causes = []
        if pipeline.five_whys_results:
            for category, analysis in pipeline.five_whys_results.items():
                if isinstance(analysis, dict) and "root_cause" in analysis:
                    root_causes.append(
                        {
                            "category": category,
                            "root_cause": analysis["root_cause"],
                            "severity": analysis.get("severity", "Medium"),
                        }
                    )

        # NOTE: Recommendations removed - LLM will generate dynamic insights from raw data
        # NOTE: HTML files removed - they contain model info, not analysis results

        # Add time-based patterns if available
        time_patterns = []
        if pipeline.pareto_results.get("top_time_patterns"):
            for pattern in pipeline.pareto_results["top_time_patterns"][:5]:
                time_patterns.append(
                    {
                        "pattern": pattern.get(
                            "DAY_OF_WEEK", pattern.get("HOUR", "Unknown")
                        ),
                        "issue_count": pattern.get("CT_ISSUE_FLAG", 0),
                        "total_shots": pattern.get("DURATION", 0),
                        "issue_rate": pattern.get("Issue_Rate", 0),
                    }
                )

        return {
            "status": "success",
            "machine_id": machine_id or "All Equipment",
            "vendor_name": vendor_name,
            "analysis_summary": summary,
            "pareto_results": pipeline.pareto_results,  # Include full Pareto results for LLM
            "top_issues": top_issues,
            "root_causes": root_causes[:10],  # Top 10 root causes
            "time_patterns": time_patterns,  # Time-based patterns for LLM analysis
            "message": f"Root cause analysis completed. Analyzed {summary['total_shots']} shots with {summary['issue_rate']:.2f}% issue rate. LLM will analyze patterns and generate insights.",
        }

    except Exception as e:
        import traceback

        error_msg = str(e)
        error_type = type(e).__name__
        full_traceback = traceback.format_exc()

        logging.error("=" * 100)
        logging.error("❌ RCA API ERROR")
        logging.error("=" * 100)
        logging.error(f"Error type: {error_type}")
        logging.error(f"Error message: {error_msg}")
        logging.error(f"Full traceback:\n{full_traceback}")
        print("=" * 100)
        print("❌ RCA API ERROR")
        print("=" * 100)
        print(f"Error type: {error_type}")
        print(f"Error message: {error_msg}")
        print(f"Full traceback:\n{full_traceback}")

        return {
            "status": "error",
            "error": error_msg,
            "error_type": error_type,
            "traceback": full_traceback,
        }
