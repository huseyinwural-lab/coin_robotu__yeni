import requests
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from indicator_screener_test_utils import ensure_user_headers, resolve_base_url


BASE_URL = resolve_base_url()
USER_HEADERS = ensure_user_headers(BASE_URL, suffix="phase3")


def test_phase3_saved_query_crud_flow():
    create_payload = {
        "name": "phase3_saved_query",
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "15m",
        "query_expression": "rsi14 < 30 AND rsi7 < 30",
        "symbol_universe": ["BTCUSDT", "ETHUSDT"],
        "result_limit": 25,
    }
    created = requests.post(
        f"{BASE_URL}/api/user/indicator-screener/saved-queries",
        json=create_payload,
        headers=USER_HEADERS,
        timeout=30,
    )
    assert created.status_code == 200, created.text
    row = created.json()
    query_id = row["id"]
    assert row["name"] == "phase3_saved_query"

    listing = requests.get(
        f"{BASE_URL}/api/user/indicator-screener/saved-queries",
        headers=USER_HEADERS,
        timeout=30,
    )
    assert listing.status_code == 200, listing.text
    assert any(item["id"] == query_id for item in listing.json())

    deleted = requests.delete(
        f"{BASE_URL}/api/user/indicator-screener/saved-queries/{query_id}",
        headers=USER_HEADERS,
        timeout=30,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json().get("deleted") is True


def test_phase3_watchlist_crud_flow():
    create_payload = {
        "exchange": "binance",
        "market_type": "spot",
        "symbol": "BTCUSDT",
        "note": "phase3 watch",
    }
    created = requests.post(
        f"{BASE_URL}/api/user/indicator-screener/watchlist",
        json=create_payload,
        headers=USER_HEADERS,
        timeout=30,
    )
    assert created.status_code == 200, created.text
    row = created.json()
    watch_id = row["id"]
    assert row["symbol"] == "BTCUSDT"

    listing = requests.get(
        f"{BASE_URL}/api/user/indicator-screener/watchlist",
        headers=USER_HEADERS,
        timeout=30,
    )
    assert listing.status_code == 200, listing.text
    assert any(item["id"] == watch_id for item in listing.json())

    deleted = requests.delete(
        f"{BASE_URL}/api/user/indicator-screener/watchlist/{watch_id}",
        headers=USER_HEADERS,
        timeout=30,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json().get("deleted") is True


def test_phase3_run_response_contains_bridge_ready_fields():
    payload = {
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "1h",
        "query_expression": "rsi14 < 100",
        "symbol_universe": ["BTCUSDT", "ETHUSDT"],
        "limit": 10,
    }
    response = requests.post(
        f"{BASE_URL}/api/user/indicator-screener/run",
        json=payload,
        headers=USER_HEADERS,
        timeout=120,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["query_valid"] is True
    assert data["match_count"] >= 1
    row = data["rows"][0]
    assert "symbol" in row
    assert "exchange" in row
    assert "timeframe" in row
    assert "updated_at" in row


def test_phase3_requires_user_auth_for_run_endpoint():
    response = requests.post(
        f"{BASE_URL}/api/user/indicator-screener/run",
        json={
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "rsi14 < 30",
            "symbol_universe": ["BTCUSDT"],
            "limit": 10,
        },
        timeout=30,
    )
    assert response.status_code in [401, 403]
