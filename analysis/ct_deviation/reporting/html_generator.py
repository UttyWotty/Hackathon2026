"""
CT Deviation HTML Report Generator.

This module generates comprehensive HTML reports for CT deviation analysis.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from ..models import DeviationMetrics

logger = logging.getLogger(__name__)


# ==================== HTML Report Generation ==================== #


def generate_html_report(
    metrics_list: List[DeviationMetrics],
    summary_stats: Dict,
    charts: Optional[Dict[str, str]] = None,
    title: str = "CT Deviation Analysis Report",
) -> str:
    """Generate a comprehensive HTML report for CT deviation analysis.

    Args:
        metrics_list: List of deviation metrics
        summary_stats: Summary statistics dictionary
        charts: Dictionary of base64-encoded chart images (optional)
        title: Report title

    Returns:
        str: Complete HTML report as string
    """
    if not metrics_list:
        return _generate_empty_report(title)

    try:
        html = _generate_html_header(title)
        html += _generate_summary_section(summary_stats)
        html += _generate_charts_section(charts)
        html += _generate_metrics_table(metrics_list)
        html += _generate_html_footer()

        logger.info("✅ Generated HTML report successfully")
        return html

    except Exception as e:
        logger.error(f"❌ Error generating HTML report: {e}")
        return _generate_error_report(title, str(e))


def _generate_html_header(title: str) -> str:
    """Generate HTML header with CSS styling.

    Args:
        title: Report title

    Returns:
        str: HTML header section
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            padding: 40px;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 4px solid #667eea;
            padding-bottom: 15px;
            margin-bottom: 10px;
        }}
        .timestamp {{
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 30px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 40px;
            margin-bottom: 20px;
            border-left: 5px solid #667eea;
            padding-left: 15px;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        .summary-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        .summary-card h3 {{
            margin: 0 0 10px 0;
            font-size: 16px;
            opacity: 0.9;
        }}
        .summary-card .value {{
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
        }}
        .chart-container {{
            margin: 30px 0;
            text-align: center;
        }}
        .chart-container img {{
            max-width: 100%;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        th {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #ecf0f1;
        }}
        tr:hover {{
            background-color: #f8f9fa;
        }}
        .excellent {{ color: #27ae60; font-weight: bold; }}
        .good {{ color: #3498db; font-weight: bold; }}
        .acceptable {{ color: #f39c12; font-weight: bold; }}
        .poor {{ color: #e67e22; font-weight: bold; }}
        .critical {{ color: #e74c3c; font-weight: bold; }}
        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 2px solid #ecf0f1;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="timestamp">Generated: {timestamp}</div>
"""


def _generate_summary_section(summary_stats: Dict) -> str:
    """Generate summary statistics section.

    Args:
        summary_stats: Dictionary with summary statistics

    Returns:
        str: HTML summary section
    """
    total_equipment = summary_stats.get("total_equipment", 0)
    total_shots = summary_stats.get("total_shots", 0)
    avg_deviation = summary_stats.get("avg_deviation", 0)
    avg_efficiency = summary_stats.get("avg_efficiency", 0)
    avg_stability = summary_stats.get("avg_stability", 0)

    return f"""
        <h2>📊 Summary Statistics</h2>
        <div class="summary-grid">
            <div class="summary-card">
                <h3>Total Equipment</h3>
                <div class="value">{total_equipment}</div>
            </div>
            <div class="summary-card">
                <h3>Total Shots</h3>
                <div class="value">{total_shots:,}</div>
            </div>
            <div class="summary-card">
                <h3>Avg Deviation</h3>
                <div class="value">{avg_deviation:.2f}%</div>
            </div>
            <div class="summary-card">
                <h3>Avg Efficiency</h3>
                <div class="value">{avg_efficiency:.1f}%</div>
            </div>
            <div class="summary-card">
                <h3>Avg Stability</h3>
                <div class="value">{avg_stability:.1f}%</div>
            </div>
        </div>
"""


def _generate_charts_section(charts: Optional[Dict[str, str]]) -> str:
    """Generate charts section with embedded images.

    Args:
        charts: Dictionary of chart_name -> base64_image

    Returns:
        str: HTML charts section
    """
    if not charts:
        return ""

    html = "<h2>📈 Visualizations</h2>\n"

    for chart_name, chart_data in charts.items():
        if chart_data:
            html += f"""
        <div class="chart-container">
            <img src="data:image/png;base64,{chart_data}" alt="{chart_name}">
        </div>
"""

    return html


def _generate_metrics_table(metrics_list: List[DeviationMetrics]) -> str:
    """Generate detailed metrics table.

    Args:
        metrics_list: List of deviation metrics

    Returns:
        str: HTML table section
    """
    html = """
        <h2>📋 Detailed Metrics</h2>
        <table>
            <thead>
                <tr>
                    <th>Equipment Code</th>
                    <th>Supplier</th>
                    <th>Total Shots</th>
                    <th>Avg CT (s)</th>
                    <th>Approved CT (s)</th>
                    <th>Deviation (%)</th>
                    <th>Category</th>
                    <th>Efficiency (%)</th>
                    <th>Stability (%)</th>
                </tr>
            </thead>
            <tbody>
"""

    # Sort by absolute deviation (best first)
    sorted_metrics = sorted(metrics_list, key=lambda x: abs(x.deviation_percentage))

    for m in sorted_metrics:
        # Determine category class for coloring
        category_class = m.deviation_category.value.split()[0].lower()

        html += f"""
                <tr>
                    <td><strong>{m.equipment_code}</strong></td>
                    <td>{m.supplier_name}</td>
                    <td>{m.total_shots:,}</td>
                    <td>{m.avg_ct:.2f}</td>
                    <td>{m.approved_ct:.2f}</td>
                    <td class="{category_class}">{m.deviation_percentage:+.2f}%</td>
                    <td class="{category_class}">{m.deviation_category.value}</td>
                    <td>{m.efficiency_score:.1f}%</td>
                    <td>{m.stability_score:.1f}%</td>
                </tr>
"""

    html += """
            </tbody>
        </table>
"""

    return html


def _generate_html_footer() -> str:
    """Generate HTML footer.

    Returns:
        str: HTML footer section
    """
    return """
        <div class="footer">
            <p>Generated by CotexAI Manufacturing Analytics Platform</p>
            <p>© 2025 CotexAI. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""


def _generate_empty_report(title: str) -> str:
    """Generate report for empty data.

    Args:
        title: Report title

    Returns:
        str: HTML report with empty data message
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; padding: 50px; text-align: center; }}
        .message {{ font-size: 24px; color: #7f8c8d; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="message">
        <p>⚠️ No data available for the specified filters.</p>
        <p>Please adjust your date range or equipment/supplier filters and try again.</p>
    </div>
</body>
</html>
"""


def _generate_error_report(title: str, error: str) -> str:
    """Generate error report.

    Args:
        title: Report title
        error: Error message

    Returns:
        str: HTML error report
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title} - Error</title>
    <style>
        body {{ font-family: Arial, sans-serif; padding: 50px; text-align: center; }}
        .error {{ color: #e74c3c; font-size: 18px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="error">
        <p>❌ Error generating report:</p>
        <p>{error}</p>
    </div>
</body>
</html>
"""
