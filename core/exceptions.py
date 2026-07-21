"""
Domain-specific exception types.

Why this exists:
  - Make API error handling explicit and consistent.
  - Avoid leaking raw exception strings that may contain sensitive data.
  - Provide a stable contract for callers and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DomainError(Exception):
    """
    Base exception for domain errors.

    Args:
        message: Safe error message for client/logs (will still be redacted by logging filter).
        code: Optional machine-readable error code.
        status_code: Suggested HTTP status code when raised from API handlers.
    """

    message: str
    code: Optional[str] = None
    status_code: int = 400

    def __str__(self) -> str:
        return self.message


class InvalidAnalysisParametersError(DomainError):
    """Raised when analysis parameters are invalid or inconsistent."""


class JobNotFoundError(DomainError):
    """Raised when a job id is not found."""

    def __init__(
        self, message: str = "Job not found", code: Optional[str] = "job_not_found"
    ):
        super().__init__(message=message, code=code, status_code=404)
