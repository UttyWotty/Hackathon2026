"""
Background Job Scheduler - Executes scheduled jobs from database.

This module polls the SQLite database for jobs that need to run and executes them.
Simple, reliable, and survives server restarts.

Architecture:
- Polls database every 60 seconds
- Finds jobs where next_run <= now and enabled = True
- Executes jobs using core/tools_config.execute_tool()
- Updates job state in database (last_run, next_run, run_count)
- Logs to audit system
- Sends metrics to monitoring

Author: Utku Gulbardak
Date: 2025-11-24
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Set

from services.infrastructure.scheduler.job_result_handler import (
    handle_job_execution_error,
    handle_job_failure,
    handle_job_success,
    log_job_execution,
)

logger = logging.getLogger(__name__)

# Constants
UNKNOWN_ERROR = "Unknown error"
POLL_INTERVAL_SECONDS = 60

# Global scheduler state
_scheduler_running = False
_running_tasks: Set[asyncio.Task] = set()  # Track running tasks to prevent GC


async def start_scheduler() -> None:
    """
    Start the background scheduler loop.

    This runs continuously, polling the database for jobs to execute.
    """
    global _scheduler_running
    _scheduler_running = True

    logger.info("Background scheduler loop starting...")

    while _scheduler_running:
        try:
            _check_and_execute_jobs()
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        except asyncio.CancelledError:
            logger.info("Scheduler loop cancelled")
            raise
        except Exception as e:
            logger.error("Scheduler loop error: %s", e, exc_info=True)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


def stop_scheduler() -> None:
    """Stop the scheduler loop."""
    global _scheduler_running
    _scheduler_running = False
    logger.info("Scheduler stop requested")


def _check_and_execute_jobs() -> None:
    """
    Check database for jobs that need to run and execute them.

    This is the main scheduler logic:
    1. Query database for enabled jobs where next_run <= now
    2. For each job, execute it in background (creates async tasks)
    3. Update job state in database

    Note: This function is synchronous but creates async tasks that run independently.
    """
    try:
        from models.database import get_session
        from models.scheduler import ScheduledJob

        with get_session() as session:
            now = datetime.now()

            jobs_to_run = (
                session.query(ScheduledJob)
                .filter(ScheduledJob.enabled)
                .filter(ScheduledJob.next_run <= now)
                .filter(ScheduledJob.status != "running")
                .all()
            )

            if jobs_to_run:
                logger.info("Found %d job(s) to execute", len(jobs_to_run))

            for job in jobs_to_run:
                task = asyncio.create_task(_execute_job_async(job.id))
                _running_tasks.add(task)
                task.add_done_callback(_running_tasks.discard)

    except Exception as e:
        logger.error("Error checking for jobs: %s", e, exc_info=True)


async def _execute_job_async(job_id: str) -> None:
    """
    Execute a single job asynchronously.

    This runs in the background so it doesn't block the scheduler loop.

    Args:
        job_id: Job ID to execute
    """
    start_time = datetime.now()

    try:
        job, execution_id = _initialize_job_execution(job_id, start_time)
        if not job:
            return

        result, execution_success, error_message = await _execute_tool(job)

        end_time = datetime.now()
        execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

        _update_job_after_execution(
            job_id,
            execution_id,
            execution_success,
            error_message,
            result,
            start_time,
            end_time,
            execution_time_ms,
        )

        await log_job_execution(
            job_id,
            job.name,
            job.tool_name,
            execution_success,
            error_message,
            start_time,
        )

    except Exception as e:
        logger.error("Fatal error executing job %s: %s", job_id, e, exc_info=True)
        handle_job_execution_error(job_id, e)


def _initialize_job_execution(job_id: str, start_time: datetime) -> tuple:
    """
    Initialize job execution by loading job and creating history record.

    Args:
        job_id: The job ID to load.
        start_time: Execution start timestamp.

    Returns:
        Tuple of (job, execution_id) or (None, None) if job not found.
    """
    import uuid

    from models.database import get_session
    from models.scheduler import JobExecutionHistory, ScheduledJob

    with get_session() as session:
        job = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()

        if not job:
            logger.error("Job %s not found in database", job_id)
            return None, None

        logger.info("Executing job: %s (tool: %s)", job.name, job.tool_name)

        execution_id = str(uuid.uuid4())
        history_record = JobExecutionHistory(
            id=execution_id,
            job_id=job.id,
            job_name=job.name,
            tool_name=job.tool_name,
            started_at=start_time,
            arguments=job.arguments or {},
            status="running",
        )
        session.add(history_record)

        job.status = "running"
        job.last_run = start_time
        session.commit()

        return job, execution_id


async def _execute_tool(job: Any) -> tuple:
    """
    Execute the tool for a job.

    Args:
        job: ScheduledJob ORM instance with tool_name and arguments.

    Returns:
        Tuple of (result, execution_success, error_message).
    """
    from services.infrastructure.scheduler.tool_dispatcher import dispatch_tool_direct

    try:
        result = await dispatch_tool_direct(job.tool_name, job.arguments or {})
        execution_success = result.get("status") == "success"
        error_message = (
            result.get("error", UNKNOWN_ERROR) if not execution_success else None
        )
        return result, execution_success, error_message

    except Exception as e:
        logger.error("Tool execution failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}, False, str(e)


def _update_job_after_execution(
    job_id: str,
    execution_id: str,
    execution_success: bool,
    error_message: Optional[str],
    result: Optional[Dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    execution_time_ms: int,
) -> None:
    """
    Update job and history records after execution.

    Delegates to handle_job_success or handle_job_failure from
    the job_result_handler module.

    Args:
        job_id: Job ID.
        execution_id: Execution history record ID.
        execution_success: Whether the tool execution succeeded.
        error_message: Error description if failed, or None.
        result: Tool execution result dictionary.
        start_time: Execution start timestamp.
        end_time: Execution end timestamp.
        execution_time_ms: Duration in milliseconds.
    """
    from models.database import get_session
    from models.scheduler import JobExecutionHistory, ScheduledJob

    with get_session() as session:
        job = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        history_record = (
            session.query(JobExecutionHistory)
            .filter(JobExecutionHistory.id == execution_id)
            .first()
        )

        if not job or not history_record:
            return

        if execution_success:
            handle_job_success(
                job,
                history_record,
                result,
                start_time,
                end_time,
                execution_time_ms,
            )
        else:
            handle_job_failure(
                job,
                history_record,
                error_message,
                result,
                start_time,
                end_time,
                execution_time_ms,
            )

        session.commit()


def _calculate_next_run(
    schedule: str, from_time: Optional[datetime] = None
) -> datetime:
    """
    Calculate next run time based on schedule string.

    Supports:
    - Cron format: '0 2 * * *' (daily at 2am) - requires croniter
    - Interval: '1h', '30m', '7d'
    - Once: 'once' (immediate)

    Args:
        schedule: Schedule string.
        from_time: Calculate from this time (defaults to now).

    Returns:
        Next run datetime.
    """
    if from_time is None:
        from_time = datetime.now()

    if schedule == "once":
        return from_time

    # Interval parsing (simple and reliable)
    if schedule.endswith("m"):
        minutes = int(schedule[:-1])
        return from_time + timedelta(minutes=minutes)
    elif schedule.endswith("h"):
        hours = int(schedule[:-1])
        return from_time + timedelta(hours=hours)
    elif schedule.endswith("d"):
        days = int(schedule[:-1])
        return from_time + timedelta(days=days)
    elif schedule.endswith("w"):
        weeks = int(schedule[:-1])
        return from_time + timedelta(weeks=weeks)

    # Try cron format if croniter is available
    try:
        from croniter import croniter  # type: ignore[import-untyped]

        cron = croniter(schedule, from_time)
        return cron.get_next(datetime)
    except ImportError:
        logger.warning("croniter not installed, cannot parse cron: %s", schedule)
        return from_time + timedelta(days=1)
    except Exception as e:
        logger.error("Invalid schedule format: %s - %s", schedule, e)
        return from_time + timedelta(days=1)
