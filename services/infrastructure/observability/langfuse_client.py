"""
Singleton Langfuse client factory with environment-based configuration.

Reads LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_ENABLED,
LANGFUSE_FLUSH_INTERVAL, and LANGFUSE_SAMPLE_RATE from the environment.
Returns None when disabled or keys are missing for graceful degradation.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment constants
# ---------------------------------------------------------------------------

LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "http://localhost:3001")
LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_ENABLED: bool = os.getenv("LANGFUSE_ENABLED", "False").lower() in (
    "true",
    "1",
    "yes",
)
LANGFUSE_FLUSH_INTERVAL: int = int(os.getenv("LANGFUSE_FLUSH_INTERVAL", "5"))
LANGFUSE_SAMPLE_RATE: float = float(os.getenv("LANGFUSE_SAMPLE_RATE", "1.0"))

# App version and release tag attached to every Langfuse trace.
# Bump APP_VERSION on each release; RELEASE can track deployment/git SHA.
APP_VERSION: str = os.getenv("APP_VERSION", "2.0.0")
APP_RELEASE: str = os.getenv("APP_RELEASE", "manufacturing-api@2.0.0")


# ---------------------------------------------------------------------------
# Singleton state
# ---------------------------------------------------------------------------

_langfuse_instance: Optional[object] = None
_initialized: bool = False


def _has_valid_keys() -> bool:
    """Check whether both API keys are present and non-empty."""
    return bool(LANGFUSE_PUBLIC_KEY) and bool(LANGFUSE_SECRET_KEY)


def get_langfuse() -> Optional[object]:
    """Return the shared Langfuse client, creating it on first call.

    Returns None when:
      - LANGFUSE_ENABLED is False
      - API keys are missing
      - The langfuse package is not installed
      - Client creation fails

    The return type is ``Optional[langfuse.Langfuse]`` but typed as
    ``object`` to avoid an import-time hard dependency.
    """
    global _langfuse_instance, _initialized

    if _initialized:
        return _langfuse_instance

    _initialized = True

    if not LANGFUSE_ENABLED:
        logger.info("Langfuse observability disabled (LANGFUSE_ENABLED=False)")
        return None

    if not _has_valid_keys():
        logger.warning("Langfuse keys missing -- observability disabled")
        return None

    try:
        from langfuse import Langfuse

        _langfuse_instance = Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
            flush_interval=LANGFUSE_FLUSH_INTERVAL,
            sample_rate=LANGFUSE_SAMPLE_RATE,
        )
        logger.info(
            "Langfuse observability initialized (host=%s, sample_rate=%.2f)",
            LANGFUSE_HOST,
            LANGFUSE_SAMPLE_RATE,
        )
        return _langfuse_instance

    except ImportError:
        logger.warning("langfuse package not installed -- observability disabled")
        return None
    except Exception:
        logger.exception("Failed to initialize Langfuse client")
        return None


def shutdown_langfuse() -> None:
    """Flush pending traces and shut down the Langfuse client."""
    global _langfuse_instance, _initialized

    if _langfuse_instance is not None:
        try:
            _langfuse_instance.flush()  # type: ignore[union-attr]
            logger.info("Langfuse traces flushed on shutdown")
        except Exception:
            logger.exception("Error flushing Langfuse traces")
        finally:
            try:
                _langfuse_instance.shutdown()  # type: ignore[union-attr]
            except Exception:
                pass
            _langfuse_instance = None

    _initialized = False
