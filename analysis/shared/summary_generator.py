"""
Executive Summary Generator for Manufacturing Analytics.

Orchestrates generation of professional HTML executive summaries for ROI
and multi-analysis reports by delegating to specialised modules.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .roi_summary import generate_roi_summary
from .summary_templates import (
    create_kpi_card,
    get_base_template,
)

logger = logging.getLogger(__name__)


class SummaryGenerator:
    """
    Generate executive summary HTML reports.

    Features automatic KPI extraction, visual dashboard creation,
    and multi-analysis support.
    """

    def generate_roi_summary(
        self,
        analysis_result: Dict[str, Any],
        output_path: str,
        llm_insights: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate executive summary for ROI analysis.

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

    def generate_multi_analysis_summary(
        self,
        roi_result: Optional[Dict[str, Any]] = None,
        output_path: str = ".",
        equipment_code: str = "Equipment",
        client: str = "Client",
        date_range: str = "Analysis Period",
    ) -> Dict[str, Any]:
        """
        Generate comprehensive HTML summary combining multiple analyses.

        Args:
            roi_result: ROI analysis results dictionary
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

            if os.path.isdir(output_path):
                filename = f"Multi_Analysis_Summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                output_path = os.path.join(output_path, filename)

            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            sections_html = []

            if roi_result:
                sections_html.append(_build_roi_section(roi_result))

            content = "".join(sections_html)

            metadata = {
                "Equipment": equipment_code,
                "Client": client,
                "Period": date_range,
                "Generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            html = get_base_template(
                title=f"{client} Equipment Performance Summary",
                subtitle=f"{equipment_code} - {date_range}",
                content=content,
                metadata=metadata,
            )

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


# Singleton
_summary_generator: Optional[SummaryGenerator] = None


def get_summary_generator() -> SummaryGenerator:
    """Get singleton summary generator instance."""
    global _summary_generator
    if _summary_generator is None:
        _summary_generator = SummaryGenerator()
    return _summary_generator
