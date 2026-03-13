import requests
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from indicator_screener_test_utils import ensure_user_headers, resolve_base_url


BASE_URL = resolve_base_url()
USER_HEADERS = ensure_user_headers(BASE_URL, suffix="filterlayer")


def _run(payload: dict) -> dict:
    response = requests.post(
        f"{BASE_URL}/api/user/indicator-screener/run",
        json=payload,
        headers=USER_HEADERS,
        timeout=180,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _base_payload() -> dict:
    return {
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "15m",
        "query_expression": "rsi14 < 100",
        "limit": 25,
        "filter_payload": {
            "symbol_universe_mode": "all_tradable",
            "market_participation": "spot_only",
            "sort_by": "symbol",
            "sort_direction": "asc",
            "min_24h_volume": 100000,
            "quote_asset_filter": "USDT",
            "only_tradable_pairs": True,
            "pair_mode": "usdt_only",
            "exclude_leveraged_tokens": True,
            "exclude_stablecoin_stablecoin_pairs": True,
            "universe_top_n": 120,
        },
    }


def test_filter_layer_invalid_volume_combination():
    payload = _base_payload()
    payload["filter_payload"]["min_24h_volume"] = 1000000
    payload["filter_payload"]["max_24h_volume"] = 1000
    data = _run(payload)
    assert data["result_state"] == "invalid_filter_combination"
    assert data["filter_error"]


def test_filter_layer_volume_filter_applies_to_pipeline():
    payload_low = _base_payload()
    payload_high = _base_payload()
    payload_high["filter_payload"]["min_24h_volume"] = 700000

    low = _run(payload_low)
    high = _run(payload_high)

    assert high["evaluated_count"] <= low["evaluated_count"]
    assert "applied_filters" in low
    assert low["applied_filters"]["min_24h_volume"] == 100000


def test_filter_layer_universe_watchlist_only():
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        upsert = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/watchlist",
            json={
                "exchange": "binance",
                "market_type": "spot",
                "symbol": symbol,
                "note": "filter-layer-watchlist",
                "context_snapshot": {"source": "test_filter_layer_universe_watchlist_only"},
            },
            headers=USER_HEADERS,
            timeout=30,
        )
        assert upsert.status_code == 200, upsert.text

    payload = _base_payload()
    payload["filter_payload"]["symbol_universe_mode"] = "watchlist_only"
    payload["filter_payload"]["min_24h_volume"] = 0
    payload["filter_payload"]["quote_asset_filter"] = "ALL"
    payload["filter_payload"]["pair_mode"] = "all"
    data = _run(payload)

    assert data["universe_mode"] == "watchlist_only"
    assert data["universe_count"] <= 2
    assert data["result_state"] in ["success", "no_match"]


def test_filter_layer_state_separation_no_match_vs_empty_universe():
    payload_no_match = _base_payload()
    payload_no_match["query_expression"] = "rsi14 < 0"
    no_match = _run(payload_no_match)
    assert no_match["result_state"] in ["no_match", "empty_universe"]

    payload_empty = _base_payload()
    payload_empty["filter_payload"]["symbol_universe_mode"] = "whitelist_only"
    payload_empty["filter_payload"]["symbol_whitelist"] = ["FAKESYMBOLUSDT"]
    empty = _run(payload_empty)
    assert empty["result_state"] == "empty_universe"


def test_filter_layer_saved_query_snapshot_roundtrip():
    save_payload = {
        "name": "filter_layer_saved_query",
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "1h",
        "query_expression": "rsi14 < 35 AND rsi7 < 40",
        "symbol_universe": ["BTCUSDT", "ETHUSDT"],
        "filter_snapshot": {
            "symbol_universe_mode": "whitelist_only",
            "symbol_whitelist": ["BTCUSDT", "ETHUSDT"],
            "market_participation": "spot_only",
            "min_24h_volume": 100000,
            "sort_by": "rsi14",
            "sort_direction": "asc",
        },
        "schema_version": 2,
        "result_limit": 20,
    }
    created = requests.post(
        f"{BASE_URL}/api/user/indicator-screener/saved-queries",
        json=save_payload,
        headers=USER_HEADERS,
        timeout=30,
    )
    assert created.status_code == 200, created.text
    row = created.json()
    assert row["schema_version"] == 2
    assert row["filter_snapshot"]["symbol_universe_mode"] == "whitelist_only"
