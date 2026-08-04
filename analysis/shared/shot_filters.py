"""
Pure DataFrame filters mirroring the MASTER_SHOT_TABLE query predicates.

Re-implements the WHERE clauses the analysis SQL applies - validity bounds on
cycle time, date ranges, and equipment or supplier membership - so shot data
can be served from a local file with identical semantics to Snowflake. Contains
no I/O and no database access, and is therefore testable in isolation.
"""

from typing import List, Optional

import pandas as pd

# Column names in MASTER_SHOT_TABLE, as emitted by the synthetic generator and
# returned by the Snowflake queries.
COL_CT = "CT"
COL_APPROVED_CT = "APPROVED_CT"
COL_SHOT_TIME = "LOCAL_SHOT_TIME"
COL_EQUIPMENT = "EQUIPMENT_CODE"
COL_SUPPLIER = "SUPPLIER_NAME"
COL_VOLUME = "VOLUME"

# Literal times the queries append to a date bound. CT deviation
# use END_OF_DAY; CT efficiency compares against the bare date, i.e. midnight.
END_OF_DAY = "23:59:59"
START_OF_DAY = "00:00:00"

# Upper sanity bound from the CT deviation query: `AND CT < 999.9`. Values at or
# above this are sentinel or corrupt readings, not real cycles.
MAX_VALID_CT = 999.9


def apply_validity_filter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop rows the analysis SQL excludes as invalid.

    Mirrors: CT IS NOT NULL AND APPROVED_CT IS NOT NULL AND CT > 0
    AND APPROVED_CT > 0 AND CT < 999.9

    Args:
        df: Raw shot rows.

    Returns:
        Only rows with usable cycle time and approved cycle time.
    """
    return df[
        df[COL_CT].notna()
        & df[COL_APPROVED_CT].notna()
        & (df[COL_CT] > 0)
        & (df[COL_APPROVED_CT] > 0)
        & (df[COL_CT] < MAX_VALID_CT)
    ]


def apply_date_filter(
    df: pd.DataFrame,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    end_time: str = END_OF_DAY,
) -> pd.DataFrame:
    """
    Restrict rows to a date window on LOCAL_SHOT_TIME.

    The upper bound is a literal comparison, exactly as the SQL writes it. The
    two analyses differ here and the difference is real: CT deviation appends
    '23:59:59', while CT efficiency compares against the bare date, which is
    midnight and therefore excludes almost all of the end day. Sub-second shot
    timestamps also mean '<= 23:59:59' is not the same as '< the next day'.

    Args:
        df: Shot rows with a datetime LOCAL_SHOT_TIME column.
        start_date: Inclusive lower bound as 'YYYY-MM-DD'. Defaults to None
            (no lower bound).
        end_date: Inclusive upper bound as 'YYYY-MM-DD'. Defaults to None
            (no upper bound).
        end_time: Time appended to end_date. Defaults to '23:59:59', the CT
            deviation behaviour; pass START_OF_DAY for CT efficiency.

    Returns:
        Rows inside the window.
    """
    times = pd.to_datetime(df[COL_SHOT_TIME])
    if start_date is not None:
        df = df[times >= pd.Timestamp(f"{start_date} {START_OF_DAY}")]
        times = times.loc[df.index]
    if end_date is not None:
        df = df[times <= pd.Timestamp(f"{end_date} {end_time}")]
    return df


def apply_membership_filter(
    df: pd.DataFrame,
    equipment_codes: Optional[List[str]] = None,
    supplier_names: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Restrict rows to given equipment codes and supplier names.

    A wildcard entry of "*" in equipment_codes means "all equipment" and
    disables the filter, matching how the sense tools request everything.

    Args:
        df: Shot rows.
        equipment_codes: Equipment codes to keep. Defaults to None (all).
        supplier_names: Supplier names to keep. Defaults to None (all).

    Returns:
        Rows matching both memberships.
    """
    if equipment_codes and "*" not in equipment_codes:
        df = df[df[COL_EQUIPMENT].isin(equipment_codes)]
    if supplier_names:
        df = df[df[COL_SUPPLIER].isin(supplier_names)]
    return df


def filter_shots(
    df: pd.DataFrame,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    equipment_codes: Optional[List[str]] = None,
    supplier_names: Optional[List[str]] = None,
    validity: bool = True,
    end_time: str = END_OF_DAY,
) -> pd.DataFrame:
    """
    Apply the full predicate set and sort, as the analysis queries do.

    Args:
        df: Raw shot rows.
        start_date: Inclusive lower date bound. Defaults to None.
        end_date: Inclusive upper date bound. Defaults to None.
        equipment_codes: Equipment codes to keep. Defaults to None.
        supplier_names: Supplier names to keep. Defaults to None.
        validity: Whether to drop invalid cycle times. Defaults to True,
            matching the CT deviation query.
        end_time: Time appended to end_date. Defaults to END_OF_DAY.

    Returns:
        Filtered rows ordered by LOCAL_SHOT_TIME, as `ORDER BY` guarantees.
    """
    if validity:
        df = apply_validity_filter(df)
    df = apply_date_filter(df, start_date, end_date, end_time)
    df = apply_membership_filter(df, equipment_codes, supplier_names)
    return df.sort_values(COL_SHOT_TIME).reset_index(drop=True)
