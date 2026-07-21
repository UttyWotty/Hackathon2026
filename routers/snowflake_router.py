"""
Snowflake Router - SQL queries and schema exploration.

This router provides direct access to Snowflake database for:
- Running SQL queries
- Listing tables and schemas
- Getting table metadata
- Schema exploration

All queries are read-only and validated before execution.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException  # type: ignore[import-untyped]
from pydantic import BaseModel, Field  # type: ignore[import-untyped]

# Import Snowflake tools
from services.config.features.sql.tools.query_tools import read_query
from services.config.features.sql.tools.schema_tools import (
    describe_table,
    get_table_sample,
    get_table_stats,
    list_tables,
)

# Import validation utilities
from utils.sql_validation import (
    SQLValidationError,
    sanitize_sql_identifier,
    validate_sql_query,
)

logger = logging.getLogger(__name__)

# Get environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

# Constants
INVALID_DATABASE_ERROR = "Database must be 'Main' or 'Raw'"
DATABASE_FIELD_DESCRIPTION = "Database name (Main or Raw)"
UNKNOWN_ERROR = "Unknown error"

# Create router
router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class QueryRequest(BaseModel):
    """SQL Query request"""

    query: str = Field(
        ...,
        description="SQL query to execute (read-only, SELECT/WITH only)",
        max_length=10000,
    )
    database: Optional[str] = Field(None, description=DATABASE_FIELD_DESCRIPTION)
    schema_name: Optional[str] = Field(None, description="Schema name", alias="schema")


class ListTablesRequest(BaseModel):
    """List tables request"""

    database: str = Field("Main", description=DATABASE_FIELD_DESCRIPTION)
    schema_name: Optional[str] = Field(
        None, description="Schema name (optional)", alias="schema"
    )


class TableInfoRequest(BaseModel):
    """Table information request"""

    table_name: str = Field(..., description="Table name", max_length=128)
    database: str = Field("Main", description=DATABASE_FIELD_DESCRIPTION)
    schema_name: Optional[str] = Field(None, description="Schema name", alias="schema")


# ============================================================================
# Snowflake Endpoints
# ============================================================================


@router.get("/")
async def database_info():
    """Get information about database operations"""
    return {
        "service": "Snowflake Database",
        "description": "SQL queries and schema exploration",
        "features": [
            "Execute read-only SQL queries",
            "List tables and schemas",
            "Get table metadata and statistics",
            "Sample table data",
        ],
        "endpoints": {
            "query": "POST /database/query",
            "tables": "POST /database/tables",
            "describe": "POST /database/describe",
            "sample": "POST /database/sample",
            "stats": "POST /database/stats",
        },
        "default_database": "Main",
        "default_schema": "Configured in .env",
    }


@router.post("/query")
async def execute_query(request: QueryRequest):
    """
    Execute a read-only SQL query.

    Queries are validated to ensure they are read-only (SELECT statements only).
    Results are returned as JSON.

    **Example:**
    ```json
    {
      "query": "SELECT * FROM MASTER_SHOT_TABLE LIMIT 10",
      "database": "Main",
      "schema": "SHOT_DATA"
    }
    ```

    **Security:**
    - Only SELECT/WITH statements are allowed
    - No DDL (CREATE, DROP, ALTER) operations
    - No DML (INSERT, UPDATE, DELETE) operations
    - Query length limited to 10,000 characters
    - SQL injection patterns are blocked
    """
    logger.info(f"Query requested: {request.query[:100]}...")

    try:
        # Validate and sanitize SQL query
        sanitized_query, _ = validate_sql_query(request.query)

        # Validate database name if provided
        if request.database:
            request.database = sanitize_sql_identifier(request.database)
            if request.database not in ["Main", "Raw"]:
                raise HTTPException(status_code=400, detail=INVALID_DATABASE_ERROR)

        # Validate schema name if provided
        if request.schema_name:
            request.schema_name = sanitize_sql_identifier(request.schema_name)

        result = await read_query(
            query=sanitized_query,
            database=request.database,
            schema=request.schema_name,
        )

        # Check if result indicates error
        if result.get("status") == "error":
            error_msg = result.get("error", UNKNOWN_ERROR)
            if ENVIRONMENT == "production":
                raise HTTPException(
                    status_code=500,
                    detail="Query execution failed. Please check your query syntax.",
                )
            else:
                raise HTTPException(status_code=500, detail=error_msg)

        return result

    except SQLValidationError as e:
        logger.warning(f"SQL validation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid query: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query execution failed: {e}", exc_info=True)
        if ENVIRONMENT == "production":
            raise HTTPException(
                status_code=500,
                detail="An error occurred while executing the query. Please try again.",
            )
        else:
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/tables")
async def list_database_tables(request: ListTablesRequest):
    """
    List all tables in a database schema.

    Returns table names, row counts, and metadata.

    **Example:**
    ```json
    {
      "database": "Main",
      "schema": "SHOT_DATA"
    }
    ```
    """
    logger.info(f"List tables requested for {request.database}.{request.schema_name}")

    try:
        # Validate inputs
        if request.database not in ["Main", "Raw"]:
            raise HTTPException(status_code=400, detail=INVALID_DATABASE_ERROR)

        if request.schema_name:
            request.schema_name = sanitize_sql_identifier(request.schema_name)

        result = await list_tables(
            database=request.database,
            schema=request.schema_name,
        )

        if result.get("status") == "error":
            error_msg = result.get("error", UNKNOWN_ERROR)
            if ENVIRONMENT == "production":
                raise HTTPException(
                    status_code=500, detail="Failed to list tables. Please try again."
                )
            else:
                raise HTTPException(status_code=500, detail=error_msg)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List tables failed: {e}", exc_info=True)
        if ENVIRONMENT == "production":
            raise HTTPException(
                status_code=500, detail="An error occurred while listing tables."
            )
        else:
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/describe")
async def describe_table_endpoint(request: TableInfoRequest):
    """
    Get table schema and column information.

    Returns column names, data types, and metadata.

    **Example:**
    ```json
    {
      "table_name": "MASTER_SHOT_TABLE",
      "database": "Main",
      "schema": "SHOT_DATA"
    }
    ```
    """
    logger.info(f"Describe table requested: {request.table_name}")

    try:
        # Validate inputs
        request.table_name = sanitize_sql_identifier(request.table_name)

        if request.database not in ["Main", "Raw"]:
            raise HTTPException(status_code=400, detail=INVALID_DATABASE_ERROR)

        if request.schema_name:
            request.schema_name = sanitize_sql_identifier(request.schema_name)

        result = await describe_table(
            table_name=request.table_name,
            database=request.database,
            schema=request.schema_name,
        )

        if result.get("status") == "error":
            error_msg = result.get("error", UNKNOWN_ERROR)
            if ENVIRONMENT == "production":
                raise HTTPException(
                    status_code=500,
                    detail="Failed to describe table. Please check table name.",
                )
            else:
                raise HTTPException(status_code=500, detail=error_msg)

        return result

    except SQLValidationError as e:
        logger.warning(f"Input validation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Describe table failed: {e}", exc_info=True)
        if ENVIRONMENT == "production":
            raise HTTPException(
                status_code=500, detail="An error occurred while describing the table."
            )
        else:
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/sample")
async def get_table_sample_endpoint(request: TableInfoRequest):
    """
    Get a sample of table data.

    Returns first 100 rows of the table.

    **Example:**
    ```json
    {
      "table_name": "MASTER_SHOT_TABLE",
      "database": "Main",
      "schema": "SHOT_DATA"
    }
    ```
    """
    logger.info(f"Table sample requested: {request.table_name}")

    try:
        # Validate inputs
        request.table_name = sanitize_sql_identifier(request.table_name)

        if request.database not in ["Main", "Raw"]:
            raise HTTPException(status_code=400, detail=INVALID_DATABASE_ERROR)

        if request.schema_name:
            request.schema_name = sanitize_sql_identifier(request.schema_name)

        result = await get_table_sample(
            table_name=request.table_name,
            database=request.database,
            schema=request.schema_name,
        )

        if result.get("status") == "error":
            error_msg = result.get("error", UNKNOWN_ERROR)
            if ENVIRONMENT == "production":
                raise HTTPException(
                    status_code=500,
                    detail="Failed to get table sample. Please try again.",
                )
            else:
                raise HTTPException(status_code=500, detail=error_msg)

        return result

    except SQLValidationError as e:
        logger.warning(f"Input validation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get table sample failed: {e}", exc_info=True)
        if ENVIRONMENT == "production":
            raise HTTPException(
                status_code=500, detail="An error occurred while sampling the table."
            )
        else:
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/stats")
async def get_table_stats_endpoint(request: TableInfoRequest):
    """
    Get table statistics.

    Returns row count, column count, and other metadata.

    **Example:**
    ```json
    {
      "table_name": "MASTER_SHOT_TABLE",
      "database": "Main",
      "schema": "SHOT_DATA"
    }
    ```
    """
    logger.info(f"Table stats requested: {request.table_name}")

    try:
        # Validate inputs
        request.table_name = sanitize_sql_identifier(request.table_name)

        if request.database not in ["Main", "Raw"]:
            raise HTTPException(status_code=400, detail=INVALID_DATABASE_ERROR)

        if request.schema_name:
            request.schema_name = sanitize_sql_identifier(request.schema_name)

        result = await get_table_stats(
            table_name=request.table_name,
            database=request.database,
            schema=request.schema_name,
        )

        if result.get("status") == "error":
            error_msg = result.get("error", UNKNOWN_ERROR)
            if ENVIRONMENT == "production":
                raise HTTPException(
                    status_code=500,
                    detail="Failed to get table statistics. Please try again.",
                )
            else:
                raise HTTPException(status_code=500, detail=error_msg)

        return result

    except SQLValidationError as e:
        logger.warning(f"Input validation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get table stats failed: {e}", exc_info=True)
        if ENVIRONMENT == "production":
            raise HTTPException(
                status_code=500,
                detail="An error occurred while getting table statistics.",
            )
        else:
            raise HTTPException(status_code=500, detail=str(e))
