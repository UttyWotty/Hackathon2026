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
