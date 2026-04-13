# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.idempotency_service import (
    _canonical_json,
    _clean_string,
    _normalize_number,
    _normalize_timestamp_window,
    build_execution_idempotency_key,
)


# ---------------------------------------------------------------------------
# _clean_string tests
# ---------------------------------------------------------------------------

class TestCleanString:
    def test_strips_and_lowercases(self):
        assert _clean_string("  HELLO  ") == "hello"

    def test_collapses_whitespace(self):
        assert _clean_string("a   b   c") == "a b c"

    def test_none_returns_empty(self):
        assert _clean_string(None) == ""

    def test_empty_string(self):
        assert _clean_string("") == ""

    def test_int_value(self):
        assert _clean_string(123) == "123"


# ---------------------------------------------------------------------------
# _normalize_number tests
# ---------------------------------------------------------------------------

class TestNormalizeNumber:
    def test_integer(self):
        assert _normalize_number(42) == "42.00000000"

    def test_float(self):
        assert _normalize_number(3.14) == "3.14000000"

    def test_string_number(self):
        assert _normalize_number("100.5") == "100.50000000"

    def test_none_returns_zero(self):
        assert _normalize_number(None) == "0"

    def test_invalid_string(self):
        assert _normalize_number("abc") == "0"

    def test_zero(self):
        assert _normalize_number(0) == "0.00000000"

    def test_negative(self):
        assert _normalize_number(-5.5) == "-5.50000000"


# ---------------------------------------------------------------------------
# _normalize_timestamp_window tests
# ---------------------------------------------------------------------------

class TestNormalizeTimestampWindow:
    def test_none_returns_empty(self):
        assert _normalize_timestamp_window(None) == ""

    def test_empty_string(self):
        assert _normalize_timestamp_window("") == ""

    def test_iso_format_with_z(self):
        result = _normalize_timestamp_window("2026-03-19T11:20:31Z")
        assert result == "2026-03-19T11:20Z"

    def test_iso_format_with_offset(self):
        result = _normalize_timestamp_window("2026-03-19T11:20:31+00:00")
        assert result == "2026-03-19T11:20Z"

    def test_unix_timestamp(self):
        # 2026-03-19 11:20:00 UTC ~ 1774012800 (approx)
        result = _normalize_timestamp_window(1774012800)
        assert result.startswith("2026-")
        assert result.endswith("Z")

    def test_float_timestamp(self):
        result = _normalize_timestamp_window(1774012800.0)
        assert "Z" in result

    def test_truncates_seconds(self):
        result1 = _normalize_timestamp_window("2026-03-19T11:20:00Z")
        result2 = _normalize_timestamp_window("2026-03-19T11:20:59Z")
        assert result1 == result2


# ---------------------------------------------------------------------------
# _canonical_json tests
# ---------------------------------------------------------------------------

class TestCanonicalJson:
    def test_sorts_keys(self):
        result = _canonical_json({"b": 1, "a": 2})
        assert result == '{"a":2,"b":1}'

    def test_no_spaces(self):
        result = _canonical_json({"key": "value"})
        assert " " not in result

    def test_empty_dict(self):
        result = _canonical_json({})
        assert result == "{}"


# ---------------------------------------------------------------------------
# build_execution_idempotency_key tests
# ---------------------------------------------------------------------------

class TestBuildExecutionIdempotencyKey:
    def test_deterministic_for_same_inputs(self):
        payload = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "market",
            "size": 0.01,
        }
        key1 = build_execution_idempotency_key(user_id="u1", payload=payload)
        key2 = build_execution_idempotency_key(user_id="u1", payload=payload)
        assert key1 == key2

    def test_different_users_different_keys(self):
        payload = {"symbol": "BTCUSDT", "side": "BUY", "size": 0.01}
        key1 = build_execution_idempotency_key(user_id="u1", payload=payload)
        key2 = build_execution_idempotency_key(user_id="u2", payload=payload)
        assert key1 != key2

    def test_different_symbols_different_keys(self):
        p1 = {"symbol": "BTCUSDT", "side": "BUY", "size": 0.01}
        p2 = {"symbol": "ETHUSDT", "side": "BUY", "size": 0.01}
        key1 = build_execution_idempotency_key(user_id="u1", payload=p1)
        key2 = build_execution_idempotency_key(user_id="u1", payload=p2)
        assert key1 != key2

    def test_case_insensitive_symbol(self):
        p1 = {"symbol": "BTCUSDT", "side": "BUY", "size": 0.01}
        p2 = {"symbol": "btcusdt", "side": "buy", "size": 0.01}
        key1 = build_execution_idempotency_key(user_id="u1", payload=p1)
        key2 = build_execution_idempotency_key(user_id="u1", payload=p2)
        assert key1 == key2

    def test_whitespace_insensitive(self):
        p1 = {"symbol": "BTCUSDT", "side": "BUY", "size": 0.01}
        p2 = {"symbol": "  BTCUSDT  ", "side": "  BUY  ", "size": 0.01}
        key1 = build_execution_idempotency_key(user_id="u1", payload=p1)
        key2 = build_execution_idempotency_key(user_id="u1", payload=p2)
        assert key1 == key2

    def test_returns_sha256_hex(self):
        payload = {"symbol": "BTCUSDT", "side": "BUY", "size": 0.01}
        key = build_execution_idempotency_key(user_id="u1", payload=payload)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_normalized_payload_overrides_payload(self):
        payload = {"symbol": "BTCUSDT", "side": "BUY", "size": 0.01}
        normalized = {"symbol": "ETHUSDT", "side": "BUY", "size": 0.01}
        key1 = build_execution_idempotency_key(
            user_id="u1", payload=payload, normalized_payload=normalized
        )
        key2 = build_execution_idempotency_key(
            user_id="u1", payload={"symbol": "ETHUSDT", "side": "BUY", "size": 0.01}
        )
        assert key1 == key2

    def test_different_sizes_different_keys(self):
        p1 = {"symbol": "BTCUSDT", "side": "BUY", "size": 0.01}
        p2 = {"symbol": "BTCUSDT", "side": "BUY", "size": 0.02}
        key1 = build_execution_idempotency_key(user_id="u1", payload=p1)
        key2 = build_execution_idempotency_key(user_id="u1", payload=p2)
        assert key1 != key2

    def test_scanner_signal_snapshot_source_event_id(self):
        payload = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "size": 0.01,
            "scanner_signal_snapshot": {"signal_id": "sig-001"},
        }
        key = build_execution_idempotency_key(user_id="u1", payload=payload)
        assert len(key) == 64
