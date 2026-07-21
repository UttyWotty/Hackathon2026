"""
Sensitive data redaction utilities.

This module provides helpers to redact secrets from strings before they are written
to logs or returned in error messages.

Notes:
  - This is intentionally conservative: it prioritizes preventing accidental secret
    leakage over preserving exact text.
  - Keep patterns simple and readable; add TODOs when new secret formats appear.
"""

from __future__ import annotations

import re
from typing import Any

_REDACTED = "<redacted>"

# Common secret-ish key names seen in env vars, JSON, and log text.
_KEY_NAMES = r"(password|passwd|secret|api[_-]?key|access[_-]?key|private[_-]?key|refresh[_-]?token|token)"

# Matches patterns like: PASSWORD=..., "api_key": "...", token: "..."
_KEY_VALUE_RE = re.compile(
    rf"(?i)\b{_KEY_NAMES}\b\s*([:=])\s*([^\s,;\"']+|\"[^\"]*\"|'[^']*')"
)

# Matches Authorization header style bearer tokens.
_BEARER_RE = re.compile(r"(?i)\bBearer\s+([A-Za-z0-9\-_.=]+)")

# Matches PEM blocks (private keys / certificates). We only redact private keys.
_PEM_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN ([A-Z ]*PRIVATE KEY)-----[\s\S]*?-----END \1-----"
)


def redact_text(text: str) -> str:
    """
    Redact sensitive data from a text blob.

    Args:
        text: Input text to redact.

    Returns:
        Redacted text.
    """
    if not text:
        return text

    # Redact PEM private key blocks.
    text = _PEM_PRIVATE_KEY_RE.sub(
        "-----BEGIN PRIVATE KEY-----<redacted>-----END PRIVATE KEY-----", text
    )

    # Redact bearer tokens.
    text = _BEARER_RE.sub("Bearer <redacted>", text)

    # Redact key/value secret fields.
    def _kv_repl(match: re.Match) -> str:
        key = match.group(0).split(match.group(1))[
            0
        ]  # preserve original key casing/spacing
        sep = match.group(1)
        return f"{key}{sep} {_REDACTED}"

    text = _KEY_VALUE_RE.sub(_kv_repl, text)
    return text


def redact_any(value: Any) -> Any:
    """
    Redact sensitive data from common Python structures.

    This is used mainly for logging extras where values can be dicts/lists.

    Args:
        value: Any object (str/dict/list/etc.)

    Returns:
        Redacted value with same structure where possible.
    """
    if value is None:
        return None

    if isinstance(value, str):
        return redact_text(value)

    if isinstance(value, dict):
        return {k: redact_any(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        redacted = [redact_any(v) for v in value]
        return type(value)(redacted) if isinstance(value, tuple) else redacted

    # Fallback: do not stringify arbitrary objects here (can be expensive).
    return value
