"""Tool definitions for the cross-analysis insights suite.

Declares Bedrock Converse API specs for synthesis (health, periods), data trust
(approved CTs, freshness, quality), mold/work-order tracing, forecasting, savings,
and knowledge tools. Implementations live in services/config/features/insights/tools.
"""

from typing import Any, Dict, List

INSIGHTS_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "get_plant_health_snapshot",
            "description": (
                "Get a ranked health snapshot of ALL equipment in one call (worst first). "
                "Blends run efficiency, cycle time performance, capacity utilization, and "
                "data recency into a 0-100 score with healthy/watch/critical grades. Use "
                "this FIRST for questions like 'which equipment needs attention' or 'how is "
                "the plant doing'."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Analysis window in days (default: 14, max: 365)",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "compare_periods",
            "description": (
                "Compare the last N days against the N days before, per equipment: shots, "
                "average cycle time, and active days with absolute and percentage deltas. "
                "Use for week-over-week or month-over-month questions."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "period_days": {
                            "type": "integer",
                            "description": "Window length in days (default: 7, max: 180)",
                        },
                        "equipment_code": {
                            "type": "string",
                            "description": "Optional single-equipment filter",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "find_top_movers",
            "description": (
                "Rank equipment by the largest change in a metric between the last two "
                "periods. Great default answer to 'anything I should know about?'."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": ["shots", "avg_ct", "active_days"],
                            "description": "Metric to rank change by (default: shots)",
                        },
                        "period_days": {
                            "type": "integer",
                            "description": "Window length in days (default: 7)",
                        },
                        "top_n": {
                            "type": "integer",
                            "description": "Number of movers to return (default: 5, max: 50)",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "validate_approved_cts",
            "description": (
                "Flag approved cycle times that have drifted from reality. Compares "
                "APPROVED_CT to the observed mode CT per equipment/part and proposes "
                "updated values for stale entries. Approved CTs are known to go stale; run "
                "this before trusting any approved-CT-based efficiency number."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Observation window in days (default: 30)",
                        },
                        "stale_threshold_pct": {
                            "type": "number",
                            "description": "Deviation percent that marks stale (default: 10)",
                        },
                        "min_shots": {
                            "type": "integer",
                            "description": "Minimum shots to judge a record (default: 100)",
                        },
                        "equipment_code": {
                            "type": "string",
                            "description": "Optional single-equipment filter",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "data_freshness_report",
            "description": (
                "Report how current every analytics table and pipeline is (fresh, stale, "
                "dead, or no data) against expected refresh cadences, including the "
                "ETL_LATEST pipeline log. Run this before trusting any analysis output."
            ),
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "data_quality_audit",
            "description": (
                "Audit master shot data integrity over a recent window: null equipment "
                "codes, invalid cycle times, missing approved CTs, future timestamps, and "
                "duplicate shots, each with pass/warn/fail verdicts."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Audit window in days (default: 30)",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_mold_history",
            "description": (
                "Full lifecycle view of a mold/tool: status, designed vs actual shots, "
                "maintenance events, location moves, and shots since last maintenance. "
                "Identify the mold by equipment_code or mold_id."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "equipment_code": {
                            "type": "string",
                            "description": "Equipment code of the mold",
                        },
                        "mold_id": {
                            "type": "integer",
                            "description": "MOLD.ID primary key (alternative to equipment_code)",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "maintenance_impact_analysis",
            "description": (
                "Measure whether maintenance actually helped: compares average CT and "
                "shots/day in equal windows before and after each maintenance event of a "
                "mold, with improved/degraded/neutral verdicts."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "equipment_code": {
                            "type": "string",
                            "description": "Equipment code of the mold",
                        },
                        "mold_id": {
                            "type": "integer",
                            "description": "MOLD.ID primary key (alternative to equipment_code)",
                        },
                        "window_days": {
                            "type": "integer",
                            "description": "Days on each side of the event (default: 7, max: 90)",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "trace_work_order",
            "description": (
                "Trace a work order end to end: its maintenance event, the mold, mounted "
                "parts, and recent production quality (rejected rates) for that mold."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "work_order_id": {
                            "type": "string",
                            "description": "Work order business key or numeric ID",
                        },
                    },
                    "required": ["work_order_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "forecast_metric",
            "description": (
                "Forecast daily shot volume or daily average cycle time from recent "
                "history using a linear trend (moving average fallback for short "
                "histories). Plant-wide or per equipment."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": ["daily_shots", "daily_avg_ct"],
                            "description": "Metric to forecast (default: daily_shots)",
                        },
                        "equipment_code": {
                            "type": "string",
                            "description": "Optional single-equipment filter",
                        },
                        "history_days": {
                            "type": "integer",
                            "description": "History window in days (default: 60)",
                        },
                        "horizon_days": {
                            "type": "integer",
                            "description": "Days to forecast (default: 14, max: 60)",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "simulate_savings",
            "description": (
                "Size the opportunity if equipment ran at a target cycle time: hours saved "
                "and extra parts possible. target='approved' compares to the approved CT; "
                "target='group_best' compares each tool to the fastest tool in its "
                "approved CT group (the fair comparison baseline)."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Analysis window in days (default: 30)",
                        },
                        "target": {
                            "type": "string",
                            "enum": ["approved", "group_best"],
                            "description": "Comparison baseline (default: approved)",
                        },
                        "equipment_code": {
                            "type": "string",
                            "description": "Optional single-equipment filter",
                        },
                        "min_shots": {
                            "type": "integer",
                            "description": "Minimum shots per record (default: 100)",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_metric_definitions",
            "description": (
                "Canonical definitions of every metric (run efficiency, MTTR, MTBF, mode "
                "CT, stop detection, NCTD, health score, ...). Use these definitions in "
                "answers so terminology stays consistent. Optionally includes the full "
                "RunRate calculation spec."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "description": "Optional single metric name filter",
                        },
                        "include_spec": {
                            "type": "boolean",
                            "description": "Include the full CALCULATION_SPEC.md text (default: false)",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "save_insight",
            "description": (
                "Persist an analysis finding so future sessions can build on it (e.g., "
                "'week 23 efficiency dip was planned maintenance on mold 4'). Becomes the "
                "institutional memory of the plant."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short insight title",
                        },
                        "content": {
                            "type": "string",
                            "description": "The finding with enough context to be useful later",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional extra tags (equipment codes, topics)",
                        },
                    },
                    "required": ["title", "content"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_insights",
            "description": (
                "Retrieve previously saved analysis insights, newest first. Check this "
                "before re-analyzing: a past session may already explain the anomaly."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Optional substring filter on title/content",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum insights to return (default: 20)",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_recent_analysis_results",
            "description": (
                "List recently executed analysis jobs with result previews. Reuse prior "
                "results for follow-up questions instead of re-running long analyses."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum jobs to return (default: 10, max: 50)",
                        },
                        "tool_name": {
                            "type": "string",
                            "description": "Optional filter to one tool name",
                        },
                    },
                }
            },
        }
    },
]
