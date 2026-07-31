"""
HTML report generation for Capacity Analysis.

This module provides HTML documentation generation for capacity/OEE analysis:
- Sales-friendly documentation explaining columns and metrics
- Technical formulas documentation for data analysts
- HTML dashboards with interactive visualizations (use /visualization endpoints)

Author: Utku Gulbardak
Date: 2025-10-27
"""

from typing import Optional

import pandas as pd  # type: ignore[import-untyped]


def generate_sales_doc_daily(
    daily: pd.DataFrame,
    equipment_code: str,
    supplier_name: Optional[str],
    start: Optional[str],
    end: Optional[str],
    output_path: str,
) -> None:
    """
    Generate a sales-friendly HTML explaining the daily analysis and columns.

    Creates a clean, professional HTML document that explains what each
    metric means in business terms.

    Args:
        daily: DataFrame with daily aggregated metrics
        equipment_code: Equipment identifier
        supplier_name: Supplier name (optional)
        start: Start date (YYYY-MM-DD) - inferred from data if None
        end: End date (YYYY-MM-DD) - inferred from data if None
        output_path: Output HTML file path

    Example:
        >>> generate_sales_doc_daily(
        ...     daily_df,
        ...     "MX-7102",
        ...     "Vantis industries",
        ...     "2025-01-01",
        ...     "2025-12-31",
        ...     "sales_notes.html"
        ... )
    """
    if not start and not end and not daily.empty:
        try:
            start = str(pd.to_datetime(daily["DAY"].min()).date())
            end = str(pd.to_datetime(daily["DAY"].max()).date())
        except Exception:
            pass

    column_explanations = {
        "DAY": "Calendar day of production.",
        "EQUIPMENT_CODE": "Equipment identifier used for the analysis.",
        "CAVITY_COUNT": "Number of cavities (parts per shot) for this equipment.",
        "VALID_SHOTS": "Valid shots (CT ≠ 999.9) before cavity multiplication.",
        "ACTUAL_OUTPUT": "Count of shots*cavities where ACTUAL_CT != 999.9. Multi-cavity support: 1 shot = N parts.",
        "OPTIMAL_OUTPUT": "(TOTAL_RUN_SEC / APPROVED_CT_SEC) × OEE_TARGET × cavity count. Theoretical output at target OEE level.",
        "GAP": "Optimal Output - Actual Output. Total shortfall between optimal and actual.",
        "PERFORMANCE_LOSS": "(PRODUCTION_TIME_SEC / APPROVED_CT_SEC) - ACTUAL_OUTPUT. Parts lost due to slow cycle times. Can be negative (overperformance).",
        "AVAILABILITY_LOSS": "DOWNTIME_SEC / APPROVED_CT_SEC × cavity count. Parts lost due to downtime.",
        "TOTAL_RUN_SEC": "Session duration (last shot time - first shot time) + mode cycle time.",
        "PRODUCTION_TIME_SEC": "Time spent producing (sum of normal intervals; if last interval is normal, add one mode cycle).",
        "IDEAL_PRODUCTION_TIME_SEC": "Time production should have taken at ideal cycle time (Valid Shots × Mode CT).",
        "EXTRA_TIME_SLOW_CYCLES_SEC": "Extra time spent due to slow cycles (Actual Production Time - Ideal Production Time using Mode CT).",
        "DOWNTIME_SEC": "TOTAL_RUN_SEC - PRODUCTION_TIME_SEC. Non-production time in the session.",
        "MODE_CT_SEC": "Mode of shot-to-shot intervals (seconds) used for stop detection.",
        "APPROVED_CT_SEC": "First positive APPROVED_CT from data (constant); fallback to mode cycle time if missing.",
        "TOTAL_SHOTS_ALL": "Total number of shots (1 shot = 1 part).",
        "INVALID_999_SHOTS": "Shots with CT = 999.9 (not counted as output).",
        # OEE Components
        "PLANNED_PRODUCTION_TIME_SEC": "Planned production time (Sum of actual runtime across all production days).",
        "RUN_TIME_SEC": "Session duration (excludes breaks > 8 hours / session ends midnight).",
        "AVAILABILITY": "RUN_TIME_SEC / PLANNED_PRODUCTION_TIME_SEC (0-1).",
        "PERFORMANCE": "(APPROVED_CT_SEC × TOTAL_SHOTS_ALL) / RUN_TIME_SEC (0-1).",
        "QUALITY": "TARGET_OEE / (AVAILABILITY × PERFORMANCE) (reverse-engineered from 50% to 100% targets).",
        "OEE_SCORE": "AVAILABILITY × PERFORMANCE × QUALITY (0-1). Overall Equipment Effectiveness.",
        "TARGET_OEE": "Target OEE value (0.50 to 1.00 = 50% to 100%).",
        "QUALITY_PARTS": "QUALITY × TOTAL_SHOTS_ALL (estimated good parts).",
        # Optimal Output at different OEE levels
        "OPTIMAL_OUTPUT_100_OEE": "PLANNED_PRODUCTION_TIME_SEC / APPROVED_CT_SEC × cavity count. Optimal output at 100% OEE.",
        "OPTIMAL_OUTPUT_TARGET_OEE": "OPTIMAL_OUTPUT_100_OEE × target OEE. Optimal output at target OEE level.",
    }

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Daily Analysis — Sales Notes</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f7f9fb; color: #0f172a; }}
    .card {{ background: #fff; border: 1px solid #e1e5ea; border-radius: 10px; padding: 18px; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 12px 0; color: #1f4e79; }}
    h2 {{ margin: 0 0 10px 0; color: #1f4e79; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; }}
    th {{ background: #eef2f5; }}
    .muted {{ color: #475569; font-size: 13px; }}
    .code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }}
  </style>
 </head>
 <body>
   <div class="card">
     <h1>Daily Analysis — Sales Notes</h1>
     <p class="muted">How to read the daily output and what each column means.</p>
     <p class="muted">Equipment: <b>{equipment_code}</b> | Supplier: <b>{supplier_name}</b> | Date range: <b>{start}</b> → <b>{end}</b></p>
   </div>

   <div class="card">
     <h2>Columns</h2>
     <table>
       <tr><th>Column</th><th>Meaning</th></tr>
"""

    for col, desc in column_explanations.items():
        html += (
            '       <tr><td><span class="code">'
            + str(col)
            + "</span></td><td>"
            + str(desc)
            + "</td></tr>\n"
        )

    html += """
     </table>
     <p class="muted">We split the shortfall (Δ) between CT Loss and Break Loss. Hover the chart for exact counts.</p>
   </div>

 </body>
 </html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def generate_formulas_doc_daily(
    equipment_code: str,
    approved_ct_sec: Optional[float],
    output_path: str,
) -> None:
    """
    Generate an HTML file documenting the formulas used in daily analysis.

    Creates a technical reference document with all formula definitions.
    Includes variable definitions and formulas for:
    - Actual Production Output
    - Slow Cycle Time Loss (CT Loss)
    - Downtime Loss (Break Loss)
    - OEE Components (Availability, Performance, Quality)
    - Optimal Output calculations

    Args:
        equipment_code: Equipment identifier
        approved_ct_sec: Approved cycle time in seconds (or None)
        output_path: Output HTML file path

    Example:
        >>> generate_formulas_doc_daily(
        ...     "MX-7102",
        ...     96.0,
        ...     "formulas_doc.html"
        ... )
    """
    approved_ct_display = (
        f"{approved_ct_sec:.2f} sec" if approved_ct_sec is not None else "Not available"
    )

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Daily Analysis — Formulas</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f7f9fb; color: #0f172a; }}
    .card {{ background: #fff; border: 1px solid #e1e5ea; border-radius: 10px; padding: 18px; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 12px 0; color: #1f4e79; }}
    h2 {{ margin: 0 0 10px 0; color: #1f4e79; }}
    code, .code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }}
    ul {{ margin-top: 8px; }}
    li {{ margin: 6px 0; }}
  </style>
 </head>
 <body>
   <div class="card">
     <h1>Daily Analysis — Formulas</h1>
     <div>Equipment: <b>{equipment_code}</b></div>
     <div>Approved CT (constant): <b>{approved_ct_display}</b></div>
   </div>

   <div class="card">
     <h2>Variables</h2>
     <ul>
       <li><span class="code">TOTAL_RUN_SEC</span>: (last shot time − first shot time) + mode cycle time</li>
       <li><span class="code">PRODUCTION_TIME_SEC</span>: sum of normal intervals; if last interval is normal, add one mode cycle</li>
       <li><span class="code">DOWNTIME_SEC</span>: <span class="code">TOTAL_RUN_SEC</span> − <span class="code">PRODUCTION_TIME_SEC</span></li>
       <li><span class="code">APPROVED_CT_SEC</span>: first positive <span class="code">APPROVED_CT</span> from data (constant); fallback to mode cycle time if missing</li>
       <li><span class="code">ACTUAL_OUTPUT</span>: count of shots*cavities where <span class="code">ACTUAL_CT != 999.9</span></li>
       <li><span class="code">CAVITY_COUNT</span>: parts per shot for this equipment (from mapping table)</li>
       <li><span class="code">PLANNED_PRODUCTION_TIME_SEC</span>: Sum of actual runtime across all production days (realistic planning)</li>
       <li><span class="code">RUN_TIME_SEC</span>: session duration (excludes breaks > 8 hours / session ends midnight)</li>
       <li><span class="code">TOTAL_SHOTS_ALL</span>: total number of shots (1 shot = 1 part)</li>
     </ul>
   </div>

   <div class="card">
     <h2>Production Output Formulas</h2>
     <ul>
       <li><b>Actual Output</b>: <span class="code">VALID_SHOTS × CAVITY_COUNT</span></li>
       <li><b>Optimal Output</b>: <span class="code">(TOTAL_RUN_SEC / APPROVED_CT_SEC) × OEE_TARGET × CAVITY_COUNT</span></li>
       <li><b>Availability Loss</b>: <span class="code">(DOWNTIME_SEC / APPROVED_CT_SEC) × CAVITY_COUNT</span></li>
       <li><b>Performance Loss</b>: <span class="code">(PRODUCTION_TIME_SEC / APPROVED_CT_SEC) − ACTUAL_OUTPUT</span> (can be negative for overperformance)</li>
       <li><b>Gap</b>: <span class="code">Optimal Output − Actual Output</span></li>
     </ul>
   </div>

   <div class="card">
     <h2>OEE (Overall Equipment Effectiveness) Formulas</h2>
     <ul>
       <li><b>Availability</b>: <span class="code">RUN_TIME_SEC / PLANNED_PRODUCTION_TIME_SEC</span> (0-1)</li>
       <li><b>Performance</b>: <span class="code">(APPROVED_CT_SEC × TOTAL_SHOTS_ALL) / RUN_TIME_SEC</span> (0-1)</li>
       <li><b>Quality</b>: <span class="code">TARGET_OEE / (AVAILABILITY × PERFORMANCE)</span> (reverse-engineered from 50% to 100% targets)</li>
       <li><b>OEE Score</b>: <span class="code">AVAILABILITY × PERFORMANCE × QUALITY</span> (0-1)</li>
       <li><b>Quality Parts</b>: <span class="code">QUALITY × TOTAL_SHOTS_ALL</span> (estimated good parts)</li>
       <li><b>Optimal Output at 100% OEE</b>: <span class="code">(PLANNED_PRODUCTION_TIME_SEC / APPROVED_CT_SEC) × CAVITY_COUNT</span></li>
       <li><b>Optimal Output at X% OEE</b>: <span class="code">OPTIMAL_OUTPUT_100_OEE × X%</span> (50% to 100% of 100% OEE optimal output)</li>
     </ul>
     <p><em>Note: Quality component is reverse-engineered from target OEE (50% to 100%) since quality data is not available.</em></p>
     <p><em>Optimal Output calculations use dynamic planned production time based on sum of actual runtime across all production days.</em></p>
     <p><em>Cavity Factor: Output calculations include cavity count multiplier for multi-cavity molds. Performance calculations use shots to maintain accuracy.</em></p>
   </div>

 </body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
