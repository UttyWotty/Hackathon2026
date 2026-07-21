"""Service-layer CRUD for scheduled jobs, used by the MCP tool dispatcher.

Provides schedule_job, list_scheduled_jobs, and cancel_job as plain functions over
the ScheduledJob SQLite model, mirroring the scheduler router behavior without HTTP.
Returns plain result dicts so callers (dispatcher, scheduler) need no FastAPI context.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from models.database import get_session
from models.scheduler import ScheduledJob

logger = logging.getLogger(__name__)

STATUS_SCHEDULED: str = "scheduled"
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_BACKOFF: int = 60


def schedule_job(
    name: str,
    tool_name: str,
    schedule: str,
    arguments: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create and persist a scheduled job.

    Args:
        name: Descriptive job name.
        tool_name: MCP tool to execute on each run.
        schedule: Cron expression, interval ('1h', '30m'), or 'once'.
        arguments: Arguments passed to the tool on execution (default: empty dict).

    Returns:
        dict: status and the created job record.
    """
    from services.infrastructure.scheduler.background_scheduler import (
        _calculate_next_run,
    )

    try:
        with get_session() as session:
            job = ScheduledJob(
                id=str(uuid.uuid4()),
                name=name,
                tool_name=tool_name,
                arguments=arguments or {},
                schedule=schedule,
                enabled=True,
                next_run=_calculate_next_run(schedule),
                status=STATUS_SCHEDULED,
                max_retries=DEFAULT_MAX_RETRIES,
                retry_backoff=DEFAULT_RETRY_BACKOFF,
                retry_count=0,
            )
            session.add(job)
            session.commit()
            result = job.to_dict()
        return {"status": "success", "job": result}
    except Exception as e:
        logger.error("schedule_job failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


def list_scheduled_jobs() -> Dict[str, Any]:
    """List all scheduled jobs ordered by next run time.

    Returns:
        dict: status, total_jobs, and the job records.
    """
    try:
        with get_session() as session:
            jobs = session.query(ScheduledJob).order_by(ScheduledJob.next_run).all()
            result_jobs = [job.to_dict() for job in jobs]
        return {
            "status": "success",
            "total_jobs": len(result_jobs),
            "jobs": result_jobs,
        }
    except Exception as e:
        logger.error("list_scheduled_jobs failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


def cancel_job(job_id: str) -> Dict[str, Any]:
    """Delete a scheduled job by ID or by exact name.

    Args:
        job_id: Job UUID or job name.

    Returns:
        dict: status and the deleted job id, or an error if not found.
    """
    try:
        with get_session() as session:
            job = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
            if job is None:
                job = (
                    session.query(ScheduledJob)
                    .filter(ScheduledJob.name == job_id)
                    .first()
                )
            if job is None:
                return {"status": "error", "error": "Job not found: %s" % job_id}
            deleted_id = job.id
            deleted_name = job.name
            session.delete(job)
            session.commit()
        return {"status": "success", "deleted_job_id": deleted_id, "name": deleted_name}
    except Exception as e:
        logger.error("cancel_job failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
