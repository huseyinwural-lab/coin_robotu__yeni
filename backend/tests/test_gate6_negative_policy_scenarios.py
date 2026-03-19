# ruff: noqa: E402
import os
import sys
import uuid
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.pipeline.cache_store import set_json
from services.pipeline.spot_dynamic_score_engine import run_dynamic_selection_cycle


def _resolve_base_url() -> str:
    env_base = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if env_base:
        return env_base
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL bulunamadı")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


class FakeCache:
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def _build_candles(start: float, drift: float, count: int = 260) -> list[dict]:
    candles: list[dict] = []
    price = start
    for idx in range(count):
        open_price = max(price, 0.1)
        close_price = max(open_price + drift, 0.1)
        candles.append(
            {
                "open": round(open_price, 6),
                "high": round(max(open_price, close_price) * 1.002, 6),
                "low": round(min(open_price, close_price) * 0.998, 6),
                "close": round(close_price, 6),
                "volume": 1_000_000 + (idx * 500),
                "end": idx,
            }
        )
        price = close_price
    return candles


def _admin_headers() -> dict:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, f"admin login failed: {response.text}"
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def _new_user_headers() -> dict:
    email = f"gate6_negative_{uuid.uuid4().hex[:8]}@example.com"
    password = "Gate6Negative123!"

    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert register.status_code == 200, register.text
    user_id = register.json().get("id")

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=_admin_headers(),
        timeout=20,
    )
    assert approve.status_code == 200, approve.text

    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json().get('access_token')}"}


def _preview_payload(symbol: str = "ETHUSDT") -> dict:
    return {
        "source_type": "scanner",
        "source_ref_id": "gate6-signal",
        "market_type": "spot",
        "symbol": symbol,
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 20,
        "take_profit_mode": "percent",
        "take_profit_value": 2,
        "stop_loss_mode": "percent",
        "stop_loss_value": 1,
        "execution_mode": "signal_follow",
        "strategy_binding": "spot_pullback_v1",
        "signal": "long",
        "score": 80,
        "confidence": 0.7,
        "timestamp": "2026-03-16T00:00:00Z",
        "scanner_signal_snapshot": {
            "symbol": symbol,
            "signal": "long",
            "score": 80,
            "strategy": "spot_pullback_v1",
            "confidence": 0.7,
            "timestamp": "2026-03-16T00:00:00Z",
        },
    }


@pytest.fixture(scope="module")
def user_headers():
    return _new_user_headers()


def test_negative_symbol_null_rejected(user_headers):
    payload = _preview_payload("ETHUSDT")
    payload["symbol"] = None
    payload["scanner_signal_snapshot"]["symbol"] = None

    response = requests.post(
        f"{BASE_URL}/api/v1/user/trading/preview",
        headers=user_headers,
        json=payload,
        timeout=30,
    )
    assert response.status_code in {400, 422}, response.text


def test_negative_symbol_empty_rejected(user_headers):
    payload = _preview_payload("ETHUSDT")
    payload["symbol"] = ""
    payload["scanner_signal_snapshot"]["symbol"] = ""

    response = requests.post(
        f"{BASE_URL}/api/v1/user/trading/preview",
        headers=user_headers,
        json=payload,
        timeout=30,
    )
    assert response.status_code == 400, response.text
    assert "symbol_required_for_execution_intent" in response.text


def test_negative_unsupported_quote_rejected(user_headers):
    payload = _preview_payload("ETHBUSD")
    response = requests.post(
        f"{BASE_URL}/api/v1/user/trading/preview",
        headers=user_headers,
        json=payload,
        timeout=30,
    )
    assert response.status_code == 400, response.text
    assert ("invalid_quote_asset" in response.text) or ("unsupported_quote_asset" in response.text)


def test_negative_btc_pair_rejected(user_headers):
    payload = _preview_payload("ETHBTC")
    response = requests.post(
        f"{BASE_URL}/api/v1/user/trading/preview",
        headers=user_headers,
        json=payload,
        timeout=30,
    )
    assert response.status_code == 400, response.text
    assert ("invalid_quote_asset" in response.text) or ("unsupported_quote_asset" in response.text)


def test_negative_watchlist_filters_policy_outside_pairs(user_headers):
    payload = {
        "name": f"gate6-watchlist-{uuid.uuid4().hex[:6]}",
        "source": "crypto",
        "exchange": "binance",
        "market_type": "spot",
        "symbols": ["ETHUSDT", "ETHBTC", "SOLUSDC", "BNBBUSD"],
    }
    response = requests.post(
        f"{BASE_URL}/api/symbol-selector/watchlists",
        headers=user_headers,
        json=payload,
        timeout=30,
    )
    assert response.status_code == 200, response.text
    saved_symbols = set((response.json() or {}).get("symbols") or [])
    assert "ETHUSDT" in saved_symbols
    assert "SOLUSDC" in saved_symbols
    assert "ETHBTC" not in saved_symbols
    assert "BNBBUSD" not in saved_symbols


def test_negative_universe_builds_without_btc_dependency():
    cache = FakeCache()
    set_json(cache, "market_data_store:ETHUSDT:15m", _build_candles(start=1200, drift=1.1))
    set_json(cache, "market_data_store:SOLUSDT:15m", _build_candles(start=100, drift=0.2))

    payload = run_dynamic_selection_cycle(
        cache,
        symbols=["ETHUSDT", "SOLUSDT"],
        open_symbols=set(),
        available_slots=2,
        params={"min_adjusted_score": 0, "active_strategies": ["spot_pullback_v1"]},
    )
    assert payload.get("symbol_count") == 2
    assert payload.get("market_bias_regime") in {"supportive", "neutral", "hostile"}


def test_negative_scanner_order_symbol_mismatch_rejected(user_headers):
    payload = _preview_payload("ETHUSDT")
    payload["scanner_signal_snapshot"]["symbol"] = "BTCUSDT"

    response = requests.post(
        f"{BASE_URL}/api/v1/user/trading/preview",
        headers=user_headers,
        json=payload,
        timeout=30,
    )
    assert response.status_code == 400, response.text
    assert "scanner_execution_symbol_mismatch" in response.text


def test_negative_execution_preview_unsupported_quote_rejected(user_headers):
    payload = _preview_payload("ETHBTC")
    response = requests.post(
        f"{BASE_URL}/api/user/execution/intent/preview",
        headers=user_headers,
        json=payload,
        timeout=30,
    )
    assert response.status_code == 400, response.text
    assert ("invalid_quote_asset" in response.text) or ("unsupported_quote_asset" in response.text)


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ETHUSDC", "SOLUSDC"])
def test_positive_allowed_quotes_accepted(user_headers, symbol):
    payload = _preview_payload(symbol)
    payload["scanner_signal_snapshot"]["symbol"] = symbol

    response = requests.post(
        f"{BASE_URL}/api/v1/user/trading/preview",
        headers=user_headers,
        json=payload,
        timeout=30,
    )
    assert response.status_code == 200, response.text

