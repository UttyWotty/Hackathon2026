"""
Pipeline MCP Tools
==================

Provides MCP tools for triggering data pipeline operations.
Wraps the pipeline modules for LLM tool calling integration.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def run_master_shot_pipeline(
    incremental: bool = True,
    start_date: Optional[str] = None,
    schema_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the Master Shot Table pipeline.

    This is the foundation pipeline that transforms raw shot data into
    the MASTER_SHOT_TABLE. Must run before other dependent pipelines.

    Args:
        incremental: True for incremental mode, False for full historical load
        start_date: Start date for full mode (YYYY-MM-DD)
        schema_name: Override schema name (e.g., CLIENT_A, CLIENT_B)

    Returns:
        Dictionary with execution results
    """
    from services.config.features.analytics.pipelines.master_shot_table.pipeline import (
        MasterShotPipeline,
    )
    from services.config.features.analytics.pipelines.shared_config import (
        PipelineConfig,
        get_snowflake_connector,
        get_snowflake_session,
    )

    start_time = datetime.now()
    session = None
    sf_conn = None
    overlap_days = 7
    end_date = datetime.now().strftime("%Y-%m-%d")
    mode = "incremental" if incremental else "full"

    try:
        session = get_snowflake_session(schema=schema_name)
        sf_conn = get_snowflake_connector(schema=schema_name)

        config = PipelineConfig(
            overlap_days=overlap_days,
            start_date=start_date,
            end_date=end_date,
            schema_name=schema_name,
        )

        pipeline = MasterShotPipeline(session, sf_conn, config)

        if mode == "full":
            success = pipeline.process_all_chunks(parallel=True, full_load=True)
        else:
            success = pipeline.process_incremental(overlap_days)

        execution_time = (datetime.now() - start_time).total_seconds()

        return {
            "status": "success" if success else "error",
            "pipeline": "master_shot_table",
            "table": "MASTER_SHOT_TABLE",
            "mode": mode,
            "incremental": incremental,
            "schema_name": schema_name,
            "message": f"Pipeline completed {'successfully' if success else 'with errors'}",
            "execution_time_seconds": execution_time,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Master Shot pipeline failed: {e}", exc_info=True)
        return {
            "status": "error",
            "pipeline": "master_shot_table",
            "mode": mode,
            "incremental": incremental,
            "schema_name": schema_name,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }

    finally:
        if sf_conn:
            sf_conn.close()
        if session:
            session.close()


def run_ana_shot_made_pipeline(
    incremental: bool = True,
    schema_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the ANA_SHOT_MADE pipeline.

    Creates session analytics and cycle time metrics.

    Args:
        incremental: True for incremental mode, False for full historical load
        schema_name: Override schema name (e.g., CLIENT_A, CLIENT_B)

    Returns:
        Dictionary with execution results
    """
    start_time = datetime.now()
    mode = "incremental" if incremental else "full"

    try:
        from services.config.features.analytics.pipelines.ana_shot_made.main import run

        success = run(full_historical_load=(not incremental), schema_name=schema_name)
        execution_time = (datetime.now() - start_time).total_seconds()

        return {
            "status": "success" if success else "error",
            "pipeline": "ana_shot_made",
            "table": "ANA_SHOT_MADE_TABLE",
            "mode": mode,
            "incremental": incremental,
            "schema_name": schema_name,
            "message": f"Pipeline completed {'successfully' if success else 'with errors'}",
            "execution_time_seconds": execution_time,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"ANA_SHOT_MADE pipeline failed: {e}", exc_info=True)
        return {
            "status": "error",
            "pipeline": "ana_shot_made",
            "mode": mode,
            "incremental": incremental,
            "schema_name": schema_name,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }


def run_roi_pipeline(
    incremental: bool = True,
    schema_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the ROI pipeline.

    Creates ROI calculations with shot counts and volumes.

    Args:
        incremental: True for incremental mode, False for full historical load
        schema_name: Override schema name (e.g., CLIENT_A, CLIENT_B)

    Returns:
        Dictionary with execution results
    """
    start_time = datetime.now()
    mode = "incremental" if incremental else "full"

    try:
        from services.config.features.analytics.pipelines.roi.main import run

        success = run(full_historical_load=(not incremental), schema_name=schema_name)
        execution_time = (datetime.now() - start_time).total_seconds()

        return {
            "status": "success" if success else "error",
            "pipeline": "roi",
            "table": "ROI",
            "mode": mode,
            "incremental": incremental,
            "schema_name": schema_name,
            "message": f"Pipeline completed {'successfully' if success else 'with errors'}",
            "execution_time_seconds": execution_time,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"ROI pipeline failed: {e}", exc_info=True)
        return {
            "status": "error",
            "pipeline": "roi",
            "mode": mode,
            "incremental": incremental,
            "schema_name": schema_name,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }


def run_runrate_pipeline(
    incremental: bool = True,
    schema_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the RUNRATE pipeline.

    Creates run rate metrics with MTTR/MTBF calculations.

    Args:
        incremental: True for incremental mode, False for full historical load
        schema_name: Override schema name (e.g., CLIENT_A, CLIENT_B)

    Returns:
        Dictionary with execution results
    """
    start_time = datetime.now()
    mode = "incremental" if incremental else "full"

    try:
        from services.config.features.analytics.pipelines.run_rate.main import run

        success = run(full_historical_load=(not incremental), schema_name=schema_name)
        execution_time = (datetime.now() - start_time).total_seconds()

        return {
            "status": "success" if success else "error",
            "pipeline": "run_rate",
            "table": "RUNRATE",
            "mode": mode,
            "incremental": incremental,
            "schema_name": schema_name,
            "message": f"Pipeline completed {'successfully' if success else 'with errors'}",
            "execution_time_seconds": execution_time,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"RUNRATE pipeline failed: {e}", exc_info=True)
        return {
            "status": "error",
            "pipeline": "run_rate",
            "mode": mode,
            "incremental": incremental,
            "schema_name": schema_name,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }


def run_all_pipelines(
    incremental: bool = True,
    start_date: Optional[str] = None,
    schema_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run all data pipelines in sequence.

    Execution order: master_shot_table -> ana_shot_made -> roi -> run_rate

    Args:
        incremental: True for incremental mode, False for full historical load
        start_date: Start date for full mode (YYYY-MM-DD)
        schema_name: Override schema name (e.g., CLIENT_A, CLIENT_B)

    Returns:
        Dictionary with results from all pipelines
    """
    start_time = datetime.now()
    results = []

    pipelines = [
        (
            "master_shot_table",
            lambda: run_master_shot_pipeline(incremental, start_date, schema_name),
        ),
        ("ana_shot_made", lambda: run_ana_shot_made_pipeline(incremental, schema_name)),
        ("roi", lambda: run_roi_pipeline(incremental, schema_name)),
        ("run_rate", lambda: run_runrate_pipeline(incremental, schema_name)),
    ]

    for name, func in pipelines:
        logger.info(f"Starting pipeline: {name}")
        result = func()
        results.append(result)

        if result["status"] == "error":
            logger.warning(f"Pipeline {name} failed, continuing with next...")

    total_time = (datetime.now() - start_time).total_seconds()
    success_count = sum(1 for r in results if r["status"] == "success")

    return {
        "status": "success" if success_count == len(pipelines) else "partial",
        "pipelines_run": len(pipelines),
        "pipelines_succeeded": success_count,
        "schema_name": schema_name,
        "total_execution_time_seconds": total_time,
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }


def get_pipeline_status(
    pipeline_name: str,
    schema_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get the status/statistics of a pipeline's target table.

    Args:
        pipeline_name: Name of the pipeline (master_shot_table, ana_shot_made, roi, run_rate)
        schema_name: Override schema name (e.g., CLIENT_A, CLIENT_B)

    Returns:
        Dictionary with table statistics
    """
    from services.config.features.analytics.pipelines.shared_config import (
        get_snowflake_session,
    )

    table_mapping = {
        "master_shot_table": "MASTER_SHOT_TABLE",
        "ana_shot_made": "ANA_SHOT_MADE_TABLE",
        "roi": "ROI",
        "run_rate": "RUNRATE",
    }

    if pipeline_name not in table_mapping:
        return {
            "status": "error",
            "message": f"Unknown pipeline: {pipeline_name}. Valid options: {list(table_mapping.keys())}",
        }

    table_name = table_mapping[pipeline_name]
    session = None

    try:
        session = get_snowflake_session(schema=schema_name)

        stats_query = f"""
        SELECT
            COUNT(*) as total_rows,
            MIN(LOCAL_SHOT_TIME) as min_date,
            MAX(LOCAL_SHOT_TIME) as max_date
        FROM {table_name}
        """

        result = session.sql(stats_query).collect()

        if result:
            return {
                "status": "success",
                "pipeline": pipeline_name,
                "table": table_name,
                "schema_name": schema_name,
                "total_rows": result[0][0] or 0,
                "min_date": str(result[0][1]) if result[0][1] else None,
                "max_date": str(result[0][2]) if result[0][2] else None,
            }
        else:
            return {
                "status": "success",
                "pipeline": pipeline_name,
                "table": table_name,
                "schema_name": schema_name,
                "total_rows": 0,
            }

    except Exception as e:
        logger.error(f"Error getting pipeline status: {e}")
        return {
            "status": "error",
            "pipeline": pipeline_name,
            "schema_name": schema_name,
            "message": str(e),
        }

    finally:
        if session:
            session.close()
