import requests
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from indicator_screener_test_utils import ensure_user_headers, resolve_base_url


BASE_URL = resolve_base_url()
USER_HEADERS = ensure_user_headers(BASE_URL, suffix="phase1")


def _run_query(payload: dict) -> dict:
    response = requests.post(
        f"{BASE_URL}/api/user/indicator-screener/run",
        json=payload,
        headers=USER_HEADERS,
        timeout=120,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_phase1_rsi14_query_executes():
    payload = {
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "15m",
        "query_expression": "rsi14 < 30",
        "symbol_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"],
        "limit": 50,
    }
    data = _run_query(payload)
    assert data["query_valid"] is True
    assert data["query_error"] is None
    assert "matched_symbols" in data
    assert data["evaluated_count"] >= 1
    for row in data["rows"]:
        assert row["rsi14"] < 30


def test_phase1_rsi7_query_executes():
    payload = {
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "15m",
        "query_expression": "rsi7 < 30",
        "symbol_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"],
        "limit": 50,
    }
    data = _run_query(payload)
    assert data["query_valid"] is True
    assert data["query_error"] is None
    assert data["evaluated_count"] >= 1
    for row in data["rows"]:
        assert row["rsi7"] < 30


def test_phase1_combined_rule_query_executes():
    payload = {
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "1h",
        "query_expression": "(rsi14 < 30 OR rsi7 < 25) AND volume > 1000",
        "symbol_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"],
        "limit": 50,
    }
    data = _run_query(payload)
    assert data["query_valid"] is True
    assert data["query_error"] is None
    assert data["evaluated_count"] >= 1


def test_phase1_invalid_query_returns_explanatory_error():
    payload = {
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "15m",
        "query_expression": "drop table",
        "symbol_universe": ["BTCUSDT", "ETHUSDT"],
        "limit": 20,
    }
    data = _run_query(payload)
    assert data["query_valid"] is False
    assert data["query_error"]


def test_phase1_deterministic_result_on_same_input():
    payload = {
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "4h",
        "query_expression": "rsi14 < 80 AND rsi7 < 85",
        "symbol_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"],
        "limit": 50,
    }
    first = _run_query(payload)
    second = _run_query(payload)
    assert first["query_valid"] is True and second["query_valid"] is True
    assert first["matched_symbols"] == second["matched_symbols"]
    assert first["match_count"] == second["match_count"]
