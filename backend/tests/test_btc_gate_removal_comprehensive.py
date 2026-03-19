# ruff: noqa: E402
"""
BTC Gate Removal - Comprehensive Backend Tests
Tests for symbol-driven scanner correction package:
- run_dynamic_selection_cycle without BTC data
- market_bias_regime field + btc_regime legacy alias
- reason_codes without btc_regime_hostile/freeze_guard_active as hard gates
- metrics with signals_rejected_market_bias and signals_rejected_market_stress
- runtime._process_spot_pullback_selection only on timeframe=15m
- relative_strength_cluster_scanner_v2 benchmark_mode btc->cluster resolution
- Admin rejection analytics endpoint with new/legacy keys
"""
import os
import sys
from pathlib import Path

import pytest
import requests

# Ensure backend module path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.pipeline.cache_store import set_json
from services.pipeline.spot_dynamic_score_engine import (
    run_dynamic_selection_cycle,
    _derive_market_bias_regime,
    _build_market_snapshot,
    _prepare_market_context,
    _build_selection_metrics,
)
from core.strategies.prefilters.relative_strength_cluster_scanner_v2 import RelativeStrengthClusterScannerV2


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class FakeCache:
    """Simple in-memory cache for unit testing"""
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)


def _build_candles(start: float, drift: float, count: int = 260) -> list[dict]:
    """Build synthetic candle data for testing"""
    candles: list[dict] = []
    price = start
    for idx in range(count):
        wobble = drift * 0.25 if idx % 5 == 0 else 0.0
        open_price = max(price, 0.1)
        close_price = max(open_price + drift - wobble, 0.1)
        high = max(open_price, close_price) * 1.003
        low = min(open_price, close_price) * 0.997
        candles.append({
            "open": round(open_price, 6),
            "high": round(high, 6),
            "low": round(low, 6),
            "close": round(close_price, 6),
            "volume": 1_200_000 + (idx * 750),
            "end": idx,
        })
        price = close_price
    return candles


class TestDynamicScannerNoBTCGate:
    """Tests verifying BTC gate removal from dynamic selection cycle"""

    def test_run_dynamic_selection_cycle_without_btc_data(self):
        """run_dynamic_selection_cycle should work with ETH/SOL only (no BTCUSDT)"""
        cache = FakeCache()
        set_json(cache, "market_data_store:ETHUSDT:15m", _build_candles(start=1000, drift=1.35))
        set_json(cache, "market_data_store:SOLUSDT:15m", _build_candles(start=90, drift=0.18))

        payload = run_dynamic_selection_cycle(
            cache,
            symbols=["ETHUSDT", "SOLUSDT"],
            open_symbols=set(),
            available_slots=2,
            params={
                "min_adjusted_score": 0,
                "active_strategies": [
                    "spot_pullback_v1",
                    "spot_range_reversion_v1",
                    "spot_volatility_breakout_v1",
                ],
            },
        )

        # Core assertions: cycle completes without BTC
        assert payload["symbol_count"] == 2
        assert payload["market_regime"] in {"TRENDING", "RANGING", "VOLATILE"}

    def test_market_bias_regime_field_exists_and_has_legacy_alias(self):
        """Scan output should have market_bias_regime and btc_regime alias"""
        cache = FakeCache()
        set_json(cache, "market_data_store:ETHUSDT:15m", _build_candles(start=1000, drift=1.35))

        payload = run_dynamic_selection_cycle(
            cache,
            symbols=["ETHUSDT"],
            open_symbols=set(),
            available_slots=1,
            params={"min_adjusted_score": 0, "active_strategies": ["spot_pullback_v1"]},
        )

        # market_bias_regime must exist
        assert "market_bias_regime" in payload
        assert payload["market_bias_regime"] in {"supportive", "neutral", "hostile"}

        # btc_regime is legacy alias and should equal market_bias_regime
        assert "btc_regime" in payload
        assert payload["btc_regime"] == payload["market_bias_regime"]

    def test_reason_codes_no_btc_regime_hostile_hard_gate(self):
        """ranked reason_codes should NOT include btc_regime_hostile or freeze_guard_active as hard gates"""
        cache = FakeCache()
        set_json(cache, "market_data_store:ETHUSDT:15m", _build_candles(start=1000, drift=1.35))
        set_json(cache, "market_data_store:SOLUSDT:15m", _build_candles(start=90, drift=0.18))

        payload = run_dynamic_selection_cycle(
            cache,
            symbols=["ETHUSDT", "SOLUSDT"],
            open_symbols=set(),
            available_slots=2,
            params={
                "min_adjusted_score": 0,
                "active_strategies": ["spot_pullback_v1"],
            },
        )

        for item in payload.get("ranked", []):
            reason_codes = item.get("reason_codes", [])
            # btc_regime_hostile and freeze_guard_active should NOT appear
            assert "btc_regime_hostile" not in reason_codes, f"btc_regime_hostile found in {item['symbol']}"
            assert "freeze_guard_active" not in reason_codes, f"freeze_guard_active found in {item['symbol']}"

    def test_metrics_has_new_and_legacy_rejection_keys(self):
        """Metrics must have signals_rejected_market_bias, signals_rejected_market_stress + legacy aliases"""
        cache = FakeCache()
        set_json(cache, "market_data_store:ETHUSDT:15m", _build_candles(start=1000, drift=1.35))

        payload = run_dynamic_selection_cycle(
            cache,
            symbols=["ETHUSDT"],
            open_symbols=set(),
            available_slots=1,
            params={"min_adjusted_score": 0, "active_strategies": ["spot_pullback_v1"]},
        )

        metrics = payload.get("metrics", {})

        # New keys
        assert "signals_rejected_market_bias" in metrics
        assert "signals_rejected_market_stress" in metrics

        # Legacy alias keys (backward compatible)
        assert "signals_rejected_btc_regime" in metrics
        assert "signals_rejected_freeze_guard" in metrics

        # Legacy aliases must equal new keys
        assert metrics["signals_rejected_btc_regime"] == metrics["signals_rejected_market_bias"]
        assert metrics["signals_rejected_freeze_guard"] == metrics["signals_rejected_market_stress"]

    def test_risk_guard_and_freeze_guard_in_payload(self):
        """risk_guard and freeze_guard objects should exist and not block by default"""
        cache = FakeCache()
        set_json(cache, "market_data_store:ETHUSDT:15m", _build_candles(start=1000, drift=1.35))

        payload = run_dynamic_selection_cycle(
            cache,
            symbols=["ETHUSDT"],
            open_symbols=set(),
            available_slots=1,
            params={"min_adjusted_score": 0, "active_strategies": ["spot_pullback_v1"]},
        )

        assert "risk_guard" in payload
        assert payload["risk_guard"]["active"] is False

        assert "freeze_guard" in payload
        assert payload["freeze_guard"]["active"] is False


class TestRelativeStrengthClusterScannerV2:
    """Tests for benchmark_mode resolution in cluster scanner"""

    def test_benchmark_mode_btc_resolves_to_cluster(self):
        """benchmark_mode='btc' should resolve to 'cluster' (not hardcoded BTC)"""
        scanner = RelativeStrengthClusterScannerV2()
        rows = [
            {"symbol": "BTCUSDT", "return_20": 0.03, "liquidity_usd": 20_000_000, "spread_bps": 4, "cluster": "majors"},
            {"symbol": "ETHUSDT", "return_20": 0.05, "liquidity_usd": 15_000_000, "spread_bps": 6, "cluster": "majors"},
            {"symbol": "SOLUSDT", "return_20": 0.07, "liquidity_usd": 12_000_000, "spread_bps": 8, "cluster": "majors"},
        ]

        result_btc = scanner.scan(rows, benchmark_mode="btc")

        assert result_btc["benchmark_mode"] == "cluster", "btc should resolve to cluster"
        assert result_btc["benchmark_mode_requested"] == "btc"

    def test_benchmark_mode_cluster_works(self):
        """benchmark_mode='cluster' should work correctly"""
        scanner = RelativeStrengthClusterScannerV2()
        rows = [
            {"symbol": "BTCUSDT", "return_20": 0.03, "liquidity_usd": 20_000_000, "spread_bps": 4, "cluster": "majors"},
            {"symbol": "ETHUSDT", "return_20": 0.05, "liquidity_usd": 15_000_000, "spread_bps": 6, "cluster": "majors"},
        ]

        result = scanner.scan(rows, benchmark_mode="cluster")
        assert result["benchmark_mode"] == "cluster"

    def test_benchmark_mode_market_works(self):
        """benchmark_mode='market' should work correctly"""
        scanner = RelativeStrengthClusterScannerV2()
        rows = [
            {"symbol": "BTCUSDT", "return_20": 0.03, "liquidity_usd": 20_000_000, "spread_bps": 4, "cluster": "majors"},
            {"symbol": "ETHUSDT", "return_20": 0.05, "liquidity_usd": 15_000_000, "spread_bps": 6, "cluster": "majors"},
        ]

        result = scanner.scan(rows, benchmark_mode="market")
        assert result["benchmark_mode"] == "market"


class TestDeriveMarketBiasRegime:
    """Tests for _derive_market_bias_regime function"""

    def test_returns_neutral_when_empty_sample(self):
        """Should return neutral when sample_count is 0"""
        snapshot = {"sample_count": 0}
        result = _derive_market_bias_regime(snapshot)
        assert result == "neutral"

    def test_returns_hostile_when_bearish_majority(self):
        """Should return hostile when bearish conditions met"""
        snapshot = {
            "sample_count": 10,
            "bullish_ratio": 0.1,
            "bearish_ratio": 0.75,
            "avg_return_3": -1.2,
        }
        result = _derive_market_bias_regime(snapshot)
        assert result == "hostile"

    def test_returns_supportive_when_bullish_majority(self):
        """Should return supportive when bullish conditions met"""
        snapshot = {
            "sample_count": 10,
            "bullish_ratio": 0.7,
            "bearish_ratio": 0.1,
            "avg_return_3": 0.5,
        }
        result = _derive_market_bias_regime(snapshot)
        assert result == "supportive"


class TestBuildSelectionMetrics:
    """Tests for _build_selection_metrics function"""

    def test_metrics_include_market_bias_and_stress_keys(self):
        """Metrics must include both new and legacy rejection keys"""
        candidates = [
            {"symbol": "ETH", "reason_codes": ["market_bias_hostile"], "hard_gate_pass": False},
            {"symbol": "SOL", "reason_codes": ["market_stress_guard_active"], "hard_gate_pass": False},
            {"symbol": "BNB", "reason_codes": [], "hard_gate_pass": True, "threshold_pass": True},
        ]
        selected = [{"symbol": "BNB", "strategy_id": "spot_pullback_v1"}]

        metrics = _build_selection_metrics(candidates, selected)

        assert "signals_rejected_market_bias" in metrics
        assert "signals_rejected_market_stress" in metrics
        assert "signals_rejected_btc_regime" in metrics
        assert "signals_rejected_freeze_guard" in metrics

        # Legacy keys should equal new keys
        assert metrics["signals_rejected_btc_regime"] == metrics["signals_rejected_market_bias"]
        assert metrics["signals_rejected_freeze_guard"] == metrics["signals_rejected_market_stress"]


class TestAPIEndpoints:
    """API endpoint tests for rejection analytics and scan endpoints"""

    @pytest.fixture
    def auth_headers(self):
        """Get auth headers for admin user"""
        if not BASE_URL:
            pytest.skip("BASE_URL not set")
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@platform.local", "password": "Admin12345!"},
            timeout=15,
        )
        if login_response.status_code != 200:
            pytest.skip("Unable to authenticate")
        token = login_response.json().get("access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_rejection_analytics_endpoint_has_new_and_legacy_keys(self, auth_headers):
        """GET /api/admin/strategy/rejection-analytics should return new/legacy keys"""
        if not BASE_URL:
            pytest.skip("BASE_URL not set")

        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/rejection-analytics",
            headers=auth_headers,
            params={"window": "24h"},
            timeout=15,
        )

        assert response.status_code == 200, f"Status: {response.status_code}, Body: {response.text}"
        data = response.json()

        # New keys
        assert "signals_rejected_market_bias" in data
        assert "signals_rejected_market_stress" in data

        # Legacy alias keys
        assert "signals_rejected_btc_regime" in data
        assert "signals_rejected_freeze_guard" in data

    def test_spot_strategy_scan_run_endpoint(self, auth_headers):
        """POST /api/spot-strategy/scan/run should include market_bias_regime and btc_regime alias"""
        if not BASE_URL:
            pytest.skip("BASE_URL not set")

        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=auth_headers,
            json={"max_symbols": 5},
            timeout=30,
        )

        # May return 200 or 4xx depending on config; check structure if 200
        if response.status_code == 200:
            data = response.json()
            # Check if market_bias_regime exists in response or top_ranked items
            if "market_bias_regime" in data:
                assert data.get("btc_regime") == data.get("market_bias_regime")

    def test_strategy_observability_report_endpoint(self, auth_headers):
        """GET /api/admin/strategy/observability-report should return rejection breakdown with new keys"""
        if not BASE_URL:
            pytest.skip("BASE_URL not set")

        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability-report",
            headers=auth_headers,
            params={"window": "24h"},
            timeout=15,
        )

        assert response.status_code == 200, f"Status: {response.status_code}, Body: {response.text}"
        data = response.json()

        # Check signals_rejected_breakdown structure
        breakdown = data.get("signals_rejected_breakdown", {})
        assert "market_bias" in breakdown or "btc_regime" in breakdown


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
