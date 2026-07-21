"""
Tests for SQL validation utilities covering query validation, identifier
sanitization, and date parameter validation. These are security-critical
functions that guard against SQL injection and unsafe query execution.
All tests are pure (no I/O, no mocks).
"""

import pytest

from utils.sql_validation import (
    SQLValidationError,
    sanitize_sql_identifier,
    validate_date_param,
    validate_sql_query,
)

# ===================================================================
# validate_sql_query
# ===================================================================


class TestValidateSqlQuery:
    """Tests for validate_sql_query."""

    # --- Happy path ---

    def test_simple_select(self) -> None:
        """A basic SELECT query passes validation and is read-only."""
        query, is_read_only = validate_sql_query("SELECT * FROM machines")
        assert query == "SELECT * FROM machines"
        assert is_read_only is True

    def test_select_with_where(self) -> None:
        """SELECT with WHERE clause passes validation."""
        sql = "SELECT id, name FROM parts WHERE status = 'active'"
        query, is_read_only = validate_sql_query(sql)
        assert query == sql
        assert is_read_only is True

    def test_with_cte_query(self) -> None:
        """WITH (CTE) queries are recognized as read-only."""
        sql = "WITH cte AS (SELECT 1 AS x) SELECT x FROM cte"
        query, is_read_only = validate_sql_query(sql)
        assert query == sql
        assert is_read_only is True

    def test_show_query(self) -> None:
        """SHOW queries are recognized as read-only."""
        sql = "SHOW TABLES"
        query, is_read_only = validate_sql_query(sql)
        assert query == sql
        assert is_read_only is True

    def test_describe_query(self) -> None:
        """DESCRIBE queries are recognized as read-only."""
        sql = "DESCRIBE machines"
        query, is_read_only = validate_sql_query(sql)
        assert query == sql
        assert is_read_only is True

    def test_desc_query(self) -> None:
        """DESC shorthand queries are recognized as read-only."""
        sql = "DESC machines"
        query, is_read_only = validate_sql_query(sql)
        assert query == sql
        assert is_read_only is True

    def test_leading_whitespace_stripped(self) -> None:
        """Leading and trailing whitespace is stripped."""
        sql = "   SELECT 1   "
        query, is_read_only = validate_sql_query(sql)
        assert query == "SELECT 1"
        assert is_read_only is True

    def test_trailing_semicolon_allowed(self) -> None:
        """A single trailing semicolon is allowed."""
        sql = "SELECT 1;"
        query, is_read_only = validate_sql_query(sql)
        assert query == sql
        assert is_read_only is True

    def test_case_insensitive_select(self) -> None:
        """Lowercase select is recognized as read-only."""
        sql = "select count(*) from machines"
        query, is_read_only = validate_sql_query(sql)
        assert is_read_only is True

    # --- Boundary cases ---

    def test_max_length_exact(self) -> None:
        """Query exactly at max_length passes validation."""
        base = "SELECT "
        padding = "x" * (100 - len(base))
        sql = base + padding
        query, _ = validate_sql_query(sql, max_length=100)
        assert query == sql

    def test_max_length_exceeded_by_one(self) -> None:
        """Query one character over max_length raises error."""
        sql = "SELECT " + "x" * 94  # 101 chars total
        with pytest.raises(SQLValidationError, match="too long"):
            validate_sql_query(sql, max_length=100)

    def test_custom_max_length(self) -> None:
        """Custom max_length is respected."""
        sql = "SELECT 1"
        query, _ = validate_sql_query(sql, max_length=20)
        assert query == sql

    def test_multiple_semicolons_rejected(self) -> None:
        """More than one semicolon rejects query chaining."""
        sql = "SELECT 1; SELECT 2;"
        with pytest.raises(SQLValidationError, match="multiple semicolons"):
            validate_sql_query(sql)

    # --- Error cases: type and emptiness ---

    def test_non_string_input(self) -> None:
        """Non-string input raises SQLValidationError."""
        with pytest.raises(SQLValidationError, match="must be a string"):
            validate_sql_query(123)  # type: ignore[arg-type]

    def test_empty_string(self) -> None:
        """Empty string raises SQLValidationError."""
        with pytest.raises(SQLValidationError, match="cannot be empty"):
            validate_sql_query("")

    def test_whitespace_only(self) -> None:
        """Whitespace-only string raises SQLValidationError."""
        with pytest.raises(SQLValidationError, match="cannot be empty"):
            validate_sql_query("   ")

    # --- Error cases: dangerous keywords ---

    def test_drop_keyword_rejected(self) -> None:
        """DROP keyword in query raises error."""
        with pytest.raises(SQLValidationError, match="dangerous keyword.*DROP"):
            validate_sql_query("SELECT 1; DROP TABLE machines")

    def test_delete_keyword_rejected(self) -> None:
        """DELETE keyword in query raises error."""
        with pytest.raises(SQLValidationError, match="dangerous keyword.*DELETE"):
            validate_sql_query("DELETE FROM machines")

    def test_update_keyword_rejected(self) -> None:
        """UPDATE keyword in query raises error."""
        with pytest.raises(SQLValidationError, match="dangerous keyword.*UPDATE"):
            validate_sql_query("UPDATE machines SET status = 'off'")

    def test_insert_keyword_rejected(self) -> None:
        """INSERT keyword in query raises error."""
        with pytest.raises(SQLValidationError, match="dangerous keyword.*INSERT"):
            validate_sql_query("INSERT INTO machines VALUES (1)")

    def test_alter_keyword_rejected(self) -> None:
        """ALTER keyword in query raises error."""
        with pytest.raises(SQLValidationError, match="dangerous keyword.*ALTER"):
            validate_sql_query("ALTER TABLE machines ADD COLUMN x INT")

    def test_create_keyword_rejected(self) -> None:
        """CREATE keyword in query raises error."""
        with pytest.raises(SQLValidationError, match="dangerous keyword.*CREATE"):
            validate_sql_query("CREATE TABLE test (id INT)")

    def test_truncate_keyword_rejected(self) -> None:
        """TRUNCATE keyword in query raises error."""
        with pytest.raises(SQLValidationError, match="dangerous keyword.*TRUNCATE"):
            validate_sql_query("TRUNCATE TABLE machines")

    def test_grant_keyword_rejected(self) -> None:
        """GRANT keyword in query raises error."""
        with pytest.raises(SQLValidationError, match="dangerous keyword.*GRANT"):
            validate_sql_query("GRANT ALL ON machines TO user1")

    def test_merge_keyword_rejected(self) -> None:
        """MERGE keyword in query raises error."""
        with pytest.raises(SQLValidationError, match="dangerous keyword.*MERGE"):
            validate_sql_query("MERGE INTO t USING s ON t.id=s.id")

    def test_copy_keyword_rejected(self) -> None:
        """COPY keyword in query raises error."""
        with pytest.raises(SQLValidationError, match="dangerous keyword.*COPY"):
            validate_sql_query("COPY INTO @stage FROM machines")

    def test_unload_keyword_rejected(self) -> None:
        """UNLOAD keyword in query raises error."""
        with pytest.raises(SQLValidationError, match="dangerous keyword.*UNLOAD"):
            validate_sql_query("UNLOAD ('SELECT 1') TO 's3://bucket'")

    def test_dangerous_keyword_case_insensitive(self) -> None:
        """Dangerous keywords are detected regardless of case."""
        with pytest.raises(SQLValidationError, match="dangerous keyword"):
            validate_sql_query("select 1; drop table machines")

    # --- Error cases: injection patterns ---

    def test_single_quote_semicolon_injection(self) -> None:
        """Single-quote-semicolon injection pattern is blocked."""
        with pytest.raises(SQLValidationError, match="dangerous pattern"):
            validate_sql_query("SELECT * FROM t WHERE name = 'x';")

    def test_double_dash_comment_injection(self) -> None:
        """Double-dash comment injection pattern is blocked."""
        with pytest.raises(SQLValidationError, match="dangerous pattern"):
            validate_sql_query("SELECT * FROM t -- comment")

    def test_block_comment_injection(self) -> None:
        """Block comment injection pattern is blocked."""
        with pytest.raises(SQLValidationError, match="dangerous pattern"):
            validate_sql_query("SELECT * FROM t /* comment */")

    def test_xp_prefix_injection(self) -> None:
        """Extended stored procedure prefix xp_ is blocked."""
        with pytest.raises(SQLValidationError, match="dangerous pattern"):
            validate_sql_query("SELECT xp_cmdshell('dir')")

    def test_sp_prefix_injection(self) -> None:
        """Stored procedure prefix sp_ is blocked."""
        with pytest.raises(SQLValidationError, match="dangerous pattern"):
            validate_sql_query("SELECT sp_helpdb")

    # --- Error cases: non-read-only ---

    def test_non_select_query_rejected(self) -> None:
        """Queries not starting with SELECT/WITH/SHOW/DESCRIBE fail."""
        with pytest.raises(SQLValidationError, match="must start with SELECT"):
            validate_sql_query("EXPLAIN SELECT 1")


# ===================================================================
# sanitize_sql_identifier
# ===================================================================


class TestSanitizeSqlIdentifier:
    """Tests for sanitize_sql_identifier."""

    # --- Happy path ---

    def test_simple_table_name(self) -> None:
        """Simple alphanumeric identifier passes."""
        result = sanitize_sql_identifier("machines")
        assert result == "machines"

    def test_identifier_with_underscore(self) -> None:
        """Identifier with underscores passes."""
        result = sanitize_sql_identifier("shot_data")
        assert result == "shot_data"

    def test_identifier_with_dot(self) -> None:
        """Dot-separated identifier (schema.table) passes."""
        result = sanitize_sql_identifier("analytics.shot_data")
        assert result == "analytics.shot_data"

    def test_identifier_with_hyphen(self) -> None:
        """Identifier with hyphens passes."""
        result = sanitize_sql_identifier("shot-data")
        assert result == "shot-data"

    def test_identifier_with_numbers(self) -> None:
        """Identifier with leading/trailing numbers passes."""
        result = sanitize_sql_identifier("table1")
        assert result == "table1"

    def test_whitespace_stripped(self) -> None:
        """Leading and trailing whitespace is stripped."""
        result = sanitize_sql_identifier("  machines  ")
        assert result == "machines"

    # --- Boundary cases ---

    def test_single_character(self) -> None:
        """Single character identifier passes."""
        result = sanitize_sql_identifier("x")
        assert result == "x"

    def test_max_length_128(self) -> None:
        """Identifier at exactly 128 characters passes."""
        ident = "a" * 128
        result = sanitize_sql_identifier(ident)
        assert result == ident

    def test_exceeds_128_chars(self) -> None:
        """Identifier over 128 characters raises error."""
        ident = "a" * 129
        with pytest.raises(SQLValidationError, match="too long"):
            sanitize_sql_identifier(ident)

    # --- Error cases ---

    def test_non_string_input(self) -> None:
        """Non-string input raises SQLValidationError."""
        with pytest.raises(SQLValidationError, match="must be a string"):
            sanitize_sql_identifier(42)  # type: ignore[arg-type]

    def test_empty_string(self) -> None:
        """Empty string raises SQLValidationError."""
        with pytest.raises(SQLValidationError, match="cannot be empty"):
            sanitize_sql_identifier("")

    def test_whitespace_only(self) -> None:
        """Whitespace-only string raises SQLValidationError."""
        with pytest.raises(SQLValidationError, match="cannot be empty"):
            sanitize_sql_identifier("   ")

    def test_special_characters_rejected(self) -> None:
        """Characters outside allowed set are rejected."""
        with pytest.raises(SQLValidationError, match="invalid characters"):
            sanitize_sql_identifier("table;name")

    def test_space_in_identifier_rejected(self) -> None:
        """Spaces within identifier are rejected."""
        with pytest.raises(SQLValidationError, match="invalid characters"):
            sanitize_sql_identifier("table name")

    def test_single_quote_rejected(self) -> None:
        """Single quotes are rejected."""
        with pytest.raises(SQLValidationError, match="invalid characters"):
            sanitize_sql_identifier("table'name")

    def test_parenthesis_rejected(self) -> None:
        """Parentheses are rejected."""
        with pytest.raises(SQLValidationError, match="invalid characters"):
            sanitize_sql_identifier("table(name)")

    def test_sql_keyword_select_rejected(self) -> None:
        """SQL keyword SELECT as identifier is rejected."""
        with pytest.raises(SQLValidationError, match="SQL keyword"):
            sanitize_sql_identifier("SELECT")

    def test_sql_keyword_drop_rejected(self) -> None:
        """SQL keyword DROP as identifier is rejected."""
        with pytest.raises(SQLValidationError, match="SQL keyword"):
            sanitize_sql_identifier("DROP")

    def test_sql_keyword_case_insensitive(self) -> None:
        """SQL keyword detection is case-insensitive."""
        with pytest.raises(SQLValidationError, match="SQL keyword"):
            sanitize_sql_identifier("select")

    def test_sql_keyword_table_rejected(self) -> None:
        """SQL keyword TABLE as identifier is rejected."""
        with pytest.raises(SQLValidationError, match="SQL keyword"):
            sanitize_sql_identifier("TABLE")

    def test_keyword_as_substring_allowed(self) -> None:
        """SQL keywords as substrings of longer identifiers are allowed."""
        result = sanitize_sql_identifier("select_columns")
        assert result == "select_columns"


# ===================================================================
# validate_date_param
# ===================================================================


class TestValidateDateParam:
    """Tests for validate_date_param."""

    # --- Happy path ---

    def test_valid_date(self) -> None:
        """Valid YYYY-MM-DD date passes."""
        result = validate_date_param("2025-06-15")
        assert result == "2025-06-15"

    def test_first_day_of_year(self) -> None:
        """January 1st is valid."""
        result = validate_date_param("2025-01-01")
        assert result == "2025-01-01"

    def test_last_day_of_year(self) -> None:
        """December 31st is valid."""
        result = validate_date_param("2025-12-31")
        assert result == "2025-12-31"

    def test_leap_year_feb_29(self) -> None:
        """Feb 29 on a leap year is valid."""
        result = validate_date_param("2024-02-29")
        assert result == "2024-02-29"

    def test_returns_string_unchanged(self) -> None:
        """Return value is the exact same string."""
        date_str = "2025-03-04"
        result = validate_date_param(date_str)
        assert result is not None
        assert result == date_str

    # --- Boundary cases ---

    def test_non_leap_year_feb_29_rejected(self) -> None:
        """Feb 29 on a non-leap year raises error."""
        with pytest.raises(SQLValidationError, match="Invalid calendar date"):
            validate_date_param("2025-02-29")

    def test_month_13_rejected(self) -> None:
        """Month 13 raises error due to calendar validation."""
        with pytest.raises(SQLValidationError, match="Invalid calendar date"):
            validate_date_param("2025-13-01")

    def test_day_32_rejected(self) -> None:
        """Day 32 raises error due to calendar validation."""
        with pytest.raises(SQLValidationError, match="Invalid calendar date"):
            validate_date_param("2025-01-32")

    def test_month_00_rejected(self) -> None:
        """Month 00 raises error due to calendar validation."""
        with pytest.raises(SQLValidationError, match="Invalid calendar date"):
            validate_date_param("2025-00-15")

    def test_day_00_rejected(self) -> None:
        """Day 00 raises error due to calendar validation."""
        with pytest.raises(SQLValidationError, match="Invalid calendar date"):
            validate_date_param("2025-06-00")

    # --- Error cases: format ---

    def test_non_string_input(self) -> None:
        """Non-string input raises SQLValidationError."""
        with pytest.raises(SQLValidationError, match="must be a string"):
            validate_date_param(20250615)  # type: ignore[arg-type]

    def test_wrong_format_slash_separator(self) -> None:
        """Slash-separated dates are rejected."""
        with pytest.raises(SQLValidationError, match="Invalid date format"):
            validate_date_param("2025/06/15")

    def test_wrong_format_no_separator(self) -> None:
        """Dates without separators are rejected."""
        with pytest.raises(SQLValidationError, match="Invalid date format"):
            validate_date_param("20250615")

    def test_wrong_format_day_month_year(self) -> None:
        """DD-MM-YYYY format fails regex (too many digits in first group)."""
        with pytest.raises(SQLValidationError, match="Invalid date format"):
            validate_date_param("15-06-2025")

    def test_date_with_time_rejected(self) -> None:
        """Date with time component is rejected."""
        with pytest.raises(SQLValidationError, match="Invalid date format"):
            validate_date_param("2025-06-15 10:00:00")

    def test_injection_attempt_rejected(self) -> None:
        """SQL injection disguised as date is rejected."""
        with pytest.raises(SQLValidationError, match="Invalid date format"):
            validate_date_param("2025-06-15' OR '1'='1")

    def test_empty_string_rejected(self) -> None:
        """Empty string is rejected."""
        with pytest.raises(SQLValidationError, match="Invalid date format"):
            validate_date_param("")

    def test_partial_date_rejected(self) -> None:
        """Partial date (year-month only) is rejected."""
        with pytest.raises(SQLValidationError, match="Invalid date format"):
            validate_date_param("2025-06")

    def test_extra_digits_in_year_rejected(self) -> None:
        """Five-digit year is rejected."""
        with pytest.raises(SQLValidationError, match="Invalid date format"):
            validate_date_param("20250-06-15")
