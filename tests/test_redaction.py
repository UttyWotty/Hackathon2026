"""
Tests for sensitive data redaction utilities covering text redaction and
recursive structure redaction. These are security-critical functions that
prevent accidental secret leakage in logs and error messages.
All tests are pure (no I/O, no mocks).
"""

from utils.redaction import redact_any, redact_text

REDACTED_PLACEHOLDER = "<redacted>"


# ===================================================================
# redact_text
# ===================================================================


class TestRedactText:
    """Tests for redact_text."""

    # --- Happy path: key-value patterns ---

    def test_password_equals(self) -> None:
        """PASSWORD=value pattern is redacted."""
        text = "PASSWORD=s3cretPass"
        result = redact_text(text)
        assert "s3cretPass" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_api_key_colon(self) -> None:
        """api_key: value pattern is redacted."""
        text = "api_key: abc123def456"
        result = redact_text(text)
        assert "abc123def456" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_secret_equals(self) -> None:
        """SECRET=value pattern is redacted."""
        text = "SECRET=xyzzy12345"
        result = redact_text(text)
        assert "xyzzy12345" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_access_key_equals(self) -> None:
        """access_key=value pattern is redacted."""
        text = "access_key=AKIAIOSFODNN7EXAMPLE"
        result = redact_text(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_private_key_equals(self) -> None:
        """PRIVATE_KEY=value pattern is redacted."""
        text = "PRIVATE_KEY=base64encodedkey"
        result = redact_text(text)
        assert "base64encodedkey" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_token_equals(self) -> None:
        """TOKEN=value pattern is redacted."""
        text = "REFRESH_TOKEN=eyJhbGciOiJIUzI1NiJ9"
        result = redact_text(text)
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_passwd_equals(self) -> None:
        """passwd=value pattern is redacted."""
        text = "passwd=hunter2"
        result = redact_text(text)
        assert "hunter2" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_quoted_value_redacted(self) -> None:
        """Quoted secret values are redacted."""
        text = 'api_key: "my-secret-key-12345"'
        result = redact_text(text)
        assert "my-secret-key-12345" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_case_insensitive_key(self) -> None:
        """Key matching is case-insensitive."""
        text = "Password=s3cret"
        result = redact_text(text)
        assert "s3cret" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_api_key_with_hyphen(self) -> None:
        """api-key pattern (hyphen variant) is redacted."""
        text = "api-key=abcdef"
        result = redact_text(text)
        assert "abcdef" not in result
        assert REDACTED_PLACEHOLDER in result

    # --- Happy path: Bearer tokens ---

    def test_bearer_token_redacted(self) -> None:
        """Bearer token in Authorization header is redacted."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def"
        result = redact_text(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "Bearer" in result
        assert REDACTED_PLACEHOLDER in result

    def test_bearer_case_insensitive(self) -> None:
        """Bearer keyword matching is case-insensitive."""
        text = "bearer abcdef123456"
        result = redact_text(text)
        assert "abcdef123456" not in result
        assert REDACTED_PLACEHOLDER in result

    # --- Happy path: PEM private keys ---

    def test_pem_private_key_redacted(self) -> None:
        """PEM-encoded private key block is redacted."""
        text = (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7\n"
            "-----END PRIVATE KEY-----"
        )
        result = redact_text(text)
        assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7" not in result
        assert "-----BEGIN PRIVATE KEY-----" in result
        assert REDACTED_PLACEHOLDER in result

    def test_rsa_private_key_redacted(self) -> None:
        """RSA PRIVATE KEY block is redacted."""
        text = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA2a2rwplBQXzO\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = redact_text(text)
        assert "MIIEowIBAAKCAQEA2a2rwplBQXzO" not in result
        assert REDACTED_PLACEHOLDER in result

    # --- Happy path: multiple secrets in one text ---

    def test_multiple_secrets_all_redacted(self) -> None:
        """Multiple secret patterns in one text are all redacted."""
        text = "password=secret123 " "api_key=abc456 " "Bearer tokenXYZ"
        result = redact_text(text)
        assert "secret123" not in result
        assert "abc456" not in result
        assert "tokenXYZ" not in result

    # --- Boundary cases ---

    def test_empty_string_returns_empty(self) -> None:
        """Empty string returns empty string."""
        result = redact_text("")
        assert result == ""

    def test_no_secrets_unchanged(self) -> None:
        """Text without secrets passes through unchanged."""
        text = "This is a normal log message with no secrets."
        result = redact_text(text)
        assert result == text

    def test_key_name_preserved(self) -> None:
        """The key name itself is preserved, only the value is redacted."""
        text = "password=mysecret"
        result = redact_text(text)
        assert "password" in result.lower()
        assert "mysecret" not in result

    def test_surrounding_text_preserved(self) -> None:
        """Text surrounding a secret is preserved."""
        text = "Connecting with password=secret123 to database"
        result = redact_text(text)
        assert "Connecting with" in result
        assert "secret123" not in result

    def test_prefixed_key_not_redacted(self) -> None:
        """Word-boundary matching means underscore-prefixed keys are not redacted."""
        text = "DATABASE_PASSWORD=still_visible"
        result = redact_text(text)
        assert result == text


# ===================================================================
# redact_any
# ===================================================================


class TestRedactAny:
    """Tests for redact_any."""

    # --- Happy path: string ---

    def test_string_redacted(self) -> None:
        """String values are redacted via redact_text."""
        result = redact_any("password=secret123")
        assert isinstance(result, str)
        assert "secret123" not in result
        assert REDACTED_PLACEHOLDER in result

    # --- Happy path: dict ---

    def test_dict_values_redacted(self) -> None:
        """Dict values containing secrets are redacted."""
        data = {
            "config": "api_key=abc123",
            "name": "safe_value",
        }
        result = redact_any(data)
        assert isinstance(result, dict)
        assert "abc123" not in result["config"]
        assert result["name"] == "safe_value"

    def test_nested_dict_redacted(self) -> None:
        """Nested dict values are recursively redacted."""
        data = {"outer": {"inner": "password=nested_secret"}}
        result = redact_any(data)
        assert "nested_secret" not in result["outer"]["inner"]

    def test_dict_keys_preserved(self) -> None:
        """Dict keys are not modified, only values."""
        data = {"password": "should_be_safe_key"}
        result = redact_any(data)
        assert "password" in result

    # --- Happy path: list ---

    def test_list_elements_redacted(self) -> None:
        """List elements containing secrets are redacted."""
        data = ["password=secret1", "normal_text", "api_key=secret2"]
        result = redact_any(data)
        assert isinstance(result, list)
        assert "secret1" not in result[0]
        assert result[1] == "normal_text"
        assert "secret2" not in result[2]

    def test_nested_list_redacted(self) -> None:
        """Nested lists are recursively redacted."""
        data = [["password=deep_secret"]]
        result = redact_any(data)
        assert isinstance(result, list)
        assert isinstance(result[0], list)
        assert "deep_secret" not in result[0][0]

    # --- Happy path: tuple ---

    def test_tuple_redacted_returns_tuple(self) -> None:
        """Tuple input returns a tuple with redacted values."""
        data = ("password=tuple_secret", "safe")
        result = redact_any(data)
        assert isinstance(result, tuple)
        assert "tuple_secret" not in result[0]
        assert result[1] == "safe"

    # --- Happy path: mixed structures ---

    def test_dict_with_list_values(self) -> None:
        """Dict containing list values is recursively redacted."""
        data = {
            "credentials": ["api_key=key1", "token=tok1"],
            "info": "no secrets here",
        }
        result = redact_any(data)
        assert "key1" not in result["credentials"][0]
        assert "tok1" not in result["credentials"][1]
        assert result["info"] == "no secrets here"

    def test_list_with_dict_elements(self) -> None:
        """List containing dict elements is recursively redacted."""
        data = [{"secret": "password=nested"}]
        result = redact_any(data)
        assert isinstance(result, list)
        assert "nested" not in str(result[0])

    # --- Boundary cases ---

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        result = redact_any(None)
        assert result is None

    def test_integer_passthrough(self) -> None:
        """Integer values pass through unchanged."""
        result = redact_any(42)
        assert result == 42

    def test_float_passthrough(self) -> None:
        """Float values pass through unchanged."""
        result = redact_any(3.14)
        assert result == 3.14

    def test_boolean_passthrough(self) -> None:
        """Boolean values pass through unchanged."""
        result = redact_any(True)
        assert result is True

    def test_empty_dict(self) -> None:
        """Empty dict returns empty dict."""
        result = redact_any({})
        assert result == {}

    def test_empty_list(self) -> None:
        """Empty list returns empty list."""
        result = redact_any([])
        assert result == []

    def test_empty_tuple(self) -> None:
        """Empty tuple returns empty tuple."""
        result = redact_any(())
        assert result == ()

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        result = redact_any("")
        assert result == ""

    # --- Error cases (robustness) ---

    def test_arbitrary_object_passthrough(self) -> None:
        """Arbitrary objects pass through without stringification."""

        class CustomObj:
            pass

        obj = CustomObj()
        result = redact_any(obj)
        assert result is obj

    def test_deeply_nested_structure(self) -> None:
        """Deeply nested structure is fully redacted."""
        data = {"a": [{"b": ("password=deep",)}]}
        result = redact_any(data)
        inner_tuple = result["a"][0]["b"]
        assert isinstance(inner_tuple, tuple)
        assert "deep" not in inner_tuple[0]
        assert REDACTED_PLACEHOLDER in inner_tuple[0]
