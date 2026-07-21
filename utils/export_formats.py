"""
Export helpers for common response formats.

This module provides small utilities to export simple data structures (dicts)
to CSV in a predictable, stable way.

We intentionally keep this minimal; complex exports should live next to the
analysis modules (e.g., ROI can export its own detailed tables).
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, Iterable, Tuple


def dict_to_two_column_csv(data: Dict[str, Any]) -> str:
    """
    Convert a dictionary into a stable two-column CSV (key,value).

    Args:
        data: Dictionary to serialize.

    Returns:
        CSV string with header row.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["key", "value"])
    for key in sorted(data.keys()):
        writer.writerow([key, data[key]])
    return output.getvalue()


def rows_to_csv(rows: Iterable[Dict[str, Any]], *, fieldnames: Tuple[str, ...]) -> str:
    """
    Serialize rows (list of dicts) to CSV with explicit fieldnames.

    Args:
        rows: Iterable of row dictionaries.
        fieldnames: Field order to write.

    Returns:
        CSV string.
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()
