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


class TestLiveTradingDailyReport:
    def test_daily_report_contract(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/daily-report",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"daily-report failed: {response.text}"
        payload = response.json()

        required_fields = [
            "date",
            "execution_mode",
            "trades_count",
            "win_rate",
            "pnl_usdt",
            "max_drawdown_pct",
            "open_positions",
            "execution_quality_score",
            "fallback_rate",
            "scan_latency_avg_ms",
            "decision_latency_avg_ms",
            "risk_reject_rate",
            "allow_count",
            "reduce_size_count",
            "pass_count",
            "block_count",
            "top_3_strategy_stats",
            "top_3_symbol_stats",
            "critical_errors",
        ]
        for field in required_fields:
            assert field in payload, f"daily-report missing field: {field}"

    def test_daily_report_export_json(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/daily-report/export",
            params={"format": "json"},
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"daily-report export json failed: {response.text}"
        payload = response.json()
        assert "date" in payload
        assert "top_3_strategy_stats" in payload
        assert "top_3_symbol_stats" in payload

    def test_daily_report_export_csv(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/daily-report/export",
            params={"format": "csv"},
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"daily-report export csv failed: {response.text}"
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type

        text = response.text
        assert "date,execution_mode,trades_count,win_rate,pnl_usdt" in text
        assert "top_3_strategy_stats" in text
        assert "top_3_symbol_stats" in text
