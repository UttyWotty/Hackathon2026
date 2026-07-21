"""Sanitize free-text user input into a safe SQLite FTS5 MATCH expression.

Raw user input passed to an FTS5 ``MATCH`` is interpreted as query syntax, so
characters like ``-``, ``:``, ``*``, and quotes make FTS treat fragments as
column filters or operators and raise ``no such column`` errors. This module
tokenizes the input and quotes each token so any term (including hyphenated
domain terms such as ``run-rate``) is matched literally.
"""

import re
from typing import List

TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


def sanitize_fts_query(raw: str) -> str:
    """
    Convert arbitrary user text into a safe FTS5 MATCH string.

    Each alphanumeric token is extracted and wrapped in double quotes so FTS
    treats it as a literal term, joined by spaces (implicit AND). Returns an
    empty string when no usable token is present, which callers must treat as
    a no-match rather than passing it to MATCH.

    Args:
        raw: Untrusted search text straight from the request.

    Returns:
        A quoted, space-joined FTS5 MATCH expression, or "" if no token found.
    """
    tokens: List[str] = TOKEN_PATTERN.findall(raw or "")
    if not tokens:
        return ""
    return " ".join(f'"{token}"' for token in tokens)
