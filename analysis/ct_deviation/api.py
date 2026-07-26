"""
CT Deviation Analysis API.

This module provides the main API wrapper for CT deviation analysis,
orchestrating data loading, calculation, and reporting.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]
from dotenv import load_dotenv  # type: ignore[import-untyped]

from .core import (
    calculate_deviation_metrics,
    create_snowpark_session,
    fetch_ct_deviation_data,
    generate_summary_statistics,
    validate_ct_data,
)
from .models import DeviationMetrics
from .reporting import (
    create_deviation_distribution_chart,
    create_performance_comparison_chart,
    create_supplier_comparison_chart,
    create_time_series_chart,
    generate_html_report,
)

# Load environment variables at module level
load_dotenv()

logger = logging.getLogger(__name__)


# ==================== Main API Function ==================== #


def run_analysis_api(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    equipment_codes: Optional[List[str]] = None,
    supplier_names: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    save_csv: bool = True,
    save_html: bool = True,
    create_charts: bool = True,
) -> Dict:
    """Run CT deviation analysis and generate reports.

    This is the main entry point for the CT deviation analysis module,
    designed for programmatic access and LLM integration.

    Args:
        start_date: Start date in 'YYYY-MM-DD' format (optional)
        end_date: End date in 'YYYY-MM-DD' format (optional)
        equipment_codes: List of equipment codes to analyze (optional)
        supplier_names: List of supplier names to analyze (optional)
        output_dir: Output directory for reports (optional, defaults to 'ct_deviation_results')
        save_csv: Whether to save CSV results (default: True)
        save_html: Whether to save HTML report (default: True)
        create_charts: Whether to create visualizations (default: True)

    Returns:
        Dict: Analysis results including metrics, summary, and file paths
            {
                "status": "success" or "error",
                "metrics": List of deviation metrics,
                "summary": Summary statistics dict,
                "output_files": Dict of generated file paths,
                "message": Status message
            }

    Example:
        >>> result = run_analysis_api(
        ...     start_date="2025-01-01",
        ...     end_date="2025-10-27",
        ...     equipment_codes=["EMA-4110"],
        ...     save_csv=True,
        ...     save_html=True
        ... )
        >>> print(result["summary"]["avg_deviation"])
    """
    try:
        logger.info("🚀 Starting CT Deviation Analysis")

        # Set default output directory (centralized)
        if output_dir is None:
            from analysis.shared import get_output_dir

            output_dir = str(get_output_dir("ct_deviation"))
        else:
            os.makedirs(output_dir, exist_ok=True)

        # Create Snowflake session
        logger.info("📡 Connecting to Snowflake...")
        session = create_snowpark_session()

        # Fetch data
        logger.info("📥 Fetching CT deviation data...")
        df = fetch_ct_deviation_data(
            session=session,
            start_date=start_date,
            end_date=end_date,
            equipment_codes=equipment_codes,
            supplier_names=supplier_names,
        )

        # Close session. None in local data mode, where no session was opened.
        if session is not None:
            session.close()

        # Validate data
        if df.empty:
            logger.warning("⚠️ No data found for the specified filters")
            return {
                "status": "success",
                "metrics": [],
                "summary": {},
                "output_files": {},
                "message": "No data found for the specified filters",
            }

        df = validate_ct_data(df)
        logger.info(f"✅ Loaded {len(df)} valid records")

        # Calculate deviation metrics
        logger.info("🔢 Calculating deviation metrics...")
        metrics_list = calculate_deviation_metrics(df)

        # Generate summary statistics
        logger.info("📊 Generating summary statistics...")
        summary_stats = generate_summary_statistics(metrics_list)

        # Generate charts
        charts = {}
        if create_charts:
            logger.info("📈 Creating visualizations...")
            charts["deviation_distribution"] = create_deviation_distribution_chart(
                metrics_list
            )
            charts["performance_comparison"] = create_performance_comparison_chart(
                metrics_list
            )
            charts["time_series"] = create_time_series_chart(df)
            charts["supplier_comparison"] = create_supplier_comparison_chart(
                metrics_list
            )

        # Save results
        output_files = {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save CSV
        if save_csv and metrics_list:
            csv_path = _save_metrics_to_csv(metrics_list, output_dir, timestamp)
            output_files["csv"] = csv_path

        # Save HTML report
        if save_html and metrics_list:
            html_path = _save_html_report(
                metrics_list, summary_stats, charts, output_dir, timestamp
            )
            output_files["html"] = html_path

        logger.info("✅ CT Deviation Analysis completed successfully")

        return {
            "status": "success",
            "metrics": _metrics_to_dict(metrics_list),
            "summary": summary_stats,
            "output_files": output_files,
            "message": f"Analysis completed successfully. Analyzed {len(metrics_list)} equipment across {summary_stats.get('total_shots', 0):,} shots.",
        }

    except Exception as e:
        logger.error(f"❌ Error in CT deviation analysis: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "metrics": [],
            "summary": {},
            "output_files": {},
            "message": f"Analysis failed: {str(e)}",
        }


# ==================== Helper Functions ==================== #


def _save_metrics_to_csv(
    metrics_list: List[DeviationMetrics], output_dir: str, timestamp: str
) -> str:
    """Save metrics list to CSV file.

    Args:
        metrics_list: List of deviation metrics
        output_dir: Output directory
        timestamp: Timestamp string for filename

    Returns:
        str: Path to saved CSV file
    """
    results_data = []
    for m in metrics_list:
        results_data.append(
            {
                "Equipment_Code": m.equipment_code,
                "Supplier_Name": m.supplier_name,
                "Total_Shots": m.total_shots,
                "Average_CT": m.avg_ct,
                "Approved_CT": m.approved_ct,
                "CT_Deviation": m.ct_deviation,
                "Deviation_Percentage": m.deviation_percentage,
                "Deviation_Category": m.deviation_category.value,
                "Shots_Above_Target": m.shots_above_target,
                "Shots_Below_Target": m.shots_below_target,
                "Shots_On_Target": m.shots_on_target,
                "Efficiency_Score": m.efficiency_score,
                "Stability_Score": m.stability_score,
            }
        )

    df_results = pd.DataFrame(results_data)
    csv_path = os.path.join(output_dir, f"ct_deviation_analysis_{timestamp}.csv")
    df_results.to_csv(csv_path, index=False)
    logger.info(f"✅ CSV results saved to {csv_path}")

    return csv_path


def _save_html_report(
    metrics_list: List[DeviationMetrics],
    summary_stats: Dict,
    charts: Dict[str, str],
    output_dir: str,
    timestamp: str,
) -> str:
    """Save HTML report to file.

    Args:
        metrics_list: List of deviation metrics
        summary_stats: Summary statistics
        charts: Dictionary of chart base64 data
        output_dir: Output directory
        timestamp: Timestamp string for filename

    Returns:
        str: Path to saved HTML file
    """
    html_content = generate_html_report(
        metrics_list=metrics_list,
        summary_stats=summary_stats,
        charts=charts,
        title="CT Deviation Analysis Report",
    )

    html_path = os.path.join(output_dir, f"ct_deviation_report_{timestamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"✅ HTML report saved to {html_path}")

    return html_path


def _metrics_to_dict(metrics_list: List[DeviationMetrics]) -> List[Dict]:
    """Convert DeviationMetrics list to dictionary list for JSON serialization.

    Args:
        metrics_list: List of DeviationMetrics

    Returns:
        List[Dict]: List of metrics as dictionaries
    """
    return [
        {
            "equipment_code": m.equipment_code,
            "supplier_name": m.supplier_name,
            "total_shots": m.total_shots,
            "avg_ct": m.avg_ct,
            "approved_ct": m.approved_ct,
            "ct_deviation": m.ct_deviation,
            "deviation_percentage": m.deviation_percentage,
            "deviation_category": m.deviation_category.value,
            "shots_above_target": m.shots_above_target,
            "shots_below_target": m.shots_below_target,
            "shots_on_target": m.shots_on_target,
            "efficiency_score": m.efficiency_score,
            "stability_score": m.stability_score,
        }
        for m in metrics_list
    ]
