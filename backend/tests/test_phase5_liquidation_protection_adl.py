import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.adl.adl_gate import ADLGate
from core.futures.adl.adl_pressure_aggregator import ADLPressureAggregator
from core.futures.adl.adl_protection_policy import ADLProtectionPolicy
from core.futures.adl.adl_risk_detector import ADLRiskDetector
from core.futures.liquidation_protection.cascade_detector import CascadeDetector
from core.futures.liquidation_protection.liquidation_risk_aggregator import LiquidationRiskAggregator
from core.futures.liquidation_protection.protection_policy_engine import ProtectionPolicyEngine


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def admin_token():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL tanımlı değil")
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {response.text}")
    return response.json()["access_token"]


class TestPhase51AUnitContracts:
    def test_liquidation_risk_aggregator_position_and_portfolio(self):
        aggregator = LiquidationRiskAggregator()
        position = {
            "symbol": "BTCUSDT",
            "distance_to_liquidation": 6,
            "margin_ratio": 18,
            "funding_bias_score": 42,
            "volatility_proxy": 50,
            "execution_risk": 15,
        }
        position_result = aggregator.evaluate_position(position)
        assert position_result.position_risk_score > 0
        assert position_result.risk_level in {"SAFE", "WARNING", "CRITICAL", "EMERGENCY"}

        portfolio_result = aggregator.evaluate_portfolio([position])
        assert portfolio_result.portfolio_risk_score == position_result.position_risk_score
        assert portfolio_result.dominant_risk_factor in {
            "LIQUIDATION_DISTANCE",
            "MARGIN_USAGE",
            "VOLATILITY",
            "FUNDING",
            "EXECUTION",
        }

    def test_cascade_detector_contract(self):
        detector = CascadeDetector()
        result = detector.evaluate(
            {
                "positions": [{"symbol": "BTCUSDT", "distance_to_liquidation": 8}],
                "positions_at_risk": 3,
                "volatility_spike": True,
                "spread_widening": True,
                "reject_rate": 0.35,
                "slippage_spike": True,
                "correlated_cluster_risk": False,
            }
        )
        assert result.cascade_state in {"NONE", "CASCADE_WARNING", "CASCADE_CONFIRMED"}
        assert result.cascade_score >= 0
        assert "BTCUSDT" in result.risk_symbols

    def test_adl_detector_aggregator_policy_gate_contract(self):
        detector = ADLRiskDetector()
        symbol_risk = detector.evaluate_symbol(
            {
                "exchange_adl_indicator": 0.9,
                "funding_rate": 0.0019,
                "funding_skew": 0.03,
                "open_interest_change": 4.8,
                "long_short_ratio": 1.24,
                "liquidation_volume": 12000000,
                "volatility_regime": "HIGH",
            }
        )
        assert 0 <= symbol_risk.adl_risk_score <= 1
        assert symbol_risk.adl_risk_level in {"LOW", "MEDIUM", "HIGH", "EXTREME"}
        assert symbol_risk.adl_pressure_side in {"LONG", "SHORT", "NONE"}

        aggregate = ADLPressureAggregator().aggregate(
            [
                {
                    "symbol": "BTCUSDT",
                    "adl_risk_score": symbol_risk.adl_risk_score,
                    "adl_risk_level": symbol_risk.adl_risk_level,
                    "adl_pressure_side": symbol_risk.adl_pressure_side,
                }
            ]
        )
        policy = ADLProtectionPolicy().evaluate(aggregate)
        gate_result = ADLGate().evaluate(
            adl_risk_level=aggregate["risk_level"],
            adl_pressure_side=aggregate["dominant_side"],
            portfolio_adl_risk=aggregate["portfolio_adl_risk"],
            trade_side=aggregate["dominant_side"],
            portfolio_threshold=0.01,
        )
        assert "adl_policy_action" in policy
        assert "adl_gate_pass" in gate_result

    def test_policy_engine_accepts_adl_and_cascade_state(self):
        decision = ProtectionPolicyEngine().evaluate(
            liquidation_state="WARNING",
            cascade_state="CASCADE_CONFIRMED",
            margin_state="CRITICAL",
            adl_state="EXTREME",
        )
        assert decision.policy_action in {"ALLOW", "LIMIT_NEW", "REDUCE", "FORCE_REDUCE", "FREEZE"}
        assert decision.policy_state in {"SAFE", "WARNING", "CRITICAL", "EMERGENCY"}


class TestPhase51AIntegrationAndContracts:
    def test_futures_risk_status_endpoint_contract(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/risk/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "portfolio_leverage" in data
        assert "margin_usage" in data
        assert "policy_state" in data
        assert "liquidation_risk_score" in data
        assert "adl_risk_score" in data
        assert "decision_trace" in data

    def test_futures_liquidation_protection_status_endpoint_contract(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/liquidation-protection/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "policy_state" in data
        assert "critical_positions" in data
        assert "symbol_risk_heatmap" in data
        assert "gate_rejections" in data
        assert "decision_trace" in data

    def test_futures_adl_status_endpoint_contract(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/adl/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "portfolio_adl_risk" in data
        assert "risk_level" in data
        assert "dominant_side" in data
        assert "symbols_at_risk" in data
        assert "adl_policy_state" in data
