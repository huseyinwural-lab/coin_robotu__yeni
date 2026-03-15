"""
Phase 5.6B - Correlation Cluster Engine Comprehensive Tests

Tests for:
- Correlation matrix endpoint contract (symbols, correlation_matrix, window/timeframe)
- Correlation clusters endpoint contract (correlation_clusters, threshold)
- Cluster risk endpoint contract (cluster_exposures, cluster_risk_alerts, cluster_limits, governance_audit_events)
- Correlation determinism (window=96)
- Cluster threshold >=0.75
- Cluster exposure calculations
- Cluster risk governor CLUSTER_RISK_LIMIT_HIT event
- Order guard CLUSTER_TRADE_REJECTED and reduce_position_size flow
- Strategy governance cluster_risk_overlay field
- Regression tests
"""

import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.correlation.cluster_exposure_calculator import calculate_cluster_exposure
from core.risk.correlation.cluster_order_guard import evaluate_cluster_order_guard
from core.risk.correlation.cluster_risk_governor import evaluate_cluster_risk
from core.risk.correlation.correlation_cluster_builder import build_correlation_clusters
from core.risk.correlation.correlation_matrix_engine import build_correlation_matrix
from core.observability.cluster_governance_audit import build_cluster_governance_audit_events

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


@pytest.fixture(scope="module")
def admin_headers():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL tanımlı değil")
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {response.text}")
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ==================== CORRELATION MATRIX ENDPOINT TESTS ====================

class TestCorrelationMatrixEndpoint:
    """GET /api/admin/futures/correlation-matrix endpoint contract tests"""

    def test_correlation_matrix_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/correlation-matrix",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_correlation_matrix_has_symbols(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/correlation-matrix",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "symbols" in payload
        assert isinstance(payload["symbols"], list)
        assert len(payload["symbols"]) >= 3

    def test_correlation_matrix_has_correlation_matrix(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/correlation-matrix",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "correlation_matrix" in payload
        assert isinstance(payload["correlation_matrix"], dict)

    def test_correlation_matrix_has_window_96(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/correlation-matrix",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "window" in payload
        assert payload["window"] == 96

    def test_correlation_matrix_has_timeframe_15m(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/correlation-matrix",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "timeframe" in payload
        assert payload["timeframe"] == "15m"


# ==================== CORRELATION CLUSTERS ENDPOINT TESTS ====================

class TestCorrelationClustersEndpoint:
    """GET /api/admin/futures/correlation-clusters endpoint contract tests"""

    def test_correlation_clusters_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/correlation-clusters",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_correlation_clusters_has_clusters(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/correlation-clusters",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "correlation_clusters" in payload
        assert isinstance(payload["correlation_clusters"], list)

    def test_correlation_clusters_has_threshold(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/correlation-clusters",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "threshold" in payload
        assert payload["threshold"] == 0.75

    def test_correlation_clusters_structure(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/correlation-clusters",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        clusters = payload.get("correlation_clusters", [])
        if clusters:
            cluster = clusters[0]
            assert "cluster_id" in cluster
            assert "symbols" in cluster
            assert "avg_correlation" in cluster
            assert "size" in cluster


# ==================== CLUSTER RISK ENDPOINT TESTS ====================

class TestClusterRiskEndpoint:
    """GET /api/admin/futures/cluster-risk endpoint contract tests"""

    def test_cluster_risk_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/cluster-risk",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_cluster_risk_has_cluster_exposures(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/cluster-risk",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "cluster_exposures" in payload
        assert isinstance(payload["cluster_exposures"], list)

    def test_cluster_risk_has_cluster_risk_alerts(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/cluster-risk",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "cluster_risk_alerts" in payload
        assert isinstance(payload["cluster_risk_alerts"], list)

    def test_cluster_risk_has_cluster_limits(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/cluster-risk",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "cluster_limits" in payload
        limits = payload["cluster_limits"]
        assert "cluster_exposure_limit" in limits
        assert "cluster_position_limit" in limits
        assert "cluster_direction_limit" in limits

    def test_cluster_risk_has_governance_audit_events(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/cluster-risk",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "governance_audit_events" in payload
        assert isinstance(payload["governance_audit_events"], list)

    def test_cluster_risk_has_risk_state(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/cluster-risk",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "risk_state" in payload
        assert payload["risk_state"] in {"NORMAL", "ALERT"}

    def test_cluster_exposure_row_structure(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/cluster-risk",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        exposures = payload.get("cluster_exposures", [])
        if exposures:
            row = exposures[0]
            expected_fields = [
                "cluster_id",
                "symbols",
                "cluster_exposure",
                "cluster_direction",
                "cluster_position_count",
            ]
            for field in expected_fields:
                assert field in row, f"Missing field: {field}"


# ==================== STRATEGY GOVERNANCE CLUSTER OVERLAY TESTS ====================

class TestStrategyGovernanceClusterOverlay:
    """GET /api/admin/futures/strategy-governance cluster_risk_overlay tests"""

    def test_governance_has_cluster_risk_overlay(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        payload = response.json()
        assert "cluster_risk_overlay" in payload
        assert isinstance(payload["cluster_risk_overlay"], list)

    def test_cluster_overlay_structure(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        overlay = payload.get("cluster_risk_overlay", [])
        if overlay:
            row = overlay[0]
            expected_fields = [
                "cluster_id",
                "cluster_exposure",
                "triggered_strategy",
                "risk_source_symbol",
            ]
            for field in expected_fields:
                assert field in row, f"Missing field in overlay: {field}"


# ==================== UNIT TESTS FOR CORE MODULES ====================

class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def expire(self, key, _ttl):
        return True


def _candles(multiplier: float, count: int = 130):
    payload = []
    base = 100.0
    for idx in range(count):
        close = base * (1 + (idx / 4000) * multiplier)
        payload.append({"close": close})
    return payload


class TestCorrelationMatrixEngine:
    """correlation_matrix_engine unit tests"""

    def test_build_correlation_matrix_deterministic(self):
        import json
        cache = FakeCache()
        cache.set("market:candles:BTCUSDT:15m", json.dumps(_candles(1.0)))
        cache.set("market:candles:ETHUSDT:15m", json.dumps(_candles(1.1)))
        cache.set("market:candles:SOLUSDT:15m", json.dumps(_candles(0.9)))

        first = build_correlation_matrix(cache, ["BTC", "ETH", "SOL"], window=96)
        second = build_correlation_matrix(cache, ["BTC", "ETH", "SOL"], window=96)

        assert first == second
        assert first["window"] == 96

    def test_build_correlation_matrix_diagonal_ones(self):
        import json
        cache = FakeCache()
        cache.set("market:candles:BTCUSDT:15m", json.dumps(_candles(1.0)))
        cache.set("market:candles:ETHUSDT:15m", json.dumps(_candles(1.1)))

        result = build_correlation_matrix(cache, ["BTC", "ETH"], window=96)
        assert result["correlation_matrix"]["BTC"]["BTC"] == 1.0
        assert result["correlation_matrix"]["ETH"]["ETH"] == 1.0


class TestCorrelationClusterBuilder:
    """correlation_cluster_builder unit tests"""

    def test_build_clusters_with_threshold_075(self):
        matrix_payload = {
            "symbols": ["BTC", "ETH", "SOL"],
            "correlation_matrix": {
                "BTC": {"BTC": 1.0, "ETH": 0.82, "SOL": 0.78},
                "ETH": {"BTC": 0.82, "ETH": 1.0, "SOL": 0.81},
                "SOL": {"BTC": 0.78, "ETH": 0.81, "SOL": 1.0},
            },
        }
        result = build_correlation_clusters(matrix_payload, threshold=0.75)
        assert result["threshold"] == 0.75
        assert len(result["correlation_clusters"]) == 1

    def test_build_clusters_separates_low_correlation(self):
        matrix_payload = {
            "symbols": ["BTC", "ETH", "DOGE"],
            "correlation_matrix": {
                "BTC": {"BTC": 1.0, "ETH": 0.85, "DOGE": 0.30},
                "ETH": {"BTC": 0.85, "ETH": 1.0, "DOGE": 0.25},
                "DOGE": {"BTC": 0.30, "ETH": 0.25, "DOGE": 1.0},
            },
        }
        result = build_correlation_clusters(matrix_payload, threshold=0.75)
        assert len(result["correlation_clusters"]) == 2  # BTC+ETH cluster and DOGE alone


class TestClusterExposureCalculator:
    """cluster_exposure_calculator unit tests"""

    def test_calculate_cluster_exposure_aggregates(self):
        result = calculate_cluster_exposure(
            clusters=[{"cluster_id": "CLUSTER_1", "symbols": ["BTC", "ETH"]}],
            positions=[
                {"symbol": "BTCUSDT", "side": "LONG", "position_notional": 1000, "leverage": 2},
                {"symbol": "ETHUSDT", "side": "LONG", "position_notional": 500, "leverage": 3},
            ],
            portfolio_equity=10000,
        )
        row = result["cluster_exposures"][0]
        assert row["cluster_exposure"] == 0.15  # 1500/10000
        assert row["cluster_direction"] == "LONG"
        assert row["cluster_position_count"] == 2


class TestClusterRiskGovernor:
    """cluster_risk_governor unit tests"""

    def test_evaluate_cluster_risk_emits_limit_hit(self):
        result = evaluate_cluster_risk(
            cluster_exposures=[
                {
                    "cluster_id": "CLUSTER_1",
                    "symbols": ["BTC", "ETH"],
                    "cluster_exposure": 0.40,
                    "cluster_position_count": 4,
                    "cluster_direction": "LONG",
                    "cluster_exposure_notional": 4000,
                }
            ],
            cluster_exposure_limit=0.35,
            cluster_position_limit=3,
        )
        assert result["risk_state"] == "ALERT"
        assert len(result["cluster_risk_alerts"]) > 0
        assert result["cluster_risk_alerts"][0]["event"] == "CLUSTER_RISK_LIMIT_HIT"

    def test_evaluate_cluster_risk_normal_state(self):
        result = evaluate_cluster_risk(
            cluster_exposures=[
                {
                    "cluster_id": "CLUSTER_1",
                    "symbols": ["BTC"],
                    "cluster_exposure": 0.10,
                    "cluster_position_count": 1,
                    "cluster_direction": "LONG",
                    "cluster_exposure_notional": 1000,
                }
            ],
            cluster_exposure_limit=0.35,
            cluster_position_limit=3,
        )
        assert result["risk_state"] == "NORMAL"
        assert len(result["cluster_risk_alerts"]) == 0


class TestClusterOrderGuard:
    """cluster_order_guard unit tests"""

    def test_order_guard_rejects_on_limit_exceed(self):
        decision = evaluate_cluster_order_guard(
            order={"symbol": "BTCUSDT", "side": "LONG", "position_notional": 1000, "position_size_ratio": 1.0},
            clusters=[{"cluster_id": "CLUSTER_1", "symbols": ["BTC", "ETH"]}],
            cluster_exposures=[{"cluster_id": "CLUSTER_1", "cluster_exposure_notional": 3000}],
            portfolio_equity=10000,
            cluster_exposure_limit=0.35,
        )
        assert decision["action"] == "REJECT"
        assert decision["event"]["event"] == "CLUSTER_TRADE_REJECTED"

    def test_order_guard_reduces_size_near_limit(self):
        decision = evaluate_cluster_order_guard(
            order={"symbol": "ETHUSDT", "side": "LONG", "position_notional": 200, "position_size_ratio": 0.8},
            clusters=[{"cluster_id": "CLUSTER_1", "symbols": ["BTC", "ETH"]}],
            cluster_exposures=[{"cluster_id": "CLUSTER_1", "cluster_exposure_notional": 3200}],
            portfolio_equity=10000,
            cluster_exposure_limit=0.35,
        )
        assert decision["action"] == "REDUCE_SIZE"
        assert decision["adjusted_position_size_ratio"] < 0.8

    def test_order_guard_allows_within_limit(self):
        decision = evaluate_cluster_order_guard(
            order={"symbol": "BTCUSDT", "side": "LONG", "position_notional": 500, "position_size_ratio": 1.0},
            clusters=[{"cluster_id": "CLUSTER_1", "symbols": ["BTC", "ETH"]}],
            cluster_exposures=[{"cluster_id": "CLUSTER_1", "cluster_exposure_notional": 1000}],
            portfolio_equity=10000,
            cluster_exposure_limit=0.35,
        )
        assert decision["action"] == "ALLOW"


class TestClusterGovernanceAudit:
    """cluster_governance_audit unit tests"""

    def test_build_governance_audit_events(self):
        matrix_payload = {"correlation_matrix": {"BTC": {"ETH": 0.85}}, "symbols": ["BTC", "ETH"]}
        clusters_payload = {
            "correlation_clusters": [{"cluster_id": "CLUSTER_1", "symbols": ["BTC", "ETH"]}]
        }
        risk_payload = {
            "cluster_risk_alerts": [
                {
                    "cluster_id": "CLUSTER_1",
                    "event": "CLUSTER_RISK_LIMIT_HIT",
                    "symbols": ["BTC", "ETH"],
                    "cluster_exposure": 0.40,
                    "cluster_direction": "LONG",
                    "reason": ["CLUSTER_EXPOSURE_LIMIT"],
                    "timestamp": "2026-03-12T00:00:00+00:00",
                }
            ]
        }
        order_events = [
            {
                "cluster_id": "CLUSTER_1",
                "event": "CLUSTER_TRADE_REJECTED",
                "symbols": ["BTC"],
                "exposure": 0.42,
                "direction": "LONG",
                "reason": ["CLUSTER_EXPOSURE_LIMIT"],
            }
        ]

        events = build_cluster_governance_audit_events(
            matrix_payload=matrix_payload,
            clusters_payload=clusters_payload,
            risk_payload=risk_payload,
            order_events=order_events,
        )

        event_types = {e["event"] for e in events}
        assert "CLUSTER_CREATED" in event_types
        assert "CLUSTER_RISK_LIMIT_HIT" in event_types
        assert "CLUSTER_TRADE_REJECTED" in event_types
        assert "CLUSTER_UPDATED" in event_types


# ==================== REGRESSION TESTS ====================

class TestRegressionStrategyHealth:
    """Regression: GET /api/admin/futures/strategy-health"""

    def test_strategy_health_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-health",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_strategy_health_contract(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-health",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "strategy_health_score" in payload
        assert "health_components" in payload
        assert "lifecycle_state" in payload
        assert "drawdown_state" in payload


class TestRegressionStrategyGovernance:
    """Regression: GET /api/admin/futures/strategy-governance"""

    def test_strategy_governance_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_strategy_governance_contract(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        required_fields = [
            "strategy_health_score",
            "throttle_state",
            "disable_state",
            "decay_events",
            "health_components",
            "decay_reason_codes",
            "lifecycle_state",
            "last_transition_at",
            "drawdown_state",
            "strategy_compare_mode",
            "cluster_risk_overlay",
        ]
        for field in required_fields:
            assert field in payload, f"Missing field: {field}"


class TestRegressionStrategyPerformance:
    """Regression: GET /api/admin/futures/strategy-performance"""

    def test_strategy_performance_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-performance",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200


class TestRegressionStrategyExecutionQuality:
    """Regression: GET /api/admin/futures/strategy-execution-quality"""

    def test_strategy_execution_quality_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-execution-quality",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_gate_reason_trend_7d_count(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-execution-quality",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "gate_reason_trend_7d" in payload
        assert len(payload["gate_reason_trend_7d"]) == 7
