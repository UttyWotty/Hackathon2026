"""Unit tests for the FTS5 query sanitizer.

Verifies that hyphenated and operator-bearing search terms are neutralized into
quoted literal tokens, and that empty or symbol-only input yields an empty
string so callers short-circuit instead of calling MATCH.
"""

from utils.fts_query import sanitize_fts_query


def test_hyphenated_term_is_quoted_per_token() -> None:
    assert sanitize_fts_query("run-rate") == '"run" "rate"'


def test_domain_terms_do_not_leak_fts_operators() -> None:
    assert sanitize_fts_query("ct-deviation") == '"ct" "deviation"'
    assert sanitize_fts_query("tooling-eol") == '"tooling" "eol"'


def test_multiword_query_joins_tokens() -> None:
    assert sanitize_fts_query("hello world") == '"hello" "world"'


def test_fts_operator_characters_are_stripped() -> None:
    assert sanitize_fts_query('foo:bar* "baz"') == '"foo" "bar" "baz"'


def test_empty_or_symbol_only_returns_empty_string() -> None:
    assert sanitize_fts_query("") == ""
    assert sanitize_fts_query("   ") == ""
    assert sanitize_fts_query("---") == ""
    assert sanitize_fts_query("*") == ""
