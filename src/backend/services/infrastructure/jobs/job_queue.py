"""Job Queue Manager for Background Task Execution.

Handles async execution of long-running analysis tasks with status tracking.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class JobStatus:
    """Job status constants."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job:
    """Represents a background job."""

    def __init__(self, job_id: str, tool_name: str, arguments: Dict[str, Any]):
        self.job_id = job_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.status = JobStatus.PENDING
        self.result = None
        self.error = None
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.progress = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary."""
        return {
            "job_id": self.job_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "progress": self.progress,
        }


class JobQueue:
    """Manages background job execution.

    Provides async job submission, execution, and status tracking.
    """

    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def submit_job(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        executor_func: Callable,
    ) -> str:
        """Submit a job for background execution.

        Args:
            tool_name: Name of the tool/analysis to run
            arguments: Tool arguments
            executor_func: Async function to execute

        Returns:
            job_id: Unique job identifier
        """
        job_id = str(uuid4())
        job = Job(job_id, tool_name, arguments)

        async with self._lock:
            self.jobs[job_id] = job

        # Execute job in background
        asyncio.create_task(self._execute_job(job, executor_func))
        logger.info(f"Job submitted: {job_id} ({tool_name})")
        return job_id

    async def _execute_job(self, job: Job, executor_func: Callable):
        """Execute a job in the background.

        Ensures job state is always updated, even on unexpected failures.

        Args:
            job: Job to execute
            executor_func: Function to execute
        """
        # Ensure started_at is always set
        job.started_at = datetime.now()
        try:
            job.status = JobStatus.RUNNING
            logger.info(f"Job started: {job.job_id}")

            # Execute the function
            result = await executor_func(job.tool_name, job.arguments)

            # Success path - update job state
            job.status = JobStatus.COMPLETED
            job.result = result
            job.completed_at = datetime.now()
            job.progress = 100

            duration = (job.completed_at - job.started_at).total_seconds()
            logger.info(f"Job completed: {job.job_id} ({duration:.1f}s)")
        except asyncio.CancelledError:
            # Handle cancellation gracefully
            job.status = JobStatus.FAILED
            job.error = "Job was cancelled"
            job.completed_at = datetime.now()
            logger.warning(f"Job cancelled: {job.job_id}")
            raise  # Re-raise to properly handle cancellation
        except Exception as e:
            # Ensure job state is always updated on any exception
            try:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = datetime.now()
                logger.error(f"Job failed: {job.job_id} - {e}", exc_info=True)
            except Exception as state_error:
                # If updating state fails, log it but don't crash
                logger.critical(
                    f"Critical: Failed to update job state for {job.job_id}: {state_error}",
                    exc_info=True,
                )

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status and result.

        Args:
            job_id: Job identifier

        Returns:
            Job status dictionary or None if not found
        """
        async with self._lock:
            job = self.jobs.get(job_id)
            if job:
                return job.to_dict()
            return None

    async def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent jobs.

        Args:
            limit: Maximum number of jobs to return

        Returns:
            List of job dictionaries
        """
        async with self._lock:
            jobs_list = sorted(
                self.jobs.values(), key=lambda j: j.created_at, reverse=True
            )[:limit]
            return [job.to_dict() for job in jobs_list]

    async def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Remove old completed/failed jobs.

        Args:
            max_age_hours: Maximum age of jobs to keep (hours)
        """
        now = datetime.now()
        async with self._lock:
            jobs_to_remove = []
            for job_id, job in self.jobs.items():
                if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                    age_hours = (now - job.created_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        jobs_to_remove.append(job_id)

            for job_id in jobs_to_remove:
                del self.jobs[job_id]

            if jobs_to_remove:
                logger.info(f"Cleaned up {len(jobs_to_remove)} old jobs")

    async def start_periodic_cleanup(
        self, cleanup_interval_hours: int = 1, max_age_hours: int = 24
    ):
        """Start periodic cleanup of old jobs.

        This runs continuously in the background to prevent memory leaks.

        Args:
            cleanup_interval_hours: How often to run cleanup (hours)
            max_age_hours: Maximum age of jobs to keep (hours)
        """
        cleanup_interval_seconds = cleanup_interval_hours * 3600

        while True:
            try:
                await asyncio.sleep(cleanup_interval_seconds)
                await self.cleanup_old_jobs(max_age_hours=max_age_hours)
            except asyncio.CancelledError:
                logger.info("Job queue cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in job queue cleanup: {e}", exc_info=True)
                # Continue cleanup loop even on error
                await asyncio.sleep(60)  # Wait 1 minute before retrying


# Global job queue instance
_job_queue = None


def get_job_queue() -> JobQueue:
    """Get the global job queue instance."""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue()
    return _job_queue
