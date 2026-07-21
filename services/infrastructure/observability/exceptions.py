"""
Domain-specific exceptions for the observability subsystem.

Covers connection failures, scoring errors, and trace recording problems
so callers can handle observability issues without catching generic exceptions.
"""

from core.exceptions import DomainError


class LangfuseConnectionError(DomainError):
    """Raised when the Langfuse client cannot connect or authenticate.

    This typically indicates misconfigured environment variables
    (host, public key, secret key) or the Langfuse server being unreachable.
    """

    def __init__(self, message: str = "Failed to connect to Langfuse") -> None:
        super().__init__(
            message=message, code="langfuse_connection_error", status_code=503
        )


class ScoringError(DomainError):
    """Raised when an automated score computation fails.

    Covers both inline scorers (latency, cost, SQL correctness) and
    LLM-as-judge evaluations (relevance, hallucination, domain accuracy).
    """

    def __init__(self, message: str = "Scoring computation failed") -> None:
        super().__init__(message=message, code="scoring_error", status_code=500)


class TraceError(DomainError):
    """Raised when a trace or generation span cannot be recorded.

    Non-fatal -- callers should log and continue rather than failing
    the original LLM request.
    """

    def __init__(self, message: str = "Failed to record trace") -> None:
        super().__init__(message=message, code="trace_error", status_code=500)
