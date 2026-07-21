"""
Tests for input validation and sanitization utilities covering SQL string
sanitization, equipment code validation, date string validation, supplier
name validation, list sanitization, and analytics request validation.
These are security-critical functions that guard against SQL injection.
"""

import pytest

from utils.input_validation import (
    InputValidationError,
    sanitize_list,
    sanitize_sql_string,
    validate_analytics_request,
    validate_date_string,
    validate_equipment_code,
    validate_supplier_name,
)

# ===================================================================
# sanitize_sql_string
# ===================================================================


class TestSanitizeSqlString:
    """Tests for sanitize_sql_string."""

    # --- Happy path ---

    def test_simple_alphanumeric(self) -> None:
        """Simple alphanumeric string passes sanitization."""
        result = sanitize_sql_string("Machine01")
        assert result == "Machine01"

    def test_string_with_hyphens(self) -> None:
        """String with hyphens passes."""
        result = sanitize_sql_string("EMA-4101")
        assert result == "EMA-4101"

    def test_string_with_underscores(self) -> None:
        """String with underscores passes."""
        result = sanitize_sql_string("equip_code_1")
        assert result == "equip_code_1"

    def test_string_with_dots(self) -> None:
        """String with dots passes."""
        result = sanitize_sql_string("v2.1.0")
        assert result == "v2.1.0"

    def test_string_with_spaces(self) -> None:
        """String with spaces passes in default mode."""
        result = sanitize_sql_string("Machine Alpha")
        assert result == "Machine Alpha"

    def test_whitespace_stripped(self) -> None:
        """Leading and trailing whitespace is stripped."""
        result = sanitize_sql_string("  Machine01  ")
        assert result == "Machine01"

    def test_allow_special_true(self) -> None:
        """With allow_special=True, special characters beyond default set pass."""
        result = sanitize_sql_string("Acme Co. (USA)", allow_special=True)
        assert result == "Acme Co. (USA)"

    # --- Boundary cases ---

    def test_exact_max_length(self) -> None:
        """String at exactly max_length passes."""
        value = "a" * 200
        result = sanitize_sql_string(value, max_length=200)
        assert result == value

    def test_exceeds_max_length(self) -> None:
        """String exceeding max_length raises error."""
        value = "a" * 201
        with pytest.raises(InputValidationError, match="too long"):
            sanitize_sql_string(value, max_length=200)

    def test_custom_max_length(self) -> None:
        """Custom max_length is respected."""
        value = "a" * 11
        with pytest.raises(InputValidationError, match="too long"):
            sanitize_sql_string(value, max_length=10)

    def test_single_character(self) -> None:
        """Single character string passes."""
        result = sanitize_sql_string("A")
        assert result == "A"

    # --- Error cases: type and emptiness ---

    def test_non_string_input(self) -> None:
        """Non-string input raises InputValidationError."""
        with pytest.raises(InputValidationError, match="Expected string"):
            sanitize_sql_string(42)  # type: ignore[arg-type]

    def test_empty_string(self) -> None:
        """Empty string raises InputValidationError."""
        with pytest.raises(InputValidationError, match="cannot be empty"):
            sanitize_sql_string("")

    def test_whitespace_only(self) -> None:
        """Whitespace-only string raises InputValidationError after strip."""
        with pytest.raises(InputValidationError, match="cannot be empty"):
            sanitize_sql_string("   ")

    # --- Error cases: dangerous patterns ---

    def test_single_quote_rejected(self) -> None:
        """Single quotes are rejected as injection risk."""
        with pytest.raises(InputValidationError, match="dangerous characters"):
            sanitize_sql_string("it's")

    def test_double_quote_rejected(self) -> None:
        """Double quotes are rejected."""
        with pytest.raises(InputValidationError, match="dangerous characters"):
            sanitize_sql_string('say "hello"')

    def test_semicolon_rejected(self) -> None:
        """Semicolons are rejected as injection risk."""
        with pytest.raises(InputValidationError, match="dangerous characters"):
            sanitize_sql_string("value;")

    def test_double_dash_comment_rejected(self) -> None:
        """Double-dash SQL comment is rejected."""
        with pytest.raises(InputValidationError, match="dangerous characters"):
            sanitize_sql_string("value -- comment")

    def test_block_comment_start_rejected(self) -> None:
        """Block comment start is rejected."""
        with pytest.raises(InputValidationError, match="dangerous characters"):
            sanitize_sql_string("value /* comment")

    def test_block_comment_end_rejected(self) -> None:
        """Block comment end is rejected."""
        with pytest.raises(InputValidationError, match="dangerous characters"):
            sanitize_sql_string("value */ end")

    def test_drop_keyword_rejected(self) -> None:
        """SQL DROP keyword is rejected."""
        with pytest.raises(InputValidationError, match="dangerous characters"):
            sanitize_sql_string("DROP TABLE")

    def test_delete_keyword_rejected(self) -> None:
        """SQL DELETE keyword is rejected."""
        with pytest.raises(InputValidationError, match="dangerous characters"):
            sanitize_sql_string("DELETE FROM t")

    def test_exec_keyword_rejected(self) -> None:
        """SQL EXEC keyword is rejected."""
        with pytest.raises(InputValidationError, match="dangerous characters"):
            sanitize_sql_string("EXEC cmd")

    # --- Error cases: invalid characters (default mode) ---

    def test_at_sign_rejected_default(self) -> None:
        """At sign is rejected in default mode."""
        with pytest.raises(InputValidationError, match="invalid characters"):
            sanitize_sql_string("user@host")

    def test_hash_rejected_default(self) -> None:
        """Hash symbol is rejected in default mode."""
        with pytest.raises(InputValidationError, match="invalid characters"):
            sanitize_sql_string("item#1")

    def test_parentheses_rejected_default(self) -> None:
        """Parentheses are rejected in default mode."""
        with pytest.raises(InputValidationError, match="invalid characters"):
            sanitize_sql_string("item(1)")


# ===================================================================
# validate_equipment_code
# ===================================================================


class TestValidateEquipmentCode:
    """Tests for validate_equipment_code."""

    # --- Happy path ---

    def test_simple_code(self) -> None:
        """Simple alphanumeric equipment code passes."""
        result = validate_equipment_code("EQ001")
        assert result == "EQ001"

    def test_code_with_hyphen(self) -> None:
        """Equipment code with hyphen passes."""
        result = validate_equipment_code("EMA-4101")
        assert result == "EMA-4101"

    def test_code_with_underscore(self) -> None:
        """Equipment code with underscore passes."""
        result = validate_equipment_code("EQ_001")
        assert result == "EQ_001"

    # --- Boundary cases ---

    def test_max_length_50(self) -> None:
        """Equipment code at exactly 50 chars passes."""
        code = "A" * 50
        result = validate_equipment_code(code)
        assert result == code

    def test_exceeds_max_length_50(self) -> None:
        """Equipment code over 50 chars raises error."""
        code = "A" * 51
        with pytest.raises(InputValidationError, match="too long"):
            validate_equipment_code(code)

    # --- Error cases ---

    def test_injection_attempt(self) -> None:
        """SQL injection in equipment code is blocked."""
        with pytest.raises(InputValidationError, match="dangerous characters"):
            validate_equipment_code("EQ001'; DROP TABLE--")

    def test_empty_code(self) -> None:
        """Empty equipment code raises error."""
        with pytest.raises(InputValidationError, match="cannot be empty"):
            validate_equipment_code("")


# ===================================================================
# validate_date_string
# ===================================================================


class TestValidateDateString:
    """Tests for validate_date_string."""

    # --- Happy path ---

    def test_valid_date(self) -> None:
        """Valid YYYY-MM-DD date passes."""
        result = validate_date_string("2025-06-15")
        assert result == "2025-06-15"

    def test_first_day(self) -> None:
        """First day of month passes."""
        result = validate_date_string("2025-01-01")
        assert result == "2025-01-01"

    def test_year_2000(self) -> None:
        """Year 2000 is within valid range."""
        result = validate_date_string("2000-01-01")
        assert result == "2000-01-01"

    def test_year_2100(self) -> None:
        """Year 2100 is within valid range."""
        result = validate_date_string("2100-12-31")
        assert result == "2100-12-31"

    # --- Boundary cases ---

    def test_year_1999_rejected(self) -> None:
        """Year below 2000 raises error."""
        with pytest.raises(InputValidationError, match="Year out of valid range"):
            validate_date_string("1999-12-31")

    def test_year_2101_rejected(self) -> None:
        """Year above 2100 raises error."""
        with pytest.raises(InputValidationError, match="Year out of valid range"):
            validate_date_string("2101-01-01")

    def test_month_0_rejected(self) -> None:
        """Month 0 raises error."""
        with pytest.raises(InputValidationError, match="Month out of valid range"):
            validate_date_string("2025-00-15")

    def test_month_13_rejected(self) -> None:
        """Month 13 raises error."""
        with pytest.raises(InputValidationError, match="Month out of valid range"):
            validate_date_string("2025-13-01")

    def test_day_0_rejected(self) -> None:
        """Day 0 raises error."""
        with pytest.raises(InputValidationError, match="Day out of valid range"):
            validate_date_string("2025-06-00")

    def test_day_32_rejected(self) -> None:
        """Day 32 raises error."""
        with pytest.raises(InputValidationError, match="Day out of valid range"):
            validate_date_string("2025-06-32")

    # --- Error cases: format ---

    def test_slash_separator_rejected(self) -> None:
        """Slash-separated date is rejected by sanitize_sql_string."""
        with pytest.raises(InputValidationError, match="invalid characters"):
            validate_date_string("2025/06/15")

    def test_date_with_time_rejected(self) -> None:
        """Date with time component exceeds max_length=10."""
        with pytest.raises(InputValidationError, match="too long"):
            validate_date_string("2025-06-15 10:00:00")

    def test_wrong_format_rejected(self) -> None:
        """Non-date string that passes sanitization fails format check."""
        with pytest.raises(InputValidationError, match="Invalid date format"):
            validate_date_string("not-a-date")

    def test_injection_attempt(self) -> None:
        """SQL injection in date parameter is blocked."""
        with pytest.raises(InputValidationError):
            validate_date_string("2025-06-15' OR '1")


# ===================================================================
# validate_supplier_name
# ===================================================================


class TestValidateSupplierName:
    """Tests for validate_supplier_name."""

    # --- Happy path ---

    def test_simple_name(self) -> None:
        """Simple supplier name passes."""
        result = validate_supplier_name("Acme Corp")
        assert result == "Acme Corp"

    def test_all_keyword(self) -> None:
        """Special value 'All' passes without sanitization."""
        result = validate_supplier_name("All")
        assert result == "All"

    def test_name_with_special_chars(self) -> None:
        """Supplier name with special characters passes via allow_special."""
        result = validate_supplier_name("Acme Co. (USA)")
        assert result == "Acme Co. (USA)"

    # --- Boundary cases ---

    def test_max_length_100(self) -> None:
        """Supplier name at 100 chars passes."""
        name = "A" * 100
        result = validate_supplier_name(name)
        assert result == name

    def test_exceeds_max_length_100(self) -> None:
        """Supplier name over 100 chars raises error."""
        name = "A" * 101
        with pytest.raises(InputValidationError, match="too long"):
            validate_supplier_name(name)

    # --- Error cases ---

    def test_injection_attempt(self) -> None:
        """SQL injection in supplier name is blocked."""
        with pytest.raises(InputValidationError, match="dangerous characters"):
            validate_supplier_name("Acme'; DROP TABLE--")

    def test_empty_supplier(self) -> None:
        """Empty supplier name raises error."""
        with pytest.raises(InputValidationError, match="cannot be empty"):
            validate_supplier_name("")


# ===================================================================
# sanitize_list
# ===================================================================


class TestSanitizeList:
    """Tests for sanitize_list."""

    # --- Happy path ---

    def test_valid_list(self) -> None:
        """Valid list of equipment codes passes."""
        result = sanitize_list(["EQ001", "EQ002"], validate_equipment_code)
        assert result == ["EQ001", "EQ002"]

    def test_single_item_list(self) -> None:
        """Single item list passes."""
        result = sanitize_list(["EQ001"], validate_equipment_code)
        assert result == ["EQ001"]

    def test_custom_validator(self) -> None:
        """Custom validator function is applied to each element."""

        def uppercase_validator(value: str) -> str:
            return value.upper()

        result = sanitize_list(["abc", "def"], uppercase_validator)
        assert result == ["ABC", "DEF"]

    # --- Boundary cases ---

    def test_empty_list(self) -> None:
        """Empty list passes validation (no items to validate)."""
        result = sanitize_list([], validate_equipment_code)
        assert result == []

    def test_max_items_boundary(self) -> None:
        """List at exactly max_items passes; one over raises error."""
        codes_ok = [f"EQ{i:03d}" for i in range(100)]
        assert len(sanitize_list(codes_ok, validate_equipment_code)) == 100
        codes_over = codes_ok + ["EQ100"]
        with pytest.raises(InputValidationError, match="Too many items"):
            sanitize_list(codes_over, validate_equipment_code)

    def test_custom_max_items(self) -> None:
        """Custom max_items is respected."""
        codes = ["EQ001", "EQ002", "EQ003"]
        with pytest.raises(InputValidationError, match="Too many items"):
            sanitize_list(codes, validate_equipment_code, max_items=2)

    # --- Error cases ---

    def test_non_list_input(self) -> None:
        """Non-list input raises InputValidationError."""
        with pytest.raises(InputValidationError, match="Expected list"):
            sanitize_list("not_a_list", validate_equipment_code)  # type: ignore[arg-type]

    def test_invalid_item_propagates_error(self) -> None:
        """Invalid item in list propagates validator error."""
        with pytest.raises(InputValidationError):
            sanitize_list(["EQ001", "'; DROP TABLE--"], validate_equipment_code)


# ===================================================================
# validate_analytics_request
# ===================================================================


class TestValidateAnalyticsRequest:
    """Tests for validate_analytics_request."""

    # --- Happy path ---

    def test_full_valid_request(self) -> None:
        """Request with all valid parameters passes."""
        result = validate_analytics_request(
            equipment_codes=["EQ001", "EQ002"],
            supplier_names=["Acme Corp"],
            start_date="2025-01-01",
            end_date="2025-06-30",
        )
        assert result["equipment_codes"] == ["EQ001", "EQ002"]
        assert result["supplier_names"] == ["Acme Corp"]
        assert result["start_date"] == "2025-01-01"
        assert result["end_date"] == "2025-06-30"

    def test_equipment_codes_only(self) -> None:
        """Request with only equipment codes omits other keys."""
        result = validate_analytics_request(equipment_codes=["EQ001"])
        assert result == {"equipment_codes": ["EQ001"]}

    def test_dates_only(self) -> None:
        """Request with only dates passes."""
        result = validate_analytics_request(
            start_date="2025-01-01", end_date="2025-12-31"
        )
        assert result["start_date"] == "2025-01-01"
        assert result["end_date"] == "2025-12-31"

    def test_all_none_returns_empty(self) -> None:
        """Request with all None parameters returns empty dict."""
        assert validate_analytics_request() == {}

    # --- Boundary cases ---

    def test_same_start_and_end_date(self) -> None:
        """Same start and end date passes (single-day range)."""
        result = validate_analytics_request(
            start_date="2025-06-15", end_date="2025-06-15"
        )
        assert result["start_date"] == result["end_date"] == "2025-06-15"

    def test_equipment_codes_at_max_50(self) -> None:
        """50 equipment codes (max for analytics) passes."""
        codes = [f"EQ{i:03d}" for i in range(50)]
        assert (
            len(validate_analytics_request(equipment_codes=codes)["equipment_codes"])
            == 50
        )

    def test_equipment_codes_over_max_50(self) -> None:
        """51 equipment codes raises error."""
        codes = [f"EQ{i:03d}" for i in range(51)]
        with pytest.raises(InputValidationError, match="Too many items"):
            validate_analytics_request(equipment_codes=codes)

    # --- Error cases ---

    def test_start_after_end_date(self) -> None:
        """Start date after end date raises error."""
        with pytest.raises(InputValidationError, match="must be before end date"):
            validate_analytics_request(start_date="2025-12-31", end_date="2025-01-01")

    def test_invalid_equipment_code_propagates(self) -> None:
        """Invalid equipment code in list propagates error."""
        with pytest.raises(InputValidationError):
            validate_analytics_request(equipment_codes=["EQ001", "'; DROP--"])

    def test_invalid_date_propagates(self) -> None:
        """Invalid date format propagates error."""
        with pytest.raises(InputValidationError):
            validate_analytics_request(start_date="not-a-date")

    def test_invalid_supplier_propagates(self) -> None:
        """Invalid supplier name propagates error."""
        with pytest.raises(InputValidationError):
            validate_analytics_request(supplier_names=["Acme'; DROP TABLE--"])
