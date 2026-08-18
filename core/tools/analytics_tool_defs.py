"""
Analytics tool definitions for Claude/Bedrock Converse API integration.

Defines manufacturing analysis tools: master table refresh, ROI,
RCA, duration deviation, duration efficiency, and tooling EOL.
"""

from typing import Any, Dict, List

ANALYTICS_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "refresh_shot_data",
            "description": """Refresh SHOT_DATA with latest production data from Snowflake. This is the FOUNDATION TABLE used by all 7 analysis modules (ROI, Duration Deviation, Duration Efficiency, RCA, Tooling EOL). Run this periodically (daily/hourly) to ensure analyses use fresh data. Supports incremental mode (fast, only new data with overlap) and full mode (complete historical reload).""",
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
            "name": "run_roi_analysis",
            "description": "Calculate ROI and duration efficiency metrics for manufacturing operations. Supports daily, weekly, or monthly aggregation. Analyzes cost savings, production efficiency, uptime, and financial returns.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "machine_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Equipment codes to analyze",
                        },
                        "vendor_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Supplier names to analyze",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format",
                        },
                        "client": {
                            "type": "string",
                            "description": "Client name/schema to query (e.g., 'NORDPLAST', 'AURELIA', 'MERIDIAN', 'ARCWELD'). If not provided, uses default from environment.",
                        },
                        "aggregation_level": {
                            "type": "string",
                            "enum": ["daily", "weekly", "monthly"],
                            "description": "Time aggregation level: 'daily' (default - most detailed), 'weekly' (week-by-week trends), or 'monthly' (high-level overview)",
                        },
                    },
                    "required": ["start_date", "end_date"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "run_rca_analysis",
            "description": "Perform root cause analysis using Pareto (80/20 rule) + 5 Whys methodology to identify top manufacturing issues, root causes, and actionable recommendations with priority levels.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "machine_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Equipment codes (optional) - e.g., ['MX-7110']. Analyzes all if not provided.",
                        },
                        "vendor_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Supplier names (optional)",
                        },
                    },
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "run_deviation_analysis",
            "description": "Analyze duration deviations from approved specifications. Calculates deviation percentages, categorizes performance (Excellent to Critical), measures efficiency and stability scores.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "description": "Start date for analysis in YYYY-MM-DD format (optional)",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date for analysis in YYYY-MM-DD format (optional)",
                        },
                        "machine_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of equipment codes to analyze (optional, analyzes all if not specified)",
                        },
                        "vendor_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of supplier names to filter by (optional)",
                        },
                        "save_csv": {
                            "type": "boolean",
                            "description": "Save CSV results (default: true)",
                        },
                        "save_html": {
                            "type": "boolean",
                            "description": "Save HTML report with charts (default: true)",
                        },
                    },
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "run_efficiency_analysis",
            "description": "Analyze duration efficiency and benchmark suppliers. Calculates efficiency metrics, ranks suppliers by performance, measures tool consistency, and assigns tier classifications.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "description": "Start date for analysis in YYYY-MM-DD format (optional)",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date for analysis in YYYY-MM-DD format (optional)",
                        },
                        "vendor_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of supplier names to analyze (optional, analyzes all if not specified)",
                        },
                        "save_csv": {
                            "type": "boolean",
                            "description": "Save CSV results (default: true)",
                        },
                        "save_html": {
                            "type": "boolean",
                            "description": "Save HTML report with supplier rankings (default: true)",
                        },
                        "normalization_method": {
                            "type": "string",
                            "description": "Score normalization method: 'z_score' (default), 'min_max', or 'percentile'",
                            "enum": ["z_score", "min_max", "percentile"],
                        },
                    },
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "run_tooling_eol_analysis",
            "description": "Predict end-of-life (EOL) for manufacturing tools and molds. Analyzes historical shot data, utilization patterns, and degradation to predict when tools will reach design life.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "type_category": {
                            "type": "string",
                            "description": "Tooling family type: 'Injection Molding', 'Die Casting', or 'Stamping' (optional)",
                            "enum": ["Injection Molding", "Die Casting", "Stamping"],
                        },
                        "save_csv": {
                            "type": "boolean",
                            "description": "Save predictions as CSV file (default: true)",
                        },
                        "save_html": {
                            "type": "boolean",
                            "description": "Save predictions as HTML report (default: false)",
                        },
                        "disable_maintenance": {
                            "type": "boolean",
                            "description": "Skip maintenance event integration (default: false)",
                        },
                    },
                    "required": [],
                }
            },
        }
    },
]
