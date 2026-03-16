"""Faz-6.1 + 6.2 Strategy Domain & Deterministic Kernel testleri"""

import copy
import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://quote-policy-admin.preview.emergentagent.com")


@pytest.fixture(scope="module")
def admin_token() -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        timeout=20,
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestStrategyDomainAndKernel:
    def test_strategy_definition_version_activation_and_kernel_determinism(self, admin_token):
        headers = _headers(admin_token)

        create_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=headers,
            json={
                "name": "Deterministic Momentum",
                "code": f"det-momo-{os.getpid()}",
                "description": "phase6 strategy domain test",
            },
            timeout=20,
        )
        assert create_response.status_code == 201
        strategy = create_response.json()
        strategy_id = strategy["strategy_id"]
        assert strategy["owner_type"] == "admin"
        assert strategy["status"] == "draft"

        v1_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=headers,
            json={
                "config_schema_version": "1.0",
                "config_json": {"momentum_threshold": 0.1, "base_size": 0.001, "volatility_guard": 0.5},
            },
            timeout=20,
        )
        assert v1_response.status_code == 201
        v1 = v1_response.json()
        assert v1["version_number"] == 1
        assert len(v1["version_hash"]) == 64

        v2_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=headers,
            json={
                "config_schema_version": "1.0",
                "config_json": {"momentum_threshold": 0.1, "base_size": 0.001, "volatility_guard": 0.6},
            },
            timeout=20,
        )
        assert v2_response.status_code == 201
        v2 = v2_response.json()
        assert v2["version_number"] >= 1

        activate_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{v2['version_id']}",
            headers=headers,
            timeout=20,
        )
        assert activate_response.status_code == 200
        activated = activate_response.json()
        assert activated["active_version_id"] == v2["version_id"]
        assert activated["status"] == "active"

        context = {
            "context_id": "ctx-1",
            "timestamp_utc": "2026-03-11T00:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900},
            "strategy_version_id": v2["version_id"],
            "strategy_version_hash": v2["version_hash"],
            "input_features": {"momentum": 0.12, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": "corr-1",
        }

        eval1 = requests.post(f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate", headers=headers, json=context, timeout=20)
        eval2 = requests.post(f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate", headers=headers, json=context, timeout=20)
        assert eval1.status_code == 200 and eval2.status_code == 200
        out1 = eval1.json()
        out2 = eval2.json()
        assert out1["context_hash"] == out2["context_hash"]
        assert out1["decision_hash"] == out2["decision_hash"]

        context_reordered = {
            "context_id": context["context_id"],
            "timestamp_utc": context["timestamp_utc"],
            "symbol": context["symbol"],
            "timeframe": context["timeframe"],
            "market_snapshot": {"ask": 100010, "last_price": 100000, "bid": 99990},
            "market_snapshot_hash": context["market_snapshot_hash"],
            "position_state": copy.deepcopy(context["position_state"]),
            "risk_state": copy.deepcopy(context["risk_state"]),
            "account_state_projection": copy.deepcopy(context["account_state_projection"]),
            "strategy_version_id": context["strategy_version_id"],
            "strategy_version_hash": context["strategy_version_hash"],
            "input_features": {"base_size": 0.001, "volatility": 0.2, "momentum": 0.12},
            "correlation_id": context["correlation_id"],
        }
        eval3 = requests.post(f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate", headers=headers, json=context_reordered, timeout=20)
        assert eval3.status_code == 200
        out3 = eval3.json()
        assert out3["context_hash"] == out1["context_hash"]
        assert out3["decision_hash"] == out1["decision_hash"]

        bad_context = copy.deepcopy(context)
        bad_context["strategy_version_hash"] = "wrong-hash"
        rejected = requests.post(f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate", headers=headers, json=bad_context, timeout=20)
        assert rejected.status_code == 200
        reject_payload = rejected.json()
        assert reject_payload["action"] == "REJECT"
        assert "strategy_version_hash_mismatch" in reject_payload["reason_codes"]

        invalid_payload = {"symbol": "BTCUSDT", "strategy_version_id": v2["version_id"]}
        invalid = requests.post(f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate", headers=headers, json=invalid_payload, timeout=20)
        assert invalid.status_code == 200
        invalid_result = invalid.json()
        assert invalid_result["action"] == "REJECT"
        assert "validation_error" in invalid_result["reason_codes"]
