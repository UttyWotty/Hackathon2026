"""The only I/O layer of the synthetic data generator: CSV output and Snowflake loading.

Writes each table to a CSV file and, when a connection is supplied, stages the files and
runs COPY INTO so multi-hundred-thousand-row shot tables load in seconds rather than via
row-by-row inserts. The Snowflake connection is injected, never constructed here.
"""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence

from .ddl import all_create_statements, column_names, truncate_statement

logger = logging.getLogger(__name__)

# Internal stage name created per load. Scoped to the target schema.
STAGE_NAME = "SYNTHETIC_LOAD_STAGE"

# Snowflake COPY options for the CSV files this module writes.
FILE_FORMAT_CLAUSE = (
    "TYPE = CSV FIELD_DELIMITER = ',' SKIP_HEADER = 1 "
    "FIELD_OPTIONALLY_ENCLOSED_BY = '\"' NULL_IF = ('') EMPTY_FIELD_AS_NULL = TRUE"
)

CSV_SUFFIX = ".csv"


class SyntheticDataLoadError(RuntimeError):
    """Raised when writing or loading the synthetic dataset fails."""


class SnowflakeCursorLike(Protocol):
    """Minimal cursor surface used by this loader, so tests can substitute a fake."""

    def execute(self, statement: str) -> Any:
        """Execute a single SQL statement."""


class SnowflakeConnectionLike(Protocol):
    """Minimal connection surface used by this loader, so tests can substitute a fake."""

    def cursor(self) -> SnowflakeCursorLike:
        """Return a cursor for statement execution."""


def write_table_csv(
    output_dir: Path,
    table: str,
    rows: List[Sequence[Any]],
) -> Path:
    """Write one table's rows to a CSV file with a DDL-ordered header row."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{table}{CSV_SUFFIX}"
    try:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(column_names(table))
            writer.writerows(rows)
    except OSError as error:
        raise SyntheticDataLoadError(
            f"failed writing CSV for table {table}: {error}"
        ) from error
    logger.info("Wrote %d rows for table %s to %s", len(rows), table, path)
    return path


def write_dataset_csv(
    output_dir: Path, tables: Dict[str, List[Sequence[Any]]]
) -> Dict[str, Path]:
    """Write every table to CSV and return the path of each written file."""
    return {
        table: write_table_csv(output_dir, table, rows)
        for table, rows in tables.items()
    }


def _execute(cursor: SnowflakeCursorLike, statement: str) -> None:
    """Execute one statement, wrapping driver errors in a domain exception."""
    try:
        cursor.execute(statement)
    except (
        Exception
    ) as error:  # noqa: BLE001 - driver exception types vary by connector version
        raise SyntheticDataLoadError(
            f"statement failed: {statement.splitlines()[0]}: {error}"
        ) from error


def create_objects(
    connection: SnowflakeConnectionLike, database: str, schema: str
) -> None:
    """Create the target schema and every synthetic table if they do not already exist."""
    cursor = connection.cursor()
    for statement in all_create_statements(database, schema):
        _execute(cursor, statement)
    _execute(cursor, f"CREATE STAGE IF NOT EXISTS {database}.{schema}.{STAGE_NAME}")


def truncate_tables(
    connection: SnowflakeConnectionLike, database: str, schema: str, tables: List[str]
) -> None:
    """Truncate the named tables so a reload does not append to a previous dataset."""
    cursor = connection.cursor()
    for table in tables:
        _execute(cursor, truncate_statement(database, schema, table))


def _put_statement(path: Path, database: str, schema: str) -> str:
    """Build the PUT statement that stages one local CSV file."""
    uri = path.resolve().as_posix()
    return f"PUT 'file://{uri}' @{database}.{schema}.{STAGE_NAME} OVERWRITE = TRUE AUTO_COMPRESS = TRUE"


def _copy_statement(table: str, database: str, schema: str) -> str:
    """Build the COPY INTO statement that loads one staged CSV into its table."""
    columns = ", ".join(column_names(table))
    return (
        f"COPY INTO {database}.{schema}.{table} ({columns}) "
        f"FROM @{database}.{schema}.{STAGE_NAME}/{table}{CSV_SUFFIX}.gz "
        f"FILE_FORMAT = ({FILE_FORMAT_CLAUSE}) ON_ERROR = ABORT_STATEMENT"
    )


def load_into_snowflake(
    csv_paths: Dict[str, Path],
    database: str,
    schema: str,
    connection: Optional[SnowflakeConnectionLike] = None,
    truncate_first: bool = True,
) -> None:
    """Stage the written CSV files and COPY them into the synthetic tables.

    Passing no connection is an explicit no-op so the CSV-only path stays usable offline;
    callers that intend to load must supply a connection.
    """
    if connection is None:
        logger.info(
            "No Snowflake connection supplied; leaving %d CSV files unloaded",
            len(csv_paths),
        )
        return

    create_objects(connection, database, schema)
    if truncate_first:
        truncate_tables(connection, database, schema, list(csv_paths))

    cursor = connection.cursor()
    for table, path in csv_paths.items():
        _execute(cursor, _put_statement(path, database, schema))
        _execute(cursor, _copy_statement(table, database, schema))
        logger.info("Loaded table %s from %s", table, path.name)
