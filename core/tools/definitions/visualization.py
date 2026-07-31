"""
Visualization tool definitions for chart and dashboard creation.

Contains 2 visualization tools: create_chart for individual charts and
create_manufacturing_dashboard for comprehensive equipment dashboards.
"""

from typing import Any, Dict, List

VISUALIZATION_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "create_chart",
            "description": """Create interactive charts from data. Supports line, bar, scatter, pie, area, and heatmap charts. Returns interactive HTML chart that can be displayed or saved to file. Perfect for visualizing analysis results, trends, and comparisons.""",
            "tags": {
                "server": "visualization",
                "domain": "analytics",
                "operation": "create",
                "environment": "production",
                "security": "public",
            },
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
                            "description": "Type of chart to create: 'line' (trends, timeseries), 'bar' (comparisons), 'scatter' (correlations), 'pie' (proportions), 'area' (cumulative), 'heatmap' (matrix data)",
                        },
                        "data": {
                            "type": "array",
                            "description": 'Array of data objects with column-value pairs, e.g., [{"date": "2025-01", "efficiency": 95.5, "downtime": 4.5}]',
                        },
                        "x_column": {
                            "type": "string",
                            "description": "Column name for X-axis (e.g., 'date', 'equipment_code')",
                        },
                        "y_column": {
                            "type": "string",
                            "description": "Column name for Y-axis (e.g., 'efficiency', 'count'). For multiple lines, use comma-separated: 'mttr,mtbf'",
                        },
                        "title": {
                            "type": "string",
                            "description": "Chart title (e.g., 'Equipment Efficiency Over Time')",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Optional: file path to save chart (e.g., 'output/charts/efficiency.html'). If not provided, chart HTML is returned in response.",
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
            "description": """Create a pre-built manufacturing dashboard with multiple charts showing equipment performance metrics. Includes efficiency timeline, downtime breakdown, quality metrics, and production analysis. Perfect for daily/weekly equipment reports and management summaries.""",
            "tags": {
                "server": "visualization",
                "domain": "analytics",
                "operation": "create",
                "environment": "production",
                "security": "public",
            },
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "equipment_code": {
                            "type": "string",
                            "description": "Equipment code to analyze (e.g., 'MX-7102', 'MX-7101')",
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
                            "description": "Metrics to include in dashboard: 'efficiency' (timeline), 'downtime' (breakdown), 'quality' (metrics), 'production' (vs target). If not provided, includes all metrics.",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Optional: file path to save dashboard HTML (e.g., 'output/dashboards/equipment_report.html')",
                        },
                    },
                    "required": ["equipment_code", "start_date", "end_date"],
                }
            },
        }
    },
]
