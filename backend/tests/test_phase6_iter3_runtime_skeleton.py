"""Faz-6.3 Runtime Skeleton testleri"""

import os
import time

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-platform-s3.preview.emergentagent.com")


@pytest.fixture(scope="module")
def admin_headers() -> dict:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        timeout=20,
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _create_strategy_with_version(headers: dict) -> tuple[str, dict]:
    create = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies",
        headers=headers,
        json={"name": "Runtime Skeleton", "code": f"runtime-{int(time.time())}", "description": "runtime test"},
        timeout=20,
    )
    assert create.status_code == 201
    strategy_id = create.json()["strategy_id"]

    version = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
        headers=headers,
        json={"config_schema_version": "1.0", "config_json": {"momentum_threshold": 0.1, "base_size": 0.001}},
        timeout=20,
    )
    assert version.status_code == 201
    return strategy_id, version.json()


def _build_context(version: dict, momentum: float, correlation_id: str) -> dict:
    return {
        "context_id": f"ctx-{correlation_id}",
        "timestamp_utc": "2026-03-11T00:00:00Z",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
        "market_snapshot_hash": f"snap-{correlation_id}",
        "position_state": {"side": "flat", "qty": 0},
        "risk_state": {"blocked": False},
        "account_state_projection": {"equity": 1000, "free_margin": 900},
        "strategy_version_id": version["version_id"],
        "strategy_version_hash": version["version_hash"],
        "input_features": {"momentum": momentum, "volatility": 0.2, "base_size": 0.001},
        "correlation_id": correlation_id,
    }


class TestRuntimeSkeleton:
    def test_dispatch_worker_and_trace_storage(self, admin_headers):
        strategy_id, version = _create_strategy_with_version(admin_headers)

        dispatch = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.12, "corr-runtime-1")},
            timeout=30,
        )
        assert dispatch.status_code == 200
        payload = dispatch.json()
        assert payload["decision_result"]["action"] == "BUY"
        assert payload["execution_intent"] is not None
        assert len(payload["emitted_events"]) >= 3
        assert all(item.get("payload_hash") for item in payload["emitted_events"])

        worker = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/worker/run-once",
            headers=admin_headers,
            timeout=20,
        )
        assert worker.status_code == 200
        assert worker.json()["status"] in {"processed", "duplicate_skipped", "no_event"}

        intents = requests.get(f"{BASE_URL}/api/strategy-domain/admin/runtime/intents", headers=admin_headers, timeout=20)
        assert intents.status_code == 200
        assert len(intents.json()) >= 1

        hot = requests.get(f"{BASE_URL}/api/strategy-domain/admin/runtime/hot-traces", headers=admin_headers, timeout=20)
        cold = requests.get(f"{BASE_URL}/api/strategy-domain/admin/runtime/cold-traces", headers=admin_headers, timeout=20)
        assert hot.status_code == 200
        assert cold.status_code == 200
        assert len(hot.json()) >= 1

    def test_reject_hold_paths(self, admin_headers):
        strategy_id, version = _create_strategy_with_version(admin_headers)

        hold_dispatch = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.0, "corr-runtime-2")},
            timeout=30,
        )
        assert hold_dispatch.status_code == 200
        hold_payload = hold_dispatch.json()
        assert hold_payload["decision_result"]["action"] == "HOLD"
        assert hold_payload["execution_intent"] is None

        reject_context = _build_context(version, 0.2, "corr-runtime-3")
        reject_context["risk_state"] = {"blocked": True}
        reject_dispatch = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": reject_context},
            timeout=30,
        )
        assert reject_dispatch.status_code == 200
        reject_payload = reject_dispatch.json()
        assert reject_payload["decision_result"]["action"] == "REJECT"
        assert reject_payload["execution_intent"] is None
