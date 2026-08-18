"""
Local CSV data source standing in for Snowflake during development.

Serves SHOT_DATA rows from the synthetic generator's output so the
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
    COL_TARGET_DURATION,
    COL_duration,
    COL_EQUIPMENT,
    COL_SHOT_TIME,
    COL_SUPPLIER,
    COL_VOLUME,
    START_OF_DAY,
    filter_shots,
)

logger = logging.getLogger(__name__)

# Directory holding the generator's CSV output. Empty means "use Snowflake",
# which is the default and the only behaviour in production.
LOCAL_DATA_DIR = os.getenv("LOCAL_DATA_DIR", "")

SHOT_DATA_FILE = "SHOT_DATA.csv"
GROUND_TRUTH_FILE = "ground_truth.json"

# Columns the duration efficiency query projects.
EFFICIENCY_COLUMNS = [
    COL_SUPPLIER,
    COL_duration,
    COL_TARGET_DURATION,
    COL_EQUIPMENT,
    "TYPE",
    COL_SHOT_TIME,
    "PRODUCT_ID",
    "PRODUCT_NAME",
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
def load_shot_data(data_dir: str = "") -> pd.DataFrame:
    """
    Read SHOT_DATA.csv into a DataFrame, cached for the process.

    The file is roughly 50 MB and 230,000 rows, so it is parsed once and
    reused. SHOT_TIME is parsed to datetime to match the Snowflake
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

    path = os.path.join(directory, SHOT_DATA_FILE)
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
    machine_ids: Optional[List[str]] = None,
    vendor_names: Optional[List[str]] = None,
    validity: bool = True,
    data_dir: str = "",
) -> pd.DataFrame:
    """
    Return filtered shot rows, the local equivalent of a SHOT_DATA query.

    Args:
        start_date: Inclusive lower date bound. Defaults to None.
        end_date: Inclusive upper date bound. Defaults to None.
        machine_ids: Equipment codes to keep. Defaults to None (all).
        vendor_names: Supplier names to keep. Defaults to None (all).
        validity: Drop invalid durations. Defaults to True.
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        A filtered copy of the shot table, ordered by SHOT_TIME.
    """
    frame = load_shot_data(data_dir)
    return filter_shots(
        frame,
        start_date=start_date,
        end_date=end_date,
        machine_ids=machine_ids,
        vendor_names=vendor_names,
        validity=validity,
    )


def query_efficiency_shots(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    vendor_names: Optional[List[str]] = None,
    data_dir: str = "",
) -> pd.DataFrame:
    """
    Return shot rows shaped as the duration efficiency query returns them.

    Note the end bound: this query compares SHOT_TIME against the bare
    end date, which is midnight, so the end day is almost entirely excluded.
    That is the query's actual behaviour and is reproduced rather than fixed.

    Args:
        start_date: Inclusive lower bound as 'YYYY-MM-DD'. Defaults to None.
        end_date: Upper bound as 'YYYY-MM-DD', compared at midnight.
        vendor_names: Supplier names to keep. Defaults to None (all).
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        The eight columns the efficiency query selects.
    """
    frame = filter_shots(
        load_shot_data(data_dir),
        start_date=start_date,
        end_date=end_date,
        vendor_names=vendor_names,
        end_time=START_OF_DAY,
    )
    return frame[EFFICIENCY_COLUMNS].reset_index(drop=True)


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


# Columns the RCA pipeline selects from SHOT_DATA.
RCA_COLUMNS = [
    COL_SUPPLIER,
    COL_EQUIPMENT,
    "SENSOR_CODE",
    COL_duration,
    COL_TARGET_DURATION,
    "TEMPERATURE",
    "PRODUCT_NAME",
    "TYPE",
    "STATUS",
    COL_SHOT_TIME,
    COL_VOLUME,
    "SENSOR_ID",
    "TOOL_ID",
    "VENDOR_ID",
    "PRODUCT_ID",
]


def query_rca_shots(
    machine_id: Optional[str] = None,
    vendor_name: Optional[str] = None,
    data_dir: str = "",
) -> pd.DataFrame:
    """
    Return shot rows for RCA analysis from local CSV.

    RCA uses minimal filtering: only requires VENDOR_NAME and PRODUCT_NAME to be
    non-null. No CT validity filter (keeps sentinel values for downtime detection).

    Args:
        machine_id: Filter to single equipment. Defaults to None (all).
        vendor_name: Filter to single supplier. Defaults to None (all).
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        DataFrame matching the RCA SQL shape, ordered by SHOT_TIME DESC,
        limited to 100000 rows (matching the Snowflake query LIMIT).
    """
    frame = load_shot_data(data_dir)
    frame = frame[frame[COL_SUPPLIER].notna() & frame["PRODUCT_NAME"].notna()]

    if machine_id:
        frame = frame[frame[COL_EQUIPMENT] == machine_id]
    if vendor_name:
        frame = frame[frame[COL_SUPPLIER] == vendor_name]

    # Add TYPE alias (RCA query does TYPE AS TYPE)
    result = frame.sort_values(COL_SHOT_TIME, ascending=False).head(100000)
    available_cols = [c for c in RCA_COLUMNS if c in result.columns]
    result = result[available_cols].copy()
    result["TYPE"] = result["TYPE"]
    return result.reset_index(drop=True)


# ==================== Tooling EOL queries ==================== #


# Columns for tooling EOL shot data.
TOOLING_EOL_COLUMNS = [
    COL_SUPPLIER,
    COL_EQUIPMENT,
    "SENSOR_CODE",
    COL_duration,
    COL_TARGET_DURATION,
    COL_SHOT_TIME,
    COL_VOLUME,
    "SENSOR_ID",
    "TOOL_ID",
    "VENDOR_ID",
    "PRODUCT_ID",
    "TYPE",
    "STATUS",
]


def query_tooling_eol_shots(data_dir: str = "") -> pd.DataFrame:
    """
    Return shot rows shaped as tooling EOL's read_shot_data returns.

    Applies only the WHERE SHOT_TIME IS NOT NULL filter, adds SHOT_COUNT=1,
    and ensures numeric types match what the EOL pipeline expects.

    Args:
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        DataFrame with EOL columns plus SHOT_COUNT.
    """
    frame = load_shot_data(data_dir)
    frame = frame[frame[COL_SHOT_TIME].notna()]

    available_cols = [c for c in TOOLING_EOL_COLUMNS if c in frame.columns]
    result = frame[available_cols].copy()
    result["SHOT_COUNT"] = 1

    for col in ["DURATION", "TARGET_DURATION", "VOLUME", "SENSOR_ID", "TOOL_ID", "VENDOR_ID"]:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    return result.reset_index(drop=True)


def query_tooling_eol_mold(data_dir: str = "") -> pd.DataFrame:
    """
    Return mold reference data shaped as tooling EOL's read_tool_table returns.

    Maps CSV columns to the shape expected: ID->TOOL_ID, plus MACHINE_ID,
    DESIGNED_SHOT, MAX_DAILY_OUTPUT, PRODUCTION_DAYS, SHIFTS_PER_DAY.

    Args:
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        DataFrame with mold reference columns.
    """
    mold = load_mold_csv(data_dir)

    # Map ID to TOOL_ID if needed
    if "ID" in mold.columns and "TOOL_ID" not in mold.columns:
        mold = mold.rename(columns={"ID": "TOOL_ID"})

    for col in [
        "TOOL_ID",
        "DESIGNED_SHOT",
        "MAX_DAILY_OUTPUT",
        "PRODUCTION_DAYS",
        "SHIFTS_PER_DAY",
    ]:
        if col in mold.columns:
            mold[col] = pd.to_numeric(mold[col], errors="coerce")

    return mold


def query_tooling_eol_maintenance(data_dir: str = "") -> pd.DataFrame:
    """
    Return maintenance events shaped as tooling EOL's read_maintenance_events returns.

    Reads WORK_ORDER.csv, keeps only completed rows, and returns TOOL_ID,
    EVENT_TS, SOURCE columns.

    Args:
        data_dir: Override the configured directory. Defaults to "".

    Returns:
        DataFrame with columns [TOOL_ID, EVENT_TS, SOURCE].
    """
    wo = load_work_order_csv(data_dir)

    # Filter to completed work orders
    if "STATUS" in wo.columns:
        wo = wo[wo["STATUS"].str.lower() == "completed"]

    # Build output matching read_maintenance_events shape
    if "TOOL_ID" not in wo.columns or "COMPLETED_AT" not in wo.columns:
        return pd.DataFrame(columns=["TOOL_ID", "EVENT_TS", "SOURCE"])

    result = pd.DataFrame(
        {
            "TOOL_ID": pd.to_numeric(wo["TOOL_ID"], errors="coerce"),
            "EVENT_TS": pd.to_datetime(wo["COMPLETED_AT"], errors="coerce"),
            "SOURCE": "WORK_ORDER",
        }
    ).dropna(subset=["TOOL_ID", "EVENT_TS"])

    result["TOOL_ID"] = result["TOOL_ID"].astype(int)
    return result.reset_index(drop=True)
