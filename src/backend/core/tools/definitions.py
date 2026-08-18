"""
Aggregated tool definitions for Claude/Bedrock Converse API integration.
Imports analytics tools from analytics_tool_defs and defines communication,
scheduler, data, and visualization tools. Combines all into a single TOOLS list.
"""

from typing import Any, Dict, List

from .analytics_tool_defs import ANALYTICS_TOOLS

# --------------------------------------------------------------------------
# Communication Tools
# --------------------------------------------------------------------------

COMMUNICATION_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "send_email_report",
            "description": "Send analysis report files (Excel, HTML) via email with custom body text. Use this when user requests to email results, insights, recommendations, or send reports to a specific email address. ALWAYS include insights/recommendations in the custom_body parameter.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "recipient_email": {
                            "type": "string",
                            "description": "Email address to send the report to (REQUIRED, e.g., 'user@example.com')",
                        },
                        "file_paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of file paths to attach (Excel, HTML reports from previous analysis)",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject line (optional, will auto-generate if not provided)",
                        },
                        "analysis_type": {
                            "type": "string",
                            "description": "Type of analysis being sent (e.g., 'ROI', 'Duration Deviation', 'RCA') for context",
                        },
                        "custom_body": {
                            "type": "string",
                            "description": "Custom email body text with insights, recommendations, and analysis details. ALWAYS include this when sending reports with analysis results, weekly trends, or recommendations.",
                        },
                    },
                    "required": ["recipient_email", "file_paths"],
                }
            },
        }
    },
]

# --------------------------------------------------------------------------
# Scheduler Tools
# --------------------------------------------------------------------------

SCHEDULER_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "schedule_job",
            "description": """Schedule a recurring or one-time job for automated analysis. Supports cron schedules (e.g., '0 9 * * *' for daily at 9am), intervals (e.g., '1h', '30m'), or 'once' for one-time execution.""",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Descriptive name for the job (e.g., 'Daily Shot Data Refresh')",
                        },
                        "tool_name": {
                            "type": "string",
                            "description": "Name of the tool to execute (e.g., 'refresh_shot_data', 'run_deviation_analysis')",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Arguments to pass to the tool (same format as calling the tool directly)",
                        },
                        "schedule": {
                            "type": "string",
                            "description": "Schedule in cron format ('0 2 * * *'), interval ('1h', '30m', '7d'), or 'once' for one-time execution",
                        },
                    },
                    "required": ["name", "tool_name", "schedule"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_scheduled_jobs",
            "description": """List all scheduled jobs with their status, next run time, and configuration.""",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "cancel_job",
            "description": """Cancel a scheduled job by ID or name. Use this to stop recurring jobs that are no longer needed.""",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "ID or name of the job to cancel",
                        },
                    },
                    "required": ["job_id"],
                }
            },
        }
    },
]

# --------------------------------------------------------------------------
# Data Tools
# --------------------------------------------------------------------------

DATA_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "run_sql_query",
            "description": """Execute a read-only SQL SELECT query on Snowflake. Returns up to 1000 rows by default.""",
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
            "description": """List all available tables in the current Snowflake schema.""",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "schema": {
                            "type": "string",
                            "description": "Optional: specify a schema (e.g., 'PUBLIC', 'ARCWELD'). If not provided, uses default from environment.",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "describe_table",
            "description": """Get the structure/schema of a specific table, including column names, data types, and constraints.""",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "Name of the table to describe (e.g., 'SHOT_DATA', 'TOOL', 'PRODUCT')",
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
            "description": """Monitor the progress of a running master table refresh job. Shows percentage complete, chunks processed, and recent log messages.""",
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

# --------------------------------------------------------------------------
# Visualization Tools
# --------------------------------------------------------------------------

VISUALIZATION_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "create_chart",
            "description": """Create interactive charts from data. Supports line, bar, scatter, pie, area, and heatmap charts. Returns interactive HTML chart.""",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "chart_type": {
                            "type": "string",
                            "enum": [
                                "line",
                                "bar",
                                "scatter",
                                "pie",
                                "area",
                                "heatmap",
                            ],
                            "description": "Type of chart to create",
                        },
                        "data": {
                            "type": "array",
                            "description": "Array of data objects with column-value pairs",
                        },
                        "x_column": {
                            "type": "string",
                            "description": "Column name for X-axis",
                        },
                        "y_column": {
                            "type": "string",
                            "description": "Column name for Y-axis. For multiple lines, use comma-separated: 'mttr,mtbf'",
                        },
                        "title": {
                            "type": "string",
                            "description": "Chart title",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Optional: file path to save chart HTML",
                        },
                    },
                    "required": ["chart_type", "data", "x_column", "y_column", "title"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_manufacturing_dashboard",
            "description": """Create a pre-built manufacturing dashboard with multiple charts showing equipment performance metrics.""",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "machine_id": {
                            "type": "string",
                            "description": "Equipment code to analyze (e.g., 'MX-7102')",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format",
                        },
                        "metrics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Metrics to include: 'efficiency', 'downtime', 'quality', 'production'. Defaults to all.",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Optional: file path to save dashboard HTML",
                        },
                    },
                    "required": ["machine_id", "start_date", "end_date"],
                }
            },
        }
    },
]

# --------------------------------------------------------------------------
# Presentation Tools (placeholder for future expansion)
# --------------------------------------------------------------------------

PRESENTATION_TOOLS: List[Dict[str, Any]] = []

# --------------------------------------------------------------------------
# Combined TOOLS list (all tools in one flat list)
# --------------------------------------------------------------------------

TOOLS: List[Dict[str, Any]] = (
    ANALYTICS_TOOLS
    + COMMUNICATION_TOOLS
    + SCHEDULER_TOOLS
    + DATA_TOOLS
    + VISUALIZATION_TOOLS
    + PRESENTATION_TOOLS
)

__all__ = [
    "TOOLS",
    "ANALYTICS_TOOLS",
    "COMMUNICATION_TOOLS",
    "SCHEDULER_TOOLS",
    "DATA_TOOLS",
    "VISUALIZATION_TOOLS",
    "PRESENTATION_TOOLS",
]
