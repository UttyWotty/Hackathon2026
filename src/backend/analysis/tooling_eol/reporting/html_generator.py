"""
Tooling EOL HTML Report Generator.

This module handles generation of HTML reports for tooling end-of-life predictions.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

# Configure logging
logger = logging.getLogger(__name__)


# ==================== HTML Generation ==================== #


def wrap_table_in_html(
    table_html: str, title: str = "Tooling End-of-Life Predictions"
) -> str:
    """Wrap a table HTML string in a minimal, styled HTML document.

    Args:
        table_html: HTML table markup (e.g., from pandas.DataFrame.to_html).
        title: Document title.

    Returns:
        str: Complete HTML document string.
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 16px; color: #2c3e50; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 12px; }}
    .table-container {{ overflow-x: auto; background: #fff; border-radius: 8px; border: 1px solid #e0e0e0; padding: 12px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
    thead th {{ position: sticky; top: 0; background: #f5f7fb; border-bottom: 1px solid #dfe3ea; text-align: left; padding: 8px; }}
    tbody td {{ border-bottom: 1px solid #f0f2f5; padding: 8px; }}
    tr:nth-child(even) td {{ background: #fafbfe; }}
    .number {{ text-align: right; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <div class="table-container">{table_html}</div>
</body>
</html>
"""


def generate_html_report(
    predictions_df: pd.DataFrame,
    output_path: Optional[str] = None,
    title: str = "Tooling End-of-Life Predictions",
) -> str:
    """Generate an HTML report from predictions DataFrame.

    Args:
        predictions_df: DataFrame with EOL predictions
        output_path: Optional path to save HTML file
        title: Report title

    Returns:
        str: Complete HTML document string
    """
    # Render table HTML (keep index off for clean UI)
    table_html = predictions_df.to_html(index=False, border=0, classes="dataframe")
    html_doc = wrap_table_in_html(table_html, title=title)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_doc)
        logger.info(f"Saved HTML report to {output_path}")

    return html_doc
