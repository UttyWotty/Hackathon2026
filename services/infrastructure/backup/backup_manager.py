"""
Backup Manager Module.

Features:
- Configuration backup (pipelines, alert rules, schedules)
- Cache snapshots
- Analysis result exports
- Incremental backups
- Backup metadata tracking

Author: Utku Gulbardak
Date: 2025-11-12
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BackupManager:
    """
    Backup Manager for MCP Ecosystem.

    Handles configuration backups, snapshots, and exports.
    """

    def __init__(self, backup_dir: Optional[str] = None):
        """
        Initialize Backup Manager.

        Args:
            backup_dir: Directory for backups (default: ./backups)
        """
        self.backup_dir = Path(backup_dir or os.getenv("BACKUP_DIR", "./backups"))
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.backup_history: List[Dict[str, Any]] = []
        self.max_history = 100

        logger.info("✅ Backup Manager initialized")
        logger.info(f"   Backup directory: {self.backup_dir}")

    def create_backup(
        self,
        backup_type: str,
        data: Dict[str, Any],
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a backup.

        Args:
            backup_type: Type of backup ('config', 'snapshot', 'export')
            data: Data to backup
            name: Optional backup name
            metadata: Optional metadata

        Returns:
            dict: Backup information
        """
        timestamp = datetime.now()
        backup_id = f"{backup_type}_{timestamp.strftime('%Y%m%d_%H%M%S')}"

        if name:
            backup_id = f"{backup_id}_{name}"

        # Create backup subdirectory
        backup_path = self.backup_dir / backup_type
        backup_path.mkdir(parents=True, exist_ok=True)

        # Save backup file
        backup_file = backup_path / f"{backup_id}.json"

        backup_data = {
            "backup_id": backup_id,
            "backup_type": backup_type,
            "timestamp": timestamp.isoformat(),
            "name": name,
            "metadata": metadata or {},
            "data": data,
        }

        with open(backup_file, "w") as f:
            json.dump(backup_data, f, indent=2, default=str)

        # Record in history
        history_entry = {
            "backup_id": backup_id,
            "backup_type": backup_type,
            "timestamp": timestamp.isoformat(),
            "name": name,
            "file_path": str(backup_file),
            "file_size_bytes": backup_file.stat().st_size,
            "metadata": metadata or {},
        }

        self.backup_history.append(history_entry)

        # Keep only last N backups in history
        if len(self.backup_history) > self.max_history:
            self.backup_history = self.backup_history[-self.max_history :]

        logger.info(f"✅ Backup created: {backup_id}")
        logger.info(f"   Location: {backup_file}")
        logger.info(f"   Size: {history_entry['file_size_bytes']} bytes")

        return history_entry

    def restore_backup(self, backup_id: str) -> Dict[str, Any]:
        """
        Restore a backup.

        Args:
            backup_id: Backup ID to restore

        Returns:
            dict: Restored data
        """
        # Find backup file
        for backup_type in ["config", "snapshot", "export"]:
            backup_path = self.backup_dir / backup_type / f"{backup_id}.json"
            if backup_path.exists():
                with open(backup_path, "r") as f:
                    backup_data = json.load(f)

                logger.info(f"✅ Backup restored: {backup_id}")
                logger.info(f"   Type: {backup_data['backup_type']}")
                logger.info(f"   Created: {backup_data['timestamp']}")

                return {
                    "status": "success",
                    "backup_id": backup_id,
                    "backup_type": backup_data["backup_type"],
                    "timestamp": backup_data["timestamp"],
                    "data": backup_data["data"],
                    "metadata": backup_data.get("metadata", {}),
                }

        return {
            "status": "error",
            "error": f"Backup '{backup_id}' not found",
        }

    def list_backups(
        self,
        backup_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        List available backups.

        Args:
            backup_type: Filter by backup type
            limit: Max results

        Returns:
            list: Backup information
        """
        backups = self.backup_history.copy()

        # Filter by type
        if backup_type:
            backups = [b for b in backups if b["backup_type"] == backup_type]

        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x["timestamp"], reverse=True)

        return backups[:limit]

    def delete_backup(self, backup_id: str) -> Dict[str, Any]:
        """
        Delete a backup.

        Args:
            backup_id: Backup ID to delete

        Returns:
            dict: Deletion result
        """
        # Find and delete backup file
        for backup_type in ["config", "snapshot", "export"]:
            backup_path = self.backup_dir / backup_type / f"{backup_id}.json"
            if backup_path.exists():
                backup_path.unlink()

                # Remove from history
                self.backup_history = [
                    b for b in self.backup_history if b["backup_id"] != backup_id
                ]

                logger.info(f"🗑️  Backup deleted: {backup_id}")

                return {
                    "status": "success",
                    "message": f"Backup '{backup_id}' deleted",
                }

        return {
            "status": "error",
            "error": f"Backup '{backup_id}' not found",
        }

    def backup_transformation_pipelines(self) -> Dict[str, Any]:
        """
        Backup all transformation pipelines.

        Returns:
            dict: Backup information
        """
        from services.infrastructure.transformation.pipeline import (
            get_pipeline,
            list_pipelines,
        )

        pipeline_names = list_pipelines()

        pipelines_data = {}
        for name in pipeline_names:
            pipeline = get_pipeline(name)
            if pipeline:
                pipelines_data[name] = pipeline.to_dict()

        backup_info = self.create_backup(
            backup_type="config",
            data=pipelines_data,
            name="transformation_pipelines",
            metadata={
                "pipeline_count": len(pipelines_data),
                "pipeline_names": pipeline_names,
            },
        )

        return {
            "status": "success",
            "backup_info": backup_info,
            "pipelines_backed_up": len(pipelines_data),
        }

    def restore_transformation_pipelines(self, backup_id: str) -> Dict[str, Any]:
        """
        Restore transformation pipelines from backup.

        Args:
            backup_id: Backup ID

        Returns:
            dict: Restoration result
        """
        from services.infrastructure.transformation.pipeline import (
            TransformationPipeline,
            register_pipeline,
        )

        restore_result = self.restore_backup(backup_id)

        if restore_result["status"] == "error":
            return restore_result

        pipelines_data = restore_result["data"]
        restored_count = 0

        for name, pipeline_config in pipelines_data.items():
            try:
                pipeline = TransformationPipeline.from_dict(pipeline_config)
                register_pipeline(pipeline)
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore pipeline '{name}': {e}")

        return {
            "status": "success",
            "pipelines_restored": restored_count,
            "total_pipelines": len(pipelines_data),
        }

    def backup_ml_models(self) -> Dict[str, Any]:
        """
        Backup ML model metadata (not model weights - those are cached in memory).

        Returns:
            dict: Backup information
        """
        from services.infrastructure.ml.anomaly_detector import get_anomaly_detector
        from services.infrastructure.ml.predictor import get_predictor

        detector = get_anomaly_detector()
        predictor = get_predictor()

        models_data = {
            "anomaly_models": detector.list_cached_models(),
            "prediction_models": list(predictor.models.keys()),
        }

        backup_info = self.create_backup(
            backup_type="config",
            data=models_data,
            name="ml_models",
            metadata={
                "anomaly_model_count": len(models_data["anomaly_models"]),
                "prediction_model_count": len(models_data["prediction_models"]),
            },
        )

        return {
            "status": "success",
            "backup_info": backup_info,
            "models_backed_up": len(models_data["anomaly_models"])
            + len(models_data["prediction_models"]),
        }

    def create_cache_snapshot(self) -> Dict[str, Any]:
        """
        Create snapshot of cache statistics.

        Returns:
            dict: Snapshot information
        """
        from services.infrastructure.cache.redis_client import get_cache_client

        cache = get_cache_client()
        cache_stats = cache.get_stats()

        backup_info = self.create_backup(
            backup_type="snapshot",
            data=cache_stats,
            name="cache_stats",
            metadata={"cache_type": "redis" if cache.use_redis else "memory"},
        )

        return {
            "status": "success",
            "backup_info": backup_info,
            "cache_stats": cache_stats,
        }

    def export_analysis_results(
        self,
        analysis_type: str,
        results: Dict[str, Any],
        equipment_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Export analysis results for archival.

        Args:
            analysis_type: Type of analysis ('roi', 'capacity', 'runrate')
            results: Analysis results
            equipment_code: Equipment code

        Returns:
            dict: Export information
        """
        metadata = {
            "analysis_type": analysis_type,
            "equipment_code": equipment_code,
        }

        backup_info = self.create_backup(
            backup_type="export",
            data=results,
            name=(
                f"{analysis_type}_{equipment_code}" if equipment_code else analysis_type
            ),
            metadata=metadata,
        )

        return {
            "status": "success",
            "backup_info": backup_info,
        }

    def get_backup_statistics(self) -> Dict[str, Any]:
        """
        Get backup statistics.

        Returns:
            dict: Backup statistics
        """
        total_backups = len(self.backup_history)

        by_type = {}
        total_size = 0

        for backup in self.backup_history:
            backup_type = backup["backup_type"]
            by_type[backup_type] = by_type.get(backup_type, 0) + 1
            total_size += backup.get("file_size_bytes", 0)

        return {
            "status": "success",
            "total_backups": total_backups,
            "by_type": by_type,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "backup_directory": str(self.backup_dir),
            "recent_backups": self.backup_history[-5:],
        }


# Global backup manager instance
_backup_manager: Optional[BackupManager] = None


def get_backup_manager() -> BackupManager:
    """
    Get global backup manager instance.

    Returns:
        BackupManager: Global backup manager instance
    """
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = BackupManager()
    return _backup_manager
