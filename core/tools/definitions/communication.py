"""
Communication tool definitions for email and notification operations.

Contains 1 email tool: send_email_report for sending analysis reports with attachments.
"""

from typing import Any, Dict, List

COMMUNICATION_TOOLS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "send_email_report",
            "description": "Send analysis report files (Excel, HTML, PowerPoint) via email with custom body text. Use this when user requests to email results, insights, recommendations, or send reports to a specific email address. ALWAYS include insights/recommendations in the custom_body parameter. Attach ALL available files including Excel reports, HTML summaries, and PowerPoint presentations.",
            "tags": {
                "server": "email",
                "domain": "communication",
                "operation": "write",
                "environment": "production",
                "security": "public",
            },
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
                            "description": "List of file paths to attach (Excel, HTML, PowerPoint/PPT reports from previous analysis). Include ALL available output files.",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject line (optional, will auto-generate if not provided)",
                        },
                        "analysis_type": {
                            "type": "string",
                            "description": "Type of analysis being sent (e.g., 'ROI', 'Runrate', 'Capacity') for context",
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
