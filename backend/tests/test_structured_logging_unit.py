# ruff: noqa: E402
import json
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.structured_logging import (
    StructuredJsonFormatter,
    _mask_sensitive_value,
    _sanitize_field,
)


# ---------------------------------------------------------------------------
# _mask_sensitive_value tests
# ---------------------------------------------------------------------------

class TestMaskSensitiveValue:
    def test_short_value_fully_masked(self):
        result = _mask_sensitive_value("abc")
        assert result == "***"

    def test_empty_value_returned_as_is(self):
        result = _mask_sensitive_value("")
        assert result == ""

    def test_exactly_8_chars_fully_masked(self):
        result = _mask_sensitive_value("12345678")
        assert result == "********"

    def test_long_value_partially_masked(self):
        result = _mask_sensitive_value("abcdefghijk")
        assert result == "abc***ijk"

    def test_9_chars_partially_masked(self):
        result = _mask_sensitive_value("123456789")
        assert result == "123***789"


# ---------------------------------------------------------------------------
# _sanitize_field tests
# ---------------------------------------------------------------------------

class TestSanitizeField:
    def test_token_field_masked(self):
        result = _sanitize_field("access_token", "my-secret-token-value-long")
        assert result != "my-secret-token-value-long"
        assert "***" in str(result)

    def test_password_field_masked(self):
        result = _sanitize_field("password", "SuperSecretPassword123")
        assert "***" in str(result)

    def test_api_key_field_masked(self):
        result = _sanitize_field("api_key", "sk-1234567890abcdef")
        assert "***" in str(result)

    def test_authorization_field_masked(self):
        result = _sanitize_field("authorization", "Bearer eyJhbGciOiJIUzI1NiJ9.xxx")
        assert "***" in str(result)

    def test_secret_field_masked(self):
        result = _sanitize_field("jwt_secret", "very-long-secret-value-here")
        assert "***" in str(result)

    def test_user_id_field_masked(self):
        result = _sanitize_field("user_id", "user-123-long-uuid")
        assert "***" in str(result)

    def test_actor_user_id_field_masked(self):
        result = _sanitize_field("actor_user_id", "actor-456-long-uuid")
        assert "***" in str(result)

    def test_normal_field_not_masked(self):
        result = _sanitize_field("symbol", "BTCUSDT")
        assert result == "BTCUSDT"

    def test_normal_numeric_field_not_masked(self):
        result = _sanitize_field("duration_ms", 150)
        assert result == 150

    def test_user_id_none_not_masked(self):
        result = _sanitize_field("user_id", None)
        assert result is None


# ---------------------------------------------------------------------------
# StructuredJsonFormatter tests
# ---------------------------------------------------------------------------

class TestStructuredJsonFormatter:
    def test_format_produces_valid_json(self):
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert "timestamp" in parsed

    def test_format_includes_exception_info(self):
        formatter = StructuredJsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys as _sys
            exc_info = _sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error occurred",
            args=None,
            exc_info=exc_info,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert parsed["exception"]["type"] == "ValueError"
        assert "test error" in parsed["exception"]["message"]

    def test_format_masks_sensitive_extra_fields(self):
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Auth event",
            args=None,
            exc_info=None,
        )
        record.access_token = "a-very-long-secret-token-value"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "***" in str(parsed.get("access_token", ""))

    def test_format_includes_custom_fields(self):
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Custom fields",
            args=None,
            exc_info=None,
        )
        record.request_id = "req-123"
        record.action = "login"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["request_id"] == "req-123"
        assert parsed["action"] == "login"
