"""
SQL Query Tools - Wrapper for Snowflake operations.

Provides MCP-compatible tools for executing SQL queries and downloading results.
Integrates with the Snowflake session pool from Phase 1.

Author: Utku Gulbardak
Date: 2025-10-22
"""

from pathlib import Path
from typing import Any, Dict, Literal, Optional

from services.infrastructure.snowflake.session_pool import get_session_pool

DatabaseType = Literal["Main", "Raw"]

DEFAULT_SQL_LIMIT: int = 1000


async def run_sql_query(query: str, limit: int = DEFAULT_SQL_LIMIT) -> Dict[str, Any]:
    """Execute a read-only SQL query, trimmed to a row limit.

    Adapter for the run_sql_query MCP tool: matches the tool's (query, limit)
    signature and delegates to read_query, which enforces read-only validation.

    Args:
        query: SQL SELECT query to execute
        limit: Maximum number of rows to return (default: 1000)

    Returns:
        dict: Query results with data and metadata (same shape as read_query)
    """
    result = await read_query(query)
    data = result.get("data")
    if isinstance(data, list) and len(data) > limit:
        result["data"] = data[:limit]
        result["returned_rows"] = limit
        result["truncated_to_limit"] = limit
    return result


async def read_query(
    query: str,
    database: Optional[DatabaseType] = None,
    params: Optional[Dict] = None,
    schema: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a read-only SQL query and return results.

    Args:
        query: SQL SELECT query to execute
        database: Target database ("Main" or "Raw", defaults to Main)
        params: Optional query parameters for binding
        schema: Target schema (defaults to configured schema from .env)

    Returns:
        dict: Query results with data and metadata
        {
            "status": "success",
            "rows": int,
            "columns": list[str],
            "data": list[dict],  # First 1000 rows
            "preview": str,  # Text preview
        }

    Raises:
        ValueError: If query is not read-only
    """
    try:
        pool = get_session_pool()
        df = pool.execute_query(query, database, params, schema)

        # Convert to JSON-safe dict (handles NaN/Inf automatically)
        import json

        df_head = df.head(1000)
        # Use pandas to_json then parse back - this handles NaN/Inf properly
        json_str = df_head.to_json(orient="records", date_format="iso")
        data = json.loads(json_str)

        return {
            "status": "success",
            "rows": len(df),
            "columns": df.columns.tolist(),
            "data": data,
            "preview": df.head(10).to_string(),
            "full_row_count": len(df),
            "returned_rows": len(data),
        }

    except ValueError as e:
        # Read-only validation error
        return {"status": "error", "error": str(e), "error_type": "validation"}

    except Exception as e:
        return {"status": "error", "error": str(e), "error_type": "execution"}


async def download_query(
    query: str,
    filename: str,
    database: Optional[DatabaseType] = None,
    description: Optional[str] = None,
    schema: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a query and save results to CSV file in storage.

    Args:
        query: SQL SELECT query to execute
        filename: Name for the output file (will add .csv if needed)
        database: Target database
        description: Optional description for file metadata
        schema: Target schema (defaults to configured schema from .env)

    Returns:
        dict: Download result with file metadata
        {
            "status": "success",
            "file_path": str,
            "rows": int,
            "columns": int,
            "size_mb": float,
        }
    """
    try:
        # Ensure filename has .csv extension
        if not filename.endswith(".csv"):
            filename = f"{filename}.csv"

        pool = get_session_pool()
        df = pool.execute_query(query, database, schema=schema)

        # Convert to CSV bytes
        csv_content = df.to_csv(index=False).encode("utf-8")

        # Save to output directory
        output_dir = Path("output/query_results")
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / filename
        file_path.write_bytes(csv_content)

        return {
            "status": "success",
            "file_path": file_path,
            "filename": filename,
            "rows": len(df),
            "columns": len(df.columns),
            "size_mb": round(len(csv_content) / (1024 * 1024), 2),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


async def get_query_preview(
    query: str,
    limit: int = 10,
    database: Optional[DatabaseType] = None,
    schema: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get a quick preview of query results without full execution.

    Args:
        query: SQL query to preview
        limit: Number of rows to return
        database: Target database
        schema: Target schema (defaults to configured schema from .env)

    Returns:
        dict: Preview results with sample data
    """
    try:
        # Add LIMIT to query if not present
        query_upper = query.strip().upper()
        if "LIMIT" not in query_upper:
            query = f"{query.strip().rstrip(';')} LIMIT {limit}"

        pool = get_session_pool()
        df = pool.execute_query(query, database, schema=schema)

        return {
            "status": "success",
            "rows": len(df),
            "columns": df.columns.tolist(),
            "data": df.to_dict(orient="records"),
            "preview": df.to_string(),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


# Tool metadata for MCP registration
QUERY_TOOLS = [
    {
        "name": "read_query",
        "description": "Execute a read-only SQL query on Snowflake and return results",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT query to execute",
                },
                "database": {
                    "type": "string",
                    "enum": ["Main", "Raw"],
                    "description": "Target database (Main=MMS, Raw=Secondary)",
                },
                "schema": {
                    "type": "string",
                    "description": "Target schema (e.g., NORDPLAST, defaults to configured schema in .env)",
                },
                "params": {
                    "type": "object",
                    "description": "Optional query parameters for binding",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "download_query",
        "description": "Execute a query and save results to CSV file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT query to execute",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename (will add .csv extension)",
                },
                "database": {
                    "type": "string",
                    "enum": ["Main", "Raw"],
                    "description": "Target database",
                },
                "schema": {
                    "type": "string",
                    "description": "Target schema (e.g., NORDPLAST, defaults to configured schema in .env)",
                },
                "description": {
                    "type": "string",
                    "description": "Optional description for the file",
                },
            },
            "required": ["query", "filename"],
        },
    },
    {
        "name": "get_query_preview",
        "description": "Get a quick preview of query results (limited rows)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL query to preview"},
                "limit": {
                    "type": "integer",
                    "description": "Number of rows to return (default: 10)",
                },
                "database": {
                    "type": "string",
                    "enum": ["Main", "Raw"],
                    "description": "Target database",
                },
                "schema": {
                    "type": "string",
                    "description": "Target schema (e.g., NORDPLAST, defaults to configured schema in .env)",
                },
            },
            "required": ["query"],
        },
    },
]
