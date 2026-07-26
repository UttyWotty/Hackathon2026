"""
Domain-specific exceptions for the Snowflake Cortex LLM client.

Defines a single CortexError base with narrow subclasses for configuration,
transport and response-shape failures, so callers can distinguish a missing
credential from a network fault from a malformed payload. No generic
exceptions are raised anywhere in the Cortex modules.
"""


class CortexError(Exception):
    """Base class for every error raised by the Cortex client modules."""


class CortexConfigurationError(CortexError):
    """Raised when required configuration (account identifier or PAT) is absent."""


class CortexRequestError(CortexError):
    """Raised when the Cortex Messages endpoint is unreachable or returns a non-2xx status."""


class CortexResponseError(CortexError):
    """Raised when a response is not shaped like an Anthropic Messages payload."""
