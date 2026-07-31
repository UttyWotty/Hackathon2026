"""Command-line entry point that generates and optionally loads the synthetic dataset.

Resolves configuration from CLI flags and environment defaults, builds the dataset purely,
then writes CSV files, a ground-truth JSON contract, and optionally copies everything into
Snowflake. This is the composition root: all clock access, filesystem and network I/O live here.
"""

import argparse
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Final, Optional

from dotenv import load_dotenv

from .constants import (
    DEFAULT_PRODUCTION_DAYS_PER_WEEK,
    DEFAULT_SEED,
    DEFAULT_SHIFT_HOURS,
    DEFAULT_SHIFT_START_HOUR,
    DEFAULT_WEEKS,
)
from .dataset import build_dataset, summarize
from .loader import SyntheticDataLoadError, load_into_snowflake, write_dataset_csv
from .models import GenerationConfig

logger = logging.getLogger(__name__)

# Load .env before reading env vars so standalone invocation picks up credentials.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Environment defaults. Every read is declared here as a module-level constant.
SYNTHETIC_DATABASE: Final[str] = os.getenv("SYNTHETIC_DATABASE", "MMS_DEMO")
SYNTHETIC_SCHEMA: Final[str] = os.getenv("SYNTHETIC_SCHEMA", "PUBLIC")
SYNTHETIC_OUTPUT_DIR: Final[str] = os.getenv("SYNTHETIC_OUTPUT_DIR", "./synthetic_out")
SNOWFLAKE_ACCOUNT: Final[str] = os.getenv("SNOWFLAKE_ACCOUNT", "")
SNOWFLAKE_USER: Final[str] = os.getenv("SNOWFLAKE_USER", "")
SNOWFLAKE_PASSWORD: Final[str] = os.getenv("SNOWFLAKE_PASSWORD", "")
SNOWFLAKE_WAREHOUSE: Final[str] = os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
SNOWFLAKE_ROLE: Final[str] = os.getenv("SNOWFLAKE_ROLE", "")

GROUND_TRUTH_FILENAME: Final[str] = "ground_truth.json"
ISO_MONDAY: Final[int] = 0


class SyntheticDataConfigError(ValueError):
    """Raised when the requested generation configuration cannot be satisfied."""


def _default_window_start(weeks: int, today: datetime) -> datetime:
    """Return the Monday that starts a window of the requested length ending near today."""
    window_start = today - timedelta(days=weeks * 7)
    return (window_start - timedelta(days=window_start.weekday() - ISO_MONDAY)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def build_parser() -> argparse.ArgumentParser:
    """Define the command-line interface for the generator."""
    parser = argparse.ArgumentParser(
        description="Generate the synthetic manufacturing dataset."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Base RNG seed.")
    parser.add_argument(
        "--weeks", type=int, default=DEFAULT_WEEKS, help="Weeks of history to generate."
    )
    parser.add_argument(
        "--production-days",
        type=int,
        default=DEFAULT_PRODUCTION_DAYS_PER_WEEK,
        help="Production days per week.",
    )
    parser.add_argument(
        "--shift-hours",
        type=float,
        default=DEFAULT_SHIFT_HOURS,
        help="Length of a daily run.",
    )
    parser.add_argument(
        "--shift-start-hour",
        type=int,
        default=DEFAULT_SHIFT_START_HOUR,
        help="Local hour a run begins.",
    )
    parser.add_argument(
        "--database", default=SYNTHETIC_DATABASE, help="Target Snowflake database."
    )
    parser.add_argument(
        "--schema", default=SYNTHETIC_SCHEMA, help="Target Snowflake schema."
    )
    parser.add_argument(
        "--output-dir", default=SYNTHETIC_OUTPUT_DIR, help="Directory for CSV output."
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="Load the CSVs into Snowflake after writing.",
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Append to existing tables instead of truncating them first.",
    )
    return parser


def build_config(namespace: argparse.Namespace, now: datetime) -> GenerationConfig:
    """Translate parsed arguments into an immutable generation config."""
    if namespace.weeks < 1:
        raise SyntheticDataConfigError("weeks must be at least 1")
    if not 1 <= namespace.production_days <= 7:
        raise SyntheticDataConfigError("production-days must be between 1 and 7")
    if not 0.0 < namespace.shift_hours <= 24.0:
        raise SyntheticDataConfigError("shift-hours must be in (0, 24]")
    return GenerationConfig(
        seed=namespace.seed,
        weeks=namespace.weeks,
        production_days_per_week=namespace.production_days,
        shift_hours=namespace.shift_hours,
        shift_start_hour=namespace.shift_start_hour,
        window_start=_default_window_start(namespace.weeks, now),
        generated_at=now,
        database=namespace.database,
        schema=namespace.schema,
    )


def open_connection() -> Any:
    """Open a Snowflake connection from environment credentials.

    Imported lazily so the CSV-only path works without the Snowflake connector installed.
    """
    if not SNOWFLAKE_ACCOUNT or not SNOWFLAKE_USER:
        raise SyntheticDataConfigError(
            "SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER must be set to use --load"
        )
    try:
        import snowflake.connector as connector
    except ImportError as error:
        raise SyntheticDataLoadError(
            "snowflake-connector-python is required for --load"
        ) from error

    parameters: Dict[str, str] = {
        "account": SNOWFLAKE_ACCOUNT,
        "user": SNOWFLAKE_USER,
        "password": SNOWFLAKE_PASSWORD,
        "warehouse": SNOWFLAKE_WAREHOUSE,
    }
    if SNOWFLAKE_ROLE:
        parameters["role"] = SNOWFLAKE_ROLE
    return connector.connect(**parameters)


def write_ground_truth(
    output_dir: Path, config: GenerationConfig, dataset: Any
) -> Path:
    """Write the planted-defect contract and dataset shape alongside the CSV files."""
    payload = {
        "config": {
            **asdict(config),
            "window_start": config.window_start.isoformat(),
            "generated_at": config.generated_at.isoformat(),
        },
        "headline_equipment": dataset.headline_equipment,
        "row_counts": summarize(dataset),
        "expected_findings": [
            {**asdict(finding), "profile_kind": finding.profile_kind.value}
            for finding in dataset.expected_findings
        ],
    }
    path = output_dir / GROUND_TRUTH_FILENAME
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def main(argv: Optional[list] = None) -> int:
    """Generate the dataset, write it to disk, and optionally load it into Snowflake."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    namespace = build_parser().parse_args(argv)
    config = build_config(namespace, datetime.now())

    dataset = build_dataset(config)
    output_dir = Path(namespace.output_dir)
    csv_paths = write_dataset_csv(output_dir, dataset.tables)
    ground_truth_path = write_ground_truth(output_dir, config, dataset)

    for table, count in summarize(dataset).items():
        logger.info("Table %s: %d rows", table, count)
    logger.info("Ground truth written to %s", ground_truth_path)

    if namespace.load:
        connection = open_connection()
        load_into_snowflake(
            csv_paths=csv_paths,
            database=config.database,
            schema=config.schema,
            connection=connection,
            truncate_first=not namespace.no_truncate,
        )
        logger.info("Loaded dataset into %s.%s", config.database, config.schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
