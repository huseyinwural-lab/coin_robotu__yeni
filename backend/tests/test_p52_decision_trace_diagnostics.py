"""
Phase 5.2 Decision Trace Standard & Diagnostics Tests
Tests for:
- Decision trace contract: tek model formatında dönüyor mu (trace_id, timestamp, symbol, strategy, side, signal_confidence, regime, microstructure_result, risk_result, liquidation_result, adl_result, final_decision, reason_code)
- Reason code taxonomy tekilleştirildi mi: SIGNAL_WEAK, MICROSTRUCTURE_SPREAD_SHOCK, MICROSTRUCTURE_DEPTH_COLLAPSE, MICROSTRUCTURE_SLIPPAGE_ANOMALY, RISK_LEVERAGE_LIMIT, RISK_MARGIN_USAGE, LIQUIDATION_DISTANCE_TOO_LOW, CASCADE_DETECTED, ADL_PRESSURE_LONG, ADL_PRESSURE_SHORT, POLICY_BLOCK, GATE_REJECT, ALLOW
- Attribution deterministic mi: decision_layer (STRATEGY/MICROSTRUCTURE/RISK_ENGINE/LIQUIDATION/ADL/POLICY/GATE) doğru atanıyor mu
- Paper decision flow updated chain çalışıyor mu: signal -> microstructure -> risk -> liquidation -> ADL -> policy -> gate -> attribution -> trace -> paper execution
- GET /api/admin/futures/decision-diagnostics endpointi contract döndürüyor mu: false_allow_count, false_reject_count, gate_reason_distribution, confidence_vs_result
- Regression: /api/admin/futures/strategy/status, /api/admin/futures/risk/status, /api/admin/futures/microstructure/status çalışıyor mu
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


# ==================== FIXTURES ====================

@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not defined")
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=25,
        )
    except requests.RequestException as exc:
        pytest.skip(f"Auth endpoint unavailable: {exc}")
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.text}")
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Get admin authorization headers"""
    return {"Authorization": f"Bearer {admin_token}"}


# ==================== UNIT TESTS ====================

class TestDecisionTraceModel:
    """Decision trace contract model tests"""

    def test_decision_trace_model_has_all_required_fields(self):
        """Verify decision trace model has tek contract format"""
        from core.futures.decision.decision_trace_model import build_decision_trace

        trace = build_decision_trace(
            symbol="BTCUSDT",
            strategy="futures_trend_follow_v1",
            side="LONG",
            signal_confidence=0.85,
            regime="TRENDING",
            microstructure_result="PASS",
            risk_result="PASS",
            liquidation_result="PASS",
            adl_result="PASS",
            final_decision="ALLOW",
            reason_code="ALLOW",
            decision_layer="GATE",
        )

        required_fields = {
            "trace_id", "timestamp", "symbol", "strategy", "side",
            "signal_confidence", "regime", "microstructure_result",
            "risk_result", "liquidation_result", "adl_result",
            "final_decision", "reason_code", "decision_layer",
        }
        assert required_fields.issubset(trace.keys()), f"Missing fields: {required_fields - set(trace.keys())}"
        assert trace["symbol"] == "BTCUSDT"
        assert trace["strategy"] == "futures_trend_follow_v1"
        assert trace["side"] == "LONG"
        assert trace["final_decision"] == "ALLOW"
        assert trace["reason_code"] == "ALLOW"
        assert trace["decision_layer"] == "GATE"

    def test_decision_trace_model_reject_case(self):
        """Verify decision trace model works for REJECT case"""
        from core.futures.decision.decision_trace_model import build_decision_trace

        trace = build_decision_trace(
            symbol="ETHUSDT",
            strategy="futures_trend_follow_v1",
            side="SHORT",
            signal_confidence=0.72,
            regime="VOLATILE",
            microstructure_result="REJECT",
            risk_result="PASS",
            liquidation_result="PASS",
            adl_result="PASS",
            final_decision="REJECT",
            reason_code="MICROSTRUCTURE_SPREAD_SHOCK",
            decision_layer="MICROSTRUCTURE",
        )

        assert trace["final_decision"] == "REJECT"
        assert trace["reason_code"] == "MICROSTRUCTURE_SPREAD_SHOCK"
        assert trace["decision_layer"] == "MICROSTRUCTURE"
        assert "trace_id" in trace
        assert "timestamp" in trace


class TestReasonCodeTaxonomy:
    """Reason code taxonomy uniqueness tests"""

    def test_reason_code_taxonomy_is_complete(self):
        """Verify all expected reason codes exist"""
        from core.futures.decision.reason_codes import ReasonCode

        expected_codes = {
            "SIGNAL_WEAK",
            "MICROSTRUCTURE_SPREAD_SHOCK",
            "MICROSTRUCTURE_DEPTH_COLLAPSE",
            "MICROSTRUCTURE_SLIPPAGE_ANOMALY",
            "RISK_LEVERAGE_LIMIT",
            "RISK_MARGIN_USAGE",
            "LIQUIDATION_DISTANCE_TOO_LOW",
            "CASCADE_DETECTED",
            "ADL_PRESSURE_LONG",
            "ADL_PRESSURE_SHORT",
            "POLICY_BLOCK",
            "GATE_REJECT",
            "ALLOW",
        }
        current_codes = {item.value for item in ReasonCode}
        assert expected_codes == current_codes, f"Mismatch: expected={expected_codes}, got={current_codes}"

    def test_reason_code_taxonomy_no_duplicates(self):
        """Verify no duplicate reason codes"""
        from core.futures.decision.reason_codes import ReasonCode

        codes = [item.value for item in ReasonCode]
        assert len(codes) == len(set(codes)), "Duplicate reason codes found"

    def test_decision_layer_taxonomy_is_complete(self):
        """Verify all expected decision layers exist"""
        from core.futures.decision.reason_codes import DecisionLayer

        expected_layers = {
            "STRATEGY",
            "MICROSTRUCTURE",
            "RISK_ENGINE",
            "LIQUIDATION",
            "ADL",
            "POLICY",
            "GATE",
        }
        current_layers = {item.value for item in DecisionLayer}
        assert expected_layers == current_layers, f"Mismatch: expected={expected_layers}, got={current_layers}"


class TestDecisionAttribution:
    """Decision attribution determinism tests"""

    def test_attribution_signal_weak_layer_is_strategy(self):
        """Verify SIGNAL_WEAK assigns STRATEGY layer"""
        from core.futures.decision.decision_attribution_engine import DecisionAttributionEngine

        result = DecisionAttributionEngine().evaluate(
            signal_valid=False,
            microstructure_pass=True,
            microstructure_reason="",
            risk_pass=True,
            risk_reason="",
            liquidation_pass=True,
            liquidation_reason="",
            adl_pass=True,
            adl_reason="",
            adl_pressure_side="NONE",
            policy_pass=True,
            gate_pass=False,
        )
        assert result["decision"] == "REJECT"
        assert result["reason_code"] == "SIGNAL_WEAK"
        assert result["decision_layer"] == "STRATEGY"

    def test_attribution_microstructure_layer_is_deterministic(self):
        """Verify microstructure failures assign MICROSTRUCTURE layer"""
        from core.futures.decision.decision_attribution_engine import DecisionAttributionEngine

        result = DecisionAttributionEngine().evaluate(
            signal_valid=True,
            microstructure_pass=False,
            microstructure_reason="SPREAD_SHOCK",
            risk_pass=True,
            risk_reason="",
            liquidation_pass=True,
            liquidation_reason="",
            adl_pass=True,
            adl_reason="",
            adl_pressure_side="NONE",
            policy_pass=True,
            gate_pass=False,
        )
        assert result["decision"] == "REJECT"
        assert result["reason_code"] == "MICROSTRUCTURE_SPREAD_SHOCK"
        assert result["decision_layer"] == "MICROSTRUCTURE"

    def test_attribution_risk_layer_is_deterministic(self):
        """Verify risk failures assign RISK_ENGINE layer"""
        from core.futures.decision.decision_attribution_engine import DecisionAttributionEngine

        result = DecisionAttributionEngine().evaluate(
            signal_valid=True,
            microstructure_pass=True,
            microstructure_reason="",
            risk_pass=False,
            risk_reason="leverage_limit_exceeded",
            liquidation_pass=True,
            liquidation_reason="",
            adl_pass=True,
            adl_reason="",
            adl_pressure_side="NONE",
            policy_pass=True,
            gate_pass=False,
        )
        assert result["decision"] == "REJECT"
        assert result["reason_code"] == "RISK_LEVERAGE_LIMIT"
        assert result["decision_layer"] == "RISK_ENGINE"

    def test_attribution_liquidation_layer_is_deterministic(self):
        """Verify liquidation failures assign LIQUIDATION layer"""
        from core.futures.decision.decision_attribution_engine import DecisionAttributionEngine

        result = DecisionAttributionEngine().evaluate(
            signal_valid=True,
            microstructure_pass=True,
            microstructure_reason="",
            risk_pass=True,
            risk_reason="",
            liquidation_pass=False,
            liquidation_reason="distance_too_low",
            adl_pass=True,
            adl_reason="",
            adl_pressure_side="NONE",
            policy_pass=True,
            gate_pass=False,
        )
        assert result["decision"] == "REJECT"
        assert result["reason_code"] == "LIQUIDATION_DISTANCE_TOO_LOW"
        assert result["decision_layer"] == "LIQUIDATION"

    def test_attribution_adl_layer_is_deterministic(self):
        """Verify ADL failures assign ADL layer"""
        from core.futures.decision.decision_attribution_engine import DecisionAttributionEngine

        result = DecisionAttributionEngine().evaluate(
            signal_valid=True,
            microstructure_pass=True,
            microstructure_reason="",
            risk_pass=True,
            risk_reason="",
            liquidation_pass=True,
            liquidation_reason="",
            adl_pass=False,
            adl_reason="",
            adl_pressure_side="LONG",
            policy_pass=True,
            gate_pass=False,
        )
        assert result["decision"] == "REJECT"
        assert result["reason_code"] == "ADL_PRESSURE_LONG"
        assert result["decision_layer"] == "ADL"

    def test_attribution_policy_layer_is_deterministic(self):
        """Verify policy failures assign POLICY layer"""
        from core.futures.decision.decision_attribution_engine import DecisionAttributionEngine

        result = DecisionAttributionEngine().evaluate(
            signal_valid=True,
            microstructure_pass=True,
            microstructure_reason="",
            risk_pass=True,
            risk_reason="",
            liquidation_pass=True,
            liquidation_reason="",
            adl_pass=True,
            adl_reason="",
            adl_pressure_side="NONE",
            policy_pass=False,
            gate_pass=False,
        )
        assert result["decision"] == "REJECT"
        assert result["reason_code"] == "POLICY_BLOCK"
        assert result["decision_layer"] == "POLICY"

    def test_attribution_allow_assigns_gate_layer(self):
        """Verify ALLOW assigns GATE layer"""
        from core.futures.decision.decision_attribution_engine import DecisionAttributionEngine

        result = DecisionAttributionEngine().evaluate(
            signal_valid=True,
            microstructure_pass=True,
            microstructure_reason="",
            risk_pass=True,
            risk_reason="",
            liquidation_pass=True,
            liquidation_reason="",
            adl_pass=True,
            adl_reason="",
            adl_pressure_side="NONE",
            policy_pass=True,
            gate_pass=True,
        )
        assert result["decision"] == "ALLOW"
        assert result["reason_code"] == "ALLOW"
        assert result["decision_layer"] == "GATE"

    def test_attribution_order_is_deterministic(self):
        """Verify attribution order: signal > microstructure > risk > liquidation > adl > policy > gate"""
        from core.futures.decision.decision_attribution_engine import DecisionAttributionEngine

        # All layers fail - should return first failure (microstructure after signal)
        result = DecisionAttributionEngine().evaluate(
            signal_valid=True,
            microstructure_pass=False,
            microstructure_reason="DEPTH_COLLAPSE",
            risk_pass=False,
            risk_reason="margin_usage",
            liquidation_pass=False,
            liquidation_reason="distance",
            adl_pass=False,
            adl_reason="SHORT",
            adl_pressure_side="SHORT",
            policy_pass=False,
            gate_pass=False,
        )
        assert result["decision"] == "REJECT"
        assert result["decision_layer"] == "MICROSTRUCTURE"
        assert result["reason_code"] == "MICROSTRUCTURE_DEPTH_COLLAPSE"


# ==================== API ENDPOINT TESTS ====================

class TestDecisionDiagnosticsEndpoint:
    """Decision diagnostics API endpoint tests"""

    def test_decision_diagnostics_returns_200(self, admin_headers):
        """Verify /api/admin/futures/decision-diagnostics returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/decision-diagnostics",
            headers=admin_headers,
            timeout=25,
        )
        assert response.status_code == 200

    def test_decision_diagnostics_contract_fields(self, admin_headers):
        """Verify decision diagnostics returns required contract fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/decision-diagnostics",
            headers=admin_headers,
            timeout=25,
        )
        assert response.status_code == 200
        payload = response.json()

        required_fields = {
            "false_allow_count",
            "false_reject_count",
            "gate_reason_distribution",
            "confidence_vs_result",
            "decision_layer_distribution",
            "updated_at",
        }
        assert required_fields.issubset(payload.keys()), f"Missing: {required_fields - set(payload.keys())}"

    def test_decision_diagnostics_false_counts_are_integers(self, admin_headers):
        """Verify false_allow_count and false_reject_count are integers"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/decision-diagnostics",
            headers=admin_headers,
            timeout=25,
        )
        assert response.status_code == 200
        payload = response.json()

        assert isinstance(payload["false_allow_count"], int)
        assert isinstance(payload["false_reject_count"], int)
        assert payload["false_allow_count"] >= 0
        assert payload["false_reject_count"] >= 0

    def test_decision_diagnostics_gate_reason_distribution_is_dict(self, admin_headers):
        """Verify gate_reason_distribution is a dictionary"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/decision-diagnostics",
            headers=admin_headers,
            timeout=25,
        )
        assert response.status_code == 200
        payload = response.json()

        assert isinstance(payload["gate_reason_distribution"], dict)

    def test_decision_diagnostics_confidence_vs_result_is_list(self, admin_headers):
        """Verify confidence_vs_result is a list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/decision-diagnostics",
            headers=admin_headers,
            timeout=25,
        )
        assert response.status_code == 200
        payload = response.json()

        assert isinstance(payload["confidence_vs_result"], list)

    def test_decision_diagnostics_decision_layer_distribution_is_dict(self, admin_headers):
        """Verify decision_layer_distribution is a dictionary"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/decision-diagnostics",
            headers=admin_headers,
            timeout=25,
        )
        assert response.status_code == 200
        payload = response.json()

        assert isinstance(payload["decision_layer_distribution"], dict)


class TestStrategyStatusEndpoint:
    """Strategy status API endpoint tests"""

    def test_strategy_status_returns_200(self, admin_headers):
        """Verify /api/admin/futures/strategy/status returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/status",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200

    def test_strategy_status_has_decision_trace_contract_records(self, admin_headers):
        """Verify strategy status includes decision_trace_contract_records"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/status",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()

        assert "decision_trace_contract_records" in payload
        assert isinstance(payload["decision_trace_contract_records"], list)

    def test_strategy_status_decision_trace_model_fields(self, admin_headers):
        """Verify decision_trace_contract_records have correct model fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/status",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()

        records = payload.get("decision_trace_contract_records", [])
        if len(records) > 0:
            record = records[0]
            required_fields = {
                "trace_id", "timestamp", "symbol", "strategy", "side",
                "signal_confidence", "regime", "microstructure_result",
                "risk_result", "liquidation_result", "adl_result",
                "final_decision", "reason_code", "decision_layer",
            }
            assert required_fields.issubset(record.keys()), f"Missing: {required_fields - set(record.keys())}"


# ==================== REGRESSION TESTS ====================

class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""

    def test_strategy_status_regression(self, admin_headers):
        """Regression: /api/admin/futures/strategy/status still works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/status",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert "strategy" in payload
        assert "metrics" in payload

    def test_risk_status_regression(self, admin_headers):
        """Regression: /api/admin/futures/risk/status still works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/risk/status",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert "portfolio_leverage" in payload
        assert "margin_usage" in payload
        assert "policy_state" in payload

    def test_microstructure_status_regression(self, admin_headers):
        """Regression: /api/admin/futures/microstructure/status still works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/status",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert "portfolio_microstructure_state" in payload
        assert "portfolio_microstructure_risk_score" in payload
        assert "execution_suitability" in payload

    def test_liquidation_protection_status_regression(self, admin_headers):
        """Regression: /api/admin/futures/liquidation-protection/status still works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/liquidation-protection/status",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200

    def test_adl_status_regression(self, admin_headers):
        """Regression: /api/admin/futures/adl/status still works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/adl/status",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200


class TestPaperDecisionFlow:
    """Paper decision flow chain tests"""

    def test_run_paper_cycle_returns_200(self, admin_headers):
        """Verify POST /api/admin/futures/strategy/run-paper-cycle returns 200"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=35,
        )
        assert response.status_code == 200

    def test_run_paper_cycle_returns_decision_trace_model(self, admin_headers):
        """Verify run-paper-cycle returns decision_trace_contract_records"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=35,
        )
        assert response.status_code == 200
        payload = response.json()

        assert "decision_trace_contract_records" in payload
        assert isinstance(payload["decision_trace_contract_records"], list)

    def test_run_paper_cycle_returns_decision_diagnostics(self, admin_headers):
        """Verify run-paper-cycle returns decision_diagnostics"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=35,
        )
        assert response.status_code == 200
        payload = response.json()

        assert "decision_diagnostics" in payload
        diagnostics = payload["decision_diagnostics"]
        assert "false_allow_count" in diagnostics
        assert "false_reject_count" in diagnostics
        assert "gate_reason_distribution" in diagnostics
