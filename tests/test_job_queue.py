"""
Tests for Job Queue functionality.

Tests critical job queue operations including:
- Job submission
- Status tracking
- Error handling
- Cleanup operations
"""

import asyncio
from datetime import datetime, timedelta

import pytest  # type: ignore[import-untyped]

from services.infrastructure.jobs.job_queue import (
    Job,
    JobQueue,
    JobStatus,
    get_job_queue,
)


@pytest.fixture
def job_queue():
    """Create a fresh job queue for testing."""
    return JobQueue()


@pytest.fixture
def sample_executor():
    """Sample executor function for testing."""

    async def executor(tool_name: str, arguments: dict):
        await asyncio.sleep(0.1)  # Simulate work
        return {"status": "success", "result": "test_result"}

    return executor


@pytest.mark.asyncio
async def test_submit_job(job_queue, sample_executor):
    """Test job submission."""
    job_id = await job_queue.submit_job(
        tool_name="test_tool",
        arguments={"param": "value"},
        executor_func=sample_executor,
    )

    assert job_id is not None
    assert len(job_id) > 0

    # Check job status
    status = await job_queue.get_job_status(job_id)
    assert status is not None
    assert status["tool_name"] == "test_tool"
    assert status["status"] == JobStatus.PENDING


@pytest.mark.asyncio
async def test_job_execution(job_queue, sample_executor):
    """Test job execution and completion."""
    job_id = await job_queue.submit_job(
        tool_name="test_tool",
        arguments={"param": "value"},
        executor_func=sample_executor,
    )

    # Wait for job to complete
    await asyncio.sleep(0.2)

    status = await job_queue.get_job_status(job_id)
    assert status is not None
    assert status["status"] == JobStatus.COMPLETED
    assert status["result"] == {"status": "success", "result": "test_result"}


@pytest.mark.asyncio
async def test_job_error_handling(job_queue):
    """Test job error handling."""

    async def failing_executor(tool_name: str, arguments: dict):
        raise ValueError("Test error")

    job_id = await job_queue.submit_job(
        tool_name="failing_tool",
        arguments={},
        executor_func=failing_executor,
    )

    # Wait for job to fail
    await asyncio.sleep(0.2)

    status = await job_queue.get_job_status(job_id)
    assert status is not None
    assert status["status"] == JobStatus.FAILED
    assert "Test error" in status["error"]


@pytest.mark.asyncio
async def test_job_status_tracking(job_queue, sample_executor):
    """Test job status tracking through lifecycle."""
    job_id = await job_queue.submit_job(
        tool_name="test_tool",
        arguments={},
        executor_func=sample_executor,
    )

    # Initially pending
    status = await job_queue.get_job_status(job_id)
    assert status["status"] == JobStatus.PENDING

    # Wait for completion
    await asyncio.sleep(0.2)

    status = await job_queue.get_job_status(job_id)
    assert status["status"] == JobStatus.COMPLETED
    assert status["started_at"] is not None
    assert status["completed_at"] is not None
    assert status["progress"] == 100


@pytest.mark.asyncio
async def test_cleanup_old_jobs(job_queue):
    """Test cleanup of old jobs."""
    # Create old completed job
    old_job = Job(job_id="old_job", tool_name="test", arguments={})
    old_job.status = JobStatus.COMPLETED
    old_job.created_at = datetime.now() - timedelta(hours=25)  # 25 hours ago
    old_job.completed_at = datetime.now() - timedelta(hours=25)

    job_queue.jobs["old_job"] = old_job

    # Create recent job
    recent_job = Job(job_id="recent_job", tool_name="test", arguments={})
    recent_job.status = JobStatus.COMPLETED
    recent_job.created_at = datetime.now() - timedelta(hours=1)  # 1 hour ago
    recent_job.completed_at = datetime.now() - timedelta(hours=1)

    job_queue.jobs["recent_job"] = recent_job

    # Cleanup jobs older than 24 hours
    await job_queue.cleanup_old_jobs(max_age_hours=24)

    # Old job should be removed
    assert "old_job" not in job_queue.jobs

    # Recent job should remain
    assert "recent_job" in job_queue.jobs


@pytest.mark.asyncio
async def test_list_jobs(job_queue, sample_executor):
    """Test listing jobs."""
    # Submit multiple jobs
    job_ids = []
    for i in range(5):
        job_id = await job_queue.submit_job(
            tool_name=f"tool_{i}",
            arguments={"index": i},
            executor_func=sample_executor,
        )
        job_ids.append(job_id)

    # Wait for jobs to complete
    await asyncio.sleep(0.3)

    # List jobs
    jobs = await job_queue.list_jobs(limit=10)
    assert len(jobs) >= 5

    # Check that all submitted jobs are in the list
    listed_job_ids = [job["job_id"] for job in jobs]
    for job_id in job_ids:
        assert job_id in listed_job_ids


@pytest.mark.asyncio
async def test_get_job_queue_singleton():
    """Test that get_job_queue returns singleton instance."""
    queue1 = get_job_queue()
    queue2 = get_job_queue()

    assert queue1 is queue2


@pytest.mark.asyncio
async def test_job_to_dict(job_queue):
    """Test job dictionary conversion."""
    job = Job(job_id="test_job", tool_name="test_tool", arguments={"key": "value"})

    job_dict = job.to_dict()

    assert job_dict["job_id"] == "test_job"
    assert job_dict["tool_name"] == "test_tool"
    assert job_dict["arguments"] == {"key": "value"}
    assert job_dict["status"] == JobStatus.PENDING
    assert "created_at" in job_dict
