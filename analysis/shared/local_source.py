"""
Local CSV data source standing in for Snowflake during development.

Serves MASTER_SHOT_TABLE rows from the synthetic generator's output so the
sense tools, and the autonomous controller above them, can run with no
Snowflake account. Activated only when LOCAL_DATA_DIR is set, so production
paths are untouched by its presence.
"""

import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

import pandas as pd

from analysis.shared.shot_filters import (
    COL_APPROVED_CT,
    COL_CT,
    COL_EQUIPMENT,
    COL_SHOT_TIME,
    COL_SUPPLIER,
    COL_VOLUME,
    MAX_VALID_CT,
    START_OF_DAY,
    apply_runrate_date_filter,
    apply_runrate_validity_filter,
    filter_shots,
)

logger = logging.getLogger(__name__)

# Directory holding the generator's CSV output. Empty means "use Snowflake",
# which is the default and the only behaviour in production.
LOCAL_DATA_DIR = os.getenv("LOCAL_DATA_DIR", "")

MASTER_SHOT_TABLE_FILE = "MASTER_SHOT_TABLE.csv"
GROUND_TRUTH_FILE = "ground_truth.json"

# The run rate query projects and renames CT; downstream code reads ACTUAL_CT.
RUNRATE_CT_ALIAS = "ACTUAL_CT"
RUNRATE_COLUMNS = [COL_SUPPLIER, COL_EQUIPMENT, COL_SHOT_TIME, COL_CT, COL_APPROVED_CT]

# Sentinel meaning "every supplier" in the run rate API.
SUPPLIER_ALL = "All"

# Columns the CT efficiency query projects. No renaming, unlike run rate.
EFFICIENCY_COLUMNS = [
    COL_SUPPLIER,
    COL_CT,
    COL_APPROVED_CT,
    COL_EQUIPMENT,
    "TOOLING_TYPE",
    COL_SHOT_TIME,
    "PART_ID",
    "PART_NAME",
]


class LocalDataError(Exception):
    """Raised when the local dataset is requested but unusable."""


def is_local_data_enabled() -> bool:
    """
    Report whether the local CSV source should be used instead of Snowflake.

    Returns:
        True when LOCAL_DATA_DIR is set to a non-empty path.
    """
    return bool(LOCAL_DATA_DIR)


@lru_cache(maxsize=1)
def load_master_shot_table(data_dir: str = "") -> pd.DataFrame:
    """
    Read MASTER_SHOT_TABLE.csv into a DataFrame, cached for the process.

    The file is roughly 50 MB and 230,000 rows, so it is parsed once and
    reused. LOCAL_SHOT_TIME is parsed to datetime to match the Snowflake
    column type that downstream analysis assumes.

    Args:
        data_dir: Directory holding the CSVs. Defaults to "" meaning
            LOCAL_DATA_DIR.

    Returns:
        The full shot table.

    Raises:
        LocalDataError: If no directory is configured or the file is absent.
    """
    directory = data_dir or LOCAL_DATA_DIR
    if not directory:
        raise LocalDataError(
            "No local data directory. Set LOCAL_DATA_DIR to the generator's "
            "output, for example ./synthetic_out."
        )

    path = os.path.join(directory, MASTER_SHOT_TABLE_FILE)
    if not os.path.exists(path):
        raise LocalDataError(
            f"{path} not found. Generate it with: "
            f"python -m synthetic_data.generate --output-dir {directory}"
        )

    frame = pd.read_csv(path, parse_dates=[COL_SHOT_TIME])
    logger.info("Loaded %d local shot rows from %s", len(frame), path)
    return frame


def load_ground_truth(data_dir: str = "") -> Dict[str, Any]:
    """
    Read the dataset's ground_truth.json contract.

    Args:
        data_dir: Directory holding the generator output. Defaults to ""
            meaning LOCAL_DATA_DIR.

    Returns:
        The parsed contract declaring every planted defect and control.

    Raises:
        LocalDataError: If no directory is configured or the file is absent.
    """
    directory = data_dir or LOCAL_DATA_DIR
    if not directory:
        raise LocalDataError(
            "No local data directory. Set LOCAL_DATA_DIR to the generator's output."
        )

    path = os.path.join(directory, GROUND_TRUTH_FILE)
    if not os.path.exists(path):
        raise LocalDataError(
            f"{path} not found. Generate it with: "
            f"python -m synthetic_data.generate --output-dir {directory}"
        )

    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def query_shots(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    equipment_codes: Optional[List[str]] = None,
    supplier_names: Optional[List[str]] = None,
    validity: bool = True,
    data_dir: str = "",
) -> pd.DataFrame:
    """
    Return filtered shot rows, the local equivalent of a MASTER_SHOT_TABLE query.

    Args:
        start_date: Inclusive lower date bound. Defaults to None.
        end_date: Inclusive upper date bound. Defaults to None.
        equipment_codes: Equipment codes to keep. Defaults to None (all).
        supplier_names: Supplier names to keep. Defaults to None (all).
        validity: Drop invalid cycle times. Defaults to True.
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        A filtered copy of the shot table, ordered by LOCAL_SHOT_TIME.
    """
    frame = load_master_shot_table(data_dir)
    return filter_shots(
        frame,
        start_date=start_date,
        end_date=end_date,
        equipment_codes=equipment_codes,
        supplier_names=supplier_names,
        validity=validity,
    )


def query_runrate_shots(
    supplier: Optional[str] = None,
    equipment_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    data_dir: str = "",
) -> pd.DataFrame:
    """
    Return shot rows shaped exactly as the run rate query returns them.

    Applies the run rate predicates rather than the cycle time ones, projects
    the five columns the query selects, and renames CT to ACTUAL_CT.

    Args:
        supplier: Supplier name, or "All"/None for every supplier.
        equipment_code: Single equipment code, or None for all.
        start_date: Inclusive lower bound as 'YYYY-MM-DD'. Defaults to None.
        end_date: Inclusive upper bound as 'YYYY-MM-DD'. Defaults to None.
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        Columns SUPPLIER_NAME, EQUIPMENT_CODE, LOCAL_SHOT_TIME, ACTUAL_CT,
        APPROVED_CT.
    """
    frame = apply_runrate_validity_filter(load_master_shot_table(data_dir))

    if supplier and supplier != SUPPLIER_ALL:
        frame = frame[frame[COL_SUPPLIER] == supplier]
    if equipment_code:
        frame = frame[frame[COL_EQUIPMENT] == equipment_code]

    frame = apply_runrate_date_filter(frame, start_date, end_date)
    projected = frame[RUNRATE_COLUMNS].rename(columns={COL_CT: RUNRATE_CT_ALIAS})
    return projected.reset_index(drop=True)


def query_efficiency_shots(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    supplier_names: Optional[List[str]] = None,
    data_dir: str = "",
) -> pd.DataFrame:
    """
    Return shot rows shaped as the CT efficiency query returns them.

    Note the end bound: this query compares LOCAL_SHOT_TIME against the bare
    end date, which is midnight, so the end day is almost entirely excluded.
    That is the query's actual behaviour and is reproduced rather than fixed.

    Args:
        start_date: Inclusive lower bound as 'YYYY-MM-DD'. Defaults to None.
        end_date: Upper bound as 'YYYY-MM-DD', compared at midnight.
        supplier_names: Supplier names to keep. Defaults to None (all).
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        The eight columns the efficiency query selects.
    """
    frame = filter_shots(
        load_master_shot_table(data_dir),
        start_date=start_date,
        end_date=end_date,
        supplier_names=supplier_names,
        end_time=START_OF_DAY,
    )
    return frame[EFFICIENCY_COLUMNS].reset_index(drop=True)


def query_capacity_shots(
    equipment_code: str,
    supplier_name: Optional[str] = None,
    supplier_like: Optional[str] = None,
    start_ts: Optional[pd.Timestamp] = None,
    end_ts: Optional[pd.Timestamp] = None,
    data_dir: str = "",
) -> pd.DataFrame:
    """
    Return shot rows shaped as the capacity query returns them.

    Capacity uses a third date convention: the end timestamp is exclusive of
    the following midnight, so the whole end day is included. Supplier matching
    is case-insensitive equality, or a substring match via supplier_like.

    Args:
        equipment_code: Equipment code to fetch. Required, as in the query.
        supplier_name: Case-insensitive exact supplier match. Defaults to None.
        supplier_like: Case-insensitive substring match, used only when
            supplier_name is absent. Defaults to None.
        start_ts: Inclusive lower timestamp bound. Defaults to None.
        end_ts: Date whose whole day is included. Defaults to None.
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        The five columns the capacity query selects, with CT as ACTUAL_CT.
    """
    frame = load_master_shot_table(data_dir)
    frame = frame[
        frame[COL_SHOT_TIME].notna()
        & (frame[COL_EQUIPMENT] == equipment_code)
        & (frame[COL_CT] < MAX_VALID_CT)
        & (frame[COL_VOLUME] > 0)
    ]

    if supplier_name:
        frame = frame[frame[COL_SUPPLIER].str.upper() == supplier_name.upper()]
    elif supplier_like:
        frame = frame[
            frame[COL_SUPPLIER].str.contains(supplier_like, case=False, na=False)
        ]

    if start_ts is not None:
        frame = frame[frame[COL_SHOT_TIME] >= pd.to_datetime(start_ts)]
    if end_ts is not None:
        frame = frame[
            frame[COL_SHOT_TIME] < pd.to_datetime(end_ts) + pd.Timedelta(days=1)
        ]

    projected = frame[RUNRATE_COLUMNS].rename(columns={COL_CT: RUNRATE_CT_ALIAS})
    return projected.reset_index(drop=True)


# ==================== Reference table loaders ==================== #

MOLD_FILE = "MOLD.csv"
WORK_ORDER_FILE = "WORK_ORDER.csv"


@lru_cache(maxsize=1)
def load_mold_csv(data_dir: str = "") -> pd.DataFrame:
    """
    Read MOLD.csv into a DataFrame, cached for the process.

    Args:
        data_dir: Directory holding the CSVs. Defaults to "" meaning LOCAL_DATA_DIR.

    Returns:
        The mold reference table.

    Raises:
        LocalDataError: If no directory is configured or the file is absent.
    """
    directory = data_dir or LOCAL_DATA_DIR
    if not directory:
        raise LocalDataError("No local data directory configured.")

    path = os.path.join(directory, MOLD_FILE)
    if not os.path.exists(path):
        raise LocalDataError(
            f"{path} not found. Generate with: "
            f"python -m synthetic_data.generate --output-dir {directory}"
        )

    frame = pd.read_csv(path)
    frame.columns = [str(c).upper() for c in frame.columns]
    logger.info("Loaded %d mold rows from %s", len(frame), path)
    return frame


@lru_cache(maxsize=1)
def load_work_order_csv(data_dir: str = "") -> pd.DataFrame:
    """
    Read WORK_ORDER.csv into a DataFrame, cached for the process.

    Args:
        data_dir: Directory holding the CSVs. Defaults to "" meaning LOCAL_DATA_DIR.

    Returns:
        The work order table.

    Raises:
        LocalDataError: If no directory is configured or the file is absent.
    """
    directory = data_dir or LOCAL_DATA_DIR
    if not directory:
        raise LocalDataError("No local data directory configured.")

    path = os.path.join(directory, WORK_ORDER_FILE)
    if not os.path.exists(path):
        raise LocalDataError(
            f"{path} not found. Generate with: "
            f"python -m synthetic_data.generate --output-dir {directory}"
        )

    frame = pd.read_csv(path, parse_dates=["COMPLETED_AT"])
    frame.columns = [str(c).upper() for c in frame.columns]
    logger.info("Loaded %d work order rows from %s", len(frame), path)
    return frame


# ==================== RCA query ==================== #


# Columns the RCA pipeline selects from MASTER_SHOT_TABLE.
RCA_COLUMNS = [
    COL_SUPPLIER, COL_EQUIPMENT, "COUNTER_CODE", COL_CT, COL_APPROVED_CT,
    "TEMPERATURE", "PART_NAME", "TOOLING_TYPE", "CT_STATUS",
    COL_SHOT_TIME, COL_VOLUME, "COUNTER_ID", "MOLD_ID", "COMPANY_ID", "PART_ID",
]


def query_rca_shots(
    equipment_code: Optional[str] = None,
    supplier_name: Optional[str] = None,
    data_dir: str = "",
) -> pd.DataFrame:
    """
    Return shot rows for RCA analysis from local CSV.

    RCA uses minimal filtering: only requires SUPPLIER_NAME and PART_NAME to be
    non-null. No CT validity filter (keeps sentinel values for downtime detection).

    Args:
        equipment_code: Filter to single equipment. Defaults to None (all).
        supplier_name: Filter to single supplier. Defaults to None (all).
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        DataFrame matching the RCA SQL shape, ordered by LOCAL_SHOT_TIME DESC,
        limited to 100000 rows (matching the Snowflake query LIMIT).
    """
    frame = load_master_shot_table(data_dir)
    frame = frame[frame[COL_SUPPLIER].notna() & frame["PART_NAME"].notna()]

    if equipment_code:
        frame = frame[frame[COL_EQUIPMENT] == equipment_code]
    if supplier_name:
        frame = frame[frame[COL_SUPPLIER] == supplier_name]

    # Add TOOLING_FAMILY alias (RCA query does TOOLING_TYPE AS TOOLING_FAMILY)
    result = frame.sort_values(COL_SHOT_TIME, ascending=False).head(100000)
    available_cols = [c for c in RCA_COLUMNS if c in result.columns]
    result = result[available_cols].copy()
    result["TOOLING_FAMILY"] = result["TOOLING_TYPE"]
    return result.reset_index(drop=True)


# ==================== Tooling EOL queries ==================== #


# Columns for tooling EOL shot data.
TOOLING_EOL_COLUMNS = [
    COL_SUPPLIER, COL_EQUIPMENT, "COUNTER_CODE", COL_CT, COL_APPROVED_CT,
    COL_SHOT_TIME, COL_VOLUME, "COUNTER_ID", "MOLD_ID", "COMPANY_ID",
    "PART_ID", "TOOLING_TYPE", "CT_STATUS",
]


def query_tooling_eol_shots(data_dir: str = "") -> pd.DataFrame:
    """
    Return shot rows shaped as tooling EOL's read_master_shot_table returns.

    Applies only the WHERE LOCAL_SHOT_TIME IS NOT NULL filter, adds SHOT_COUNT=1,
    and ensures numeric types match what the EOL pipeline expects.

    Args:
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        DataFrame with EOL columns plus SHOT_COUNT.
    """
    frame = load_master_shot_table(data_dir)
    frame = frame[frame[COL_SHOT_TIME].notna()]

    available_cols = [c for c in TOOLING_EOL_COLUMNS if c in frame.columns]
    result = frame[available_cols].copy()
    result["SHOT_COUNT"] = 1

    for col in ["CT", "APPROVED_CT", "VOLUME", "COUNTER_ID", "MOLD_ID", "COMPANY_ID"]:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    return result.reset_index(drop=True)


def query_tooling_eol_mold(data_dir: str = "") -> pd.DataFrame:
    """
    Return mold reference data shaped as tooling EOL's read_mold_table returns.

    Maps CSV columns to the shape expected: ID->MOLD_ID, plus EQUIPMENT_CODE,
    DESIGNED_SHOT, DAILY_MAX_CAPACITY, PRODUCTION_DAYS, SHIFTS_PER_DAY.

    Args:
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        DataFrame with mold reference columns.
    """
    mold = load_mold_csv(data_dir)

    # Map ID to MOLD_ID if needed
    if "ID" in mold.columns and "MOLD_ID" not in mold.columns:
        mold = mold.rename(columns={"ID": "MOLD_ID"})

    for col in ["MOLD_ID", "DESIGNED_SHOT", "DAILY_MAX_CAPACITY",
                "PRODUCTION_DAYS", "SHIFTS_PER_DAY"]:
        if col in mold.columns:
            mold[col] = pd.to_numeric(mold[col], errors="coerce")

    return mold


def query_tooling_eol_maintenance(data_dir: str = "") -> pd.DataFrame:
    """
    Return maintenance events shaped as tooling EOL's read_maintenance_events returns.

    Reads WORK_ORDER.csv, keeps only completed rows, and returns MOLD_ID,
    EVENT_TS, SOURCE columns.

    Args:
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        DataFrame with columns [MOLD_ID, EVENT_TS, SOURCE].
    """
    wo = load_work_order_csv(data_dir)

    # Filter to completed work orders
    if "STATUS" in wo.columns:
        wo = wo[wo["STATUS"].str.lower() == "completed"]

    # Build output matching read_maintenance_events shape
    if "MOLD_ID" not in wo.columns or "COMPLETED_AT" not in wo.columns:
        return pd.DataFrame(columns=["MOLD_ID", "EVENT_TS", "SOURCE"])

    result = pd.DataFrame({
        "MOLD_ID": pd.to_numeric(wo["MOLD_ID"], errors="coerce"),
        "EVENT_TS": pd.to_datetime(wo["COMPLETED_AT"], errors="coerce"),
        "SOURCE": "WORK_ORDER",
    }).dropna(subset=["MOLD_ID", "EVENT_TS"])

    result["MOLD_ID"] = result["MOLD_ID"].astype(int)
    return result.reset_index(drop=True)
