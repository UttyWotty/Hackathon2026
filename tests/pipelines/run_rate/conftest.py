"""Shared pytest fixtures for the run_rate pipeline test suite.
Provides DataFrames at various pipeline stages (raw, sessioned, calculated)
and helper factories for edge-case testing.
"""

import os
from datetime import datetime, timedelta
from typing import List

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Environment guard -- config.py calls get_database_schema() at import time,
# which reads SNOWFLAKE_DATABASE and SNOWFLAKE_SCHEMA from the environment.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _ensure_pipeline_env() -> None:
    """Set Snowflake env vars so config.py can be imported safely."""
    os.environ.setdefault("SNOWFLAKE_DATABASE", "TEST_DB")
    os.environ.setdefault("SNOWFLAKE_SCHEMA", "TEST_SCHEMA")


# ---------------------------------------------------------------------------
# Base DataFrames
# ---------------------------------------------------------------------------
@pytest.fixture()
def raw_shot_df() -> pd.DataFrame:
    """Base DataFrame with EQUIPMENT_CODE, LOCAL_SHOT_TIME, CT columns.

    Contains 2 equipment codes and ~20 rows spanning 2 days.
    CT values hover around 10.0 with outliers at 999.9 and 15.0.
    """
    base_time = datetime(2025, 6, 1, 8, 0, 0)
    rows = []

    # Equipment A -- 12 shots, normal cadence (~10s apart)
    for i in range(10):
        rows.append(
            {
                "EQUIPMENT_CODE": "EQ_A",
                "LOCAL_SHOT_TIME": base_time + timedelta(seconds=i * 10),
                "CT": 10.0,
            }
        )
    # Add one hard-stop outlier
    rows.append(
        {
            "EQUIPMENT_CODE": "EQ_A",
            "LOCAL_SHOT_TIME": base_time + timedelta(seconds=100),
            "CT": 999.9,
        }
    )
    # Add one mode-band violation
    rows.append(
        {
            "EQUIPMENT_CODE": "EQ_A",
            "LOCAL_SHOT_TIME": base_time + timedelta(seconds=110),
            "CT": 15.0,
        }
    )

    # Equipment B -- 8 shots on the next day
    day2 = base_time + timedelta(days=1)
    for i in range(8):
        rows.append(
            {
                "EQUIPMENT_CODE": "EQ_B",
                "LOCAL_SHOT_TIME": day2 + timedelta(seconds=i * 10),
                "CT": 10.0,
            }
        )

    return pd.DataFrame(rows)


@pytest.fixture()
def sessioned_df(raw_shot_df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame with an 8+ hour gap injected to force session breaks.

    Injects a 9-hour gap after the 6th row for EQ_A and after the 4th
    row for EQ_B so that detect_sessions produces multiple sessions
    per equipment.
    """
    from services.config.features.analytics.pipelines.run_rate.session_processor import (
        detect_sessions,
    )

    df = raw_shot_df.copy()

    # Inject 9-hour gap for EQ_A after 6th shot
    eq_a_mask = df["EQUIPMENT_CODE"] == "EQ_A"
    eq_a_idx = df[eq_a_mask].index
    for idx in eq_a_idx[6:]:
        df.loc[idx, "LOCAL_SHOT_TIME"] += timedelta(hours=9)

    # Inject 9-hour gap for EQ_B after 4th shot
    eq_b_mask = df["EQUIPMENT_CODE"] == "EQ_B"
    eq_b_idx = df[eq_b_mask].index
    for idx in eq_b_idx[4:]:
        df.loc[idx, "LOCAL_SHOT_TIME"] += timedelta(hours=9)

    return detect_sessions(df)


@pytest.fixture()
def calculated_df(sessioned_df: pd.DataFrame) -> pd.DataFrame:
    """Full pipeline DataFrame through mode CT, stops, efficiency.

    Used by validation and weighted efficiency tests.
    """
    from services.config.features.analytics.pipelines.run_rate.calculations import (
        calculate_mode_ct,
        calculate_run_efficiency,
        detect_stops,
    )

    df = calculate_mode_ct(sessioned_df)
    df = detect_stops(df)
    df = calculate_run_efficiency(df)
    return df


@pytest.fixture()
def empty_schema_df() -> "callable":
    """Factory that returns an empty DataFrame with given columns."""

    def _factory(columns: List[str]) -> pd.DataFrame:
        return pd.DataFrame(columns=columns)

    return _factory


@pytest.fixture()
def single_shot_df() -> pd.DataFrame:
    """Minimal single-row DataFrame for boundary tests."""
    return pd.DataFrame(
        [
            {
                "EQUIPMENT_CODE": "EQ_X",
                "LOCAL_SHOT_TIME": datetime(2025, 6, 1, 12, 0, 0),
                "CT": 10.0,
            }
        ]
    )
