import requests
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from indicator_screener_test_utils import ensure_user_headers, resolve_base_url


BASE_URL = resolve_base_url()
USER_HEADERS = ensure_user_headers(BASE_URL, suffix="phase2")


def _run_query(payload: dict) -> dict:
    response = requests.post(
        f"{BASE_URL}/api/user/indicator-screener/run",
        json=payload,
        headers=USER_HEADERS,
        timeout=120,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_phase2_presets_endpoint():
    response = requests.get(
        f"{BASE_URL}/api/user/indicator-screener/presets",
        headers=USER_HEADERS,
        timeout=30,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    keys = {item["preset_key"] for item in data}
    assert "oversold_rsi14" in keys
    assert "oversold_rsi7" in keys
    assert "double_oversold" in keys


def test_phase2_indicator_columns_exist_in_result_rows():
    payload = {
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "1h",
        "query_expression": "rsi14 < 100",
        "symbol_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        "limit": 10,
    }
    data = _run_query(payload)
    assert data["query_valid"] is True
    assert data["match_count"] >= 1

    row = data["rows"][0]
    required_columns = [
        "close",
        "rsi14",
        "rsi7",
        "ema20",
        "ema50",
        "sma20",
        "sma50",
        "fibo_161_8",
        "fibo_127_2",
        "fibo_100",
        "fibo_78_6",
    ]
    for col in required_columns:
        assert col in row


def test_phase2_futures_market_type_optional_works():
    payload = {
        "exchange": "binance",
        "market_type": "futures",
        "timeframe": "1h",
        "query_expression": "rsi14 < 95 AND volume > 1000",
        "symbol_universe": ["BTCUSDT", "ETHUSDT"],
        "limit": 10,
    }
    data = _run_query(payload)
    if data["query_valid"]:
        assert data["evaluated_count"] >= 1
    else:
        assert data["query_error"]


def test_phase2_rejects_unknown_indicator_field():
    payload = {
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "15m",
        "query_expression": "unknown_indicator < 10",
        "symbol_universe": ["BTCUSDT", "ETHUSDT"],
        "limit": 10,
    }
    data = _run_query(payload)
    assert data["query_valid"] is False
    assert "Desteklenmeyen alan adı" in data["query_error"]
