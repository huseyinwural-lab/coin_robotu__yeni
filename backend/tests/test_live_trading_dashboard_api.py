import os
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    env_base = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if env_base:
        return env_base
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL bulunamadı")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


@pytest.fixture(scope="module")
def admin_headers():
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    assert token, "access_token missing"
    return {"Authorization": f"Bearer {token}"}


class TestLiveTradingSummaryWindow:
    def test_summary_window_1h_6h_24h(self, admin_headers):
        for window in ["1h", "6h", "24h"]:
            response = requests.get(
                f"{BASE_URL}/api/admin/live-trading/summary",
                params={"window": window},
                headers=admin_headers,
                timeout=30,
            )
            assert response.status_code == 200, f"summary {window} failed: {response.text}"
            payload = response.json()
            assert payload.get("window") == window
            for key in [
                "system_health",
                "trading_performance",
                "risk_engine",
                "scanner_health",
                "execution_quality",
                "learning_snapshot",
                "critical_alerts",
            ]:
                assert key in payload, f"summary missing key: {key}"

    def test_summary_contract_fields(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/summary",
            params={"window": "1h"},
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        system_health = payload.get("system_health") or {}
        for key in [
            "execution_mode",
            "kill_switch_active",
            "fallback_active",
            "queue_depth",
            "scan_latency_avg_ms",
            "decision_latency_avg_ms",
            "snapshot_age_avg_ms",
            "execution_quality_score",
        ]:
            assert key in system_health, f"system_health missing {key}"


class TestLiveTradingSectionEndpoints:
    def test_scanner_health_endpoint(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/scanner-health",
            params={"window": "6h"},
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        for key in [
            "symbols_scanned",
            "discovery_candidates",
            "qualified_candidates",
            "decisions_generated",
            "fallback_rate",
            "stale_skip_count",
            "spread_reject_count",
        ]:
            assert key in payload, f"scanner-health missing {key}"

    def test_execution_quality_endpoint(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/execution-quality",
            params={"window": "6h"},
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        for key in [
            "execution_latency_avg_ms",
            "slippage_avg_pct",
            "reject_rate",
            "partial_fill_rate",
            "precision_error_count",
            "retry_count",
            "execution_quality_score",
        ]:
            assert key in payload, f"execution-quality missing {key}"

    def test_risk_summary_endpoint(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/risk-summary",
            params={"window": "24h"},
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        for key in [
            "allow_count",
            "reduce_size_count",
            "pass_count",
            "block_count",
            "risk_reject_rate",
            "daily_loss_pct",
            "portfolio_exposure_pct",
            "symbol_exposure_top",
            "cluster_exposure_top",
        ]:
            assert key in payload, f"risk-summary missing {key}"

    def test_learning_summary_endpoint(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/learning-summary",
            params={"window": "24h"},
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        for key in [
            "strategy_top_win_rate",
            "strategy_top_loss_rate",
            "false_allow_rate",
            "false_reject_rate",
            "quality_score_by_strategy",
            "new_recommendations_count",
        ]:
            assert key in payload, f"learning-summary missing {key}"
