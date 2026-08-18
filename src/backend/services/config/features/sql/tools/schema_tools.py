"""
SQL Schema Exploration Tools.

Provides tools for exploring database schema, listing tables,
describing table structures, and sampling data.

Author: Utku Gulbardak
Date: 2025-10-22
"""

import json
from typing import Any, Dict, List, Literal, Optional

import pandas as pd

from services.infrastructure.snowflake.session_pool import get_session_pool

DatabaseType = Literal["Main", "Raw"]


def _dataframe_to_json_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert a DataFrame to JSON-safe records (NaN/Inf become null)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


async def list_tables(
    database: Optional[DatabaseType] = None, schema: Optional[str] = None
) -> Dict[str, Any]:
    """
    List all tables in a schema.

    Args:
        database: Target database ("Main" or "Raw")
        schema: Schema name (defaults to configured schema)

    Returns:
        dict: List of tables with metadata
        {
            "status": "success",
            "tables": list[dict],
            "count": int,
        }
    """
    try:
        pool = get_session_pool()
        df = pool.list_tables(database, schema)

        return {
            "status": "success",
            "tables": _dataframe_to_json_records(df),
            "count": len(df),
            "columns": df.columns.tolist(),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


async def describe_table(
    table_name: str,
    database: Optional[DatabaseType] = None,
    schema: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get detailed column information for a table.

    Args:
        table_name: Name of the table
        database: Target database
        schema: Schema name

    Returns:
        dict: Table structure with column details
        {
            "status": "success",
            "table_name": str,
            "columns": list[dict],
            "column_count": int,
        }
    """
    try:
        pool = get_session_pool()
        df = pool.describe_table(table_name, database, schema)

        return {
            "status": "success",
            "table_name": table_name,
            "columns": _dataframe_to_json_records(df),
            "column_count": len(df),
        }

    except Exception as e:
        return {"status": "error", "error": str(e), "table_name": table_name}


async def get_table_sample(
    table_name: str,
    limit: int = 100,
    database: Optional[DatabaseType] = None,
    schema: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get sample rows from a table.

    Args:
        table_name: Name of the table
        limit: Number of rows to sample (default: 100)
        database: Target database
        schema: Schema name

    Returns:
        dict: Sample data from table
        {
            "status": "success",
            "table_name": str,
            "rows": int,
            "columns": list[str],
            "data": list[dict],
        }
    """
    try:
        pool = get_session_pool()
        df = pool.get_table_sample(table_name, limit, database, schema)

        return {
            "status": "success",
            "table_name": table_name,
            "rows": len(df),
            "columns": df.columns.tolist(),
            "data": _dataframe_to_json_records(df),
            "preview": df.head(10).to_string(),
        }

    except Exception as e:
        return {"status": "error", "error": str(e), "table_name": table_name}


async def get_table_stats(
    table_name: str,
    database: Optional[DatabaseType] = None,
    schema: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get basic statistics about a table (row count, column count, size).

    Args:
        table_name: Name of the table
        database: Target database
        schema: Schema name

    Returns:
        dict: Table statistics
    """
    try:
        pool = get_session_pool()

        # Get table info from INFORMATION_SCHEMA
        schema_name = schema or pool.config["schema"]
        query = f"""
        SELECT 
            ROW_COUNT,
            BYTES,
            TABLE_TYPE,
            CREATED,
            LAST_ALTERED
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = '{schema_name}'
          AND TABLE_NAME = '{table_name}'
        """

        df = pool.execute_query(query, database)

        if len(df) == 0:
            return {
                "status": "error",
                "error": f"Table {table_name} not found",
                "table_name": table_name,
            }

        stats = df.iloc[0].to_dict()

        # Get column count
        desc_df = pool.describe_table(table_name, database, schema)

        return {
            "status": "success",
            "table_name": table_name,
            "row_count": stats.get("ROW_COUNT", 0),
            "size_bytes": stats.get("BYTES", 0),
            "size_mb": round(stats.get("BYTES", 0) / (1024 * 1024), 2),
            "column_count": len(desc_df),
            "table_type": stats.get("TABLE_TYPE"),
            "created": str(stats.get("CREATED")),
            "last_altered": str(stats.get("LAST_ALTERED")),
        }

    except Exception as e:
        return {"status": "error", "error": str(e), "table_name": table_name}


# Tool metadata for MCP registration
SCHEMA_TOOLS = [
    {
        "name": "list_tables",
        "description": "List all tables in a Snowflake schema",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "enum": ["Main", "Raw"],
                    "description": "Target database",
                },
                "schema": {
                    "type": "string",
                    "description": "Schema name (optional, defaults to configured schema)",
                },
            },
        },
    },
    {
        "name": "describe_table",
        "description": "Get detailed column information for a table",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table to describe",
                },
                "database": {
                    "type": "string",
                    "enum": ["Main", "Raw"],
                    "description": "Target database",
                },
                "schema": {
                    "type": "string",
                    "description": "Schema name (optional)",
                },
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "get_table_sample",
        "description": "Get sample rows from a table",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Name of the table"},
                "limit": {
                    "type": "integer",
                    "description": "Number of rows to return (default: 100)",
                },
                "database": {
                    "type": "string",
                    "enum": ["Main", "Raw"],
                    "description": "Target database",
                },
                "schema": {"type": "string", "description": "Schema name (optional)"},
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "get_table_stats",
        "description": "Get statistics about a table (row count, size, etc.)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Name of the table"},
                "database": {
                    "type": "string",
                    "enum": ["Main", "Raw"],
                    "description": "Target database",
                },
                "schema": {"type": "string", "description": "Schema name (optional)"},
            },
            "required": ["table_name"],
        },
    },
]
