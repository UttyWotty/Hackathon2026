"""
Backup Router - Disaster Recovery & Data Protection

Provides backup and recovery capabilities:
- Database backups (SQLite snapshots)
- Configuration backups (jobs, alerts, settings)
- Analysis results archiving
- Backup restoration
- Automated backup scheduling

Uses: services/infrastructure/backup/
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.infrastructure.backup.backup_manager import BackupManager
from services.infrastructure.backup.recovery_manager import RecoveryManager
from utils.error_handling import sanitize_error_message

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize backup components
backup_mgr = BackupManager()
recovery_mgr = RecoveryManager()


# Request Models
class CreateBackupRequest(BaseModel):
    backup_type: str = Field(
        "full", description="Backup type: 'full', 'database', 'config', 'results'"
    )
    description: Optional[str] = Field(None, description="Backup description")
    include_results: bool = Field(True, description="Include analysis results")


class RestoreBackupRequest(BaseModel):
    backup_id: str = Field(..., description="Backup ID to restore")
    restore_type: str = Field(
        "full", description="What to restore: 'full', 'database', 'config'"
    )
    confirm: bool = Field(False, description="Must be true to proceed with restore")


@router.get("/", summary="Backup Service Info")
async def backup_info():
    """Get information about the backup service."""
    try:
        backup_count = len(backup_mgr.backup_history)
        latest_backup = (
            backup_mgr.backup_history[-1] if backup_mgr.backup_history else None
        )

        return {
            "service": "Backup Service",
            "description": "Disaster recovery and data protection",
            "backup_directory": str(backup_mgr.backup_dir),
            "total_backups": backup_count,
            "latest_backup": latest_backup,
            "capabilities": [
                "Database Backups (SQLite snapshots)",
                "Configuration Backups (jobs, alerts, settings)",
                "Analysis Results Archiving",
                "Point-in-Time Recovery",
                "Automated Backup Scheduling",
            ],
            "backup_types": {
                "full": "Complete system backup (database + config + results)",
                "database": "Database only (SQLite + schemas)",
                "config": "Configuration only (jobs, alerts, settings)",
                "results": "Analysis results only (Excel, HTML reports)",
            },
        }
    except Exception as e:
        logger.error(f"Backup info error: {e}")
        return {
            "service": "Backup Service",
            "error": str(e),
        }


@router.post("/create", summary="Create Backup")
async def create_backup(request: CreateBackupRequest):
    """
    Create a backup of system data and configurations.

    Backup Types:
    - **full**: Complete system backup (recommended)
    - **database**: SQLite database only
    - **config**: Jobs, alerts, settings only
    - **results**: Analysis outputs only

    Backups are stored in the configured backup directory with timestamps.
    """
    start_time = time.time()

    try:
        # Collect data to backup based on type
        backup_data = {}

        if request.backup_type in ["full", "database"]:
            # Backup database
            db_path = Path("data/manufacturing.db")
            if db_path.exists():
                backup_data["database"] = str(db_path)
            else:
                logger.warning("Database file not found for backup")

        if request.backup_type in ["full", "config"]:
            # Backup configurations (would need to query database for jobs, alerts, etc.)
            backup_data["config"] = {
                "scheduled_jobs": "from database",
                "alert_rules": "from database",
                "cache_settings": "from env",
            }

        if request.backup_type in ["full", "results"] and request.include_results:
            # Backup analysis results
            output_dirs = ["output/roi", "output/runrate", "output/capacity"]
            backup_data["results"] = [str(d) for d in output_dirs if Path(d).exists()]

        # Create backup
        result = backup_mgr.create_backup(
            backup_type=request.backup_type,
            data=backup_data,
            description=request.description,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "backup_id": result["backup_id"],
            "backup_type": request.backup_type,
            "backup_path": result["backup_path"],
            "backup_size_mb": result.get("size_mb", 0),
            "timestamp": result["timestamp"],
            "description": request.description,
            "execution_time_ms": round(execution_time_ms, 2),
            "message": f"Backup created successfully: {result['backup_id']}",
        }

    except Exception as e:
        logger.error(f"Backup creation error: {e}", exc_info=True)

        error_msg = sanitize_error_message(
            e, "Backup creation failed. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/list", summary="List Backups")
async def list_backups(limit: int = 50):
    """
    List all available backups.

    Returns backup history with IDs, timestamps, types, and sizes.
    Useful for selecting a backup to restore.
    """
    try:
        backups = (
            backup_mgr.backup_history[-limit:] if backup_mgr.backup_history else []
        )

        # Reverse to show newest first
        backups = list(reversed(backups))

        return {
            "status": "success",
            "total_backups": len(backup_mgr.backup_history),
            "showing": len(backups),
            "backups": backups,
            "backup_directory": str(backup_mgr.backup_dir),
            "message": f"Found {len(backups)} backups",
        }

    except Exception as e:
        logger.error(f"List backups error: {e}", exc_info=True)

        error_msg = sanitize_error_message(
            e, "Failed to list backups. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/info/{backup_id}", summary="Get Backup Info")
async def get_backup_info(backup_id: str):
    """
    Get detailed information about a specific backup.

    Includes:
    - Backup metadata
    - Size and contents
    - Creation timestamp
    - Restore availability
    """
    try:
        # Find backup in history
        backup = next(
            (b for b in backup_mgr.backup_history if b["backup_id"] == backup_id), None
        )

        if not backup:
            raise HTTPException(
                status_code=404, detail=f"Backup not found: {backup_id}"
            )

        # Check if backup file still exists
        backup_path = Path(backup["backup_path"])
        file_exists = backup_path.exists() if backup_path else False

        return {
            "status": "success",
            "backup": backup,
            "file_exists": file_exists,
            "can_restore": file_exists,
            "message": f"Backup {backup_id} details retrieved",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get backup info error: {e}", exc_info=True)

        error_msg = sanitize_error_message(
            e, "Failed to get backup info. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/restore", summary="Restore from Backup")
async def restore_backup(request: RestoreBackupRequest):
    """
    Restore system from a backup.

    ⚠️ **WARNING**: This will overwrite current data!

    Restore Types:
    - **full**: Restore everything (database + config)
    - **database**: Restore database only
    - **config**: Restore configuration only

    Requires `confirm: true` to proceed.
    """
    start_time = time.time()

    try:
        if not request.confirm:
            raise HTTPException(
                status_code=400,
                detail="Restore confirmation required. Set 'confirm: true' to proceed.",
            )

        # Find backup
        backup = next(
            (
                b
                for b in backup_mgr.backup_history
                if b["backup_id"] == request.backup_id
            ),
            None,
        )

        if not backup:
            raise HTTPException(
                status_code=404, detail=f"Backup not found: {request.backup_id}"
            )

        # Check backup file exists
        backup_path = Path(backup["backup_path"])
        if not backup_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Backup file not found: {backup_path}"
            )

        # Perform restore
        result = recovery_mgr.restore_backup(
            backup_id=request.backup_id,
            backup_path=str(backup_path),
            restore_type=request.restore_type,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "backup_id": request.backup_id,
            "restore_type": request.restore_type,
            "items_restored": result.get("items_restored", []),
            "execution_time_ms": round(execution_time_ms, 2),
            "message": f"Successfully restored from backup: {request.backup_id}",
            "next_steps": [
                "Restart the server to apply restored configuration",
                "Verify data integrity",
                "Check logs for any issues",
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backup restore error: {e}", exc_info=True)

        error_msg = sanitize_error_message(
            e, "Backup restore failed. Please check the backup ID and try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.delete("/delete/{backup_id}", summary="Delete Backup")
async def delete_backup(backup_id: str):
    """
    Delete a specific backup.

    Permanently removes backup file and removes from history.
    Use with caution!
    """
    try:
        # Find backup
        backup = next(
            (b for b in backup_mgr.backup_history if b["backup_id"] == backup_id), None
        )

        if not backup:
            raise HTTPException(
                status_code=404, detail=f"Backup not found: {backup_id}"
            )

        # Delete backup file
        backup_path = Path(backup["backup_path"])
        if backup_path.exists():
            backup_path.unlink()

        # Remove from history
        backup_mgr.backup_history = [
            b for b in backup_mgr.backup_history if b["backup_id"] != backup_id
        ]

        return {
            "status": "success",
            "backup_id": backup_id,
            "message": f"Backup {backup_id} deleted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete backup error: {e}", exc_info=True)

        error_msg = sanitize_error_message(
            e, "Failed to delete backup. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/health", summary="Backup Service Health")
async def health_check():
    """Check if backup service is operational."""
    try:
        # Check backup directory exists and is writable
        backup_dir_ok = backup_mgr.backup_dir.exists() and os.access(
            backup_mgr.backup_dir, os.W_OK
        )

        components_status = {
            "backup_manager": "ready" if backup_mgr else "not_initialized",
            "recovery_manager": "ready" if recovery_mgr else "not_initialized",
            "backup_directory": "ready" if backup_dir_ok else "not_accessible",
        }

        overall_status = (
            "healthy"
            if all(s == "ready" for s in components_status.values())
            else "degraded"
        )

        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "components": components_status,
            "backup_directory": str(backup_mgr.backup_dir),
            "total_backups": len(backup_mgr.backup_history),
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }
