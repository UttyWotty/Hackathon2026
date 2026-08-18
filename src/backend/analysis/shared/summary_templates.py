"""
HTML Templates for Executive Summaries.

Provides reusable templates and styling for professional
executive summary reports across all analysis types.

Author: Utku Gulbardak
Date: 2025-10-30
"""

from datetime import datetime
from typing import Dict, Optional


def get_base_template(
    title: str, subtitle: str, content: str, metadata: Optional[Dict[str, str]] = None
) -> str:
    """
    Get base HTML template for executive summaries.

    Args:
        title: Main report title
        subtitle: Subtitle (equipment, date range, etc.)
        content: Main content HTML
        metadata: Additional metadata (client, equipment, etc.)

    Returns:
        str: Complete HTML document
    """
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    meta_section = ""
    if metadata:
        meta_items = "".join(
            [
                f'<span class="meta-item"><strong>{k}:</strong> {v}</span>'
                for k, v in metadata.items()
            ]
        )
        meta_section = f'<div class="metadata">{meta_items}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        {get_base_css()}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="report-header">
            <div class="header-content">
                <h1 class="report-title">{title}</h1>
                <p class="report-subtitle">{subtitle}</p>
                {meta_section}
            </div>
            <div class="header-date">
                <span class="date-label">Generated:</span>
                <span class="date-value">{current_date}</span>
            </div>
        </header>
        
        <!-- Main Content -->
        <main class="report-content">
            {content}
        </main>
        
        <!-- Footer -->
        <footer class="report-footer">
            <p>Manufacturing Analytics AI • Confidential</p>
        </footer>
    </div>
</body>
</html>"""


def get_base_css() -> str:
    """Get base CSS styling for executive summaries."""
    return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', sans-serif;
            background: #f5f7fa;
            color: #1e293b;
            line-height: 1.6;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            min-height: 100vh;
        }
        
        /* Header */
        .report-header {
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
            color: white;
            padding: 40px 40px 30px 40px;
            border-bottom: 5px solid #1e40af;
        }
        
        .report-title {
            font-size: 36px;
            font-weight: 700;
            margin-bottom: 8px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .report-subtitle {
            font-size: 18px;
            opacity: 0.95;
            margin-bottom: 15px;
        }
        
        .metadata {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid rgba(255,255,255,0.2);
        }
        
        .meta-item {
            font-size: 14px;
            opacity: 0.9;
        }
        
        .header-date {
            margin-top: 15px;
            font-size: 14px;
            opacity: 0.85;
        }
        
        /* Content */
        .report-content {
            padding: 40px;
        }
        
        /* KPI Cards */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 24px;
            margin: 30px 0;
        }
        
        .kpi-card {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .kpi-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        
        .kpi-label {
            font-size: 14px;
            color: #64748b;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }
        
        .kpi-value {
            font-size: 42px;
            font-weight: 700;
            color: #1e293b;
            margin-bottom: 8px;
        }
        
        .kpi-unit {
            font-size: 18px;
            color: #64748b;
            margin-left: 4px;
        }
        
        .kpi-change {
            font-size: 14px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 6px;
            margin-top: 8px;
        }
        
        .kpi-change.positive {
            background: #dcfce7;
            color: #166534;
        }
        
        .kpi-change.negative {
            background: #fee2e2;
            color: #991b1b;
        }
        
        .kpi-change.neutral {
            background: #f1f5f9;
            color: #475569;
        }
        
        /* Sections */
        .section {
            margin: 40px 0;
        }
        
        .section-title {
            font-size: 24px;
            font-weight: 700;
            color: #1e293b;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #3b82f6;
        }
        
        /* Insights */
        .insight-list {
            list-style: none;
            padding: 0;
        }
        
        .insight-item {
            background: #f8fafc;
            border-left: 4px solid #3b82f6;
            padding: 20px;
            margin-bottom: 16px;
            border-radius: 0 8px 8px 0;
        }
        
        .insight-item.warning {
            border-left-color: #f59e0b;
            background: #fffbeb;
        }
        
        .insight-item.critical {
            border-left-color: #ef4444;
            background: #fef2f2;
        }
        
        .insight-title {
            font-size: 18px;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 8px;
        }
        
        .insight-description {
            font-size: 15px;
            color: #475569;
            line-height: 1.6;
        }
        
        /* Recommendations */
        .recommendation-card {
            background: white;
            border: 2px solid #e2e8f0;
            border-radius: 10px;
            padding: 24px;
            margin-bottom: 20px;
            position: relative;
            overflow: hidden;
        }
        
        .recommendation-card::before {
            content: '';
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 6px;
            background: #3b82f6;
        }
        
        .recommendation-card.high-priority::before {
            background: #ef4444;
        }
        
        .recommendation-card.medium-priority::before {
            background: #f59e0b;
        }
        
        .recommendation-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        
        .recommendation-title {
            font-size: 18px;
            font-weight: 600;
            color: #1e293b;
        }
        
        .priority-badge {
            font-size: 12px;
            font-weight: 700;
            padding: 6px 12px;
            border-radius: 20px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .priority-badge.high {
            background: #fee2e2;
            color: #991b1b;
        }
        
        .priority-badge.medium {
            background: #fef3c7;
            color: #92400e;
        }
        
        .priority-badge.low {
            background: #dbeafe;
            color: #1e40af;
        }
        
        .recommendation-impact {
            font-size: 24px;
            font-weight: 700;
            color: #059669;
            margin: 12px 0;
        }
        
        .recommendation-description {
            font-size: 15px;
            color: #475569;
            line-height: 1.6;
        }
        
        /* Status Indicators */
        .status-indicator {
            display: inline-flex;
            align-items: center;
            font-size: 14px;
            font-weight: 600;
            padding: 6px 12px;
            border-radius: 6px;
            margin-right: 8px;
        }
        
        .status-indicator.good {
            background: #dcfce7;
            color: #166534;
        }
        
        .status-indicator.warning {
            background: #fef3c7;
            color: #92400e;
        }
        
        .status-indicator.critical {
            background: #fee2e2;
            color: #991b1b;
        }
        
        .status-indicator::before {
            content: '●';
            margin-right: 6px;
            font-size: 16px;
        }
        
        /* Progress Bars */
        .progress-bar {
            width: 100%;
            height: 12px;
            background: #e2e8f0;
            border-radius: 6px;
            overflow: hidden;
            margin: 10px 0;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #3b82f6 0%, #1e40af 100%);
            border-radius: 6px;
            transition: width 0.3s ease;
        }
        
        .progress-fill.high {
            background: linear-gradient(90deg, #10b981 0%, #059669 100%);
        }
        
        .progress-fill.medium {
            background: linear-gradient(90deg, #f59e0b 0%, #d97706 100%);
        }
        
        .progress-fill.low {
            background: linear-gradient(90deg, #ef4444 0%, #dc2626 100%);
        }
        
        /* Footer */
        .report-footer {
            background: #f8fafc;
            padding: 20px 40px;
            text-align: center;
            color: #64748b;
            font-size: 14px;
            border-top: 1px solid #e2e8f0;
        }
        
        /* Print Styles */
        @media print {
            body {
                background: white;
            }
            .kpi-card {
                break-inside: avoid;
            }
            .recommendation-card {
                break-inside: avoid;
            }
        }
    """


def create_kpi_card(
    label: str,
    value: str,
    unit: str = "",
    change: Optional[str] = None,
    change_type: str = "neutral",
) -> str:
    """
    Create a KPI card HTML.

    Args:
        label: KPI label (e.g., "Efficiency")
        value: Main value (e.g., "91.2")
        unit: Unit (e.g., "%", "shots", "minutes")
        change: Change indicator (e.g., "+5.3% vs Q3")
        change_type: "positive", "negative", or "neutral"

    Returns:
        str: KPI card HTML
    """
    change_html = ""
    if change:
        change_html = f'<div class="kpi-change {change_type}">{change}</div>'

    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}<span class="kpi-unit">{unit}</span></div>
        {change_html}
    </div>
    """


def create_insight(title: str, description: str, severity: str = "info") -> str:
    """
    Create an insight item HTML.

    Args:
        title: Insight title
        description: Detailed description
        severity: "info", "warning", or "critical"

    Returns:
        str: Insight HTML
    """
    severity_class = (
        "warning"
        if severity == "warning"
        else ("critical" if severity == "critical" else "")
    )

    return f"""
    <li class="insight-item {severity_class}">
        <div class="insight-title">{title}</div>
        <div class="insight-description">{description}</div>
    </li>
    """


def create_recommendation(
    title: str, description: str, impact: str, priority: str = "medium"
) -> str:
    """
    Create a recommendation card HTML.

    Args:
        title: Recommendation title
        description: Detailed description
        impact: Financial/business impact (e.g., "+$320K/year")
        priority: "high", "medium", or "low"

    Returns:
        str: Recommendation card HTML
    """
    return f"""
    <div class="recommendation-card {priority}-priority">
        <div class="recommendation-header">
            <div class="recommendation-title">{title}</div>
            <span class="priority-badge {priority}">{priority} priority</span>
        </div>
        <div class="recommendation-impact">💰 {impact}</div>
        <div class="recommendation-description">{description}</div>
    </div>
    """
