"""
Spot Strategy Engine (Faz-1 P0) Endpoint Tests
Tests for:
- POST /api/spot-strategy/universe/refresh - Universe refresh & bootstrap (admin)
- GET /api/spot-strategy/universe - Universe read (user/admin)
- GET /api/spot-strategy/market-data/{symbol} - 15m market data (>=500 candles)
- GET /api/spot-strategy/indicators/{symbol} - Indicator cache (EMA50/EMA200/RSI14/ATR14/VWAP)
- POST /api/spot-strategy/scan/run - Signal scan (admin)
- POST /api/spot-strategy/report/daily/generate - Daily strategy report (admin)
- GET /api/pipeline/monitoring - Pipeline monitoring regression test
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


@pytest.fixture(scope="module")
def admin_token():
    """Authenticate as admin and get token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip(f"No access_token in response: {data}")
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers for admin requests"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestSpotUniverseRefresh:
    """Tests for POST /api/spot-strategy/universe/refresh - Should produce 30-50 symbols"""
    
    def test_universe_refresh_success(self, admin_headers):
        """Universe refresh should succeed and return 30-50 symbols"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/universe/refresh",
            headers=admin_headers,
            timeout=30  # Network calls may take time
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "universe" in data, f"Missing 'universe' in response: {data.keys()}"
        assert "bootstrap" in data, f"Missing 'bootstrap' in response: {data.keys()}"
        
        universe = data["universe"]
        assert "symbols" in universe, "Missing 'symbols' in universe"
        assert "count" in universe, "Missing 'count' in universe"
        
        symbol_count = universe.get("count", 0)
        assert 30 <= symbol_count <= 50, f"Expected 30-50 symbols, got {symbol_count}"
        
        # Verify BTCUSDT is always present
        symbols = universe.get("symbols", [])
        assert "BTCUSDT" in symbols, "BTCUSDT should always be in universe"
        
        # Verify bootstrap result
        bootstrap = data["bootstrap"]
        assert "seeded" in bootstrap or "skipped" in bootstrap, f"Bootstrap result incomplete: {bootstrap}"
        print(f"Universe refresh: {symbol_count} symbols, bootstrap: seeded={bootstrap.get('seeded', 0)}")


class TestSpotUniverseRead:
    """Tests for GET /api/spot-strategy/universe - Response structure validation"""
    
    def test_universe_response_structure(self, admin_headers):
        """Universe response should have symbol, 24h_volume, spread, status fields"""
        response = requests.get(
            f"{BASE_URL}/api/spot-strategy/universe",
            headers=admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "symbols" in data, "Missing 'symbols' in response"
        
        # Check rows if present
        rows = data.get("rows", [])
        if rows:
            first_row = rows[0]
            assert "symbol" in first_row, "Missing 'symbol' in row"
            assert "24h_volume" in first_row, "Missing '24h_volume' in row"
            assert "spread" in first_row, "Missing 'spread' in row"
            assert "status" in first_row, "Missing 'status' in row"
            
            # Status should be active, filtered_out, or fallback
            valid_statuses = {"active", "filtered_out", "fallback"}
            assert first_row["status"] in valid_statuses, f"Invalid status: {first_row['status']}"
        
        symbols = data.get("symbols", [])
        print(f"Universe has {len(symbols)} symbols, {len(rows)} rows with details")


class TestMarketData:
    """Tests for GET /api/spot-strategy/market-data/{symbol} - 15m data >=500 candles"""
    
    def test_market_data_btc_count(self, admin_headers):
        """BTCUSDT market data should have >= 500 candles"""
        response = requests.get(
            f"{BASE_URL}/api/spot-strategy/market-data/BTCUSDT",
            headers=admin_headers,
            timeout=15
        )
        
        if response.status_code == 404:
            pytest.skip("Market data not yet bootstrapped for BTCUSDT")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "count" in data, f"Missing 'count' in response: {data.keys()}"
        assert "candles" in data, "Missing 'candles' in response"
        assert "timeframe" in data, "Missing 'timeframe' in response"
        
        count = data.get("count", 0)
        assert count >= 500, f"Expected >= 500 candles, got {count}"
        assert data.get("timeframe") == "15m", "Expected 15m timeframe"
        
        # Validate candle structure
        candles = data.get("candles", [])
        if candles:
            candle = candles[0]
            required_fields = {"open", "high", "low", "close", "volume"}
            for field in required_fields:
                assert field in candle, f"Missing '{field}' in candle"
        
        print(f"BTCUSDT market data: {count} candles, timeframe={data.get('timeframe')}")
    
    def test_market_data_eth_count(self, admin_headers):
        """ETHUSDT market data should also have >= 500 candles"""
        response = requests.get(
            f"{BASE_URL}/api/spot-strategy/market-data/ETHUSDT",
            headers=admin_headers,
            timeout=15
        )
        
        if response.status_code == 404:
            pytest.skip("Market data not yet bootstrapped for ETHUSDT")
        
        assert response.status_code == 200
        data = response.json()
        count = data.get("count", 0)
        assert count >= 500, f"Expected >= 500 candles for ETHUSDT, got {count}"
        print(f"ETHUSDT market data: {count} candles")


class TestIndicatorCache:
    """Tests for GET /api/spot-strategy/indicators/{symbol} - EMA50/EMA200/RSI14/ATR14/VWAP"""
    
    def test_indicator_fields_present(self, admin_headers):
        """Indicators should have EMA50, EMA200, RSI14, ATR14, VWAP fields"""
        response = requests.get(
            f"{BASE_URL}/api/spot-strategy/indicators/BTCUSDT",
            headers=admin_headers,
            timeout=15
        )
        
        if response.status_code == 404:
            pytest.skip("Indicators not yet cached for BTCUSDT")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify all required indicator fields
        required_indicators = ["ema50", "ema200", "rsi14", "atr14", "vwap"]
        for indicator in required_indicators:
            assert indicator in data, f"Missing '{indicator}' in indicators response"
            assert isinstance(data[indicator], (int, float)), f"{indicator} should be numeric"
        
        # Additional validation
        assert "close" in data, "Missing 'close' in indicators"
        assert "updated_at" in data, "Missing 'updated_at' in indicators"
        
        print(f"BTCUSDT indicators: EMA50={data.get('ema50'):.2f}, RSI={data.get('rsi14'):.2f}, ATR={data.get('atr14'):.6f}")
    
    def test_indicator_values_reasonable(self, admin_headers):
        """RSI should be 0-100, ATR should be positive"""
        response = requests.get(
            f"{BASE_URL}/api/spot-strategy/indicators/BTCUSDT",
            headers=admin_headers,
            timeout=15
        )
        
        if response.status_code == 404:
            pytest.skip("Indicators not yet cached for BTCUSDT")
        
        assert response.status_code == 200
        data = response.json()
        
        rsi = data.get("rsi14", 50)
        assert 0 <= rsi <= 100, f"RSI should be 0-100, got {rsi}"
        
        atr = data.get("atr14", 0)
        assert atr >= 0, f"ATR should be >= 0, got {atr}"
        
        ema50 = data.get("ema50", 0)
        ema200 = data.get("ema200", 0)
        assert ema50 > 0, f"EMA50 should be positive, got {ema50}"
        assert ema200 > 0, f"EMA200 should be positive, got {ema200}"


class TestScanRun:
    """Tests for POST /api/spot-strategy/scan/run - Signal scan"""
    
    def test_scan_run_returns_expected_fields(self, admin_headers):
        """Scan should return symbol_count, executable_count, top_ranked"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            timeout=30  # Scan may take time
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Required fields
        assert "symbol_count" in data, "Missing 'symbol_count' in scan response"
        assert "executable_count" in data, "Missing 'executable_count' in scan response"
        assert "top_ranked" in data, "Missing 'top_ranked' in scan response"
        
        symbol_count = data.get("symbol_count", 0)
        executable_count = data.get("executable_count", 0)
        top_ranked = data.get("top_ranked", [])
        
        assert isinstance(symbol_count, int), "symbol_count should be int"
        assert isinstance(executable_count, int), "executable_count should be int"
        assert isinstance(top_ranked, list), "top_ranked should be list"
        
        # Verify top_ranked structure if present
        if top_ranked:
            first = top_ranked[0]
            assert "symbol" in first, "Missing 'symbol' in top_ranked item"
            assert "signal" in first, "Missing 'signal' in top_ranked item"
            assert "signal_score" in first, "Missing 'signal_score' in top_ranked item"
        
        print(f"Scan result: {symbol_count} symbols, {executable_count} executable, {len(top_ranked)} top ranked")
    
    def test_scan_top_ranked_sorted(self, admin_headers):
        """Top ranked should be sorted by signal_score descending"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        top_ranked = data.get("top_ranked", [])
        
        if len(top_ranked) >= 2:
            scores = [item.get("signal_score", 0) for item in top_ranked]
            assert scores == sorted(scores, reverse=True), "top_ranked should be sorted by signal_score desc"


class TestDailyReport:
    """Tests for POST /api/spot-strategy/report/daily/generate - Daily report generation"""
    
    def test_daily_report_fields(self, admin_headers):
        """Daily report should have win_rate, profit_factor, avg_trade_return, max_drawdown, daily_trades"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/report/daily/generate",
            headers=admin_headers,
            timeout=20
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Required fields
        required_fields = ["win_rate", "profit_factor", "avg_trade_return", "max_drawdown", "daily_trades"]
        for field in required_fields:
            assert field in data, f"Missing '{field}' in daily report"
        
        # Validate types
        assert isinstance(data.get("win_rate"), (int, float)), "win_rate should be numeric"
        assert isinstance(data.get("profit_factor"), (int, float)), "profit_factor should be numeric"
        assert isinstance(data.get("avg_trade_return"), (int, float)), "avg_trade_return should be numeric"
        assert isinstance(data.get("max_drawdown"), (int, float)), "max_drawdown should be numeric"
        assert isinstance(data.get("daily_trades"), int), "daily_trades should be int"
        
        # Additional expected fields
        assert "date" in data, "Missing 'date' in daily report"
        assert "strategy" in data, "Missing 'strategy' in daily report"
        
        print(f"Daily report: date={data.get('date')}, trades={data.get('daily_trades')}, win_rate={data.get('win_rate')}")
    
    def test_daily_report_values_reasonable(self, admin_headers):
        """Win rate should be 0-100, max_drawdown >= 0"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/report/daily/generate",
            headers=admin_headers,
            timeout=20
        )
        assert response.status_code == 200
        
        data = response.json()
        
        win_rate = data.get("win_rate", 0)
        assert 0 <= win_rate <= 100, f"win_rate should be 0-100, got {win_rate}"
        
        max_drawdown = data.get("max_drawdown", 0)
        assert max_drawdown >= 0, f"max_drawdown should be >= 0, got {max_drawdown}"


class TestPipelineMonitoringRegression:
    """Regression test for GET /api/pipeline/monitoring"""
    
    def test_pipeline_monitoring_endpoint(self, admin_headers):
        """Pipeline monitoring should return expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/monitoring",
            headers=admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Key monitoring fields
        expected_fields = [
            "websocket_status",
            "heartbeat",
            "signal_rate_last_5m",
            "paper_trades_last_5m",
            "open_positions",
            "latency_ms",
            "queue_depth",
        ]
        
        for field in expected_fields:
            assert field in data, f"Missing '{field}' in monitoring response"
        
        print(f"Pipeline monitoring: ws_status={data.get('websocket_status')}, queue={data.get('queue_depth')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
