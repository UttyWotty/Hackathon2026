"""
CT Efficiency HTML Report Generator.

This module generates comprehensive HTML reports for CT efficiency and
supplier benchmarking analysis.

Author: Utku Gulbardak
Date: 2025-10-27
"""

import logging
from datetime import datetime
from typing import Dict, List

from ..models import SupplierBenchmark, get_tier_color

logger = logging.getLogger(__name__)


# ==================== HTML Report Generation ==================== #


def generate_html_report(
    supplier_benchmarks: List[SupplierBenchmark],
    efficiency_summary: Dict,
    supplier_summary: Dict,
    title: str = "CT Efficiency & Supplier Benchmarking Report",
) -> str:
    """Generate a comprehensive HTML report for CT efficiency analysis.

    Args:
        supplier_benchmarks: List of supplier benchmark results
        efficiency_summary: Overall efficiency summary statistics
        supplier_summary: Supplier benchmarking summary
        title: Report title

    Returns:
        str: Complete HTML report as string
    """
    if not supplier_benchmarks:
        return _generate_empty_report(title)

    try:
        html = _generate_html_header(title)
        html += _generate_summary_section(efficiency_summary, supplier_summary)
        html += _generate_supplier_table(supplier_benchmarks)
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
        .tier-badge {{
            padding: 5px 10px;
            border-radius: 20px;
            font-weight: bold;
            color: white;
            display: inline-block;
        }}
        .rank-badge {{
            background: #3498db;
            color: white;
            padding: 5px 10px;
            border-radius: 50%;
            font-weight: bold;
            display: inline-block;
            min-width: 30px;
            text-align: center;
        }}
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


def _generate_summary_section(efficiency_summary: Dict, supplier_summary: Dict) -> str:
    """Generate summary statistics section.

    Args:
        efficiency_summary: Efficiency summary statistics
        supplier_summary: Supplier benchmarking summary

    Returns:
        str: HTML summary section
    """
    total_tools = efficiency_summary.get("total_tools", 0)
    total_shots = efficiency_summary.get("total_shots", 0)
    mean_eff = efficiency_summary.get("mean_efficiency", 0)
    total_suppliers = supplier_summary.get("total_suppliers", 0)
    mean_consistency = supplier_summary.get("mean_consistency", 0)

    return f"""
        <h2>📊 Summary Statistics</h2>
        <div class="summary-grid">
            <div class="summary-card">
                <h3>Total Tools Analyzed</h3>
                <div class="value">{total_tools}</div>
            </div>
            <div class="summary-card">
                <h3>Total Shots</h3>
                <div class="value">{total_shots:,}</div>
            </div>
            <div class="summary-card">
                <h3>Mean Efficiency</h3>
                <div class="value">{mean_eff:.2f}%</div>
            </div>
            <div class="summary-card">
                <h3>Total Suppliers</h3>
                <div class="value">{total_suppliers}</div>
            </div>
            <div class="summary-card">
                <h3>Mean Consistency</h3>
                <div class="value">{mean_consistency:.1f}%</div>
            </div>
        </div>
"""


def _generate_supplier_table(supplier_benchmarks: List[SupplierBenchmark]) -> str:
    """Generate supplier benchmarking table.

    Args:
        supplier_benchmarks: List of supplier benchmark results

    Returns:
        str: HTML table section
    """
    html = """
        <h2>🏆 Supplier Benchmarking Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Supplier Name</th>
                    <th>Efficiency</th>
                    <th>Consistency</th>
                    <th>Total Tools</th>
                    <th>Tier</th>
                </tr>
            </thead>
            <tbody>
"""

    for benchmark in supplier_benchmarks:
        tier_color = get_tier_color(benchmark.tier_classification)

        html += f"""
                <tr>
                    <td><span class="rank-badge">{benchmark.performance_rank}</span></td>
                    <td><strong>{benchmark.supplier_name}</strong></td>
                    <td>{benchmark.mean_normalized_efficiency:.4f}</td>
                    <td>{benchmark.tool_consistency_score:.2f}%</td>
                    <td>{benchmark.total_tools}</td>
                    <td><span class="tier-badge" style="background: {tier_color};">{benchmark.tier_classification}</span></td>
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
        <p>Please adjust your filters and try again.</p>
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
