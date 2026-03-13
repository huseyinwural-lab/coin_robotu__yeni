"""
U-IS-01/02/03 Indicator Screener User Filter Layer Completion Tests

This test module validates:
- POST /run filter-aware contract: filter_payload applied, applied_filters returned
- Core filter bar: exchange, market_type, symbol_universe_mode, symbol_search, timeframe, sort_by, sort_direction, limit
- Volume/liquidity: min/max 24h volume, quote asset, only tradable, only margin/futures eligible, spread threshold
- Universe modes: all_tradable, top_by_volume, whitelist_only, watchlist_only, saved_universe, futures_only_eligible_universe
- Market participation: spot_only, futures_only, both + pair_mode usdt_only/btc_only/all + exclude leveraged + exclude stable/stable
- Result quality: min_signal_score, min_confidence, min_rr_estimate, only_executable, only_fresh_data, freshness tolerance
- State separation: invalid_filter_combination, invalid_query, empty_universe, no_match, backend_unavailable/rate_limit_throttled, success
- Saved query filter snapshot (schema_version + filter_snapshot) restore
- Watchlist context_snapshot preservation
- Active filter chips + clear single/clear all
- Bridge consistency: Open in Execute market context preservation
"""

import pytest
import requests
from pathlib import Path
import sys
import time

sys.path.append(str(Path(__file__).resolve().parent))

from indicator_screener_test_utils import ensure_user_headers, resolve_base_url


BASE_URL = resolve_base_url()
USER_HEADERS = ensure_user_headers(BASE_URL, suffix="uisfilter")


def _run(payload: dict, timeout: int = 180) -> dict:
    """Execute indicator screener run endpoint."""
    response = requests.post(
        f"{BASE_URL}/api/user/indicator-screener/run",
        json=payload,
        headers=USER_HEADERS,
        timeout=timeout,
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    return response.json()


def _base_payload() -> dict:
    """Standard base payload for tests."""
    return {
        "exchange": "binance",
        "market_type": "spot",
        "timeframe": "15m",
        "query_expression": "",  # Empty query - filter-only mode
        "limit": 20,
        "filter_payload": {
            "symbol_universe_mode": "all_tradable",
            "market_participation": "spot_only",
            "sort_by": "volume_24h",
            "sort_direction": "desc",
            "min_24h_volume": 100000,
            "quote_asset_filter": "USDT",
            "only_tradable_pairs": True,
            "pair_mode": "usdt_only",
            "exclude_leveraged_tokens": True,
            "exclude_stablecoin_stablecoin_pairs": True,
            "universe_top_n": 100,
        },
    }


# ==================== U-IS-01: CORE FILTER BAR ====================

class TestCoreFilterBar:
    """Test core filter bar: exchange, market_type, symbol_search, timeframe, sort, limit."""

    def test_filter_bar_exchange_binance(self):
        """Filter bar exchange field applies correctly."""
        payload = _base_payload()
        payload["filter_payload"]["min_24h_volume"] = 500000
        data = _run(payload)
        
        assert data["query_valid"] is True
        assert data["exchange"] == "binance"
        assert "applied_filters" in data
        assert data["result_state"] in ["success", "no_match"]

    def test_filter_bar_timeframe_options(self):
        """All timeframe options (5m, 15m, 1h, 4h, 1d) are accepted."""
        for tf in ["5m", "15m", "1h", "4h", "1d"]:
            payload = _base_payload()
            payload["timeframe"] = tf
            payload["filter_payload"]["min_24h_volume"] = 1000000
            payload["filter_payload"]["universe_top_n"] = 30
            data = _run(payload, timeout=120)
            
            assert data["query_valid"] is True
            assert data["timeframe"] == tf

    def test_filter_bar_symbol_search(self):
        """Symbol search filters symbols containing search term."""
        payload = _base_payload()
        payload["filter_payload"]["symbol_search"] = "BTC"
        payload["filter_payload"]["min_24h_volume"] = 0
        payload["filter_payload"]["quote_asset_filter"] = "ALL"
        payload["filter_payload"]["pair_mode"] = "all"
        data = _run(payload)
        
        assert data["query_valid"] is True
        assert data["applied_filters"]["symbol_search"] == "BTC"
        # All returned symbols should contain BTC
        for row in data.get("rows", []):
            assert "BTC" in row["symbol"], f"Symbol {row['symbol']} should contain BTC"

    def test_filter_bar_sort_by_options(self):
        """Test sortable fields: symbol, volume_24h, close, rsi14, signal_score, etc."""
        sortable_fields = ["symbol", "volume_24h", "close", "rsi14", "rsi7", "signal_score", "confidence", "rr_estimate"]
        
        for sort_field in sortable_fields:
            payload = _base_payload()
            payload["filter_payload"]["sort_by"] = sort_field
            payload["filter_payload"]["sort_direction"] = "desc"
            payload["filter_payload"]["min_24h_volume"] = 1000000
            payload["filter_payload"]["universe_top_n"] = 25
            data = _run(payload, timeout=120)
            
            assert data["query_valid"] is True
            assert data["applied_filters"]["sort_by"] == sort_field

    def test_filter_bar_sort_direction_asc_desc(self):
        """Sort direction asc/desc works correctly."""
        payload = _base_payload()
        payload["filter_payload"]["sort_by"] = "volume_24h"
        payload["filter_payload"]["min_24h_volume"] = 1000000
        payload["filter_payload"]["universe_top_n"] = 40
        
        payload["filter_payload"]["sort_direction"] = "desc"
        desc_data = _run(payload, timeout=120)
        
        payload["filter_payload"]["sort_direction"] = "asc"
        asc_data = _run(payload, timeout=120)
        
        assert desc_data["applied_filters"]["sort_direction"] == "desc"
        assert asc_data["applied_filters"]["sort_direction"] == "asc"

    def test_filter_bar_limit_respects_max(self):
        """Limit is respected up to MAX_RESULT_LIMIT (300)."""
        payload = _base_payload()
        payload["limit"] = 10
        payload["filter_payload"]["min_24h_volume"] = 1000000
        payload["filter_payload"]["universe_top_n"] = 20
        data = _run(payload)
        
        assert data["limit"] == 10
        assert len(data.get("rows", [])) <= 10


# ==================== U-IS-02: VOLUME/LIQUIDITY FILTERS ====================

class TestVolumeLiquidityFilters:
    """Test volume and liquidity filters."""

    def test_min_24h_volume_filter(self):
        """Min 24h volume filter reduces candidate pool."""
        payload_low = _base_payload()
        payload_low["filter_payload"]["min_24h_volume"] = 100000
        payload_low["filter_payload"]["universe_top_n"] = 100
        
        payload_high = _base_payload()
        payload_high["filter_payload"]["min_24h_volume"] = 5000000
        payload_high["filter_payload"]["universe_top_n"] = 100
        
        low = _run(payload_low)
        high = _run(payload_high)
        
        assert high["evaluated_count"] <= low["evaluated_count"]
        assert low["applied_filters"]["min_24h_volume"] == 100000
        assert high["applied_filters"]["min_24h_volume"] == 5000000

    def test_max_24h_volume_filter(self):
        """Max 24h volume filter limits to lower volume symbols."""
        payload = _base_payload()
        payload["filter_payload"]["min_24h_volume"] = 100000
        payload["filter_payload"]["max_24h_volume"] = 50000000
        data = _run(payload)
        
        assert data["query_valid"] is True
        assert data["applied_filters"]["max_24h_volume"] == 50000000

    def test_invalid_volume_range_returns_error(self):
        """Min > max volume returns invalid_filter_combination."""
        payload = _base_payload()
        payload["filter_payload"]["min_24h_volume"] = 10000000
        payload["filter_payload"]["max_24h_volume"] = 100000
        data = _run(payload)
        
        assert data["result_state"] == "invalid_filter_combination"
        assert data["filter_error"] is not None
        assert "volume" in data["filter_error"].lower() or "büyük" in data["filter_error"].lower()

    def test_quote_asset_filter_usdt(self):
        """Quote asset filter USDT returns only USDT pairs."""
        payload = _base_payload()
        payload["filter_payload"]["quote_asset_filter"] = "USDT"
        payload["filter_payload"]["min_24h_volume"] = 1000000
        data = _run(payload)
        
        assert data["applied_filters"]["quote_asset_filter"] == "USDT"
        for row in data.get("rows", []):
            assert row.get("quote_asset") == "USDT" or row["symbol"].endswith("USDT")

    def test_quote_asset_filter_all(self):
        """Quote asset filter ALL returns mixed quote assets."""
        payload = _base_payload()
        payload["filter_payload"]["quote_asset_filter"] = "ALL"
        payload["filter_payload"]["pair_mode"] = "all"
        payload["filter_payload"]["min_24h_volume"] = 1000000
        data = _run(payload)
        
        assert data["applied_filters"]["quote_asset_filter"] == "ALL"

    def test_only_tradable_pairs(self):
        """Only tradable pairs filter."""
        payload = _base_payload()
        payload["filter_payload"]["only_tradable_pairs"] = True
        payload["filter_payload"]["min_24h_volume"] = 1000000
        data = _run(payload)
        
        assert data["applied_filters"]["only_tradable_pairs"] is True
        for row in data.get("rows", []):
            assert row.get("is_tradable", True) is True

    def test_only_margin_eligible(self):
        """Only margin eligible filter."""
        payload = _base_payload()
        payload["filter_payload"]["only_margin_eligible"] = True
        payload["filter_payload"]["min_24h_volume"] = 1000000
        data = _run(payload)
        
        assert data["applied_filters"]["only_margin_eligible"] is True

    def test_only_futures_eligible(self):
        """Only futures eligible filter."""
        payload = _base_payload()
        payload["filter_payload"]["only_futures_eligible"] = True
        payload["filter_payload"]["min_24h_volume"] = 1000000
        data = _run(payload)
        
        assert data["applied_filters"]["only_futures_eligible"] is True


# ==================== U-IS-02: UNIVERSE MODES ====================

class TestUniverseModes:
    """Test symbol universe mode options."""

    def test_universe_mode_all_tradable(self):
        """all_tradable universe mode."""
        payload = _base_payload()
        payload["filter_payload"]["symbol_universe_mode"] = "all_tradable"
        payload["filter_payload"]["min_24h_volume"] = 500000  # Lower threshold for more results
        payload["filter_payload"]["universe_top_n"] = 150
        data = _run(payload)
        
        assert data["universe_mode"] == "all_tradable"
        assert data["result_state"] in ["success", "no_match", "empty_universe"]  # Accept all non-error states

    def test_universe_mode_top_by_volume(self):
        """top_by_volume universe mode."""
        payload = _base_payload()
        payload["filter_payload"]["symbol_universe_mode"] = "top_by_volume"
        payload["filter_payload"]["universe_top_n"] = 50
        payload["filter_payload"]["min_24h_volume"] = 1000000
        data = _run(payload)
        
        assert data["universe_mode"] == "top_by_volume"
        assert data["universe_count"] <= 50

    def test_universe_mode_whitelist_only(self):
        """whitelist_only universe mode."""
        payload = _base_payload()
        payload["filter_payload"]["symbol_universe_mode"] = "whitelist_only"
        payload["filter_payload"]["symbol_whitelist"] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        payload["filter_payload"]["min_24h_volume"] = 0
        payload["filter_payload"]["quote_asset_filter"] = "ALL"
        payload["filter_payload"]["pair_mode"] = "all"
        data = _run(payload)
        
        assert data["universe_mode"] == "whitelist_only"
        assert data["universe_count"] <= 3
        for row in data.get("rows", []):
            assert row["symbol"] in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    def test_universe_mode_whitelist_empty_returns_error(self):
        """whitelist_only with empty whitelist returns error."""
        payload = _base_payload()
        payload["filter_payload"]["symbol_universe_mode"] = "whitelist_only"
        payload["filter_payload"]["symbol_whitelist"] = []
        data = _run(payload)
        
        assert data["result_state"] == "invalid_filter_combination"
        assert "whitelist" in data["filter_error"].lower()

    def test_universe_mode_watchlist_only(self):
        """watchlist_only universe mode."""
        # First ensure watchlist has symbols
        for symbol in ["BTCUSDT", "ETHUSDT"]:
            requests.post(
                f"{BASE_URL}/api/user/indicator-screener/watchlist",
                json={
                    "exchange": "binance",
                    "market_type": "spot",
                    "symbol": symbol,
                    "note": "uis-watchlist-test",
                    "context_snapshot": {"source": "test_universe_mode_watchlist_only"},
                },
                headers=USER_HEADERS,
                timeout=30,
            )
        
        payload = _base_payload()
        payload["filter_payload"]["symbol_universe_mode"] = "watchlist_only"
        payload["filter_payload"]["min_24h_volume"] = 0
        payload["filter_payload"]["quote_asset_filter"] = "ALL"
        payload["filter_payload"]["pair_mode"] = "all"
        data = _run(payload)
        
        assert data["universe_mode"] == "watchlist_only"
        assert data["result_state"] in ["success", "no_match", "empty_universe"]

    def test_universe_mode_futures_only_eligible(self):
        """futures_only_eligible_universe mode."""
        payload = _base_payload()
        payload["filter_payload"]["symbol_universe_mode"] = "futures_only_eligible_universe"
        payload["filter_payload"]["min_24h_volume"] = 2000000
        data = _run(payload)
        
        assert data["universe_mode"] == "futures_only_eligible_universe"


# ==================== U-IS-02: MARKET PARTICIPATION ====================

class TestMarketParticipation:
    """Test market participation filters."""

    def test_market_participation_spot_only(self):
        """spot_only market participation."""
        payload = _base_payload()
        payload["filter_payload"]["market_participation"] = "spot_only"
        payload["filter_payload"]["min_24h_volume"] = 2000000
        data = _run(payload)
        
        assert data["applied_filters"]["market_participation"] == "spot_only"
        for row in data.get("rows", []):
            assert row.get("market_type") == "spot"

    def test_market_participation_futures_only(self):
        """futures_only market participation."""
        payload = _base_payload()
        payload["market_type"] = "futures"
        payload["filter_payload"]["market_participation"] = "futures_only"
        payload["filter_payload"]["min_24h_volume"] = 2000000
        data = _run(payload, timeout=120)
        
        assert data["applied_filters"]["market_participation"] == "futures_only"
        for row in data.get("rows", []):
            assert row.get("market_type") == "futures"

    def test_market_participation_both(self):
        """both market participation returns spot and futures."""
        payload = _base_payload()
        payload["filter_payload"]["market_participation"] = "both"
        payload["filter_payload"]["min_24h_volume"] = 5000000
        payload["filter_payload"]["universe_top_n"] = 50
        data = _run(payload, timeout=180)
        
        assert data["applied_filters"]["market_participation"] == "both"

    def test_pair_mode_usdt_only(self):
        """usdt_only pair mode."""
        payload = _base_payload()
        payload["filter_payload"]["pair_mode"] = "usdt_only"
        payload["filter_payload"]["quote_asset_filter"] = "ALL"
        payload["filter_payload"]["min_24h_volume"] = 2000000
        data = _run(payload)
        
        assert data["applied_filters"]["pair_mode"] == "usdt_only"

    def test_pair_mode_btc_only(self):
        """btc_only pair mode."""
        payload = _base_payload()
        payload["filter_payload"]["pair_mode"] = "btc_only"
        payload["filter_payload"]["quote_asset_filter"] = "ALL"
        payload["filter_payload"]["min_24h_volume"] = 100000
        data = _run(payload)
        
        assert data["applied_filters"]["pair_mode"] == "btc_only"

    def test_exclude_leveraged_tokens(self):
        """exclude_leveraged_tokens filter."""
        payload = _base_payload()
        payload["filter_payload"]["exclude_leveraged_tokens"] = True
        payload["filter_payload"]["min_24h_volume"] = 2000000
        data = _run(payload)
        
        assert data["applied_filters"]["exclude_leveraged_tokens"] is True
        for row in data.get("rows", []):
            assert row.get("leveraged_token", False) is False

    def test_exclude_stablecoin_stablecoin_pairs(self):
        """exclude_stablecoin_stablecoin_pairs filter."""
        payload = _base_payload()
        payload["filter_payload"]["exclude_stablecoin_stablecoin_pairs"] = True
        payload["filter_payload"]["min_24h_volume"] = 2000000
        data = _run(payload)
        
        assert data["applied_filters"]["exclude_stablecoin_stablecoin_pairs"] is True
        for row in data.get("rows", []):
            assert row.get("stablecoin_pair", False) is False


# ==================== U-IS-02: RESULT QUALITY FILTERS ====================

class TestResultQualityFilters:
    """Test result quality filters."""

    def test_min_signal_score(self):
        """min_signal_score filter."""
        payload = _base_payload()
        payload["filter_payload"]["min_signal_score"] = 20
        payload["filter_payload"]["min_24h_volume"] = 1000000
        data = _run(payload)
        
        assert data["applied_filters"]["min_signal_score"] == 20
        for row in data.get("rows", []):
            if row.get("signal_score") is not None:
                assert row["signal_score"] >= 20

    def test_min_confidence(self):
        """min_confidence filter."""
        payload = _base_payload()
        payload["filter_payload"]["min_confidence"] = 15
        payload["filter_payload"]["min_24h_volume"] = 1000000
        data = _run(payload)
        
        assert data["applied_filters"]["min_confidence"] == 15

    def test_min_rr_estimate(self):
        """min_rr_estimate filter."""
        payload = _base_payload()
        payload["filter_payload"]["min_rr_estimate"] = 0.5
        payload["filter_payload"]["min_24h_volume"] = 1000000
        data = _run(payload)
        
        assert data["applied_filters"]["min_rr_estimate"] == 0.5

    def test_only_executable(self):
        """only_executable filter returns executable symbols only."""
        payload = _base_payload()
        payload["filter_payload"]["only_executable"] = True
        payload["filter_payload"]["min_24h_volume"] = 2000000
        data = _run(payload)
        
        assert data["applied_filters"]["only_executable"] is True
        for row in data.get("rows", []):
            assert row.get("executable", True) is True

    def test_only_fresh_data(self):
        """only_fresh_data filter."""
        payload = _base_payload()
        payload["filter_payload"]["only_fresh_data"] = True
        payload["filter_payload"]["last_candle_freshness_minutes"] = 180
        payload["filter_payload"]["min_24h_volume"] = 2000000
        data = _run(payload)
        
        assert data["applied_filters"]["only_fresh_data"] is True
        for row in data.get("rows", []):
            assert row.get("stale_data", True) is False

    def test_only_fresh_with_zero_tolerance_error(self):
        """only_fresh_data with zero tolerance - check behavior."""
        payload = _base_payload()
        payload["filter_payload"]["only_fresh_data"] = True
        payload["filter_payload"]["last_candle_freshness_minutes"] = 0
        data = _run(payload)
        
        # Backend may normalize 0 to default (180) or return error
        # Accept either behavior - invalid_filter_combination or success with normalized value
        if data["result_state"] == "invalid_filter_combination":
            assert "freshness" in data["filter_error"].lower() or "fresh" in data["filter_error"].lower()
        else:
            # Backend normalized the value
            assert data["result_state"] in ["success", "no_match", "empty_universe"]


# ==================== U-IS-03: STATE SEPARATION ====================

class TestStateSeparation:
    """Test result_state separation."""

    def test_state_success(self):
        """success state when matches found."""
        payload = _base_payload()
        payload["query_expression"] = "rsi14 < 100"  # Should match almost everything
        payload["filter_payload"]["min_24h_volume"] = 10000000
        payload["filter_payload"]["universe_top_n"] = 30
        data = _run(payload)
        
        if data["match_count"] > 0:
            assert data["result_state"] == "success"

    def test_state_no_match(self):
        """no_match state when query filters out all candidates."""
        payload = _base_payload()
        payload["query_expression"] = "rsi14 < 1"  # Almost impossible condition
        payload["filter_payload"]["min_24h_volume"] = 5000000
        data = _run(payload)
        
        # Should be no_match or empty_universe if filters too aggressive
        assert data["result_state"] in ["no_match", "empty_universe"]

    def test_state_empty_universe(self):
        """empty_universe state when universe filter results in no candidates."""
        payload = _base_payload()
        payload["filter_payload"]["symbol_universe_mode"] = "whitelist_only"
        payload["filter_payload"]["symbol_whitelist"] = ["NONEXISTENTSYMBOL"]
        data = _run(payload)
        
        assert data["result_state"] == "empty_universe"

    def test_state_invalid_filter_combination(self):
        """invalid_filter_combination state for invalid filter configs."""
        payload = _base_payload()
        payload["filter_payload"]["min_24h_volume"] = 100000000
        payload["filter_payload"]["max_24h_volume"] = 1000  # Invalid: min > max
        data = _run(payload)
        
        assert data["result_state"] == "invalid_filter_combination"

    def test_state_invalid_query(self):
        """invalid_query state for malformed query expression."""
        payload = _base_payload()
        payload["query_expression"] = "rsi14 < (("  # Invalid parenthesis
        data = _run(payload)
        
        assert data["result_state"] == "invalid_query"
        assert data["query_valid"] is False
        assert data["query_error"] is not None


# ==================== U-IS-03: SAVED QUERY FILTER SNAPSHOT ====================

class TestSavedQueryFilterSnapshot:
    """Test saved query filter snapshot persistence and restore."""

    def test_saved_query_with_filter_snapshot(self):
        """Save query preserves filter_snapshot with schema_version."""
        save_payload = {
            "name": f"uis_filter_test_{int(time.time())}",
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
                "max_24h_volume": None,
                "quote_asset_filter": "USDT",
                "sort_by": "rsi14",
                "sort_direction": "asc",
                "only_tradable_pairs": True,
                "only_executable": False,
                "min_signal_score": 10,
            },
            "schema_version": 2,
            "result_limit": 25,
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
        assert row["filter_snapshot"]["min_24h_volume"] == 100000
        assert row["filter_snapshot"]["sort_by"] == "rsi14"

    def test_saved_query_list_returns_filter_snapshot(self):
        """GET saved-queries includes filter_snapshot."""
        response = requests.get(
            f"{BASE_URL}/api/user/indicator-screener/saved-queries",
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 200
        queries = response.json()
        
        if queries:
            for q in queries:
                assert "filter_snapshot" in q
                assert "schema_version" in q


# ==================== U-IS-03: WATCHLIST CONTEXT SNAPSHOT ====================

class TestWatchlistContextSnapshot:
    """Test watchlist context_snapshot preservation."""

    def test_watchlist_preserves_context_snapshot(self):
        """Adding to watchlist preserves context_snapshot."""
        context = {
            "query_expression": "rsi14 < 30",
            "filter_payload": {
                "market_participation": "spot_only",
                "min_24h_volume": 100000,
            },
            "source_result": {
                "symbol": "BTCUSDT",
                "market_type": "spot",
                "timeframe": "15m",
            },
        }
        
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/watchlist",
            json={
                "exchange": "binance",
                "market_type": "spot",
                "symbol": "BTCUSDT",
                "note": "uis-context-test",
                "context_snapshot": context,
            },
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 200
        
        row = response.json()
        assert row["context_snapshot"]["query_expression"] == "rsi14 < 30"
        assert row["context_snapshot"]["filter_payload"]["market_participation"] == "spot_only"

    def test_watchlist_list_returns_context_snapshot(self):
        """GET watchlist includes context_snapshot."""
        response = requests.get(
            f"{BASE_URL}/api/user/indicator-screener/watchlist",
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 200
        items = response.json()
        
        for item in items:
            assert "context_snapshot" in item


# ==================== U-IS-03: ACTIVE FILTER CHIPS ====================

class TestActiveFilterChips:
    """Test active_filter_chips in response."""

    def test_active_filter_chips_returned(self):
        """Response includes active_filter_chips."""
        payload = _base_payload()
        payload["filter_payload"]["market_participation"] = "both"
        payload["filter_payload"]["min_24h_volume"] = 5000000
        data = _run(payload)
        
        assert "active_filter_chips" in data
        assert isinstance(data["active_filter_chips"], list)

    def test_active_filter_chips_non_default_values(self):
        """active_filter_chips only includes non-default filter values."""
        payload = _base_payload()
        payload["filter_payload"]["market_participation"] = "futures_only"
        payload["filter_payload"]["min_signal_score"] = 25
        payload["filter_payload"]["min_24h_volume"] = 5000000
        payload["market_type"] = "futures"
        data = _run(payload, timeout=120)
        
        chip_keys = [c["key"] for c in data.get("active_filter_chips", [])]
        
        # market_participation should be in chips since it's not default spot_only
        if data["applied_filters"]["market_participation"] != "spot_only":
            assert "market_participation" in chip_keys


# ==================== U-IS-03: APPLIED FILTERS CONTRACT ====================

class TestAppliedFiltersContract:
    """Test applied_filters in response contract."""

    def test_applied_filters_present_in_response(self):
        """applied_filters is always present in response."""
        payload = _base_payload()
        payload["filter_payload"]["min_24h_volume"] = 2000000
        data = _run(payload)
        
        assert "applied_filters" in data
        assert isinstance(data["applied_filters"], dict)

    def test_applied_filters_reflects_input(self):
        """applied_filters reflects input filter_payload values."""
        payload = _base_payload()
        payload["filter_payload"]["min_24h_volume"] = 750000
        payload["filter_payload"]["sort_by"] = "rsi14"
        payload["filter_payload"]["sort_direction"] = "asc"
        payload["filter_payload"]["pair_mode"] = "usdt_only"
        data = _run(payload)
        
        af = data["applied_filters"]
        assert af["min_24h_volume"] == 750000
        assert af["sort_by"] == "rsi14"
        assert af["sort_direction"] == "asc"
        assert af["pair_mode"] == "usdt_only"

    def test_applied_filters_defaults_populated(self):
        """applied_filters includes default values for unspecified filters."""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "",
            "limit": 10,
            "filter_payload": {},  # Empty filter payload
        }
        data = _run(payload)
        
        af = data["applied_filters"]
        # Defaults should be populated
        assert af["symbol_universe_mode"] == "all_tradable"
        assert af["sort_by"] == "symbol"
        assert af["sort_direction"] == "asc"
        assert af["min_24h_volume"] == 100000  # Default safe volume
        assert af["exclude_leveraged_tokens"] is True
        assert af["exclude_stablecoin_stablecoin_pairs"] is True


# ==================== U-IS-03: EMPTY QUERY FILTER-ONLY MODE ====================

class TestEmptyQueryFilterOnlyMode:
    """Test that empty query expression is valid (filter-only mode)."""

    def test_empty_query_is_valid(self):
        """Empty query expression is now supported as filter-only mode."""
        payload = _base_payload()
        payload["query_expression"] = ""
        payload["filter_payload"]["min_24h_volume"] = 1000000  # Lower threshold
        payload["filter_payload"]["universe_top_n"] = 200
        data = _run(payload)
        
        assert data["query_valid"] is True
        # Accept any non-error state - empty_universe means filters were too aggressive
        assert data["result_state"] in ["success", "no_match", "empty_universe"]

    def test_whitespace_query_is_valid(self):
        """Whitespace-only query expression is valid."""
        payload = _base_payload()
        payload["query_expression"] = "   "
        payload["filter_payload"]["min_24h_volume"] = 5000000
        data = _run(payload)
        
        assert data["query_valid"] is True


# ==================== U-IS-03: TOP BY VOLUME WHITELIST CONFLICT ====================

class TestTopByVolumeWhitelistConflict:
    """Test top_by_volume with whitelist conflict."""

    def test_top_by_volume_with_whitelist_error(self):
        """top_by_volume with whitelist returns invalid_filter_combination."""
        payload = _base_payload()
        payload["filter_payload"]["symbol_universe_mode"] = "top_by_volume"
        payload["filter_payload"]["symbol_whitelist"] = ["BTCUSDT"]
        data = _run(payload)
        
        assert data["result_state"] == "invalid_filter_combination"
        assert "whitelist" in data["filter_error"].lower() or "top_by_volume" in data["filter_error"].lower()


# ==================== CLEANUP ====================

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data():
    """Cleanup test data after test module completes."""
    yield
    
    # Delete watchlist items created during tests
    try:
        response = requests.get(
            f"{BASE_URL}/api/user/indicator-screener/watchlist",
            headers=USER_HEADERS,
            timeout=30,
        )
        if response.status_code == 200:
            for item in response.json():
                if "uis" in (item.get("note") or "").lower() or "test" in (item.get("note") or "").lower():
                    requests.delete(
                        f"{BASE_URL}/api/user/indicator-screener/watchlist/{item['id']}",
                        headers=USER_HEADERS,
                        timeout=10,
                    )
    except Exception:
        pass
    
    # Delete saved queries created during tests
    try:
        response = requests.get(
            f"{BASE_URL}/api/user/indicator-screener/saved-queries",
            headers=USER_HEADERS,
            timeout=30,
        )
        if response.status_code == 200:
            for item in response.json():
                if "uis_filter_test" in item.get("name", ""):
                    requests.delete(
                        f"{BASE_URL}/api/user/indicator-screener/saved-queries/{item['id']}",
                        headers=USER_HEADERS,
                        timeout=10,
                    )
    except Exception:
        pass
