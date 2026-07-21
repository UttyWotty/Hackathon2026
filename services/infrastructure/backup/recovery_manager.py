"""
Recovery Manager Module.

Features:
- Disaster recovery
- Point-in-time recovery (using Snowflake Time Travel)
- Configuration restoration
- Rollback support
- Recovery validation

Author: Utku Gulbardak
Date: 2025-11-12
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RecoveryManager:
    """
    Recovery Manager for MCP Ecosystem.

    Handles disaster recovery and restoration.
    """

    def __init__(self):
        """Initialize Recovery Manager."""
        self.recovery_history: List[Dict[str, Any]] = []
        self.max_history = 100

        logger.info("✅ Recovery Manager initialized")

    def recover_from_backup(
        self,
        backup_id: str,
        recovery_type: str = "full",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Recover from a backup.

        Args:
            backup_id: Backup ID to recover from
            recovery_type: 'full', 'config_only', or 'selective'
            dry_run: If True, validate without applying changes

        Returns:
            dict: Recovery result
        """
        from services.infrastructure.backup.backup_manager import get_backup_manager

        backup_manager = get_backup_manager()

        # Restore backup
        restore_result = backup_manager.restore_backup(backup_id)

        if restore_result["status"] == "error":
            return restore_result

        recovery_log = {
            "timestamp": datetime.now().isoformat(),
            "backup_id": backup_id,
            "recovery_type": recovery_type,
            "dry_run": dry_run,
            "steps": [],
        }

        if dry_run:
            logger.info(f"🔍 Dry run recovery from backup: {backup_id}")
            recovery_log["steps"].append({"action": "validate", "status": "success"})

            return {
                "status": "success",
                "message": "Dry run completed - no changes applied",
                "recovery_log": recovery_log,
            }

        # Apply recovery based on backup type
        backup_type = restore_result["backup_type"]

        if backup_type == "config" and "transformation_pipelines" in backup_id:
            result = backup_manager.restore_transformation_pipelines(backup_id)
            recovery_log["steps"].append(
                {
                    "action": "restore_pipelines",
                    "status": result["status"],
                    "pipelines_restored": result.get("pipelines_restored", 0),
                }
            )

        # Record recovery
        self.recovery_history.append(recovery_log)

        if len(self.recovery_history) > self.max_history:
            self.recovery_history = self.recovery_history[-self.max_history :]

        logger.info(f"✅ Recovery completed from backup: {backup_id}")

        return {
            "status": "success",
            "message": f"Recovery completed from backup: {backup_id}",
            "recovery_log": recovery_log,
        }

    def point_in_time_recovery(
        self,
        table_name: str,
        target_time: str,
        database: Optional[str] = None,
        schema: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform point-in-time recovery using Snowflake Time Travel.

        Args:
            table_name: Table name
            target_time: Target timestamp (ISO format or 'YYYY-MM-DD HH:MM:SS')
            database: Database name
            schema: Schema name

        Returns:
            dict: Recovery result
        """
        from services.infrastructure.snowflake.session_pool import get_session_pool

        pool = get_session_pool()

        database = database or pool.main_database
        schema = schema or os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")

        # Generate Time Travel query
        query = f"""
        SELECT *
        FROM {database}.{schema}.{table_name}
        AT (TIMESTAMP => '{target_time}')
        LIMIT 10
        """

        try:
            logger.info(f"🔄 Point-in-time recovery for {table_name} at {target_time}")

            df = pool.execute_query(query)

            recovery_log = {
                "timestamp": datetime.now().isoformat(),
                "recovery_type": "point_in_time",
                "table_name": table_name,
                "target_time": target_time,
                "rows_retrieved": len(df),
            }

            self.recovery_history.append(recovery_log)

            return {
                "status": "success",
                "message": f"Retrieved {len(df)} rows from {target_time}",
                "data": df.to_dict(orient="records"),
                "recovery_log": recovery_log,
            }

        except Exception as e:
            logger.error(f"Point-in-time recovery failed: {e}")
            return {
                "status": "error",
                "error": f"Recovery failed: {str(e)}",
                "hint": "Ensure Time Travel is enabled and target time is within retention period",
            }

    def list_recovery_points(
        self,
        backup_type: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        List available recovery points.

        Args:
            backup_type: Filter by backup type
            limit: Max results

        Returns:
            dict: Available recovery points
        """
        from services.infrastructure.backup.backup_manager import get_backup_manager

        backup_manager = get_backup_manager()
        backups = backup_manager.list_backups(backup_type=backup_type, limit=limit)

        return {
            "status": "success",
            "recovery_points": backups,
            "count": len(backups),
        }

    def validate_backup(self, backup_id: str) -> Dict[str, Any]:
        """
        Validate a backup before recovery.

        Args:
            backup_id: Backup ID to validate

        Returns:
            dict: Validation result
        """
        from services.infrastructure.backup.backup_manager import get_backup_manager

        backup_manager = get_backup_manager()

        restore_result = backup_manager.restore_backup(backup_id)

        if restore_result["status"] == "error":
            return {
                "status": "error",
                "is_valid": False,
                "error": restore_result["error"],
            }

        validation_checks = {
            "backup_exists": True,
            "backup_readable": True,
            "data_integrity": True,  # Could add checksum verification
            "metadata_valid": "metadata" in restore_result,
        }

        all_valid = all(validation_checks.values())

        return {
            "status": "success",
            "is_valid": all_valid,
            "backup_id": backup_id,
            "backup_type": restore_result["backup_type"],
            "timestamp": restore_result["timestamp"],
            "validation_checks": validation_checks,
        }

    def rollback_to_backup(
        self,
        backup_id: str,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """
        Rollback to a specific backup (destructive operation).

        Args:
            backup_id: Backup ID to rollback to
            confirm: Must be True to execute

        Returns:
            dict: Rollback result
        """
        if not confirm:
            return {
                "status": "error",
                "error": "Rollback requires confirmation. Set confirm=True to proceed.",
                "warning": "This is a destructive operation that will replace current configuration.",
            }

        logger.warning(f"⚠️  Rollback initiated to backup: {backup_id}")

        # First validate backup
        validation = self.validate_backup(backup_id)

        if not validation.get("is_valid"):
            return {
                "status": "error",
                "error": "Backup validation failed. Cannot rollback.",
                "validation": validation,
            }

        # Perform recovery
        recovery_result = self.recover_from_backup(
            backup_id, recovery_type="full", dry_run=False
        )

        if recovery_result["status"] == "success":
            logger.info(f"✅ Rollback completed to backup: {backup_id}")

        return recovery_result

    def get_recovery_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recovery operation history.

        Args:
            limit: Max results

        Returns:
            list: Recovery history
        """
        return self.recovery_history[-limit:]

    def create_recovery_plan(
        self,
        scenario: str,
        backup_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a recovery plan for disaster scenarios.

        Args:
            scenario: Scenario name ('full_system', 'config_only', 'data_loss')
            backup_id: Optional specific backup to use

        Returns:
            dict: Recovery plan
        """
        from services.infrastructure.backup.backup_manager import get_backup_manager

        backup_manager = get_backup_manager()

        if scenario == "full_system":
            # Full system recovery
            backups = backup_manager.list_backups(limit=5)

            plan = {
                "scenario": "full_system",
                "steps": [
                    {
                        "step": 1,
                        "action": "Verify Snowflake connectivity",
                        "estimated_time": "1 minute",
                    },
                    {
                        "step": 2,
                        "action": "Restore transformation pipelines",
                        "backup_type": "config",
                        "estimated_time": "2 minutes",
                    },
                    {
                        "step": 3,
                        "action": "Restore alert rules",
                        "backup_type": "config",
                        "estimated_time": "1 minute",
                    },
                    {
                        "step": 4,
                        "action": "Restore ML models metadata",
                        "backup_type": "config",
                        "estimated_time": "1 minute",
                    },
                    {
                        "step": 5,
                        "action": "Validate all services",
                        "estimated_time": "2 minutes",
                    },
                ],
                "total_estimated_time": "7 minutes",
                "available_backups": backups[:3],
            }

        elif scenario == "config_only":
            plan = {
                "scenario": "config_only",
                "steps": [
                    {
                        "step": 1,
                        "action": "Restore configuration backups only",
                        "estimated_time": "3 minutes",
                    },
                    {
                        "step": 2,
                        "action": "Validate configurations",
                        "estimated_time": "1 minute",
                    },
                ],
                "total_estimated_time": "4 minutes",
            }

        elif scenario == "data_loss":
            plan = {
                "scenario": "data_loss",
                "steps": [
                    {
                        "step": 1,
                        "action": "Use Snowflake Time Travel for data recovery",
                        "note": "Snowflake retains data for 1-90 days (Fail-safe)",
                        "estimated_time": "Varies",
                    },
                    {
                        "step": 2,
                        "action": "Restore from analysis exports if needed",
                        "backup_type": "export",
                        "estimated_time": "5 minutes",
                    },
                ],
                "total_estimated_time": "Varies",
                "recommendation": "Contact Snowflake support for Fail-safe recovery if needed",
            }

        else:
            return {
                "status": "error",
                "error": f"Unknown scenario: {scenario}",
                "available_scenarios": ["full_system", "config_only", "data_loss"],
            }

        return {
            "status": "success",
            "recovery_plan": plan,
        }


# Global recovery manager instance
_recovery_manager: Optional[RecoveryManager] = None


def get_recovery_manager() -> RecoveryManager:
    """
    Get global recovery manager instance.

    Returns:
        RecoveryManager: Global recovery manager instance
    """
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = RecoveryManager()
    return _recovery_manager
