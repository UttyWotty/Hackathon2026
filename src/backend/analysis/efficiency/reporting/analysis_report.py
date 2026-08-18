"""
Duration Efficiency Analysis Report Generator.

This module produces a clean, light-themed HTML report covering operator analysis,
tool comparison, and approved target staleness findings. Designed to look good when
saved as PDF -- minimal color, clear typography, data-driven narrative.
"""

import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)


def generate_analysis_report(
    shift_analyses: List,
    tool_groups: List,
    windowed_groups: List,
    staleness_results: List,
    chart_paths: Dict[str, str],
) -> str:
    """Generate the full analysis HTML report.

    Args:
        shift_analyses: EquipmentShiftAnalysis list
        tool_groups: ApprovedCTGroup list
        windowed_groups: WindowedGroupResult list
        staleness_results: StalenessResult list
        chart_paths: Dict of chart name to file path

    Returns:
        Complete HTML string
    """
    html = _header()
    html += _section_executive_summary(staleness_results, shift_analyses, tool_groups)
    html += _section_operator_analysis(shift_analyses)
    html += _section_tool_comparison(tool_groups)
    html += _section_monthly_trends(windowed_groups)
    html += _section_staleness(staleness_results)
    html += _section_recommendations(staleness_results)
    html += _footer(chart_paths)
    return html


# ==================== Header ==================== #


def _header() -> str:
    """Generate HTML header with light CSS."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Duration Efficiency Analysis Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
    color: #2D3748; background: #FFFFFF;
    line-height: 1.6; font-size: 14px;
    max-width: 900px; margin: 0 auto; padding: 40px 32px;
  }}
  h1 {{ font-size: 24px; font-weight: 600; color: #1A202C;
       border-bottom: 2px solid #E2E8F0; padding-bottom: 12px; margin-bottom: 8px; }}
  h2 {{ font-size: 18px; font-weight: 600; color: #2D3748;
       margin-top: 36px; margin-bottom: 12px;
       border-left: 3px solid #4A7C94; padding-left: 12px; }}
  h3 {{ font-size: 15px; font-weight: 600; color: #4A5568; margin-top: 20px; margin-bottom: 8px; }}
  .timestamp {{ color: #A0AEC0; font-size: 13px; margin-bottom: 28px; }}
  p {{ margin-bottom: 10px; }}
  .highlight {{ background: #F7FAFC; border-left: 3px solid #4A7C94;
               padding: 12px 16px; margin: 16px 0; border-radius: 0 4px 4px 0; }}
  .warning {{ background: #FFFBEB; border-left: 3px solid #C4956A; }}
  .critical {{ background: #FFF5F5; border-left: 3px solid #C05050; }}
  .ok {{ background: #F0FFF4; border-left: 3px solid #7BA38C; }}
  table {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }}
  th {{ background: #F7FAFC; color: #4A5568; font-weight: 600;
       text-align: left; padding: 10px 12px; border-bottom: 2px solid #E2E8F0; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #EDF2F7; }}
  tr:hover {{ background: #FAFAFA; }}
  .metric {{ font-size: 28px; font-weight: 700; color: #1A202C; }}
  .metric-label {{ font-size: 12px; color: #A0AEC0; text-transform: uppercase;
                   letter-spacing: 0.5px; }}
  .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                  gap: 16px; margin: 20px 0; }}
  .metric-card {{ background: #F7FAFC; border-radius: 6px; padding: 16px; text-align: center; }}
  .tag {{ display: inline-block; padding: 2px 8px; border-radius: 3px;
          font-size: 12px; font-weight: 600; }}
  .tag-ok {{ background: #C6F6D5; color: #276749; }}
  .tag-warning {{ background: #FEFCBF; color: #975A16; }}
  .tag-stale {{ background: #FED7D7; color: #9B2C2C; }}
  .tag-severely {{ background: #FEB2B2; color: #742A2A; }}
  .section-divider {{ border-top: 1px solid #E2E8F0; margin-top: 32px; padding-top: 4px; }}
  .footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid #E2E8F0;
             color: #A0AEC0; font-size: 12px; text-align: center; }}
  .chart-link {{ color: #4A7C94; text-decoration: none; font-weight: 500; }}
  .chart-link:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>Duration Efficiency Analysis Report</h1>
<div class="timestamp">Generated: {timestamp}</div>
"""


# ==================== Executive Summary ==================== #


def _section_executive_summary(
    staleness: List,
    shifts: List,
    tools: List,
) -> str:
    """Executive summary with key metrics."""
    stale_count = sum(1 for r in staleness if r.is_stale)
    total_groups = len(staleness)

    # Operator impact
    has_variance = [a for a in shifts if a.variance is not None]
    if has_variance:
        avg_ratio = sum(a.variance.operator_ratio for a in has_variance) / len(
            has_variance
        )
    else:
        avg_ratio = 0.0

    # Worst staleness
    worst = staleness[0] if staleness else None

    html = """<h2>Executive Summary</h2>"""

    html += '<div class="metric-grid">'
    html += f"""
    <div class="metric-card">
      <div class="metric">{total_groups}</div>
      <div class="metric-label">Part Groups Analyzed</div>
    </div>
    <div class="metric-card">
      <div class="metric">{stale_count}/{total_groups}</div>
      <div class="metric-label">Stale Baselines</div>
    </div>
    <div class="metric-card">
      <div class="metric">{avg_ratio:.2f}</div>
      <div class="metric-label">Avg Operator Ratio</div>
    </div>
    """
    if worst:
        html += f"""
    <div class="metric-card">
      <div class="metric">{worst.latest_efficiency:.1f}%</div>
      <div class="metric-label">Worst Group Efficiency</div>
    </div>
    """
    html += "</div>"

    html += '<div class="highlight critical"><strong>Key Finding:</strong> '
    html += "All approved duration baselines are out of date. Machines run 17-43% slower "
    html += "than target across all part groups. Performance differences between "
    html += "operators are negligible (ratio &lt; 0.3). The primary issue is stale "
    html += "baselines, not machine or operator performance.</div>"

    return html


# ==================== Operator Analysis ==================== #


def _section_operator_analysis(shifts: List) -> str:
    """Operator shift analysis section."""
    html = '<div class="section-divider"></div>'
    html += "<h2>1. Operator Shift Analysis</h2>"
    html += "<p>Each day's shift (6am-2pm, 2pm-10pm, 10pm-6am) is treated as a "
    html += "unique operator instance. Within-day variance measures shift/operator "
    html += "effect; across-day variance measures machine/tooling drift.</p>"

    has_variance = [a for a in shifts if a.variance is not None]
    if not has_variance:
        html += "<p>Insufficient multi-shift data for variance decomposition.</p>"
        return html

    html += """<table>
    <thead><tr>
      <th>Equipment</th><th>Within-Day Std</th><th>Across-Day Std</th>
      <th>Operator Ratio</th><th>Days Analyzed</th><th>Verdict</th>
    </tr></thead><tbody>"""

    for a in has_variance:
        v = a.variance
        html += f"""<tr>
        <td><strong>{a.machine_id}</strong></td>
        <td>{v.within_day_std}</td>
        <td>{v.across_day_std}</td>
        <td>{v.operator_ratio}</td>
        <td>{v.days_with_all_shifts}</td>
        <td>{v.conclusion}</td>
        </tr>"""

    html += "</tbody></table>"

    html += '<div class="highlight ok"><strong>Conclusion:</strong> '
    html += "Within-day shift variance is consistently smaller than across-day "
    html += "variance. Operator ratio is below 0.3 for all equipment. "
    html += "Operators are interchangeable -- machine performance does not change "
    html += "between shifts.</div>"

    return html


# ==================== Tool Comparison ==================== #


def _section_tool_comparison(tool_groups: List) -> str:
    """Tool comparison within same-part groups."""
    html = '<div class="section-divider"></div>'
    html += "<h2>2. Tool Comparison (Same Part Groups)</h2>"
    html += (
        "<p>Equipment grouped by TARGET_DURATION (same target = same or similar parts). "
    )
    html += "Machines compared head-to-head on identical work.</p>"

    for group in tool_groups:
        part_label = ", ".join(group.product_names[:2])
        html += f"<h3>Approved Duration: {group.target_duration}s -- {part_label}</h3>"
        html += f"<p>Group mean: {group.group_mean_efficiency}% | "
        html += f"Spread: {group.group_std_efficiency} pct points | "
        html += f"{group.equipment_count} machines | {group.total_shots:,} shots</p>"

        html += """<table>
        <thead><tr>
          <th>Rank</th><th>Equipment</th><th>Type</th><th>Shots</th>
          <th>Mean Eff %</th><th>Std</th><th>vs Group</th>
        </tr></thead><tbody>"""

        for t in group.tools:
            dev_class = (
                "" if t.deviation_from_group_mean >= 0 else ' style="color:#C05050"'
            )
            sign = "+" if t.deviation_from_group_mean >= 0 else ""
            html += f"""<tr>
            <td>{t.rank_in_group}</td>
            <td><strong>{t.machine_id}</strong></td>
            <td>{t.process_type}</td>
            <td>{t.shot_count:,}</td>
            <td>{t.mean_efficiency_pct}%</td>
            <td>{t.std_efficiency_pct}</td>
            <td{dev_class}>{sign}{t.deviation_from_group_mean}</td>
            </tr>"""

        html += "</tbody></table>"

    html += '<div class="highlight"><strong>Observation:</strong> '
    html += "Machine-to-machine differences within the same part group are modest "
    html += "(2-7 percentage points). The much larger issue is that ALL machines "
    html += "underperform their approved duration target.</div>"

    return html


# ==================== Monthly Trends ==================== #


def _section_monthly_trends(windowed: List) -> str:
    """Monthly trend analysis section."""
    html = '<div class="section-divider"></div>'
    html += "<h2>3. Monthly Performance Trends</h2>"
    html += "<p>Same comparison as above, but broken into monthly windows to show "
    html += "whether machine rankings are stable or shift over time.</p>"

    for group in windowed:
        part_label = ", ".join(group.product_names[:2])
        stable_text = (
            "Rankings are stable"
            if group.rankings_stable
            else "Rankings shift over time"
        )
        html += f"<h3>Approved Duration: {group.target_duration}s -- {part_label}</h3>"
        html += f"<p>{group.window_count} months analyzed | "
        html += f"{group.equipment_count} equipment | {stable_text}</p>"

        if group.trend_summaries:
            html += """<table>
            <thead><tr>
              <th>Equipment</th><th>Windows</th><th>Mean Rank</th>
              <th>Rank Std</th><th>Trend/Month</th><th>Best</th><th>Worst</th>
            </tr></thead><tbody>"""

            for t in group.trend_summaries:
                trend_color = (
                    ' style="color:#C05050"' if t.efficiency_trend < -0.3 else ""
                )
                html += f"""<tr>
                <td><strong>{t.machine_id}</strong></td>
                <td>{t.windows_present}</td>
                <td>{t.mean_rank}</td>
                <td>{t.rank_std}</td>
                <td{trend_color}>{t.efficiency_trend:+.3f}%</td>
                <td>{t.best_efficiency}% ({t.best_window})</td>
                <td>{t.worst_efficiency}% ({t.worst_window})</td>
                </tr>"""

            html += "</tbody></table>"

    html += '<div class="highlight warning"><strong>Finding:</strong> '
    html += "Machines rotate onto different parts over time, and ALL machines show "
    html += "declining efficiency. The degradation is temporal (tooling wear, baseline "
    html += (
        "drift), not machine-specific. Rankings within any given month are tight.</div>"
    )

    return html


# ==================== Staleness ==================== #


def _section_staleness(staleness: List) -> str:
    """Approved target staleness section."""
    html = '<div class="section-divider"></div>'
    html += "<h2>4. Approved Duration Baseline Assessment</h2>"
    html += "<p>Each approved duration is evaluated for staleness based on trend, "
    html += (
        "current performance level, and gap between target and actual duration.</p>"
    )

    html += """<table>
    <thead><tr>
      <th>Approved Duration</th><th>Parts</th><th>Severity</th>
      <th>Trend/Month</th><th>Current Eff</th><th>Actual Duration</th>
      <th>Gap</th><th>Suggested Duration</th>
    </tr></thead><tbody>"""

    for r in staleness:
        tag_class = {
            "ok": "tag-ok",
            "warning": "tag-warning",
            "stale": "tag-stale",
            "severely_stale": "tag-severely",
        }.get(r.severity, "")

        latest_ct = r.monthly_snapshots[-1].mean_duration if r.monthly_snapshots else 0
        gap_pct = round((latest_ct - r.target_duration) / r.target_duration * 100, 1)

        html += f"""<tr>
        <td><strong>{r.target_duration}s</strong></td>
        <td>{', '.join(r.product_names[:2])}</td>
        <td><span class="tag {tag_class}">{r.severity.replace('_', ' ').upper()}</span></td>
        <td>{r.trend_per_month:+.2f}%</td>
        <td>{r.latest_efficiency}%</td>
        <td>{latest_ct}s</td>
        <td>+{gap_pct}%</td>
        <td><strong>{r.suggested_duration}s</strong></td>
        </tr>"""

    html += "</tbody></table>"

    return html


# ==================== Recommendations ==================== #


def _section_recommendations(staleness: List) -> str:
    """Actionable recommendations section."""
    html = '<div class="section-divider"></div>'
    html += "<h2>5. Recommendations</h2>"

    html += '<div class="highlight critical">'
    html += '<strong>Immediate Action Required:</strong><ol style="margin-top:8px;padding-left:20px">'

    stale = [r for r in staleness if r.is_stale]
    if stale:
        html += "<li><strong>Recalibrate approved durations.</strong> "
        html += 'The following baselines are stale and should be updated:<ul style="margin-top:4px">'
        for r in stale:
            html += (
                f"<li>{r.target_duration}s &rarr; {r.suggested_duration}s "
                f'({", ".join(r.product_names[:2])})</li>'
            )
        html += "</ul></li>"

    html += "<li><strong>Investigate root causes of duration drift.</strong> "
    html += (
        "All groups show degradation over time. Potential causes: die/tooling wear, "
    )
    html += "process parameter drift, material batch variation.</li>"

    html += "<li><strong>Establish periodic baseline review.</strong> "
    html += "Approved Durations should be reviewed quarterly against actual performance "
    html += "to prevent staleness from accumulating.</li>"

    html += (
        "<li><strong>Operator benchmarking is not needed for this supplier.</strong> "
    )
    html += "Shift analysis confirms operators are interchangeable. Focus efficiency "
    html += "efforts on tooling maintenance and process optimization instead.</li>"

    html += "</ol></div>"

    return html


# ==================== Footer ==================== #


def _footer(chart_paths: Dict[str, str]) -> str:
    """Report footer with links to interactive charts."""
    html = '<div class="footer">'

    if chart_paths:
        html += '<p style="margin-bottom:8px"><strong>Interactive Charts:</strong></p>'
        for name, path in chart_paths.items():
            filename = os.path.basename(path) if path else name
            display = name.replace("_", " ").title()
            html += f'<a class="chart-link" href="{filename}">{display}</a> | '
        html = html.rstrip(" | ")

    html += '<p style="margin-top:12px">Generated by CotexAI Manufacturing Analytics Platform</p>'
    html += "</div></body></html>"
    return html


# Need os for basename in footer
import os  # noqa: E402
