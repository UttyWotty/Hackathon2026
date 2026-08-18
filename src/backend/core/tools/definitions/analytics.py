"""
Analytics tool definitions for manufacturing analysis modules.

Contains analysis tools: ROI, RCA, Duration Deviation, Duration Efficiency, and Tooling EOL.
These tools perform manufacturing analytics on production data from SHOT_DATA.
"""

from typing import Any, Dict, List

# Common tool parameter descriptions
DESC_CLIENT_PARAM = (
    "Client name/schema to query (e.g., 'PUBLIC', 'AURELIA', 'MERIDIAN', 'ARCWELD'). "
    "If not provided, uses default from environment."
)

ANALYTICS_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "run_roi_analysis",
            "description": "Calculate ROI and duration efficiency metrics for manufacturing operations. Supports daily, weekly, or monthly aggregation. Analyzes cost savings, production efficiency, uptime, and financial returns.",
            "tags": {
                "server": "mfg",
                "domain": "analytics",
                "operation": "analyze",
                "environment": "production",
                "security": "public",
            },
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
                            "description": DESC_CLIENT_PARAM,
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
            "tags": {
                "server": "mfg",
                "domain": "analytics",
                "operation": "analyze",
                "environment": "production",
                "security": "public",
            },
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
            "description": "Analyze duration deviations from approved specifications. Calculates deviation percentages, categorizes performance (Excellent to Critical), measures efficiency and stability scores. Use for questions about duration accuracy, process stability, equipment performance consistency, and identifying machines with poor duration control.",
            "tags": {
                "server": "mfg",
                "domain": "analytics",
                "operation": "analyze",
                "environment": "production",
                "security": "public",
            },
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
            "description": "Analyze duration efficiency and benchmark suppliers. Calculates efficiency metrics, ranks suppliers by performance, measures tool consistency, and assigns tier classifications. Use for questions about supplier efficiency comparison, performance ranking, consistency analysis, and identifying best/worst performing suppliers.",
            "tags": {
                "server": "mfg",
                "domain": "analytics",
                "operation": "analyze",
                "environment": "production",
                "security": "public",
            },
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
            "description": "Predict end-of-life (EOL) for manufacturing tools and molds. Analyzes historical shot data, utilization patterns, and degradation to predict when tools will reach design life. Provides remaining shots/days, confidence scores, utilization analysis, and early warning flags for overutilization.",
            "tags": {
                "server": "mfg",
                "domain": "analytics",
                "operation": "analyze",
                "environment": "production",
                "security": "public",
            },
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "type_category": {
                            "type": "string",
                            "description": "Tooling family type for family-specific OEE and bins: 'Injection Molding', 'Die Casting', or 'Stamping' (optional)",
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
