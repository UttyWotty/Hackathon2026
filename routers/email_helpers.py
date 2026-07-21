"""
Email template rendering and formatting helpers for the email router.

Provides Jinja2-based HTML template rendering with plain-text fallback,
and utility functions for formatting analytics data into email-ready text.
This module is consumed exclusively by email_router.py.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Jinja2 template environment (optional dependency)
# ---------------------------------------------------------------------------

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    TEMPLATES_DIR: Path = Path(__file__).parent.parent / "templates" / "email"
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    jinja_env: Optional[Environment] = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    JINJA2_AVAILABLE: bool = True
except ImportError:
    jinja_env = None
    JINJA2_AVAILABLE = False
    logger.warning(
        "Jinja2 not installed. HTML templates disabled. Install with: pip install jinja2"
    )


# ---------------------------------------------------------------------------
# Plain-text template rendering (fallback)
# ---------------------------------------------------------------------------

_ANALYSIS_REPORT_TEMPLATE = (
    "\nManufacturing Analytics Report\n\n"
    "Analysis Type: {analysis_type}\n"
    "Generated: {generated}\n"
    "Date Range: {date_range}\n\n"
    "Summary:\n{summary}\n\n"
    "Key Metrics:\n{metrics}\n\n"
    "Insights:\n{insights}\n\n"
    "Please find the attached report(s) for detailed analysis.\n\n"
    "---\n"
    "This is an automated message from the Manufacturing Analytics System.\n"
)

_ALERT_TEMPLATE = (
    "\nALERT NOTIFICATION\n\n"
    "Alert: {alert_title}\n"
    "Severity: {severity}\n"
    "Time: {time}\n\n"
    "Details:\n{details}\n\n"
    "Action Required:\n{action}\n\n"
    "---\n"
    "This is an automated alert from the Manufacturing Analytics System.\n"
)

_SUMMARY_TEMPLATE = (
    "\nManufacturing Summary Report\n\n"
    "Period: {period}\n"
    "Generated: {generated}\n\n"
    "Highlights:\n{highlights}\n\n"
    "Performance:\n{performance}\n\n"
    "Trends:\n{trends}\n\n"
    "Recommendations:\n{recommendations}\n\n"
    "---\n"
    "This is an automated summary from the Manufacturing Analytics System.\n"
)

_FALLBACK_BODY = "Email content unavailable."


def render_plain_text_template(template_name: str, data: dict) -> str:
    """Render a plain-text email template (fallback when Jinja2 is absent)."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if template_name == "analysis_report":
        return _ANALYSIS_REPORT_TEMPLATE.format(
            analysis_type=data.get("analysis_type", "N/A"),
            generated=now_str,
            date_range=data.get("date_range", "N/A"),
            summary=data.get("summary", "No summary provided"),
            metrics=data.get("metrics", "No metrics provided"),
            insights=data.get("insights", "No insights provided"),
        )

    if template_name == "alert":
        return _ALERT_TEMPLATE.format(
            alert_title=data.get("alert_title", "N/A"),
            severity=data.get("severity", "N/A"),
            time=now_str,
            details=data.get("details", "No details provided"),
            action=data.get("action", "Please review the alert details"),
        )

    if template_name == "summary":
        return _SUMMARY_TEMPLATE.format(
            period=data.get("period", "Weekly"),
            generated=now_str,
            highlights=data.get("highlights", "No highlights provided"),
            performance=data.get("performance", "No performance data provided"),
            trends=data.get("trends", "No trends identified"),
            recommendations=data.get("recommendations", "No recommendations provided"),
        )

    return _FALLBACK_BODY


# ---------------------------------------------------------------------------
# HTML template rendering
# ---------------------------------------------------------------------------


def render_html_template(template_name: str, data: dict) -> str:
    """
    Render an HTML email template using Jinja2.

    Falls back to plain text if Jinja2 is not available or the template
    cannot be found / rendered.
    """
    if not JINJA2_AVAILABLE or jinja_env is None:
        return render_plain_text_template(template_name, data)

    try:
        template_data = {
            **data,
            "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "year": datetime.now().year,
        }

        template = jinja_env.get_template(f"{template_name}.html")
        return template.render(**template_data)
    except Exception:
        logger.warning(
            "Failed to render HTML template '%s', falling back to plain text",
            template_name,
        )
        return render_plain_text_template(template_name, data)


# ---------------------------------------------------------------------------
# Analytics data formatting
# ---------------------------------------------------------------------------

_BULLET = "  - "


def format_analysis_summary(result_data: dict) -> str:
    """Format analysis result data into a human-readable summary string."""
    summary_parts: list[str] = []

    if "equipment_codes" in result_data:
        codes = ", ".join(result_data["equipment_codes"])
        summary_parts.append(f"Equipment: {codes}")

    if "metrics" in result_data:
        metrics = result_data["metrics"]
        if isinstance(metrics, dict):
            for key, value in metrics.items():
                summary_parts.append(f"{key}: {value}")

    return (
        "\n".join(summary_parts)
        if summary_parts
        else "Analysis completed successfully."
    )


def format_analysis_metrics(result_data: dict) -> str:
    """Format analysis metrics dictionary into readable bulleted text."""
    if "metrics" not in result_data:
        return "No metrics available."

    metrics = result_data["metrics"]
    if isinstance(metrics, dict):
        lines: list[str] = []
        for key, value in metrics.items():
            lines.append(f"{_BULLET}{key}: {value}")
        return "\n".join(lines)

    return str(metrics)
