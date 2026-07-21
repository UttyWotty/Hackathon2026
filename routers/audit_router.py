"""
Audit Router - Compliance logging and audit trail management.
Provides core audit endpoints: info, query, search, export, and event logging.
Delegates compliance report endpoints to audit_compliance_router sub-router.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func  # type: ignore[import-untyped]

from models.audit import AuditLog
from models.database import get_session
from routers.audit_compliance_router import router as compliance_router
from utils.error_handling import sanitize_error_message

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(compliance_router)


# Request Models
class QueryAuditRequest(BaseModel):
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")
    user_id: Optional[str] = Field(None, description="Filter by user ID")
    service: Optional[str] = Field(None, description="Filter by service name")
    tool_name: Optional[str] = Field(None, description="Filter by tool name")
    status: Optional[str] = Field(None, description="Filter by status (success/error)")
    limit: int = Field(1000, description="Maximum number of records")


class ExportAuditRequest(BaseModel):
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    format: str = Field("csv", description="Export format: csv or json")
    output_path: str = Field(..., description="Output file path")


class LogEventRequest(BaseModel):
    service: str = Field(..., description="Name of the service emitting the event")
    tool_name: str = Field(..., description="Name of the tool that was executed")
    user_id: Optional[str] = Field(None, description="User ID, defaults to 'system'")
    status: str = Field("success", description="Outcome status: success or error")
    execution_time_ms: Optional[float] = Field(
        None, description="Wall-clock execution duration in ms"
    )
    error_message: Optional[str] = Field(
        None, description="Error message if status is error"
    )
    extra_data: Optional[Dict[str, Any]] = Field(
        None, description="Arbitrary structured metadata"
    )


@router.get("/", summary="Audit Service Info")
async def audit_info():
    """Get information about the audit service."""
    try:
        with get_session() as session:
            total_logs = session.query(AuditLog).count()

            # Get oldest and newest
            oldest = session.query(func.min(AuditLog.timestamp)).scalar()
            newest = session.query(func.max(AuditLog.timestamp)).scalar()

        return {
            "service": "Audit Service",
            "description": "Compliance logging with persistent SQLite storage",
            "storage": "SQLite (persists across restarts)",
            "total_logs": total_logs,
            "oldest_log": oldest.isoformat() if oldest else None,
            "newest_log": newest.isoformat() if newest else None,
        }
    except Exception as e:
        logger.error("Audit info error: %s", e)
        return {
            "service": "Audit Service",
            "description": "Compliance logging and audit trails",
            "error": "Database connection error",
        }


@router.post("/query", summary="Query Audit Logs")
async def query_audit_logs(request: QueryAuditRequest):
    """Query audit logs from database with filtering."""
    start_time = time.time()

    try:
        with get_session() as session:
            query = session.query(AuditLog)

            # Apply filters
            if request.start_date:
                start_dt = datetime.fromisoformat(f"{request.start_date}T00:00:00")
                query = query.filter(AuditLog.timestamp >= start_dt)

            if request.end_date:
                end_dt = datetime.fromisoformat(f"{request.end_date}T23:59:59")
                query = query.filter(AuditLog.timestamp <= end_dt)

            if request.user_id:
                query = query.filter(AuditLog.user_id == request.user_id)

            if request.service:
                query = query.filter(AuditLog.service == request.service)

            if request.tool_name:
                query = query.filter(AuditLog.tool_name == request.tool_name)

            if request.status:
                query = query.filter(AuditLog.status == request.status)

            # Order by timestamp descending (newest first) and limit
            logs = query.order_by(AuditLog.timestamp.desc()).limit(request.limit).all()

            result_logs = [log.to_dict() for log in logs]

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "records": result_logs,
            "count": len(result_logs),
            "filters_applied": {
                "start_date": request.start_date,
                "end_date": request.end_date,
                "user_id": request.user_id,
                "service": request.service,
                "tool_name": request.tool_name,
                "status": request.status,
            },
            "metadata": {
                "execution_time_ms": execution_time_ms,
            },
        }

    except ValueError as e:
        # Bad start_date/end_date (fromisoformat) is client input, not a 500.
        raise HTTPException(
            status_code=400,
            detail="Invalid date format (expected YYYY-MM-DD): %s" % e,
        ) from e
    except Exception as e:
        logger.error("Query audit logs error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(
            e, "Failed to query audit logs. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/user/{user_id}/activity", summary="Get User Activity")
async def get_user_activity(user_id: str, days: int = 30):
    """Get activity summary for a specific user from database."""
    start_time = time.time()

    try:
        with get_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)

            logs = (
                session.query(AuditLog)
                .filter(AuditLog.user_id == user_id, AuditLog.timestamp >= cutoff_date)
                .all()
            )

        if not logs:
            return {
                "status": "success",
                "user_id": user_id,
                "period_days": days,
                "total_actions": 0,
                "message": "No activity found for this user",
            }

        # Calculate statistics
        total_actions = len(logs)
        success_count = sum(1 for log in logs if log.status == "success")
        error_count = total_actions - success_count

        # Tools used
        tools_used = {}
        for log in logs:
            tool = log.tool_name or "unknown"
            tools_used[tool] = tools_used.get(tool, 0) + 1

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "user_id": user_id,
            "period_days": days,
            "total_actions": total_actions,
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": (
                round(success_count / total_actions * 100, 2)
                if total_actions > 0
                else 0
            ),
            "tools_used": tools_used,
            "most_used_tool": (
                max(tools_used, key=tools_used.get) if tools_used else None
            ),
            "metadata": {
                "execution_time_ms": execution_time_ms,
            },
        }

    except Exception as e:
        logger.error("Get user activity error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/stats", summary="Get Audit Statistics")
async def get_audit_stats(days: int = 7):
    """Get overall audit statistics from database."""
    start_time = time.time()

    try:
        with get_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)

            logs = (
                session.query(AuditLog).filter(AuditLog.timestamp >= cutoff_date).all()
            )

        if not logs:
            return {
                "status": "success",
                "period_days": days,
                "message": "No logs found for this period",
            }

        total_logs = len(logs)
        success_count = sum(1 for log in logs if log.status == "success")
        error_count = total_logs - success_count

        # Unique users
        unique_users = len(set(log.user_id for log in logs if log.user_id))

        # Services and tools
        services = {}
        tools = {}
        for log in logs:
            services[log.service] = services.get(log.service, 0) + 1
            tools[log.tool_name or "unknown"] = (
                tools.get(log.tool_name or "unknown", 0) + 1
            )

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "period_days": days,
            "total_logs": total_logs,
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": (
                round(success_count / total_logs * 100, 2) if total_logs > 0 else 0
            ),
            "unique_users": unique_users,
            "services_used": services,
            "most_used_service": max(services, key=services.get) if services else None,
            "tools_used": tools,
            "most_used_tool": max(tools, key=tools.get) if tools else None,
            "metadata": {
                "execution_time_ms": execution_time_ms,
            },
        }

    except Exception as e:
        logger.error("Get audit stats error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/log", summary="Log Event (Internal)")
async def log_event(payload: LogEventRequest):
    """
    Log an audit event to database (used internally by other services).

    Events persist across server restarts.
    """
    try:
        with get_session() as session:
            log_entry = AuditLog(
                user_id=payload.user_id or "system",
                service=payload.service,
                tool_name=payload.tool_name,
                status=payload.status,
                execution_time_ms=payload.execution_time_ms,
                error_message=payload.error_message,
                extra_data=payload.extra_data or {},
                ip_address=None,
                user_agent=None,
            )

            session.add(log_entry)
            session.commit()

            log_id = log_entry.id

        return {
            "status": "success",
            "event_id": log_id,
            "message": "Event logged to database successfully",
        }

    except Exception as e:
        logger.error("Log event error: %s", e, exc_info=True)
        return {
            "status": "error",
            "error": str(e),
        }


@router.get("/search", summary="Search Audit Logs")
async def search_audit_logs(query: str, limit: int = 100):
    """Full-text search across audit logs in database."""
    start_time = time.time()

    try:
        with get_session() as session:
            # Simple search across tool_name, service, user_id, error_message
            logs = (
                session.query(AuditLog)
                .filter(
                    (AuditLog.tool_name.like(f"%{query}%"))
                    | (AuditLog.service.like(f"%{query}%"))
                    | (AuditLog.user_id.like(f"%{query}%"))
                    | (AuditLog.error_message.like(f"%{query}%"))
                )
                .order_by(AuditLog.timestamp.desc())
                .limit(limit)
                .all()
            )

            result_logs = [log.to_dict() for log in logs]

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "query": query,
            "results": result_logs,
            "count": len(result_logs),
            "metadata": {
                "execution_time_ms": execution_time_ms,
            },
        }

    except Exception as e:
        logger.error("Search audit logs error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/export", summary="Export Audit Logs")
async def export_audit_logs(request: ExportAuditRequest):
    """
    Export audit logs to CSV or JSON file for compliance reporting.

    Perfect for:
    - SOC2 audits
    - HIPAA compliance
    - GDPR data access requests
    - Internal audits
    """
    start_time = time.time()

    try:
        import csv
        import json
        from pathlib import Path

        with get_session() as session:
            # Parse dates
            start_dt = datetime.fromisoformat(f"{request.start_date}T00:00:00")
            end_dt = datetime.fromisoformat(f"{request.end_date}T23:59:59")

            # Query logs
            logs = (
                session.query(AuditLog)
                .filter(AuditLog.timestamp >= start_dt, AuditLog.timestamp <= end_dt)
                .order_by(AuditLog.timestamp)
                .all()
            )

        if not logs:
            raise HTTPException(
                status_code=404, detail="No logs found for the specified date range"
            )

        # Create output directory
        output_path = Path(request.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Export based on format
        if request.format.lower() == "csv":
            with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
                fieldnames = [
                    "id",
                    "timestamp",
                    "user_id",
                    "service",
                    "tool_name",
                    "status",
                    "execution_time_ms",
                    "error_message",
                    "error_type",
                    "ip_address",
                    "user_agent",
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for log in logs:
                    log_dict = log.to_dict()
                    # Remove extra_data for CSV (complex JSON)
                    log_dict.pop("extra_data", None)
                    writer.writerow(log_dict)

        elif request.format.lower() == "json":
            log_dicts = [log.to_dict() for log in logs]
            with open(output_path, "w", encoding="utf-8") as jsonfile:
                json.dump(
                    {
                        "export_date": datetime.now().isoformat(),
                        "start_date": request.start_date,
                        "end_date": request.end_date,
                        "total_records": len(log_dicts),
                        "logs": log_dicts,
                    },
                    jsonfile,
                    indent=2,
                    default=str,
                )

        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported format: {request.format}"
            )

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "message": f"Exported {len(logs)} audit logs to {request.format.upper()}",
            "output_file": str(output_path),
            "records_exported": len(logs),
            "date_range": f"{request.start_date} to {request.end_date}",
            "metadata": {
                "execution_time_ms": execution_time_ms,
            },
        }

    except HTTPException:
        raise
    except ValueError as e:
        # Bad start_date/end_date (fromisoformat) is client input, not a 500.
        raise HTTPException(
            status_code=400,
            detail="Invalid date format (expected YYYY-MM-DD): %s" % e,
        ) from e
    except Exception as e:
        logger.error("Export audit logs error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)
