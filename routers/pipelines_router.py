"""
Pipelines Router -- REST API endpoints for triggering data pipeline operations.
Pipelines run as background jobs; callers receive a job_id immediately and poll for status.
Provides endpoints for master_shot_table, ana_shot_made, roi, and run_rate pipelines.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from routers.pipeline_job_store import (
    JobRecord,
    JobStatus,
    create_job,
    get_job,
    list_jobs,
    mark_completed,
    mark_running,
)
from services.config.features.analytics.pipelines.shared_config import (
    PipelineConfig,
    get_snowflake_connector,
    get_snowflake_session,
)

logger = logging.getLogger(__name__)
router = APIRouter()  # prefix and tags set in app/routers.py


class PipelineRequest(BaseModel):
    """Request model for pipeline execution."""

    incremental: bool = Field(
        default=True,
        description="True for incremental mode, False for full historical load",
    )
    start_date: Optional[str] = Field(
        default=None, description="Start date (YYYY-MM-DD) for full mode"
    )
    schema_name: Optional[str] = Field(
        default=None, description="Override schema name (e.g., CLIENT_A, CLIENT_B)"
    )

    @property
    def mode(self) -> str:
        """Get mode string from incremental boolean."""
        return "incremental" if self.incremental else "full"


class PipelineJobAccepted(BaseModel):
    """Immediate response when a pipeline job is accepted for background execution."""

    job_id: str
    pipeline: str
    mode: str
    status: str
    message: str


class PipelineJobDetail(BaseModel):
    """Full detail of a pipeline job retrieved via the jobs endpoint."""

    job_id: str
    pipeline_name: str
    mode: str
    schema_name: Optional[str] = None
    status: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    message: Optional[str] = None
    execution_time_seconds: Optional[float] = None


class PipelineResponse(BaseModel):
    """Response model for synchronous pipeline execution (used by run-all)."""

    status: str
    pipeline: str
    mode: str
    incremental: bool
    schema_name: Optional[str] = None
    message: str
    timestamp: str
    execution_time_seconds: Optional[float] = None


class PipelineStatusResponse(BaseModel):
    """Response model for pipeline status check."""

    pipeline: str
    table_name: str
    total_rows: int
    min_date: Optional[str] = None
    max_date: Optional[str] = None


OVERLAP_DAYS = 7

VALID_PIPELINES = frozenset(
    {
        "master_shot_table",
        "ana_shot_made",
        "roi",
        "run_rate",
    }
)


def _execute_pipeline(pipeline_name: str, request: PipelineRequest) -> bool:
    """
    Execute a specific pipeline and return success boolean.

    Handles Snowflake session lifecycle internally.
    Raises ValueError for unknown pipeline names.
    """
    session = None
    sf_conn = None
    end_date = datetime.now().strftime("%Y-%m-%d")

    try:
        session = get_snowflake_session(schema=request.schema_name)
        sf_conn = get_snowflake_connector(schema=request.schema_name)

        config = PipelineConfig(
            overlap_days=OVERLAP_DAYS,
            start_date=request.start_date,
            end_date=end_date,
            schema_name=request.schema_name,
        )

        return _dispatch_pipeline(pipeline_name, request, session, sf_conn, config)

    finally:
        if sf_conn:
            sf_conn.close()
        if session:
            session.close()


def _dispatch_pipeline(
    pipeline_name: str,
    request: PipelineRequest,
    session: object,
    sf_conn: object,
    config: PipelineConfig,
) -> bool:
    """Route to the correct pipeline implementation and return success."""
    if pipeline_name == "master_shot_table":
        from services.config.features.analytics.pipelines.master_shot_table.pipeline import (
            MasterShotPipeline,
        )

        pipeline = MasterShotPipeline(session, sf_conn, config)
        if request.mode == "full":
            return pipeline.process_all_chunks(parallel=True, full_load=True)
        return pipeline.process_incremental(OVERLAP_DAYS)

    if pipeline_name == "ana_shot_made":
        from services.config.features.analytics.pipelines.ana_shot_made.main import run

        return run(
            full_historical_load=(request.mode == "full"),
            schema_name=request.schema_name,
        )

    if pipeline_name == "roi":
        from services.config.features.analytics.pipelines.roi.main import run

        return run(
            full_historical_load=(request.mode == "full"),
            schema_name=request.schema_name,
        )

    if pipeline_name == "run_rate":
        from services.config.features.analytics.pipelines.run_rate.main import run

        return run(
            full_historical_load=(request.mode == "full"),
            schema_name=request.schema_name,
        )

    raise ValueError("Unknown pipeline: %s" % pipeline_name)


def _run_pipeline_background(
    job_id: str, pipeline_name: str, request: PipelineRequest
) -> None:
    """Background task wrapper: marks the job running, executes, and records the outcome."""
    start_time = datetime.now()
    mark_running(job_id)
    logger.info("Job %s started for pipeline %s", job_id, pipeline_name)

    try:
        success = _execute_pipeline(pipeline_name, request)
        execution_time = (datetime.now() - start_time).total_seconds()
        message = "Pipeline %s completed %s" % (
            pipeline_name,
            "successfully" if success else "with errors",
        )
        mark_completed(
            job_id,
            success=success,
            message=message,
            execution_time_seconds=execution_time,
        )
        logger.info("Job %s finished: %s (%.1fs)", job_id, message, execution_time)

    except Exception as exc:
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            "Job %s failed for pipeline %s: %s",
            job_id,
            pipeline_name,
            exc,
            exc_info=True,
        )
        mark_completed(
            job_id,
            success=False,
            message=str(exc),
            execution_time_seconds=execution_time,
        )


def _job_record_to_detail(record: JobRecord) -> PipelineJobDetail:
    """Convert an internal JobRecord to the API response model."""
    return PipelineJobDetail(
        job_id=record.job_id,
        pipeline_name=record.pipeline_name,
        mode=record.mode,
        schema_name=record.schema_name,
        status=record.status.value,
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        message=record.message,
        execution_time_seconds=record.execution_time_seconds,
    )


@router.get("/")
async def list_pipelines():
    """List all available pipelines."""
    return {
        "pipelines": [
            {
                "name": "master_shot_table",
                "table": "MASTER_SHOT_TABLE",
                "description": "Foundation table with shot-to-part resolution",
            },
            {
                "name": "ana_shot_made",
                "table": "ANA_SHOT_MADE_TABLE",
                "description": "Session analytics and cycle time metrics",
            },
            {
                "name": "roi",
                "table": "ROI",
                "description": "ROI calculations with shot counts and volumes",
            },
            {
                "name": "run_rate",
                "table": "RUNRATE",
                "description": "Run rate metrics with MTTR/MTBF calculations",
            },
        ]
    }


@router.post(
    "/master-shot-table/run", response_model=PipelineJobAccepted, status_code=202
)
async def run_master_shot_table(
    request: PipelineRequest, background_tasks: BackgroundTasks
):
    """
    Run the Master Shot Table pipeline in the background.

    Returns immediately with a job_id. Poll /jobs/{job_id} for status.
    This is the foundation pipeline that must run before other pipelines.
    """
    return _enqueue_pipeline("master_shot_table", request, background_tasks)


@router.post("/ana-shot-made/run", response_model=PipelineJobAccepted, status_code=202)
async def run_ana_shot_made(
    request: PipelineRequest, background_tasks: BackgroundTasks
):
    """Run the ANA_SHOT_MADE pipeline in the background. Poll /jobs/{job_id} for status."""
    return _enqueue_pipeline("ana_shot_made", request, background_tasks)


@router.post("/roi/run", response_model=PipelineJobAccepted, status_code=202)
async def run_roi(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Run the ROI pipeline in the background. Poll /jobs/{job_id} for status."""
    return _enqueue_pipeline("roi", request, background_tasks)


@router.post("/run-rate/run", response_model=PipelineJobAccepted, status_code=202)
async def run_run_rate(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Run the RUNRATE pipeline in the background. Poll /jobs/{job_id} for status."""
    return _enqueue_pipeline("run_rate", request, background_tasks)


@router.post("/run-all", response_model=List[PipelineJobAccepted], status_code=202)
async def run_all_pipelines(
    request: PipelineRequest, background_tasks: BackgroundTasks
):
    """
    Enqueue all pipelines for sequential background execution.

    Order: master_shot_table -> ana_shot_made -> roi -> run_rate.
    Returns a list of accepted job references.
    """
    pipeline_order = ["master_shot_table", "ana_shot_made", "roi", "run_rate"]
    accepted: List[PipelineJobAccepted] = []

    for pipeline_name in pipeline_order:
        result = _enqueue_pipeline(pipeline_name, request, background_tasks)
        accepted.append(result)

    return accepted


def _enqueue_pipeline(
    pipeline_name: str,
    request: PipelineRequest,
    background_tasks: BackgroundTasks,
) -> PipelineJobAccepted:
    """Create a job record, schedule it on BackgroundTasks, and return the accepted response."""
    if pipeline_name not in VALID_PIPELINES:
        raise HTTPException(
            status_code=404, detail="Unknown pipeline: %s" % pipeline_name
        )

    job = create_job(
        pipeline_name=pipeline_name,
        mode=request.mode,
        schema_name=request.schema_name,
    )

    background_tasks.add_task(
        _run_pipeline_background, job.job_id, pipeline_name, request
    )

    return PipelineJobAccepted(
        job_id=job.job_id,
        pipeline=pipeline_name,
        mode=request.mode,
        status=JobStatus.PENDING.value,
        message="Pipeline %s accepted. Poll /pipelines/jobs/%s for status."
        % (pipeline_name, job.job_id),
    )


@router.get("/jobs", response_model=List[PipelineJobDetail])
async def list_pipeline_jobs():
    """List all tracked pipeline jobs, newest first."""
    return [_job_record_to_detail(r) for r in list_jobs()]


@router.get("/jobs/{job_id}", response_model=PipelineJobDetail)
async def get_pipeline_job(job_id: str):
    """Get the current status of a specific pipeline job."""
    record = get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found: %s" % job_id)
    return _job_record_to_detail(record)


PIPELINE_TABLE_MAPPING: dict = {
    "master_shot_table": "MASTER_SHOT_TABLE",
    "ana_shot_made": "ANA_SHOT_MADE_TABLE",
    "roi": "ROI",
    "run_rate": "RUNRATE",
}

# Tables differ in which time column they carry (e.g., the deployed RUNRATE
# table is weekly-aggregated with START_DATE, while shot-level tables use
# LOCAL_SHOT_TIME), so the status endpoint resolves it per table at runtime.
TIME_COLUMN_CANDIDATES: tuple = ("LOCAL_SHOT_TIME", "START_DATE", "DATE", "UPLOAD_TIME")


def _resolve_time_column(session: object, table_name: str) -> Optional[str]:
    """Return the first known time column present on the table, or None."""
    columns_query = f"""
    SELECT COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = '{table_name}'
      AND TABLE_SCHEMA = CURRENT_SCHEMA()
    """
    present = {row[0] for row in session.sql(columns_query).collect()}
    for candidate in TIME_COLUMN_CANDIDATES:
        if candidate in present:
            return candidate
    return None


@router.get("/status/{pipeline_name}", response_model=PipelineStatusResponse)
async def get_pipeline_status(pipeline_name: str):
    """Get the status/statistics of a pipeline's target table."""
    if pipeline_name not in PIPELINE_TABLE_MAPPING:
        raise HTTPException(
            status_code=404, detail=f"Unknown pipeline: {pipeline_name}"
        )

    table_name = PIPELINE_TABLE_MAPPING[pipeline_name]
    session = None

    try:
        session = get_snowflake_session()

        time_column = _resolve_time_column(session, table_name)
        if time_column:
            stats_query = f"""
            SELECT
                COUNT(*) as total_rows,
                MIN({time_column}) as min_date,
                MAX({time_column}) as max_date
            FROM {table_name}
            """
        else:
            logger.warning(
                "No known time column on table %s; returning row count only", table_name
            )
            stats_query = f"""
            SELECT
                COUNT(*) as total_rows,
                NULL as min_date,
                NULL as max_date
            FROM {table_name}
            """

        result = session.sql(stats_query).collect()

        if result:
            return PipelineStatusResponse(
                pipeline=pipeline_name,
                table_name=table_name,
                total_rows=result[0][0] or 0,
                min_date=str(result[0][1]) if result[0][1] else None,
                max_date=str(result[0][2]) if result[0][2] else None,
            )
        else:
            return PipelineStatusResponse(
                pipeline=pipeline_name,
                table_name=table_name,
                total_rows=0,
            )

    except Exception as e:
        logger.error(f"Error getting pipeline status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if session:
            session.close()
