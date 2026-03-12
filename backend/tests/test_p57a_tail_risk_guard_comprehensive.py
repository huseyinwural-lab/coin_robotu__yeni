"""
Phase 5.7A Tail Risk Guard Comprehensive Tests
- Tail risk detector unit tests
- Liquidation cascade guard event contracts
- Extreme volatility guard event contracts  
- Exchange outage guard event contracts
- Global risk score engine threshold tests (>60 downshift, >80 throttle, >90 pause)
- Tail risk order guard REJECT/REDUCE_SIZE behavior
- Tail risk audit payload schema
- Endpoint contract tests: /tail-risk, /global-risk
- Regression: correlation-*, capital-*, strategy-governance, strategy-performance, strategy-execution-quality
"""
import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


# ============ FIXTURES ============

@pytest.fixture(scope="module")
def admin_headers():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    login = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if login.status_code != 200:
        pytest.skip(f"Admin login failed: {login.text}")
    token = login.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ============ UNIT TESTS: TAIL RISK DETECTOR ============

class TestTailRiskDetector:
    """Tail risk detector unit tests"""

    def test_tail_risk_score_deterministic_calculation(self):
        from core.risk.tail_risk.tail_risk_detector import compute_tail_risk_score
        
        payload = compute_tail_risk_score({
            "volatility_pct": 5.0,
            "liquidation_pressure_input": 0.5,
            "liquidity_depth_score": 0.3,
            "spread_bps": 20,
        })
        assert 0 <= payload["tail_risk_score"] <= 100
        assert "volatility_score" in payload
        assert "liquidation_pressure" in payload
        assert "liquidity_score" in payload
        assert "spread_anomaly" in payload

    def test_tail_risk_fallback_mode_applies_minimum_score(self):
        from core.risk.tail_risk.tail_risk_detector import compute_tail_risk_score
        
        payload = compute_tail_risk_score({
            "volatility_pct": 1.0,
            "liquidation_pressure_input": 0.1,
            "liquidity_depth_score": 0.8,
            "spread_bps": 5,
            "fallback_mode": True,
        })
        assert payload["tail_risk_score"] >= 62.0
        assert payload["fallback_applied"] is True

    def test_tail_risk_high_volatility_increases_score(self):
        from core.risk.tail_risk.tail_risk_detector import compute_tail_risk_score
        
        low_vol = compute_tail_risk_score({
            "volatility_pct": 1.0,
            "liquidation_pressure_input": 0.0,
            "liquidity_depth_score": 1.0,
            "spread_bps": 0,
        })
        high_vol = compute_tail_risk_score({
            "volatility_pct": 10.0,
            "liquidation_pressure_input": 0.0,
            "liquidity_depth_score": 1.0,
            "spread_bps": 0,
        })
        assert high_vol["tail_risk_score"] > low_vol["tail_risk_score"]


# ============ UNIT TESTS: LIQUIDATION CASCADE GUARD ============

class TestLiquidationCascadeGuard:
    """Liquidation cascade guard event contracts"""

    def test_liquidation_cascade_emits_alert_when_multiple_triggers(self):
        from core.risk.tail_risk.liquidation_cascade_guard import detect_liquidation_cascade
        
        payload = detect_liquidation_cascade({
            "rapid_price_drop_pct": -4.0,  # triggers RAPID_PRICE_DROP
            "liquidation_volume_spike": 2.5,  # triggers LIQUIDATION_VOLUME_SPIKE
            "funding_rate_anomaly": 0.025,  # triggers FUNDING_RATE_ANOMALY
        })
        assert payload["active"] is True
        assert payload["severity"] == "HIGH"
        assert payload["event"]["event"] == "LIQUIDATION_CASCADE_ALERT"
        assert "RAPID_PRICE_DROP" in payload["reason"]
        assert "LIQUIDATION_VOLUME_SPIKE" in payload["reason"]
        assert "FUNDING_RATE_ANOMALY" in payload["reason"]

    def test_liquidation_cascade_inactive_when_single_trigger(self):
        from core.risk.tail_risk.liquidation_cascade_guard import detect_liquidation_cascade
        
        payload = detect_liquidation_cascade({
            "rapid_price_drop_pct": -4.0,
            "liquidation_volume_spike": 1.0,
            "funding_rate_anomaly": 0.01,
        })
        assert payload["active"] is False
        assert payload["event"] is None

    def test_liquidation_cascade_applies_throttle_multiplier(self):
        from core.risk.tail_risk.liquidation_cascade_guard import detect_liquidation_cascade
        
        payload = detect_liquidation_cascade({
            "rapid_price_drop_pct": -4.0,
            "liquidation_volume_spike": 2.5,
            "funding_rate_anomaly": 0.025,
        })
        assert payload["position_size_multiplier"] == 0.45


# ============ UNIT TESTS: EXTREME VOLATILITY GUARD ============

class TestExtremeVolatilityGuard:
    """Extreme volatility guard event contracts"""

    def test_extreme_volatility_emits_alert_when_multiple_triggers(self):
        from core.risk.tail_risk.extreme_volatility_guard import detect_extreme_volatility
        
        payload = detect_extreme_volatility({
            "atr_ratio": 2.5,  # triggers ATR_EXPLOSION
            "price_delta_pct": 3.5,  # triggers PRICE_DELTA_ANOMALY
            "volatility_percentile": 0.95,  # triggers VOLATILITY_PERCENTILE_SPIKE
        })
        assert payload["active"] is True
        assert payload["severity"] == "HIGH"
        assert payload["event"]["event"] == "EXTREME_VOLATILITY_ALERT"
        assert "ATR_EXPLOSION" in payload["reason"]
        assert "PRICE_DELTA_ANOMALY" in payload["reason"]
        assert "VOLATILITY_PERCENTILE_SPIKE" in payload["reason"]

    def test_extreme_volatility_inactive_when_single_trigger(self):
        from core.risk.tail_risk.extreme_volatility_guard import detect_extreme_volatility
        
        payload = detect_extreme_volatility({
            "atr_ratio": 2.5,
            "price_delta_pct": 1.0,
            "volatility_percentile": 0.5,
        })
        assert payload["active"] is False
        assert payload["event"] is None

    def test_extreme_volatility_applies_multipliers(self):
        from core.risk.tail_risk.extreme_volatility_guard import detect_extreme_volatility
        
        payload = detect_extreme_volatility({
            "atr_ratio": 2.5,
            "price_delta_pct": 3.5,
            "volatility_percentile": 0.95,
        })
        assert payload["trade_frequency_multiplier"] == 0.5
        assert payload["position_size_multiplier"] == 0.6


# ============ UNIT TESTS: EXCHANGE OUTAGE GUARD ============

class TestExchangeOutageGuard:
    """Exchange outage guard event contracts"""

    def test_exchange_health_emits_alert_when_multiple_triggers(self):
        from core.risk.tail_risk.exchange_outage_guard import evaluate_exchange_health
        
        payload = evaluate_exchange_health({
            "api_latency_ms": 1500,  # triggers API_LATENCY_SPIKE
            "ack_delay_ms": 2000,  # triggers ACK_DELAY_SPIKE
            "order_reject_rate": 0.3,  # triggers ORDER_REJECT_ANOMALY
            "heartbeat_age_sec": 40,  # triggers HEARTBEAT_TIMEOUT
        })
        assert payload["active"] is True
        assert payload["severity"] == "CRITICAL"
        assert payload["trade_pause"] is True
        assert payload["event"]["event"] == "EXCHANGE_HEALTH_ALERT"

    def test_exchange_health_inactive_when_normal(self):
        from core.risk.tail_risk.exchange_outage_guard import evaluate_exchange_health
        
        payload = evaluate_exchange_health({
            "api_latency_ms": 200,
            "ack_delay_ms": 300,
            "order_reject_rate": 0.05,
            "heartbeat_age_sec": 5,
        })
        assert payload["active"] is False
        assert payload["trade_pause"] is False
        assert payload["event"] is None


# ============ UNIT TESTS: GLOBAL RISK SCORE ENGINE ============

class TestGlobalRiskScoreEngine:
    """Global risk score engine threshold tests"""

    def test_global_risk_normal_state_below_60(self):
        from core.risk.tail_risk.global_risk_score_engine import compute_global_risk_score
        
        payload = compute_global_risk_score(
            strategy_health_score=80,
            cluster_risk_state="NORMAL",
            capital_drift_state="NORMAL",
            tail_risk_score=10,
        )
        assert payload["global_risk_score"] < 60
        assert payload["risk_state"] == "NORMAL"
        assert payload["active_events"] == []

    def test_global_risk_downshift_state_above_60(self):
        from core.risk.tail_risk.global_risk_score_engine import compute_global_risk_score
        
        payload = compute_global_risk_score(
            strategy_health_score=30,  # 70 risk component
            cluster_risk_state="ALERT",  # 78 risk component
            capital_drift_state="NORMAL",  # 24 risk component
            tail_risk_score=50,  # 50 risk component
        )
        # 70*0.25 + 78*0.25 + 24*0.20 + 50*0.30 = 17.5 + 19.5 + 4.8 + 15 = 56.8
        # Need higher values for >60
        payload = compute_global_risk_score(
            strategy_health_score=20,  # 80 risk component
            cluster_risk_state="ALERT",  # 78 risk component
            capital_drift_state="NORMAL",  # 24 risk component
            tail_risk_score=70,  # 70 risk component
        )
        # 80*0.25 + 78*0.25 + 24*0.20 + 70*0.30 = 20 + 19.5 + 4.8 + 21 = 65.3
        assert payload["global_risk_score"] > 60
        assert payload["risk_state"] == "DOWNSHIFT"
        assert any(e["event"] == "GLOBAL_RISK_ALERT" for e in payload["active_events"])

    def test_global_risk_throttle_state_above_80(self):
        from core.risk.tail_risk.global_risk_score_engine import compute_global_risk_score
        
        payload = compute_global_risk_score(
            strategy_health_score=10,  # 90 risk component
            cluster_risk_state="ALERT",  # 78 risk component
            capital_drift_state="ALERT",  # 82 risk component
            tail_risk_score=85,  # 85 risk component
        )
        # 90*0.25 + 78*0.25 + 82*0.20 + 85*0.30 = 22.5 + 19.5 + 16.4 + 25.5 = 83.9
        assert payload["global_risk_score"] > 80
        assert payload["risk_state"] == "THROTTLE"
        assert any(e["event"] == "GLOBAL_RISK_THROTTLE" for e in payload["active_events"])

    def test_global_risk_pause_state_above_90(self):
        from core.risk.tail_risk.global_risk_score_engine import compute_global_risk_score
        
        payload = compute_global_risk_score(
            strategy_health_score=0,  # 100 risk component
            cluster_risk_state="ALERT",  # 78 risk component
            capital_drift_state="ALERT",  # 82 risk component
            tail_risk_score=100,  # 100 risk component
        )
        # 100*0.25 + 78*0.25 + 82*0.20 + 100*0.30 = 25 + 19.5 + 16.4 + 30 = 90.9
        assert payload["global_risk_score"] > 90
        assert payload["risk_state"] == "PAUSE"
        assert any(e["event"] == "TRADE_ENGINE_PAUSED" for e in payload["active_events"])

    def test_global_risk_correct_weights(self):
        from core.risk.tail_risk.global_risk_score_engine import compute_global_risk_score
        
        payload = compute_global_risk_score(
            strategy_health_score=50,
            cluster_risk_state="NORMAL",
            capital_drift_state="NORMAL",
            tail_risk_score=50,
        )
        assert payload["weights"]["strategy"] == 0.25
        assert payload["weights"]["cluster"] == 0.25
        assert payload["weights"]["capital"] == 0.20
        assert payload["weights"]["tail_risk"] == 0.30


# ============ UNIT TESTS: TAIL RISK ORDER GUARD ============

class TestTailRiskOrderGuard:
    """Tail risk order guard REJECT/REDUCE_SIZE behavior"""

    def test_tail_risk_order_guard_rejects_on_pause_state(self):
        from core.risk.tail_risk.tail_risk_order_guard import evaluate_tail_risk_order_guard
        
        payload = evaluate_tail_risk_order_guard(
            strategy_id="trend_follow_v1",
            global_risk_score=95,
            risk_state="PAUSE",
            active_alerts=[{"event": "TRADE_ENGINE_PAUSED"}],
        )
        assert payload["action"] == "REJECT"
        assert payload["size_multiplier"] == 0.0
        assert payload["pause_strategy"] is True
        assert payload["event"]["event"] == "TAIL_RISK_TRADE_REJECTED"

    def test_tail_risk_order_guard_reduces_size_on_throttle(self):
        from core.risk.tail_risk.tail_risk_order_guard import evaluate_tail_risk_order_guard
        
        payload = evaluate_tail_risk_order_guard(
            strategy_id="trend_follow_v1",
            global_risk_score=85,
            risk_state="THROTTLE",
            active_alerts=[],
        )
        assert payload["action"] == "REDUCE_SIZE"
        assert payload["size_multiplier"] == 0.45
        assert payload["pause_strategy"] is False
        assert payload["event"] is None

    def test_tail_risk_order_guard_reduces_size_on_downshift(self):
        from core.risk.tail_risk.tail_risk_order_guard import evaluate_tail_risk_order_guard
        
        payload = evaluate_tail_risk_order_guard(
            strategy_id="trend_follow_v1",
            global_risk_score=70,
            risk_state="DOWNSHIFT",
            active_alerts=[],
        )
        assert payload["action"] == "REDUCE_SIZE"
        assert payload["size_multiplier"] == 0.7
        assert payload["pause_strategy"] is False

    def test_tail_risk_order_guard_allows_on_normal(self):
        from core.risk.tail_risk.tail_risk_order_guard import evaluate_tail_risk_order_guard
        
        payload = evaluate_tail_risk_order_guard(
            strategy_id="trend_follow_v1",
            global_risk_score=30,
            risk_state="NORMAL",
            active_alerts=[],
        )
        assert payload["action"] == "ALLOW"
        assert payload["size_multiplier"] == 1.0
        assert payload["pause_strategy"] is False


# ============ UNIT TESTS: TAIL RISK AUDIT ============

class TestTailRiskAudit:
    """Tail risk audit payload schema tests"""

    def test_tail_risk_audit_builds_event_list(self):
        from core.observability.tail_risk_audit import build_tail_risk_audit_events
        
        events = build_tail_risk_audit_events(
            tail_risk_score=75.0,
            detector_events=[
                {"event": "LIQUIDATION_CASCADE_ALERT", "reason": ["RAPID_PRICE_DROP"], "timestamp": "2026-03-12T00:00:00+00:00"}
            ],
            global_events=[
                {"event": "GLOBAL_RISK_ALERT", "timestamp": "2026-03-12T00:00:00+00:00"}
            ],
            order_events=[
                {"event": "TAIL_RISK_TRADE_REJECTED", "reason": ["TRADE_ENGINE_PAUSED"], "timestamp": "2026-03-12T00:00:00+00:00"}
            ],
            affected_symbols=["BTCUSDT", "ETHUSDT"],
        )
        assert len(events) >= 4  # TAIL_RISK_ALERT + detector + global + order
        assert events[0]["event"] == "TAIL_RISK_ALERT"
        assert events[0]["risk_score"] == 75.0
        assert "BTCUSDT" in events[0]["affected_symbols"]

    def test_tail_risk_audit_includes_all_event_types(self):
        from core.observability.tail_risk_audit import build_tail_risk_audit_events
        
        events = build_tail_risk_audit_events(
            tail_risk_score=80.0,
            detector_events=[
                {"event": "LIQUIDATION_CASCADE_ALERT", "reason": ["RAPID_PRICE_DROP"], "timestamp": "2026-03-12T00:00:00+00:00"},
                {"event": "EXTREME_VOLATILITY_ALERT", "reason": ["ATR_EXPLOSION"], "timestamp": "2026-03-12T00:00:00+00:00"},
            ],
            global_events=[{"event": "GLOBAL_RISK_THROTTLE", "timestamp": "2026-03-12T00:00:00+00:00"}],
            order_events=[],
            affected_symbols=["BTCUSDT"],
        )
        event_types = [e["event"] for e in events]
        assert "TAIL_RISK_ALERT" in event_types
        assert "LIQUIDATION_CASCADE_ALERT" in event_types
        assert "EXTREME_VOLATILITY_ALERT" in event_types
        assert "GLOBAL_RISK_THROTTLE" in event_types


# ============ ENDPOINT CONTRACT TESTS ============

class TestTailRiskEndpointContract:
    """GET /api/admin/futures/tail-risk endpoint contract"""

    def test_tail_risk_endpoint_returns_200(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/tail-risk", headers=admin_headers, timeout=20)
        assert response.status_code == 200

    def test_tail_risk_endpoint_contract_fields(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/tail-risk", headers=admin_headers, timeout=20)
        payload = response.json()
        required_fields = [
            "tail_risk_score", "risk_state", "active_alerts",
            "volatility_score", "liquidation_pressure", "liquidity_score", "spread_anomaly",
            "liquidation_cascade", "extreme_volatility", "exchange_health", "tail_risk_history"
        ]
        for field in required_fields:
            assert field in payload, f"Missing field: {field}"

    def test_tail_risk_score_within_bounds(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/tail-risk", headers=admin_headers, timeout=20)
        payload = response.json()
        assert 0 <= payload["tail_risk_score"] <= 100

    def test_tail_risk_risk_state_valid(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/tail-risk", headers=admin_headers, timeout=20)
        payload = response.json()
        assert payload["risk_state"] in ["NORMAL", "ELEVATED", "HIGH"]


class TestGlobalRiskEndpointContract:
    """GET /api/admin/futures/global-risk endpoint contract"""

    def test_global_risk_endpoint_returns_200(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/global-risk", headers=admin_headers, timeout=20)
        assert response.status_code == 200

    def test_global_risk_endpoint_contract_fields(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/global-risk", headers=admin_headers, timeout=20)
        payload = response.json()
        required_fields = [
            "tail_risk_score", "global_risk_score", "risk_state", "active_alerts", "components", "weights"
        ]
        for field in required_fields:
            assert field in payload, f"Missing field: {field}"

    def test_global_risk_components_present(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/global-risk", headers=admin_headers, timeout=20)
        payload = response.json()
        components = payload.get("components", {})
        required_components = [
            "strategy_risk_component", "cluster_risk_component",
            "capital_risk_component", "tail_risk_component"
        ]
        for comp in required_components:
            assert comp in components, f"Missing component: {comp}"

    def test_global_risk_weights_sum_to_one(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/global-risk", headers=admin_headers, timeout=20)
        payload = response.json()
        weights = payload.get("weights", {})
        total = sum(float(v) for v in weights.values())
        assert abs(total - 1.0) < 0.01  # Allow small float tolerance


# ============ REGRESSION TESTS ============

class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""

    def test_cluster_risk_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/cluster-risk", headers=admin_headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        assert "risk_state" in payload
        assert "cluster_id_count" in payload

    def test_capital_drift_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-drift", headers=admin_headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        assert "drift_state" in payload
        assert "capital_drift_events" in payload

    def test_strategy_governance_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-governance", headers=admin_headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        assert "strategy_health_score" in payload
        assert "tail_risk_score" in payload
        assert "global_risk_score" in payload

    def test_strategy_performance_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-performance", headers=admin_headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        assert "strategy_registry" in payload
        assert "strategy_pnl_contribution" in payload

    def test_strategy_execution_quality_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality", headers=admin_headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        assert "strategy_execution_quality" in payload
        assert "strategy_slippage" in payload

    def test_capital_budget_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-budget", headers=admin_headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        assert "portfolio_capital_registry" in payload

    def test_capital_usage_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-usage", headers=admin_headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        assert "strategy_capital_usage" in payload


# ============ INTEGRATION TESTS ============

class TestTailRiskIntegration:
    """Integration tests for tail risk in strategy governance"""

    def test_strategy_governance_includes_tail_risk_overlay(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-governance", headers=admin_headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        # Strategy governance should include global risk state from tail risk
        assert "tail_risk_score" in payload
        assert "global_risk_score" in payload
        assert "global_risk_state" in payload

    def test_global_risk_state_valid_values(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/global-risk", headers=admin_headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        assert payload["risk_state"] in ["NORMAL", "DOWNSHIFT", "THROTTLE", "PAUSE"]
