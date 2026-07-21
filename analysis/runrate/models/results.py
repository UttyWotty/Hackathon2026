"""Result models for RunRate analysis."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SessionMetrics:
    """Metrics for a single production session."""

    equipment_code: str
    session_id: int
    total_shots: int
    total_stops: int
    production_time_minutes: float
    downtime_minutes: float
    efficiency_percentage: float
    mode_ct_seconds: Optional[float] = None
    avg_stop_duration_minutes: Optional[float] = None


@dataclass
class RunRateResults:
    """
    Complete results of RunRate analysis.

    Attributes:
        status: Analysis status ("completed", "failed", etc.)
        message: Human-readable status message
        supplier_name: Supplier analyzed
        equipment_code: Equipment code (if filtered)
        date_range: Date range analyzed
        metrics: Dictionary of aggregate metrics
        output_files: List of generated file paths
        session_metrics: Optional list of per-session metrics
        error: Optional error message if analysis failed
    """

    status: str
    message: str
    supplier_name: str
    equipment_code: Optional[str]
    date_range: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    output_files: List[str] = field(default_factory=list)
    session_metrics: Optional[List[SessionMetrics]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary for API responses."""
        result = {
            "status": self.status,
            "message": self.message,
            "supplier_name": self.supplier_name,
            "equipment_code": self.equipment_code,
            "date_range": self.date_range,
            "metrics": self.metrics,
            "output_files": self.output_files,
        }

        if self.error:
            result["error"] = self.error

        if self.session_metrics:
            result["session_metrics"] = [
                {
                    "equipment_code": s.equipment_code,
                    "session_id": s.session_id,
                    "total_shots": s.total_shots,
                    "total_stops": s.total_stops,
                    "production_time_minutes": s.production_time_minutes,
                    "downtime_minutes": s.downtime_minutes,
                    "efficiency_percentage": s.efficiency_percentage,
                    "mode_ct_seconds": s.mode_ct_seconds,
                    "avg_stop_duration_minutes": s.avg_stop_duration_minutes,
                }
                for s in self.session_metrics
            ]

        return result

    @classmethod
    def empty_result(
        cls,
        supplier_name: str,
        equipment_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> "RunRateResults":
        """Create an empty result when no data is found."""
        date_range = f"{start_date or 'No limit'} to {end_date or 'No limit'}"

        return cls(
            status="completed",
            message="No data found for the specified criteria",
            supplier_name=supplier_name,
            equipment_code=equipment_code,
            date_range=date_range,
            metrics={
                "total_records": 0,
                "total_sessions": 0,
                "total_shots": 0,
                "total_stops": 0,
                "efficiency_percentage": 0.0,
            },
            output_files=[],
        )

    @classmethod
    def error_result(
        cls,
        supplier_name: str,
        error_message: str,
        equipment_code: Optional[str] = None,
    ) -> "RunRateResults":
        """Create an error result when analysis fails."""
        return cls(
            status="failed",
            message="Analysis failed",
            supplier_name=supplier_name,
            equipment_code=equipment_code,
            date_range="N/A",
            error=error_message,
        )
