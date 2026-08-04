"""
Presentation tool definitions for PowerPoint generation.

Contains 2 presentation tools: generate_presentation for single analysis PPTs
and generate_weekly_comparison_ppt for week-over-week comparison reports.
"""

from typing import Any, Dict, List

PRESENTATION_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "generate_presentation",
            "description": "Generate PowerPoint presentation from analysis results. Creates professional PPT with executive summary, key metrics, charts, and recommendations. Currently supports  analysis. Use this after running an analysis when user requests a PowerPoint or presentation.",
            "tags": {
                "server": "mfg",
                "domain": "analytics",
                "operation": "write",
                "environment": "production",
                "security": "public",
            },
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "analysis_type": {
                            "type": "string",
                            "description": "Type of analysis (e.g., 'ct_deviation', 'roi').",
                            "enum": ["ct_deviation", "roi"],
                        },
                        "metrics": {
                            "type": "object",
                            "description": "Analysis metrics dictionary from previous analysis result",
                        },
                        "session_data": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Optional: Session-level data as array of objects (from session_metrics in analysis result)",
                        },
                        "equipment_code": {
                            "type": "string",
                            "description": "Equipment code/identifier",
                        },
                        "supplier_name": {
                            "type": "string",
                            "description": "Supplier or client name",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Analysis start date (YYYY-MM-DD)",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "Analysis end date (YYYY-MM-DD)",
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "Optional: Output directory path (defaults to output/{analysis_type})",
                        },
                    },
                    "required": ["analysis_type", "metrics"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "generate_weekly_comparison_ppt",
            "description": "Generate weekly comparison PowerPoint report comparing two weeks of data. Weeks are defined as Friday to Thursday (midnight). Runs  and Capacity analyses for both weeks and creates a newsletter-style comparison PPT with KPI tables, percentage changes, and key insights. Perfect for weekly performance reviews and trend analysis. If dates not provided, uses current week vs previous week.",
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
                        "equipment_code": {
                            "type": "string",
                            "description": "Equipment code to analyze (REQUIRED)",
                        },
                        "supplier_name": {
                            "type": "string",
                            "description": "Optional supplier/client name",
                        },
                        "week1_start_date": {
                            "type": "string",
                            "description": "Week 1 start date (YYYY-MM-DD, Friday) - optional, auto-calculated if not provided",
                        },
                        "week1_end_date": {
                            "type": "string",
                            "description": "Week 1 end date (YYYY-MM-DD, Thursday) - optional, auto-calculated if not provided",
                        },
                        "week2_start_date": {
                            "type": "string",
                            "description": "Week 2 start date (YYYY-MM-DD, Friday) - optional, auto-calculated if not provided",
                        },
                        "week2_end_date": {
                            "type": "string",
                            "description": "Week 2 end date (YYYY-MM-DD, Thursday) - optional, auto-calculated if not provided",
                        },
                        "week2_reference_date": {
                            "type": "string",
                            "description": "Any date in week 2 (YYYY-MM-DD) - auto-calculates Friday-Thursday week. Useful when user says 'week of Nov 21' or 'Nov 21-27'",
                        },
                        "client": {
                            "type": "string",
                            "description": "Optional client schema name (e.g., 'VANTIS', 'NORDPLAST')",
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "Optional output directory (defaults to output/comparison)",
                        },
                    },
                    "required": [
                        "equipment_code",
                    ],
                }
            },
        }
    },
]
