"""
Spot Strategy Engine Faz-2 (P1) Dynamic Score Engine Tests
Features:
- market_regime (TRENDING|RANGING|VOLATILE), multiplier_version=v1, multiplier_set
- threshold (min_adjusted_score=55 config based), hard gate scoring
- BTC hostile freeze guard (2 candle)
- Scan metrics: signals_total, signals_after_hard_gate, signals_above_threshold, 
  signals_selected, signals_rejected_trend_strength, signals_rejected_btc_regime, signals_rejected_freeze_guard
- Selection ordering deterministic: top_ranked adjusted_score desc
- Report new fields: market_regime, multiplier_version, multiplier_set, base_score, adjusted_score, score_delta + metrics
- Regression: universe/data/indicator/pipeline monitoring endpoints
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


# ============== SCAN /api/spot-strategy/scan/run TESTS ==============

class TestScanRunFaz2Fields:
    """Tests for POST /api/spot-strategy/scan/run - Faz-2 new fields"""
    
    def test_scan_returns_market_regime(self, admin_headers):
        """Scan response should include market_regime field (TRENDING|RANGING|VOLATILE)"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run?top_n=5",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "market_regime" in data, f"Missing 'market_regime' in scan response: {data.keys()}"
        valid_regimes = {"TRENDING", "RANGING", "VOLATILE"}
        assert data["market_regime"] in valid_regimes, f"Invalid market_regime: {data['market_regime']}"
        print(f"Market regime: {data['market_regime']}")
    
    def test_scan_returns_multiplier_version_v1(self, admin_headers):
        """Scan response should have multiplier_version=v1"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run?top_n=5",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "multiplier_version" in data, "Missing 'multiplier_version' in scan response"
        assert data["multiplier_version"] == "v1", f"Expected multiplier_version='v1', got {data['multiplier_version']}"
        print(f"Multiplier version: {data['multiplier_version']}")
    
    def test_scan_returns_multiplier_set(self, admin_headers):
        """Scan response should have multiplier_set with 5 multiplier keys"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run?top_n=5",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "multiplier_set" in data, "Missing 'multiplier_set' in scan response"
        
        multiplier_set = data["multiplier_set"]
        expected_keys = [
            "trend_quality_multiplier",
            "pullback_quality_multiplier", 
            "relative_volume_multiplier",
            "volatility_quality_multiplier",
            "structure_quality_multiplier"
        ]
        for key in expected_keys:
            assert key in multiplier_set, f"Missing '{key}' in multiplier_set"
            assert isinstance(multiplier_set[key], (int, float)), f"{key} should be numeric"
            # Multipliers should be within 0.75-1.25 bounds
            assert 0.75 <= multiplier_set[key] <= 1.25, f"{key} out of bounds: {multiplier_set[key]}"
        
        print(f"Multiplier set: {multiplier_set}")
    
    def test_scan_returns_threshold(self, admin_headers):
        """Scan response should have threshold field (min_adjusted_score, default 55)"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run?top_n=5",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "threshold" in data, "Missing 'threshold' in scan response"
        assert isinstance(data["threshold"], (int, float)), "threshold should be numeric"
        # Default should be 55 but could be configured
        assert data["threshold"] >= 0, f"threshold should be non-negative: {data['threshold']}"
        print(f"Threshold (min_adjusted_score): {data['threshold']}")
    
    def test_scan_returns_metrics(self, admin_headers):
        """Scan response should have all required metrics fields"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run?top_n=5",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "metrics" in data, "Missing 'metrics' in scan response"
        
        metrics = data["metrics"]
        required_metrics = [
            "signals_total",
            "signals_after_hard_gate",
            "signals_above_threshold",
            "signals_selected",
            "signals_rejected_trend_strength",
            "signals_rejected_btc_regime",
            "signals_rejected_freeze_guard"
        ]
        
        for metric in required_metrics:
            assert metric in metrics, f"Missing '{metric}' in metrics"
            assert isinstance(metrics[metric], int), f"{metric} should be int, got {type(metrics[metric])}"
        
        # Validate relationships between metrics
        assert metrics["signals_total"] >= metrics["signals_after_hard_gate"], \
            "signals_total should be >= signals_after_hard_gate"
        assert metrics["signals_after_hard_gate"] >= metrics["signals_above_threshold"], \
            "signals_after_hard_gate should be >= signals_above_threshold"
        
        print(f"Metrics: {metrics}")
    
    def test_scan_returns_top_ranked_and_executable_count(self, admin_headers):
        """Scan response should have top_ranked list and executable_count"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run?top_n=5",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "top_ranked" in data, "Missing 'top_ranked' in scan response"
        assert "executable_count" in data, "Missing 'executable_count' in scan response"
        
        assert isinstance(data["top_ranked"], list), "top_ranked should be list"
        assert isinstance(data["executable_count"], int), "executable_count should be int"
        
        # Verify top_ranked item structure
        if data["top_ranked"]:
            first = data["top_ranked"][0]
            assert "symbol" in first, "Missing 'symbol' in top_ranked item"
            assert "signal_score" in first or "adjusted_score" in first, \
                "Missing score field in top_ranked item"
        
        print(f"Top ranked: {len(data['top_ranked'])} items, executable_count: {data['executable_count']}")


class TestScanSelectionOrdering:
    """Tests for selection ordering - deterministic adjusted_score desc"""
    
    def test_top_ranked_sorted_by_adjusted_score_desc(self, admin_headers):
        """Top ranked should be sorted by adjusted_score descending"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run?top_n=10",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        top_ranked = data.get("top_ranked", [])
        
        if len(top_ranked) >= 2:
            # Get scores - could be signal_score or adjusted_score based on response
            scores = [item.get("signal_score", item.get("adjusted_score", 0)) for item in top_ranked]
            sorted_scores = sorted(scores, reverse=True)
            assert scores == sorted_scores, \
                f"top_ranked not sorted by score desc: {scores[:5]} != {sorted_scores[:5]}"
            print(f"Selection ordering verified: {scores[:5]}")
    
    def test_ranked_items_have_adjusted_score(self, admin_headers):
        """Each ranked item should have adjusted_score field"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run?top_n=5",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        # Check ranked list (full list before truncation to top_ranked)
        ranked = data.get("ranked", [])
        if ranked:
            for item in ranked[:5]:
                assert "adjusted_score" in item, f"Missing 'adjusted_score' in ranked item: {item.get('symbol')}"
                assert "base_score" in item, f"Missing 'base_score' in ranked item: {item.get('symbol')}"
                assert "score_delta" in item, f"Missing 'score_delta' in ranked item: {item.get('symbol')}"


class TestScanFreezeGuard:
    """Tests for BTC hostile freeze guard (2 candle)"""
    
    def test_freeze_guard_field_present(self, admin_headers):
        """Scan response should have freeze_guard field"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run?top_n=5",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "freeze_guard" in data, "Missing 'freeze_guard' in scan response"
        
        freeze_guard = data["freeze_guard"]
        assert "active" in freeze_guard, "Missing 'active' in freeze_guard"
        assert isinstance(freeze_guard["active"], bool), "freeze_guard.active should be boolean"
        
        if freeze_guard["active"]:
            assert "reason" in freeze_guard, "Missing 'reason' when freeze_guard is active"
        
        print(f"Freeze guard: active={freeze_guard['active']}, reason={freeze_guard.get('reason')}")


# ============== REPORT /api/spot-strategy/report/daily/generate TESTS ==============

class TestDailyReportFaz2Fields:
    """Tests for POST /api/spot-strategy/report/daily/generate - Faz-2 new fields"""
    
    def test_report_has_market_regime(self, admin_headers):
        """Daily report should have market_regime field"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/report/daily/generate",
            headers=admin_headers,
            timeout=20
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "market_regime" in data, "Missing 'market_regime' in daily report"
        valid_regimes = {"TRENDING", "RANGING", "VOLATILE"}
        assert data["market_regime"] in valid_regimes, f"Invalid market_regime: {data['market_regime']}"
        print(f"Report market_regime: {data['market_regime']}")
    
    def test_report_has_multiplier_version(self, admin_headers):
        """Daily report should have multiplier_version field"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/report/daily/generate",
            headers=admin_headers,
            timeout=20
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "multiplier_version" in data, "Missing 'multiplier_version' in daily report"
        assert data["multiplier_version"] == "v1", f"Expected 'v1', got {data['multiplier_version']}"
    
    def test_report_has_multiplier_set(self, admin_headers):
        """Daily report should have multiplier_set dict"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/report/daily/generate",
            headers=admin_headers,
            timeout=20
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "multiplier_set" in data, "Missing 'multiplier_set' in daily report"
        assert isinstance(data["multiplier_set"], dict), "multiplier_set should be dict"
    
    def test_report_has_base_adjusted_score_delta(self, admin_headers):
        """Daily report should have base_score, adjusted_score, score_delta fields"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/report/daily/generate",
            headers=admin_headers,
            timeout=20
        )
        assert response.status_code == 200
        
        data = response.json()
        score_fields = ["base_score", "adjusted_score", "score_delta"]
        for field in score_fields:
            assert field in data, f"Missing '{field}' in daily report"
            assert isinstance(data[field], (int, float)), f"{field} should be numeric"
        
        print(f"Report scores: base={data['base_score']}, adjusted={data['adjusted_score']}, delta={data['score_delta']}")
    
    def test_report_has_new_metrics(self, admin_headers):
        """Daily report should have new metrics fields in metrics dict"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/report/daily/generate",
            headers=admin_headers,
            timeout=20
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "metrics" in data, "Missing 'metrics' in daily report"
        
        metrics = data["metrics"]
        required_metrics = [
            "signals_total",
            "signals_after_hard_gate",
            "signals_above_threshold",
            "signals_selected",
            "signals_rejected_trend_strength",
            "signals_rejected_btc_regime",
            "signals_rejected_freeze_guard"
        ]
        
        for metric in required_metrics:
            assert metric in metrics, f"Missing '{metric}' in report metrics"
        
        print(f"Report metrics: {metrics}")


# ============== REGRESSION TESTS ==============

class TestUniverseRegression:
    """Regression tests for universe endpoints"""
    
    def test_universe_get_works(self, admin_headers):
        """GET /api/spot-strategy/universe should return symbols"""
        response = requests.get(
            f"{BASE_URL}/api/spot-strategy/universe",
            headers=admin_headers,
            timeout=15
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "symbols" in data
        assert len(data["symbols"]) > 0, "Universe should have at least one symbol"
        print(f"Universe regression: {len(data['symbols'])} symbols")


class TestMarketDataRegression:
    """Regression tests for market data endpoint"""
    
    def test_market_data_btcusdt(self, admin_headers):
        """GET /api/spot-strategy/market-data/BTCUSDT should return candles"""
        response = requests.get(
            f"{BASE_URL}/api/spot-strategy/market-data/BTCUSDT",
            headers=admin_headers,
            timeout=15
        )
        
        if response.status_code == 404:
            pytest.skip("Market data not bootstrapped")
        
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "candles" in data
        assert "timeframe" in data
        assert data["count"] >= 500, f"Expected >= 500 candles, got {data['count']}"
        print(f"Market data regression: BTCUSDT {data['count']} candles")


class TestIndicatorsRegression:
    """Regression tests for indicator endpoint"""
    
    def test_indicators_btcusdt(self, admin_headers):
        """GET /api/spot-strategy/indicators/BTCUSDT should return indicator values"""
        response = requests.get(
            f"{BASE_URL}/api/spot-strategy/indicators/BTCUSDT",
            headers=admin_headers,
            timeout=15
        )
        
        if response.status_code == 404:
            pytest.skip("Indicators not cached")
        
        assert response.status_code == 200
        data = response.json()
        
        required = ["ema50", "ema200", "rsi14", "atr14", "vwap"]
        for field in required:
            assert field in data, f"Missing '{field}' in indicators"
        
        print(f"Indicators regression: EMA50={data['ema50']:.2f}, RSI={data['rsi14']:.2f}")


class TestPipelineMonitoringRegression:
    """Regression tests for pipeline monitoring endpoint"""
    
    def test_pipeline_monitoring(self, admin_headers):
        """GET /api/pipeline/monitoring should return monitoring data"""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/monitoring",
            headers=admin_headers,
            timeout=15
        )
        assert response.status_code == 200
        
        data = response.json()
        expected = ["websocket_status", "heartbeat", "queue_depth", "latency_ms"]
        for field in expected:
            assert field in data, f"Missing '{field}' in monitoring"
        
        print(f"Pipeline monitoring regression: ws={data['websocket_status']}, queue={data['queue_depth']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
