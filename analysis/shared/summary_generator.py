"""
Executive Summary Generator for Manufacturing Analytics.
Orchestrates generation of professional HTML executive summaries for ROI,
RunRate, Capacity, and multi-analysis reports by delegating to specialised modules.
This module owns the SummaryGenerator class and its singleton accessor.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .roi_summary import generate_roi_summary
from .summary_templates import (
    create_insight,
    create_kpi_card,
    create_recommendation,
    get_base_template,
)

logger = logging.getLogger(__name__)


class SummaryGenerator:
    """
    Generate executive summary HTML reports.

    Features:
    - Automatic KPI extraction from analysis results
    - Visual dashboard creation
    - Insight and recommendation formatting
    - Multi-analysis support (ROI, RunRate, Capacity)
    """

    def generate_roi_summary(
        self,
        analysis_result: Dict[str, Any],
        output_path: str,
        llm_insights: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate executive summary for ROI analysis.

        Delegates to the standalone generate_roi_summary function in
        analysis.shared.roi_summary.

        Args:
            analysis_result: ROI analysis result dictionary
            output_path: Output HTML file path
            llm_insights: Optional insights from LLM analysis

        Returns:
            dict: Generation result with path and status
        """
        return generate_roi_summary(
            analysis_result=analysis_result,
            output_path=output_path,
            llm_insights=llm_insights,
        )

    def generate_runrate_summary(
        self,
        analysis_result: Dict[str, Any],
        output_path: str,
        llm_insights: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate executive summary for RunRate analysis."""
        try:
            metrics = analysis_result.get("metrics", {})

            # Extract metadata
            equipment_code = analysis_result.get("equipment_code", "N/A")
            supplier_name = analysis_result.get("supplier_name", "N/A")

            metadata = {
                "Equipment": equipment_code,
                "Supplier": supplier_name,
                "Date Range": analysis_result.get("date_range", "N/A"),
                "Analysis Type": "RunRate (MTTR/MTBF)",
            }

            # Build KPI cards
            kpis_html = '<div class="kpi-grid">'

            # MTTR KPI
            mttr = metrics.get("avg_mttr", 0)
            kpis_html += create_kpi_card(
                label="MTTR (Mean Time To Repair)",
                value=f"{mttr:.1f}",
                unit="min",
                change="Average Repair Time",
                change_type="positive" if mttr <= 45 else "warning",
            )

            # MTBF KPI
            mtbf = metrics.get("avg_mtbf", 0)
            mtbf_hours = mtbf / 60 if mtbf > 0 else 0
            kpis_html += create_kpi_card(
                label="MTBF (Mean Time Between Failures)",
                value=f"{mtbf_hours:.1f}",
                unit="hrs",
                change="Reliability Metric",
                change_type="positive" if mtbf_hours >= 8 else "warning",
            )

            # Efficiency KPI
            efficiency = metrics.get("avg_efficiency", 0)
            kpis_html += create_kpi_card(
                label="Overall Efficiency",
                value=f"{efficiency:.1f}",
                unit="%",
                change="Production vs Stops",
                change_type="positive" if efficiency >= 75 else "neutral",
            )

            # Total Stops KPI
            total_stops = metrics.get("total_stop_events", 0)
            kpis_html += create_kpi_card(
                label="Total Stop Events",
                value=f"{total_stops:,}",
                unit="",
                change="Downtime Events",
                change_type="neutral",
            )

            kpis_html += "</div>"

            # Build insights
            insights_html = '<ul class="insight-list">'
            insights_html += create_insight(
                title="MTTR Analysis",
                description=(
                    f"Average repair time of {mttr:.1f} minutes. "
                    f"{'Excellent performance - below 45-minute target.' if mttr <= 45 else 'Focus on reducing downtime duration through maintenance training and spare parts availability.'}"
                ),
                severity="info" if mttr <= 45 else "warning",
            )
            insights_html += "</ul>"

            # Build recommendations
            recommendations_html = create_recommendation(
                title="Detailed Analysis Available",
                description=(
                    "This is a preliminary summary. Full RunRate analysis with "
                    "time bucket patterns, stop detection details, and MTTR/MTBF "
                    "trends is available in the detailed Excel report."
                ),
                impact="Review detailed report",
                priority="medium",
            )

            # Add LLM insights if provided
            llm_section = ""
            if llm_insights:
                llm_section = (
                    '<section class="section">'
                    '<h2 class="section-title">AI-Generated Analysis</h2>'
                    '<div class="insight-item">'
                    f'<div class="insight-description">{llm_insights}</div>'
                    "</div>"
                    "</section>"
                )

            # Assemble content
            content = (
                '<section class="section">'
                '<h2 class="section-title">Key Performance Indicators</h2>'
                f"{kpis_html}"
                "</section>"
                '<section class="section">'
                '<h2 class="section-title">Executive Insights</h2>'
                f"{insights_html}"
                "</section>"
                '<section class="section">'
                '<h2 class="section-title">Next Steps</h2>'
                f"{recommendations_html}"
                "</section>"
                f"{llm_section}"
            )

            # Generate HTML
            html = get_base_template(
                title="RunRate Analysis - Executive Summary",
                subtitle=f"{equipment_code} - {analysis_result.get('date_range', 'N/A')}",
                content=content,
                metadata=metadata,
            )

            # Write file
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)

            logger.info("Executive summary generated: %s", output_path_obj.name)

            return {
                "status": "success",
                "summary_html_path": str(output_path),
                "message": f"Executive summary generated: {output_path_obj.name}",
            }

        except Exception as e:
            logger.error("Failed to generate summary: %s", str(e))
            return {"status": "error", "error": f"Failed to generate summary: {str(e)}"}

    def generate_capacity_summary(
        self,
        analysis_result: Dict[str, Any],
        output_path: str,
        llm_insights: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate executive summary for Capacity analysis."""
        logger.info("Capacity summary generation - using generic template")
        return {
            "status": "success",
            "summary_html_path": output_path,
            "message": "Capacity summary template (to be enhanced)",
        }

    def generate_multi_analysis_summary(
        self,
        roi_result: Optional[Dict[str, Any]] = None,
        runrate_result: Optional[Dict[str, Any]] = None,
        capacity_result: Optional[Dict[str, Any]] = None,
        output_path: str = ".",
        equipment_code: str = "Equipment",
        client: str = "Client",
        date_range: str = "Analysis Period",
    ) -> Dict[str, Any]:
        """
        Generate comprehensive HTML summary combining multiple analyses.

        Args:
            roi_result: ROI analysis results dictionary
            runrate_result: RunRate analysis results dictionary
            capacity_result: Capacity analysis results dictionary
            output_path: Output directory or file path
            equipment_code: Equipment code for title
            client: Client name for title
            date_range: Date range string

        Returns:
            Dict with status and file path
        """
        try:
            import os
            from datetime import datetime

            # Create output directory if needed
            if os.path.isdir(output_path):
                filename = f"Multi_Analysis_Summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                output_path = os.path.join(output_path, filename)

            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # Build sections for each available analysis
            sections_html = []

            if roi_result:
                sections_html.append(_build_roi_section(roi_result))

            if runrate_result:
                sections_html.append(_build_runrate_section(runrate_result))

            if capacity_result:
                sections_html.append(_build_capacity_section(capacity_result))

            # Combine all sections
            content = "".join(sections_html)

            # Add metadata
            metadata = {
                "Equipment": equipment_code,
                "Client": client,
                "Period": date_range,
                "Generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Generate HTML
            html = get_base_template(
                title=f"{client} Equipment Performance Summary",
                subtitle=f"{equipment_code} - {date_range}",
                content=content,
                metadata=metadata,
            )

            # Write to file
            output_path_obj.write_text(html, encoding="utf-8")

            logger.info("Multi-analysis summary generated: %s", output_path_obj.name)
            return {
                "status": "success",
                "summary_html_path": str(output_path),
                "message": f"Multi-analysis summary generated: {output_path_obj.name}",
            }

        except Exception as e:
            logger.error("Failed to generate multi-analysis summary: %s", str(e))
            return {
                "status": "error",
                "error": f"Failed to generate multi-analysis summary: {str(e)}",
            }


def _build_roi_section(roi_result: Dict[str, Any]) -> str:
    """
    Build ROI KPI section for multi-analysis summary.

    Args:
        roi_result: ROI analysis results dictionary.

    Returns:
        HTML string for the ROI section.
    """
    roi_kpis = []
    roi_kpis.append(
        create_kpi_card(
            "Total Shots",
            f"{roi_result.get('total_shots', 'N/A'):,}",
            "success",
        )
    )
    roi_kpis.append(
        create_kpi_card(
            "Avg Efficiency",
            f"{roi_result.get('avg_efficiency', 0):.1f}%",
            "success" if roi_result.get("avg_efficiency", 0) > 90 else "warning",
        )
    )
    roi_kpis.append(
        create_kpi_card(
            "Avg Uptime",
            f"{roi_result.get('avg_uptime', 0):.1f}%",
            "success" if roi_result.get("avg_uptime", 0) > 85 else "warning",
        )
    )
    return (
        '<section class="section">'
        '<h2 class="section-title">ROI and Efficiency Analysis</h2>'
        '<div class="kpi-grid">'
        f'{"".join(roi_kpis)}'
        "</div>"
        "</section>"
    )


def _build_runrate_section(runrate_result: Dict[str, Any]) -> str:
    """
    Build RunRate KPI section for multi-analysis summary.

    Args:
        runrate_result: RunRate analysis results dictionary.

    Returns:
        HTML string for the RunRate section.
    """
    runrate_kpis = []
    runrate_kpis.append(
        create_kpi_card(
            "Efficiency",
            f"{runrate_result.get('efficiency', 0):.1f}%",
            "success" if runrate_result.get("efficiency", 0) > 90 else "warning",
        )
    )
    runrate_kpis.append(
        create_kpi_card(
            "MTTR",
            f"{runrate_result.get('mttr', 0):.1f} min",
            "success" if runrate_result.get("mttr", 0) < 30 else "warning",
        )
    )
    runrate_kpis.append(
        create_kpi_card(
            "MTBF",
            f"{runrate_result.get('mtbf', 0):.1f} min",
            "success" if runrate_result.get("mtbf", 0) > 120 else "warning",
        )
    )
    runrate_kpis.append(
        create_kpi_card(
            "Total Stops",
            f"{runrate_result.get('total_stops', 0)}",
            "success" if runrate_result.get("total_stops", 0) < 20 else "warning",
        )
    )
    return (
        '<section class="section">'
        '<h2 class="section-title">RunRate and Reliability Analysis</h2>'
        '<div class="kpi-grid">'
        f'{"".join(runrate_kpis)}'
        "</div>"
        "</section>"
    )


def _build_capacity_section(capacity_result: Dict[str, Any]) -> str:
    """
    Build Capacity KPI section for multi-analysis summary.

    Args:
        capacity_result: Capacity analysis results dictionary.

    Returns:
        HTML string for the Capacity section.
    """
    capacity_kpis = []
    capacity_kpis.append(
        create_kpi_card(
            "OEE",
            f"{capacity_result.get('oee', 0):.1f}%",
            "success" if capacity_result.get("oee", 0) > 75 else "warning",
        )
    )
    capacity_kpis.append(
        create_kpi_card(
            "Performance",
            f"{capacity_result.get('performance', 0):.1f}%",
            "success" if capacity_result.get("performance", 0) > 85 else "warning",
        )
    )
    capacity_kpis.append(
        create_kpi_card(
            "Availability",
            f"{capacity_result.get('availability', 0):.1f}%",
            "success" if capacity_result.get("availability", 0) > 85 else "warning",
        )
    )
    capacity_kpis.append(
        create_kpi_card(
            "Quality",
            f"{capacity_result.get('quality', 0):.1f}%",
            "success" if capacity_result.get("quality", 0) > 95 else "warning",
        )
    )
    return (
        '<section class="section">'
        '<h2 class="section-title">Capacity and OEE Analysis</h2>'
        '<div class="kpi-grid">'
        f'{"".join(capacity_kpis)}'
        "</div>"
        "</section>"
    )


# Singleton
_summary_generator: Optional[SummaryGenerator] = None


def get_summary_generator() -> SummaryGenerator:
    """Get singleton summary generator instance."""
    global _summary_generator
    if _summary_generator is None:
        _summary_generator = SummaryGenerator()
    return _summary_generator
