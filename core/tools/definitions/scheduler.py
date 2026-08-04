"""
Scheduler tool definitions for job scheduling and management.

Contains 3 scheduler tools: schedule_job, list_scheduled_jobs, and cancel_job
for automated analysis scheduling and recurring report generation.
"""

from typing import Any, Dict, List

SCHEDULER_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "schedule_job",
            "description": """Schedule a recurring or one-time job for automated analysis. Perfect for daily reports, weekly summaries, or periodic data refreshes. Supports cron schedules (e.g., '0 9 * * *' for daily at 9am), intervals (e.g., '1h', '30m'), or 'once' for one-time execution. Use this to automate master table refreshes, recurring analyses, or scheduled reports.""",
            "tags": {
                "server": "scheduler",
                "domain": "planning",
                "operation": "create",
                "environment": "production",
                "security": "public",
            },
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Descriptive name for the job (e.g., 'Daily NORDPLAST Master Table Refresh')",
                        },
                        "tool_name": {
                            "type": "string",
                            "description": "Name of the tool to execute (e.g., 'refresh_master_shot_table', 'run_ct_deviation_analysis')",
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
            "description": """List all scheduled jobs with their status, next run time, and configuration. Use this to see what jobs are currently active, when they'll run next, and review their settings. Routes through Orchestrator MCP.""",
            "tags": {
                "server": "scheduler",
                "domain": "planning",
                "operation": "read",
                "environment": "production",
                "security": "public",
            },
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
            "description": """Cancel a scheduled job by ID or name. Use this to stop recurring jobs that are no longer needed or to remove incorrectly configured jobs. Routes through Orchestrator MCP.""",
            "tags": {
                "server": "scheduler",
                "domain": "planning",
                "operation": "delete",
                "environment": "production",
                "security": "public",
            },
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
