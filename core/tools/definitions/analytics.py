"""
Analytics tool definitions for manufacturing analysis modules.

Contains 7 analysis tools: RunRate, ROI, Capacity, RCA, CT Deviation, CT Efficiency, and Tooling EOL.
These tools perform comprehensive manufacturing analytics on production data from MASTER_SHOT_TABLE.
"""

from typing import Any, Dict, List

# Common tool parameter descriptions
DESC_CLIENT_PARAM = (
    "Client name/schema to query (e.g., 'NORDPLAST', 'AURELIA', 'MERIDIAN', 'ARCWELD'). "
    "If not provided, uses default from environment."
)

ANALYTICS_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "run_risk_tower_analysis",
            "description": "Score equipment risk over a rolling multi-week window. Detects three failure modes that a single-period average hides: stability declining week over week, abnormally frequent stops (low MTBF), and abnormally long repairs (high MTTR). Returns a risk score, RAG status and primary risk factor per machine. Use this when asked which equipment is deteriorating or trending worse, rather than which is worst right now.",
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
                        "equipment_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Equipment codes to analyze. Omit for all equipment, which is the usual case for a sweep.",
                        },
                        "supplier_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional supplier names to filter.",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Optional start date in YYYY-MM-DD format.",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "Optional end date in YYYY-MM-DD format.",
                        },
                        "weeks": {
                            "type": "integer",
                            "description": "Rolling window length in weeks. Defaults to 4. Needs at least two weeks of data to compute a trend.",
                        },
                    },
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "run_runrate_analysis",
            "description": "Analyze production runrate with MTTR/MTBF metrics, stop detection, and efficiency tracking for specific equipment over a date range. Returns comprehensive Excel reports with session analysis.",
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
                        "equipment_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Equipment codes to analyze (REQUIRED, e.g., ['MX-7110', 'MX-7104'])",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format (REQUIRED)",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format (REQUIRED)",
                        },
                        "supplier_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional supplier names to filter (e.g., ['Vantis industries SCS'])",
                        },
                        "client": {
                            "type": "string",
                            "description": DESC_CLIENT_PARAM,
                        },
                    },
                    "required": ["equipment_codes", "start_date", "end_date"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "run_roi_analysis",
            "description": "Calculate ROI and cycle time efficiency metrics for manufacturing operations. Supports daily, weekly, or monthly aggregation. Analyzes cost savings, production efficiency, uptime, and financial returns.",
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
                        "equipment_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Equipment codes to analyze",
                        },
                        "supplier_names": {
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
            "name": "run_capacity_analysis",
            "description": "Analyze production capacity and OEE with multi-target scenarios (50%-100%). Calculates Availability, Performance, Quality metrics, performance/availability losses, and generates Excel reports with 6 OEE sheets.",
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
                        "equipment_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Equipment codes (REQUIRED) - e.g., ['MX-7102']",
                        },
                        "supplier_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Supplier names (optional)",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date (YYYY-MM-DD)",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date (YYYY-MM-DD)",
                        },
                        "oee_targets": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "OEE targets (default: [0.5, 0.6, 0.7, 0.8, 0.9, 1.0])",
                        },
                        "client": {
                            "type": "string",
                            "description": DESC_CLIENT_PARAM,
                        },
                    },
                    "required": ["equipment_codes", "start_date", "end_date"],
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
                        "equipment_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Equipment codes (optional) - e.g., ['MX-7110']. Analyzes all if not provided.",
                        },
                        "supplier_names": {
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
            "name": "run_ct_deviation_analysis",
            "description": "Analyze cycle time (CT) deviations from approved specifications. Calculates deviation percentages, categorizes performance (Excellent to Critical), measures efficiency and stability scores. Use for questions about CT accuracy, process stability, equipment performance consistency, and identifying machines with poor cycle time control.",
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
                        "equipment_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of equipment codes to analyze (optional, analyzes all if not specified)",
                        },
                        "supplier_names": {
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
            "name": "run_ct_efficiency_analysis",
            "description": "Analyze cycle time efficiency and benchmark suppliers. Calculates efficiency metrics, ranks suppliers by performance, measures tool consistency, and assigns tier classifications. Use for questions about supplier efficiency comparison, performance ranking, consistency analysis, and identifying best/worst performing suppliers.",
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
                        "supplier_names": {
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
                        "tooling_family": {
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
