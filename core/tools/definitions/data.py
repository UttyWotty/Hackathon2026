"""
Data tool definitions for database operations and master table management.

Contains 5 data tools: refresh_master_shot_table, run_sql_query, list_tables,
describe_table, and get_master_table_progress for Snowflake data operations.
"""

from typing import Any, Dict, List

DATA_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "refresh_master_shot_table",
            "description": """Refresh MASTER_SHOT_TABLE with latest production data from Snowflake. This is the FOUNDATION TABLE used by all 7 analysis modules (ROI, CT Deviation, CT Efficiency, RCA, Tooling EOL). Run this periodically (daily/hourly) to ensure analyses use fresh data. Supports incremental mode (fast, only new data with overlap) and full mode (complete historical reload).""",
            "tags": {
                "server": "mfg",
                "domain": "data",
                "operation": "transform",
                "environment": "production",
                "security": "public",
            },
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "description": "Processing mode: 'incremental' (default, recommended for scheduled jobs) or 'full' (initial setup/recovery)",
                            "enum": ["incremental", "full"],
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date for full mode (YYYY-MM-DD). Defaults to 2022-01-01 if not specified.",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date for full mode (YYYY-MM-DD). Defaults to current date if not specified.",
                        },
                        "overlap_days": {
                            "type": "integer",
                            "description": "Days to overlap in incremental mode (default: 7) to catch late-arriving data",
                        },
                        "chunk_size_days": {
                            "type": "integer",
                            "description": "Days per processing chunk (default: 7)",
                        },
                        "delete_overlap": {
                            "type": "boolean",
                            "description": "Delete overlap period before processing to avoid duplicates (default: true). Set to false only if you want to append data with potential duplicates.",
                        },
                        "schemas": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Client schema(s) to process (e.g., ['NORDPLAST', 'ARCWELD']). If not provided, uses SNOWFLAKE_SCHEMA from .env. Supports single or multiple clients.",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "run_sql_query",
            "description": """Execute a read-only SQL SELECT query on Snowflake. Use this to explore data, check table contents, or run custom queries. Returns up to 1000 rows by default. Perfect for data exploration, debugging, or answering specific questions about the database.""",
            "tags": {
                "server": "database",
                "domain": "data",
                "operation": "read",
                "environment": "production",
                "security": "public",
            },
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "SQL SELECT query to execute (read-only, no INSERT/UPDATE/DELETE)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of rows to return (default: 1000)",
                        },
                    },
                    "required": ["query"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_tables",
            "description": """List all available tables in the current Snowflake schema. Use this to discover what data is available, find table names, or explore the database structure.""",
            "tags": {
                "server": "database",
                "domain": "data",
                "operation": "read",
                "environment": "production",
                "security": "public",
            },
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "schema": {
                            "type": "string",
                            "description": "Optional: specify a schema (e.g., 'NORDPLAST', 'ARCWELD'). If not provided, uses default from environment.",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "describe_table",
            "description": """Get the structure/schema of a specific table, including column names, data types, and constraints. Use this to understand table structure before querying or to see what columns are available.""",
            "tags": {
                "server": "database",
                "domain": "data",
                "operation": "read",
                "environment": "production",
                "security": "public",
            },
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "Name of the table to describe (e.g., 'MASTER_SHOT_TABLE', 'MOLD', 'PART')",
                        },
                    },
                    "required": ["table_name"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_master_table_progress",
            "description": """Monitor the progress of a running master table refresh job. Shows percentage complete, chunks processed, and recent log messages. Use this to track long-running full loads or check on incremental refreshes.""",
            "tags": {
                "server": "mfg",
                "domain": "data",
                "operation": "read",
                "environment": "production",
                "security": "public",
            },
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "lines": {
                            "type": "integer",
                            "description": "Number of recent log lines to return (default: 50)",
                        },
                    },
                }
            },
        }
    },
]
