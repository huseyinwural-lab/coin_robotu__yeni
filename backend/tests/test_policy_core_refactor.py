# ruff: noqa: E402
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.policy.quote_policy import InvalidSymbol, filter_allowed_symbols, normalize_symbol, validate_symbol
from services.execution_precheck_service import validate_execution_payload


def test_core_quote_policy_rejects_empty_symbol():
    with pytest.raises(InvalidSymbol) as exc_info:
        validate_symbol(None)
    assert str(exc_info.value) == "symbol_empty"


def test_core_quote_policy_rejects_unsupported_quote_asset():
    with pytest.raises(InvalidSymbol) as exc_info:
        validate_symbol("ETHBTC")
    assert str(exc_info.value) == "unsupported_quote_asset"


def test_core_quote_policy_accepts_btcusdt_and_usdc_symbols():
    assert normalize_symbol("BTCUSDT") == "BTCUSDT"
    assert normalize_symbol("ethusdc") == "ETHUSDC"


def test_filter_allowed_symbols_keeps_only_usdt_usdc():
    result = filter_allowed_symbols(["ETHUSDT", "ETHBTC", "SOLUSDC", "BNBBUSD"])
    assert result == ["ETHUSDT", "SOLUSDC"]


def test_execution_precheck_returns_primary_and_legacy_invalid_codes():
    payload = {
        "symbol": "ETHBTC",
        "market_type": "spot",
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 25,
        "execution_mode": "manual",
    }
    result = validate_execution_payload(payload)
    codes = result.get("reject_reason_codes") or []
    assert "unsupported_quote_asset" in codes
    assert "invalid_quote_asset" in codes


def test_no_btc_fallback_patterns_in_blocker_files():
    target_files = [
        Path("/app/backend/schemas.py"),
        Path("/app/backend/model_domains/risk_execution_positions.py"),
        Path("/app/backend/services/trading_preview_service.py"),
        Path("/app/backend/model_domains/learning_recommendations.py"),
        Path("/app/backend/routers/admin_strategy_intelligence.py"),
    ]
    forbidden_patterns = [
        'symbol or "BTCUSDT"',
        'default="BTCUSDT"',
        'fallback="BTCUSDT"',
    ]

    for file_path in target_files:
        content = file_path.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            assert pattern not in content, f"{file_path} contains forbidden fallback pattern: {pattern}"
