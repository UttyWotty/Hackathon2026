"""Recent analysis results retrieval tool adapter.

Lists recently executed background tool jobs with truncated result previews so
follow-up questions can reuse prior analysis output instead of re-running it.
Exposes the get_recent_analysis_results MCP tool.
"""

import json
import logging
from typing import Any, Dict, Optional

from services.infrastructure.jobs.job_queue import get_job_queue

logger = logging.getLogger(__name__)

DEFAULT_LIMIT: int = 10
MAX_LIMIT: int = 50
RESULT_PREVIEW_CHARS: int = 2000


def _preview(result: Any) -> Optional[str]:
    """Truncated JSON preview of a job result."""
    if result is None:
        return None
    text = json.dumps(result, default=str)
    if len(text) <= RESULT_PREVIEW_CHARS:
        return text
    return text[:RESULT_PREVIEW_CHARS] + "...(truncated)"


async def get_recent_analysis_results(
    limit: int = DEFAULT_LIMIT, tool_name: Optional[str] = None
) -> Dict[str, Any]:
    """List recent background tool runs and their result previews.

    Args:
        limit: Maximum jobs to return (default: 10, max: 50).
        tool_name: Optional filter to one tool (e.g., run_deviation_analysis).

    Returns:
        dict with job records: tool, status, timings, and a truncated result
        preview. Full results remain available via /mcp/tools/jobs/{job_id}.
    """
    try:
        limit = max(1, min(int(limit), MAX_LIMIT))
        queue = get_job_queue()
        jobs = await queue.list_jobs(limit=MAX_LIMIT)
        if tool_name:
            jobs = [j for j in jobs if j.get("tool_name") == tool_name]

        results = [
            {
                "job_id": j.get("job_id"),
                "tool_name": j.get("tool_name"),
                "status": j.get("status"),
                "created_at": j.get("created_at"),
                "completed_at": j.get("completed_at"),
                "error": j.get("error"),
                "result_preview": _preview(j.get("result")),
            }
            for j in jobs[:limit]
        ]
        return {
            "status": "success",
            "count": len(results),
            "jobs": results,
            "notes": "Jobs are kept in memory for 24 hours; full results via /mcp/tools/jobs/{job_id}.",
        }
    except Exception as e:
        logger.error("get_recent_analysis_results failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
