"""
Duration Efficiency Analysis API.

This module provides the main API wrapper for duration efficiency and supplier
benchmarking analysis, orchestrating data loading, calculation, and reporting.

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
    aggregate_per_tool,
    analyze_all_equipment_shifts,
    benchmark_operators,
    benchmark_suppliers,
    calculate_duration_efficiency,
    compare_tools_by_target_duration,
    compare_tools_windowed,
    create_snowpark_session,
    detect_shift_boundaries,
    detect_shift_patterns,
    detect_shifts_per_supplier,
    detect_stale_baselines,
    fetch_efficiency_data,
    generate_efficiency_summary,
    generate_operator_summary,
    generate_supplier_summary,
    get_supplier_comparison,
    normalize_efficiency_scores,
    prepare_efficiency_data,
)
from .models import MIN_SESSIONS_FOR_SHIFT_REPORT, get_default_config
from .reporting import (
    generate_all_charts,
    generate_analysis_report,
    generate_html_report,
)
from .serializers import (
    benchmarks_to_dict as _benchmarks_to_dict,
    format_break_schedule as _format_break_schedule,
    operator_benchmarks_to_dict as _operator_benchmarks_to_dict,
    save_shift_performance_to_csv as _save_shift_performance_to_csv,
    save_staleness_report_to_csv as _save_staleness_report_to_csv,
    save_supplier_shifts_to_csv as _save_supplier_shifts_to_csv,
    save_tool_comparison_to_csv as _save_tool_comparison_to_csv,
    save_windowed_comparison_to_csv as _save_windowed_comparison_to_csv,
    shift_analyses_to_dict as _shift_analyses_to_dict,
    shift_patterns_to_dict as _shift_patterns_to_dict,
    tool_comparison_to_dict as _tool_comparison_to_dict,
)

# Load environment variables at module level
load_dotenv()

logger = logging.getLogger(__name__)


# ==================== Main API Function ==================== #


def run_analysis_api(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    vendor_names: Optional[List[str]] = None,
    client: Optional[str] = None,
    output_dir: Optional[str] = None,
    save_csv: bool = True,
    save_html: bool = True,
    normalization_method: str = "z_score",
    config: Optional[Dict] = None,
) -> Dict:
    """Run duration efficiency analysis: supplier benchmarking, operator shift
    analysis (per-supplier boundaries), tool comparison, and staleness detection.

    Args:
        start_date: Start date 'YYYY-MM-DD' (optional)
        end_date: End date 'YYYY-MM-DD' (optional)
        vendor_names: Supplier name filter (optional)
        client: Client/schema name for Snowflake (e.g. 'KESTREL')
        output_dir: Output directory (default: output/efficiency)
        save_csv: Save CSV results (default: True)
        save_html: Save HTML reports (default: True)
        normalization_method: 'z_score', 'min_max', or 'percentile'
        config: Optional config dict

    Returns:
        Dict with status, summaries, benchmarks, and output file paths
    """
    try:
        logger.info("🚀 Starting Duration Efficiency Analysis")

        # Get configuration
        if config is None:
            config = get_default_config()

        # Set default output directory (centralized)
        if output_dir is None:
            from analysis.shared import get_output_dir

            output_dir = str(get_output_dir("efficiency"))
        else:
            os.makedirs(output_dir, exist_ok=True)

        # Create Snowflake session
        logger.info("📡 Connecting to Snowflake...")
        session = create_snowpark_session()

        # Fetch data
        logger.info("📥 Fetching duration efficiency data...")
        df = fetch_efficiency_data(
            session=session,
            start_date=start_date,
            end_date=end_date,
            vendor_names=vendor_names,
            client=client,
        )

        # Close session
        session.close()

        # Check if data exists
        if df.empty:
            logger.warning("⚠️ No data found for the specified filters")
            return {
                "status": "success",
                "efficiency_summary": {},
                "supplier_summary": {},
                "supplier_benchmarks": [],
                "top_suppliers": [],
                "operator_summary": {},
                "operator_benchmarks": [],
                "shift_patterns": [],
                "shift_performance": [],
                "tool_comparison": [],
                "output_files": {},
                "message": "No data found for the specified filters",
            }

        # Prepare data
        logger.info("🧹 Preparing data...")
        df = prepare_efficiency_data(df)

        # Calculate efficiency
        logger.info("🔢 Calculating duration efficiency...")
        df = calculate_duration_efficiency(df)

        # Aggregate per tool
        logger.info("📊 Aggregating metrics per tool...")
        tool_metrics = aggregate_per_tool(df)

        # Normalize scores
        logger.info(f"🎯 Normalizing efficiency scores ({normalization_method})...")
        tool_metrics = normalize_efficiency_scores(
            tool_metrics, method=normalization_method
        )

        # Generate efficiency summary
        logger.info("Generating efficiency summary...")
        efficiency_summary = generate_efficiency_summary(tool_metrics)

        # Benchmark suppliers
        logger.info("🏆 Benchmarking suppliers...")
        supplier_benchmarks = benchmark_suppliers(tool_metrics)

        # Generate supplier summary
        logger.info("📊 Generating supplier summary...")
        supplier_summary = generate_supplier_summary(supplier_benchmarks)

        # Get top suppliers for quick reference
        top_suppliers = get_supplier_comparison(supplier_benchmarks)[:5]

        # Operator benchmarking (session-based behavioral analysis)
        logger.info("Performing operator benchmarking...")
        operator_benchmarks = benchmark_operators(df)

        # Detect shift patterns per equipment (min 10 sessions to reduce noise)
        shift_patterns = []
        for equip_code, equip_df in df.groupby("tool_id"):
            pattern = detect_shift_patterns(equip_df, str(equip_code))
            if pattern.total_sessions >= MIN_SESSIONS_FOR_SHIFT_REPORT:
                shift_patterns.append(pattern)

        operator_summary = generate_operator_summary(
            operator_benchmarks, shift_patterns
        )

        # Auto-detect shift boundaries per supplier
        logger.info("Detecting shift boundaries per supplier...")
        supplier_shifts = detect_shifts_per_supplier(df)
        # Also keep a global detection for charting
        detected_shifts = detect_shift_boundaries(df)

        # Shift performance analysis using per-supplier boundaries
        logger.info("Analyzing shift performance per supplier...")
        all_shift_analyses = []
        for vendor_name, supplier_df in df.groupby("VENDOR_NAME"):
            s_name = str(vendor_name)
            if s_name in supplier_shifts:
                bounds = supplier_shifts[s_name].boundaries
            else:
                bounds = detected_shifts.boundaries
            supplier_analyses = analyze_all_equipment_shifts(
                supplier_df, boundaries=bounds
            )
            all_shift_analyses.extend(supplier_analyses)
        shift_analyses = all_shift_analyses

        # Tool comparison by approved duration groups
        logger.info("Comparing tools within same approved duration groups...")
        tool_groups = compare_tools_by_target_duration(df)

        # Time-windowed tool comparison (monthly)
        logger.info("Running monthly windowed tool comparison...")
        windowed_groups = compare_tools_windowed(df)

        # Approved target staleness detection
        logger.info("Detecting stale approved duration baselines...")
        staleness_results = detect_stale_baselines(df)

        # Save results
        output_files = {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save CSVs
        if save_csv:
            csv_path = _save_benchmarks_to_csv(
                supplier_benchmarks, output_dir, timestamp
            )
            output_files["supplier_csv"] = csv_path

            operator_csv_path = _save_operator_benchmarks_to_csv(
                operator_benchmarks, output_dir, timestamp
            )
            output_files["operator_csv"] = operator_csv_path

            shift_csv_path = _save_shift_patterns_to_csv(
                shift_patterns, output_dir, timestamp
            )
            output_files["shift_patterns_csv"] = shift_csv_path

            shift_perf_csv = _save_shift_performance_to_csv(
                shift_analyses, output_dir, timestamp
            )
            output_files["shift_performance_csv"] = shift_perf_csv

            tool_comp_csv = _save_tool_comparison_to_csv(
                tool_groups, output_dir, timestamp
            )
            output_files["tool_comparison_csv"] = tool_comp_csv

            windowed_csv = _save_windowed_comparison_to_csv(
                windowed_groups, output_dir, timestamp
            )
            output_files["tool_trend_csv"] = windowed_csv

            staleness_csv = _save_staleness_report_to_csv(
                staleness_results, output_dir, timestamp
            )
            output_files["staleness_csv"] = staleness_csv

            supplier_shifts_csv = _save_supplier_shifts_to_csv(
                supplier_shifts, output_dir, timestamp
            )
            output_files["supplier_shifts_csv"] = supplier_shifts_csv

        # Save HTML reports
        if save_html:
            html_path = _save_html_report(
                supplier_benchmarks,
                efficiency_summary,
                supplier_summary,
                output_dir,
                timestamp,
            )
            output_files["html"] = html_path

            # Interactive charts + report (non-fatal if they fail)
            try:
                chart_paths = generate_all_charts(
                    shift_analyses,
                    tool_groups,
                    windowed_groups,
                    staleness_results,
                    output_dir,
                    detected_shifts=detected_shifts,
                )
                output_files["charts"] = chart_paths

                report_html = generate_analysis_report(
                    shift_analyses,
                    tool_groups,
                    windowed_groups,
                    staleness_results,
                    chart_paths,
                )
                report_path = os.path.join(
                    output_dir, f"analysis_report_{timestamp}.html"
                )
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(report_html)
                output_files["analysis_report"] = report_path
                logger.info("Analysis report saved to %s", report_path)
            except Exception as chart_err:
                logger.warning("Chart/report generation failed: %s", chart_err)

        logger.info("✅ Duration Efficiency Analysis completed successfully")

        return {
            "status": "success",
            "efficiency_summary": efficiency_summary,
            "supplier_summary": supplier_summary,
            "supplier_benchmarks": _benchmarks_to_dict(supplier_benchmarks),
            "top_suppliers": top_suppliers,
            "operator_summary": operator_summary,
            "operator_benchmarks": _operator_benchmarks_to_dict(operator_benchmarks),
            "shift_patterns": _shift_patterns_to_dict(shift_patterns),
            "shift_performance": _shift_analyses_to_dict(shift_analyses),
            "tool_comparison": _tool_comparison_to_dict(tool_groups),
            "output_files": output_files,
            "message": (
                f"Analysis completed successfully. Analyzed {len(tool_metrics)} tools "
                f"from {len(supplier_benchmarks)} suppliers, "
                f"{len(tool_groups)} approved duration groups for tool comparison."
            ),
        }

    except Exception as e:
        logger.error(f"❌ Error in duration efficiency analysis: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "efficiency_summary": {},
            "supplier_summary": {},
            "supplier_benchmarks": [],
            "top_suppliers": [],
            "operator_summary": {},
            "operator_benchmarks": [],
            "shift_patterns": [],
            "output_files": {},
            "message": f"Analysis failed: {str(e)}",
        }


# ==================== Helper Functions ==================== #


def _save_benchmarks_to_csv(benchmarks: List, output_dir: str, timestamp: str) -> str:
    """Save supplier benchmarks to CSV file.

    Args:
        benchmarks: List of SupplierBenchmark objects
        output_dir: Output directory
        timestamp: Timestamp string for filename

    Returns:
        str: Path to saved CSV file
    """
    data = []
    for b in benchmarks:
        data.append(
            {
                "Rank": b.performance_rank,
                "Vendor_Name": b.vendor_name,
                "Efficiency_Score": round(b.mean_normalized_efficiency, 4),
                "Consistency_Score": round(b.tool_consistency_score, 2),
                "Total_Tools": b.total_tools,
                "Tier": b.tier_classification,
                "Adjusted_Score": round(b.adjusted_score, 4),
            }
        )

    df_benchmarks = pd.DataFrame(data)
    csv_path = os.path.join(output_dir, f"supplier_benchmarks_{timestamp}.csv")
    df_benchmarks.to_csv(csv_path, index=False)
    logger.info(f"✅ CSV results saved to {csv_path}")

    return csv_path


def _save_operator_benchmarks_to_csv(
    benchmarks: List, output_dir: str, timestamp: str
) -> str:
    """Save operator benchmarks to CSV file.

    Args:
        benchmarks: List of OperatorBenchmark objects
        output_dir: Output directory
        timestamp: Timestamp string for filename

    Returns:
        str: Path to saved CSV file
    """
    data = []
    for b in benchmarks:
        data.append(
            {
                "Rank": b.performance_rank,
                "Machine_Id": b.machine_id,
                "Tooling_Type": b.process_type,
                "Vendor_Name": b.vendor_name,
                "Session_Count": b.session_count,
                "Mean_Efficiency_Pct": round(b.mean_efficiency_pct, 2),
                "Within_Session_Consistency": round(b.within_session_consistency, 2),
                "Cross_Session_Consistency": round(b.cross_session_consistency, 2),
                "Warmup_Impact_Pct": round(b.warmup_impact_pct, 2),
                "Tier": b.tier_classification,
                "Adjusted_Score": round(b.adjusted_score, 4),
            }
        )

    df_benchmarks = pd.DataFrame(data)
    csv_path = os.path.join(output_dir, f"operator_benchmarks_{timestamp}.csv")
    df_benchmarks.to_csv(csv_path, index=False)
    logger.info("Operator benchmarks CSV saved to %s", csv_path)

    return csv_path


def _save_shift_patterns_to_csv(patterns: List, output_dir: str, timestamp: str) -> str:
    """Save shift patterns to CSV file.

    Args:
        patterns: List of OperatorShiftPattern objects
        output_dir: Output directory
        timestamp: Timestamp string for filename

    Returns:
        str: Path to saved CSV file
    """
    data = []
    for p in patterns:
        data.append(
            {
                "Machine_Id": p.machine_id,
                "Tooling_Type": p.process_type,
                "Total_Sessions": p.total_sessions,
                "Avg_Session_Duration_Hours": p.avg_session_duration_hours,
                "Avg_Break_Duration_Hours": p.avg_break_duration_hours,
                "Production_End_Count": p.production_end_count,
                "Has_Planned_Downtime": p.has_planned_downtime,
                "Avg_Warmup_Penalty_Pct": p.avg_warmup_penalty_pct,
                "Shots_Per_Session": p.shots_per_session,
                "Break_Schedule": _format_break_schedule(p.break_schedule),
            }
        )

    df_patterns = pd.DataFrame(data)
    csv_path = os.path.join(output_dir, f"shift_patterns_{timestamp}.csv")
    df_patterns.to_csv(csv_path, index=False)
    logger.info("Shift patterns CSV saved to %s", csv_path)

    return csv_path


def _save_html_report(
    benchmarks: List,
    efficiency_summary: Dict,
    supplier_summary: Dict,
    output_dir: str,
    timestamp: str,
) -> str:
    """Save HTML report to file.

    Args:
        benchmarks: List of SupplierBenchmark objects
        efficiency_summary: Efficiency summary statistics
        supplier_summary: Supplier summary statistics
        output_dir: Output directory
        timestamp: Timestamp string for filename

    Returns:
        str: Path to saved HTML file
    """
    html_content = generate_html_report(
        supplier_benchmarks=benchmarks,
        efficiency_summary=efficiency_summary,
        supplier_summary=supplier_summary,
        title="Duration Efficiency & Supplier Benchmarking Report",
    )

    html_path = os.path.join(output_dir, f"efficiency_report_{timestamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"✅ HTML report saved to {html_path}")

    return html_path
