"""
Audit Compliance Sub-Router - Compliance report endpoints for audit trails.
Provides user access, data access, error, and summary compliance reports.
Designed for SOC2, HIPAA, and GDPR compliance audit workflows.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from models.audit import AuditLog
from models.database import get_session
from utils.error_handling import sanitize_error_message

logger = logging.getLogger(__name__)

router = APIRouter()

ANONYMOUS_USER = "anonymous"
UNKNOWN_LABEL = "unknown"
SUCCESS_STATUS = "success"
RECENT_ERRORS_LIMIT = 20


def _build_user_entry(user: str, first_timestamp: str) -> Dict[str, Any]:
    """Build an initial user activity dictionary for the access report."""
    return {
        "user_id": user,
        "total_actions": 0,
        "successful_actions": 0,
        "failed_actions": 0,
        "tools_used": {},
        "first_access": first_timestamp,
        "last_access": first_timestamp,
        "ip_addresses": set(),
    }


def _accumulate_user_log(user_data: Dict[str, Any], log: Any) -> None:
    """Accumulate a single audit log entry into a user activity record."""
    user_data["total_actions"] += 1

    if log.status == SUCCESS_STATUS:
        user_data["successful_actions"] += 1
    else:
        user_data["failed_actions"] += 1

    tool = log.tool_name or UNKNOWN_LABEL
    user_data["tools_used"][tool] = user_data["tools_used"].get(tool, 0) + 1

    if log.ip_address:
        user_data["ip_addresses"].add(log.ip_address)

    if log.timestamp.isoformat() > user_data["last_access"]:
        user_data["last_access"] = log.timestamp.isoformat()


def _finalize_user_list(
    user_activity: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert user activity map to a sorted list with computed fields."""
    user_list: List[Dict[str, Any]] = []
    for user_data in user_activity.values():
        user_data["unique_ip_addresses"] = len(user_data["ip_addresses"])
        user_data["ip_addresses"] = list(user_data["ip_addresses"])
        user_data["success_rate"] = (
            round(
                user_data["successful_actions"] / user_data["total_actions"] * 100,
                2,
            )
            if user_data["total_actions"] > 0
            else 0
        )
        user_list.append(user_data)

    user_list.sort(key=lambda x: x["total_actions"], reverse=True)
    return user_list


@router.get("/compliance/user-access", summary="User Access Compliance Report")
async def get_user_access_report(days: int = 30) -> Dict[str, Any]:
    """
    Generate user access compliance report.

    Shows all users who accessed the system, when they accessed it,
    what they did, and success/failure rates.
    Perfect for SOC2/HIPAA compliance audits.
    """
    try:
        with get_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)
            logs = (
                session.query(AuditLog).filter(AuditLog.timestamp >= cutoff_date).all()
            )

        user_activity: Dict[str, Dict[str, Any]] = {}
        for log in logs:
            user = log.user_id or ANONYMOUS_USER
            if user not in user_activity:
                user_activity[user] = _build_user_entry(user, log.timestamp.isoformat())
            _accumulate_user_log(user_activity[user], log)

        user_list = _finalize_user_list(user_activity)

        return {
            "status": SUCCESS_STATUS,
            "report_type": "user_access_compliance",
            "period_days": days,
            "generated_at": datetime.now().isoformat(),
            "total_users": len(user_list),
            "total_actions": sum(u["total_actions"] for u in user_list),
            "users": user_list,
        }

    except Exception as e:
        logger.error("User access report error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


def _build_tool_entry(log: Any) -> Dict[str, Any]:
    """Build an initial tool access dictionary for the data access report."""
    return {
        "service": log.service,
        "tool_name": log.tool_name,
        "total_accesses": 0,
        "unique_users": set(),
        "successful_accesses": 0,
        "failed_accesses": 0,
        "first_access": log.timestamp.isoformat(),
        "last_access": log.timestamp.isoformat(),
    }


def _accumulate_tool_log(tool_data: Dict[str, Any], log: Any) -> None:
    """Accumulate a single audit log entry into a tool access record."""
    tool_data["total_accesses"] += 1
    tool_data["unique_users"].add(log.user_id or ANONYMOUS_USER)

    if log.status == SUCCESS_STATUS:
        tool_data["successful_accesses"] += 1
    else:
        tool_data["failed_accesses"] += 1

    if log.timestamp.isoformat() > tool_data["last_access"]:
        tool_data["last_access"] = log.timestamp.isoformat()


def _finalize_tool_list(tool_access: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert tool access map to a sorted list with computed fields."""
    tool_list: List[Dict[str, Any]] = []
    for tool_data in tool_access.values():
        tool_data["unique_users_count"] = len(tool_data["unique_users"])
        tool_data["unique_users"] = list(tool_data["unique_users"])
        tool_list.append(tool_data)

    tool_list.sort(key=lambda x: x["total_accesses"], reverse=True)
    return tool_list


@router.get("/compliance/data-access", summary="Data Access Compliance Report")
async def get_data_access_report(days: int = 30) -> Dict[str, Any]:
    """
    Generate data access compliance report.

    Shows what data/tools were accessed and by whom.
    Perfect for GDPR data access audits.
    """
    try:
        with get_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)
            logs = (
                session.query(AuditLog).filter(AuditLog.timestamp >= cutoff_date).all()
            )

        tool_access: Dict[str, Dict[str, Any]] = {}
        for log in logs:
            tool_key = "%s::%s" % (log.service, log.tool_name)
            if tool_key not in tool_access:
                tool_access[tool_key] = _build_tool_entry(log)
            _accumulate_tool_log(tool_access[tool_key], log)

        tool_list = _finalize_tool_list(tool_access)

        return {
            "status": SUCCESS_STATUS,
            "report_type": "data_access_compliance",
            "period_days": days,
            "generated_at": datetime.now().isoformat(),
            "total_tools": len(tool_list),
            "total_accesses": sum(t["total_accesses"] for t in tool_list),
            "tools": tool_list,
        }

    except Exception as e:
        logger.error("Data access report error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


def _build_error_summary(error_logs: List[Any]) -> List[Dict[str, Any]]:
    """Group error logs by error type and return a sorted summary list."""
    error_types: Dict[str, Dict[str, Any]] = {}
    for log in error_logs:
        error_type = log.error_type or UNKNOWN_LABEL
        if error_type not in error_types:
            error_types[error_type] = {
                "error_type": error_type,
                "count": 0,
                "affected_users": set(),
                "affected_tools": set(),
            }

        error_types[error_type]["count"] += 1
        error_types[error_type]["affected_users"].add(log.user_id or ANONYMOUS_USER)
        error_types[error_type]["affected_tools"].add(log.tool_name or UNKNOWN_LABEL)

    error_summary: List[Dict[str, Any]] = []
    for et_data in error_types.values():
        et_data["affected_users_count"] = len(et_data["affected_users"])
        et_data["affected_users"] = list(et_data["affected_users"])
        et_data["affected_tools"] = list(et_data["affected_tools"])
        error_summary.append(et_data)

    error_summary.sort(key=lambda x: x["count"], reverse=True)
    return error_summary


@router.get("/compliance/errors", summary="Error Compliance Report")
async def get_error_report(days: int = 30) -> Dict[str, Any]:
    """
    Generate error compliance report.

    Shows all errors/failures for security audits.
    """
    try:
        with get_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)
            error_logs = (
                session.query(AuditLog)
                .filter(
                    AuditLog.timestamp >= cutoff_date, AuditLog.status != SUCCESS_STATUS
                )
                .order_by(AuditLog.timestamp.desc())
                .all()
            )

        error_summary = _build_error_summary(error_logs)

        return {
            "status": SUCCESS_STATUS,
            "report_type": "error_compliance",
            "period_days": days,
            "generated_at": datetime.now().isoformat(),
            "total_errors": len(error_logs),
            "unique_error_types": len(error_summary),
            "error_summary": error_summary,
            "recent_errors": [
                log.to_dict() for log in error_logs[:RECENT_ERRORS_LIMIT]
            ],
        }

    except Exception as e:
        logger.error("Error report error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/compliance/summary", summary="Compliance Summary Report")
async def get_compliance_summary(days: int = 30) -> Dict[str, Any]:
    """
    Generate comprehensive compliance summary.

    All-in-one report for auditors covering activity, users, and system status.
    """
    try:
        with get_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)
            logs = (
                session.query(AuditLog).filter(AuditLog.timestamp >= cutoff_date).all()
            )

        if not logs:
            return {
                "status": SUCCESS_STATUS,
                "report_type": "compliance_summary",
                "period_days": days,
                "message": "No activity in this period",
            }

        total_logs = len(logs)
        success_count = sum(1 for log in logs if log.status == SUCCESS_STATUS)
        error_count = total_logs - success_count

        unique_users = len(set(log.user_id for log in logs if log.user_id))
        unique_services = len(set(log.service for log in logs))
        unique_tools = len(set(log.tool_name for log in logs if log.tool_name))

        timestamps = [log.timestamp for log in logs]
        first_log = min(timestamps).isoformat()
        last_log = max(timestamps).isoformat()

        return {
            "status": SUCCESS_STATUS,
            "report_type": "compliance_summary",
            "period_days": days,
            "generated_at": datetime.now().isoformat(),
            "date_range": {
                "start": cutoff_date.isoformat(),
                "end": datetime.now().isoformat(),
                "first_log": first_log,
                "last_log": last_log,
            },
            "activity_summary": {
                "total_actions": total_logs,
                "successful_actions": success_count,
                "failed_actions": error_count,
                "success_rate": (
                    round(success_count / total_logs * 100, 2) if total_logs > 0 else 0
                ),
            },
            "user_summary": {
                "unique_users": unique_users,
                "total_user_sessions": total_logs,
            },
            "system_summary": {
                "unique_services": unique_services,
                "unique_tools": unique_tools,
            },
            "compliance_status": {
                "audit_logs_enabled": True,
                "data_retention": "Active (SQLite)",
                "export_available": True,
                "user_tracking": True,
                "error_tracking": True,
            },
        }

    except Exception as e:
        logger.error("Compliance summary error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, "Operation failed. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)
