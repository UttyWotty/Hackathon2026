"""
Risk Tower analysis tool for the agent's sense sweep.

Exposes analysis/runrate/core/risk_tower.py, which was previously reachable
only as a worksheet inside the run rate Excel report. It is the detector for
declining stability, frequent stops and long repairs across a rolling window.

Author: Utku Gulbardak
Date: 2026-07-21
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from analysis.runrate.core import preprocess_data, process_shots
from analysis.runrate.core.data_loader import load_data
from analysis.runrate.core.risk_tower import (
    HIGH_MTTR_MULTIPLIER,
    LOW_MTBF_MULTIPLIER,
    calculate_risk_tower,
)

logger = logging.getLogger(__name__)

# Rolling window, in weeks. Four matches the Risk Tower worksheet's own default
# and needs at least two distinct weeks of data to compute a trend.
DEFAULT_WEEKS = 4

STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Grouping keys for session analysis, as the run rate api uses.
SESSION_GROUP_KEYS = ["EQUIPMENT_CODE", "SESSION_ID"]

# Risk Tower emits upper-case column names; the other analytics tools return
# lower-case keys, and the sense summariser reads equipment_code.
COLUMN_RENAMES = {
    "EQUIPMENT_CODE": "equipment_code",
    "STABILITY_INDEX": "stability_index",
    "FIRST_WEEK_STABILITY": "first_week_stability",
    "LAST_WEEK_STABILITY": "last_week_stability",
    "IS_DECLINING": "is_declining",
    "RISK_SCORE": "risk_score",
    "PRIMARY_RISK_FACTOR": "primary_risk_factor",
    "RAG_STATUS": "rag_status",
    "MTTR": "mttr_minutes",
    "MTBF": "mtbf_minutes",
    "STOP_EVENTS": "stop_events",
}


def _process_sessions(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Run the shot data through preprocessing and session analysis.

    Mirrors the run rate api's pipeline, which is what Risk Tower expects as
    input; it operates on session metrics, not raw shots.

    Args:
        frame: Raw shot rows from the run rate loader.

    Returns:
        The processed frame with session and stop columns.
    """
    preprocessed = preprocess_data(frame)
    try:
        return (
            preprocessed.groupby(SESSION_GROUP_KEYS, group_keys=False)
            .apply(process_shots, include_groups=False)
            .reset_index(drop=True)
        )
    except TypeError:
        # Older pandas does not accept include_groups.
        return (
            preprocessed.groupby(SESSION_GROUP_KEYS, group_keys=False)
            .apply(process_shots)
            .reset_index(drop=True)
        )


def _fleet_average(
    rows: List[Dict[str, Any]], key: str, exclude: Optional[str] = None
) -> float:
    """
    Mean of a metric across the other machines.

    The comparison is leave-one-out: a machine is judged against its peers, not
    against a fleet average it is itself dragging. This matches how the dataset
    contract defines the thresholds in synthetic_data/tests/test_planted_defects.

    Args:
        rows: Per-equipment rows.
        key: Metric to average.
        exclude: Equipment code to leave out. Defaults to None.

    Returns:
        The mean over positive values, or 0.0 when there are none.
    """
    values = [
        row[key]
        for row in rows
        if row.get("equipment_code") != exclude
        and isinstance(row.get(key), (int, float))
        and row[key] > 0
    ]
    return sum(values) / len(values) if values else 0.0


def _add_fleet_ratios(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add fleet-relative MTTR and MTBF ratios, and the outlier flags they imply.

    get_primary_risk_factor only tests these ratios when stability is already
    below 70, so a machine with long repairs but decent stability is reported
    as Stable and its defect never surfaces. The ratios are computed here, in
    the tool layer, rather than by changing that function's documented
    priority order, which other callers rely on.

    Args:
        rows: Per-equipment Risk Tower rows.

    Returns:
        The same rows with ratio and flag fields added.
    """
    for row in rows:
        code = row.get("equipment_code")
        avg_mttr = _fleet_average(rows, "mttr_minutes", exclude=code)
        avg_mtbf = _fleet_average(rows, "mtbf_minutes", exclude=code)

        mttr = row.get("mttr_minutes") or 0
        mtbf = row.get("mtbf_minutes") or 0
        row["mttr_vs_peers"] = round(mttr / avg_mttr, 2) if avg_mttr else None
        row["mtbf_vs_peers"] = round(mtbf / avg_mtbf, 2) if avg_mtbf else None
        row["high_mttr"] = bool(avg_mttr and mttr > HIGH_MTTR_MULTIPLIER * avg_mttr)
        row["frequent_stops"] = bool(
            avg_mtbf and 0 < mtbf < LOW_MTBF_MULTIPLIER * avg_mtbf
        )
    return rows


def _summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate the per-equipment rows into headline counts."""
    by_status: Dict[str, int] = {}
    for row in rows:
        status = str(row.get("rag_status", "unknown"))
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "total_equipment": len(rows),
        "declining_equipment": [
            r["equipment_code"] for r in rows if r.get("is_declining")
        ],
        "high_mttr_equipment": [
            r["equipment_code"] for r in rows if r.get("high_mttr")
        ],
        "frequent_stops_equipment": [
            r["equipment_code"] for r in rows if r.get("frequent_stops")
        ],
        "rag_distribution": by_status,
    }


async def run_risk_tower_analysis(
    equipment_codes: Optional[list] = None,
    supplier_names: Optional[list] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    weeks: int = DEFAULT_WEEKS,
) -> Dict[str, Any]:
    """
    Score equipment risk over a rolling multi-week window.

    Detects three failure modes a single-period average hides: stability that
    is declining week over week, abnormally frequent stops (low MTBF), and
    abnormally long repairs (high MTTR).

    Args:
        equipment_codes: Equipment to include. Defaults to None, meaning all.
        supplier_names: Supplier filter. Defaults to None, meaning all.
        start_date: Optional lower date bound as 'YYYY-MM-DD'.
        end_date: Optional upper date bound as 'YYYY-MM-DD'.
        weeks: Rolling window length. Defaults to 4.

    Returns:
        A dict with status, per-equipment metrics and a summary. On failure,
        status is error and the reason is in the error key.
    """
    try:
        single_equipment = (
            equipment_codes[0]
            if equipment_codes and len(equipment_codes) == 1
            else None
        )
        supplier = supplier_names[0] if supplier_names else None

        frame = load_data(
            supplier=supplier,
            equipment_code=single_equipment,
            start_date=start_date,
            end_date=end_date,
        )
        if frame.empty:
            return {
                "status": STATUS_SUCCESS,
                "metrics": [],
                "summary": {},
                "message": "No shot data matched the filters.",
            }

        processed = _process_sessions(frame)
        tower = calculate_risk_tower(processed, weeks=weeks)

        if tower.empty:
            return {
                "status": STATUS_SUCCESS,
                "metrics": [],
                "summary": {},
                "message": f"Not enough history for a {weeks}-week risk window.",
            }

        if equipment_codes and len(equipment_codes) > 1:
            tower = tower[tower["EQUIPMENT_CODE"].isin(equipment_codes)]

        renamed = tower.rename(columns=COLUMN_RENAMES)
        rows = renamed.to_dict(orient="records")
        rows = [
            {
                key: (value.item() if hasattr(value, "item") else value)
                for key, value in row.items()
            }
            for row in rows
        ]

        rows = _add_fleet_ratios(rows)

        return {
            "status": STATUS_SUCCESS,
            "metrics": rows,
            "summary": _summarize(rows),
            "weeks": weeks,
            "message": f"Risk Tower computed for {len(rows)} equipment.",
        }

    except Exception as exc:  # noqa: BLE001 - reported to the caller as status
        logger.exception("Risk Tower analysis failed")
        return {
            "status": STATUS_ERROR,
            "error": str(exc),
            "metrics": [],
            "summary": {},
            "message": f"Risk Tower analysis failed: {exc}",
        }
