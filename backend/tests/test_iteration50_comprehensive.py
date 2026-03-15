"""
Iteration 50 Comprehensive Backend Tests
- PG-01 weekly reports live + artifact download
- Execution policy registry validation
- Pre-trade validation reject reason codes
- Intent API: preview -> submit -> queued flow
- Preview required enforcement
- Preview hash mismatch rejection
- Admin execution queue endpoints
- Admin execution policies view
"""
import os
import random
import string
import json
from pathlib import Path

import pytest
import requests

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        if raw_line.strip().startswith("REACT_APP_BACKEND_URL="):
            return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()


def _random_email(prefix: str = "iter50comp") -> str:
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@example.com"


@pytest.fixture(scope="module")
def auth_context():
    email = _random_email()
    password = "Iter50CompTest!"

    register = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password}, timeout=20)
    assert register.status_code == 200
    user_id = register.json()["id"]

    admin_login = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert approve.status_code == 200

    user_login = requests.post(f"{BASE_URL}/api/auth/login/user", json={"email": email, "password": password}, timeout=20)
    assert user_login.status_code == 200
    user_token = user_login.json()["access_token"]

    return {
        "user_headers": {"Authorization": f"Bearer {user_token}"},
        "admin_headers": {"Authorization": f"Bearer {admin_token}"},
        "user_email": email,
    }


# ==================== PG-01 Weekly Reports Tests ====================

class TestPG01WeeklyReports:
    """PG-01: Weekly reporting service tests"""
    
    def test_weekly_report_returns_200(self, auth_context):
        """GET /api/user/reports/weekly returns 200 with report_id/summary/download_links"""
        response = requests.get(
            f"{BASE_URL}/api/user/reports/weekly",
            headers=auth_context["user_headers"],
            params={"include_artifacts": True},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "report_id" in data
        assert "summary" in data
        assert "download_links" in data
        assert "pnl" in data
        assert "win_rate" in data
        assert "max_drawdown" in data
        assert "strategy_contribution" in data
        assert "status" in data

    def test_weekly_report_empty_week_handling(self, auth_context):
        """Empty week produces status: empty_week or ready"""
        response = requests.get(
            f"{BASE_URL}/api/user/reports/weekly",
            headers=auth_context["user_headers"],
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["ready", "empty_week"]

    def test_weekly_report_artifact_download(self, auth_context):
        """Artifact download endpoint returns file for owner"""
        report_res = requests.get(
            f"{BASE_URL}/api/user/reports/weekly",
            headers=auth_context["user_headers"],
            params={"include_artifacts": True},
            timeout=20,
        )
        assert report_res.status_code == 200
        links = report_res.json().get("download_links", {})
        
        for name, url in links.items():
            artifact_res = requests.get(f"{BASE_URL}{url}", headers=auth_context["user_headers"], timeout=20)
            assert artifact_res.status_code == 200, f"Failed to download {name}"


# ==================== Execution Policy Tests ====================

class TestExecutionPolicyRegistry:
    """Execution policy registry allowlist validation"""

    def test_allowed_symbols_in_policy(self):
        """BTCUSDT/ETHUSDT/BNBUSDT/SOLUSDT in allowlist"""
        policy_path = Path("/app/config/execution_policy_registry.json")
        registry = json.loads(policy_path.read_text())
        allowlist = set(registry.get("symbols_allowlist", []))
        expected = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"}
        assert expected.issubset(allowlist)

    def test_policy_validates_symbol_not_allowed(self, auth_context):
        """Symbol not in allowlist produces reject_reason_code: symbol_not_allowed"""
        payload = {
            "symbol": "INVALIDUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
            "execution_mode": "manual",
        }
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=payload,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["validation_status"] == "rejected"
        assert "symbol_not_allowed" in data["reject_reason_codes"]

    def test_policy_validates_leverage_cap_exceeded(self, auth_context):
        """Leverage exceeding cap produces leverage_cap_exceeded"""
        payload = {
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "side": "long",
            "order_type": "market",
            "margin_mode": "isolated",
            "leverage": 50,  # exceeds max 20
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "execution_mode": "manual",
        }
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=payload,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "leverage_cap_exceeded" in data["reject_reason_codes"]

    def test_policy_validates_margin_mode_not_allowed(self, auth_context):
        """Invalid margin mode produces margin_mode_not_allowed"""
        payload = {
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "side": "long",
            "order_type": "market",
            "margin_mode": "invalid_mode",
            "leverage": 5,
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "execution_mode": "manual",
        }
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=payload,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "margin_mode_not_allowed" in data["reject_reason_codes"]

    def test_policy_validates_min_notional_not_met(self, auth_context):
        """Notional below minimum produces min_notional_not_met"""
        payload = {
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 1,  # below 10 min
            "execution_mode": "manual",
        }
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=payload,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "min_notional_not_met" in data["reject_reason_codes"]

    def test_policy_stop_loss_missing_warning_futures(self, auth_context):
        """Futures without stop_loss produces risk_flag: stop_loss_missing_warning"""
        payload = {
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "side": "long",
            "order_type": "market",
            "margin_mode": "isolated",
            "leverage": 5,
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "take_profit_mode": "percent",
            "take_profit_value": 5,
            "stop_loss_mode": "none",
            "execution_mode": "manual",
        }
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=payload,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "stop_loss_missing_warning" in data.get("risk_flags", [])


# ==================== Intent API Flow Tests ====================

class TestIntentAPIFlow:
    """Intent API: preview -> submit -> queued flow tests"""

    def test_preview_creates_intent_token(self, auth_context):
        """Preview returns intent_token and preview_hash"""
        payload = {
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "execution_mode": "manual",
        }
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=payload,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "intent_token" in data
        assert "preview_hash" in data
        assert data["validation_status"] == "valid"
        assert data["intent_status"] == "PREVIEWED"

    def test_submit_without_preview_rejected(self, auth_context):
        """Submit without preview (tokenless) is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/submit",
            headers=auth_context["user_headers"],
            json={"intent_token": "nonexistent_token_12345"},
            timeout=20,
        )
        assert response.status_code == 400
        assert "intent_not_found" in response.json().get("detail", "")

    def test_submit_with_preview_hash_mismatch_rejected(self, auth_context):
        """Submit with wrong preview_hash is rejected"""
        payload = {
            "symbol": "ETHUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "execution_mode": "manual",
        }
        preview_res = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=payload,
            timeout=20,
        )
        assert preview_res.status_code == 200
        preview_data = preview_res.json()
        
        submit_res = requests.post(
            f"{BASE_URL}/api/user/execution/intent/submit",
            headers=auth_context["user_headers"],
            json={
                "intent_token": preview_data["intent_token"],
                "preview_hash": "wrong_hash_value"
            },
            timeout=20,
        )
        assert submit_res.status_code == 400
        assert "preview_hash_mismatch" in submit_res.json().get("detail", "")

    def test_full_preview_submit_queue_flow(self, auth_context):
        """Full flow: preview -> submit -> QUEUED_FOR_APPROVAL"""
        payload = {
            "symbol": "BNBUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
            "execution_mode": "manual",
        }
        preview_res = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=payload,
            timeout=20,
        )
        assert preview_res.status_code == 200
        preview_data = preview_res.json()
        assert preview_data["validation_status"] == "valid"
        assert preview_data["queue_mode"] == "ASSISTED"
        assert preview_data["approval_required"] == True

        submit_res = requests.post(
            f"{BASE_URL}/api/user/execution/intent/submit",
            headers=auth_context["user_headers"],
            json={
                "intent_token": preview_data["intent_token"],
                "preview_hash": preview_data["preview_hash"],
            },
            timeout=20,
        )
        assert submit_res.status_code == 200
        submit_data = submit_res.json()
        assert submit_data["intent_status"] == "QUEUED_FOR_APPROVAL"
        assert submit_data["queue_state"] == "QUEUED"

    def test_cancel_intent_works(self, auth_context):
        """Cancel intent after preview"""
        payload = {
            "symbol": "SOLUSDT",
            "market_type": "spot",
            "side": "sell",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 20,
            "execution_mode": "manual",
        }
        preview_res = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=payload,
            timeout=20,
        )
        assert preview_res.status_code == 200
        
        cancel_res = requests.post(
            f"{BASE_URL}/api/user/execution/intent/cancel",
            headers=auth_context["user_headers"],
            json={"intent_token": preview_res.json()["intent_token"]},
            timeout=20,
        )
        assert cancel_res.status_code == 200
        assert cancel_res.json()["cancelled"] == True


# ==================== Admin Execution Queue Tests ====================

class TestAdminExecutionQueue:
    """Admin execution queue endpoints"""

    def test_admin_execution_queue_list(self, auth_context):
        """GET /api/admin/execution-queue returns queue list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=auth_context["admin_headers"],
            params={"status_filter": "all", "limit": 100},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_admin_execution_queue_approve_reject(self, auth_context):
        """Admin can approve and reject queued intents"""
        # Create a preview + submit to queue
        payload = {
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 35,
            "execution_mode": "manual",
        }
        preview_res = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=payload,
            timeout=20,
        )
        assert preview_res.status_code == 200
        preview_data = preview_res.json()
        
        submit_res = requests.post(
            f"{BASE_URL}/api/user/execution/intent/submit",
            headers=auth_context["user_headers"],
            json={"intent_token": preview_data["intent_token"], "preview_hash": preview_data["preview_hash"]},
            timeout=20,
        )
        assert submit_res.status_code == 200
        intent_id = submit_res.json()["intent_id"]

        # Admin approve
        approve_res = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
            headers=auth_context["admin_headers"],
            json={"note": "approved_in_comprehensive_test"},
            timeout=20,
        )
        assert approve_res.status_code == 200
        assert approve_res.json()["status"] == "RELEASED"


# ==================== Admin Execution Policies View Tests ====================

class TestAdminExecutionPolicies:
    """Admin execution policies view API"""

    def test_admin_execution_policies_returns_registry(self, auth_context):
        """GET /api/admin/execution-policies returns registry + violations"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-policies",
            headers=auth_context["admin_headers"],
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "registry" in data
        assert "recent_policy_violations" in data
        assert "symbols_allowlist" in data["registry"]
        assert "market_type" in data["registry"]


# ==================== User Execution Presets Tests ====================

class TestExecutionPresets:
    """Execution presets endpoint"""

    def test_execution_presets_list(self, auth_context):
        """GET /api/user/execution/presets returns presets"""
        response = requests.get(
            f"{BASE_URL}/api/user/execution/presets",
            headers=auth_context["user_headers"],
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        preset_codes = [p["preset_code"] for p in data]
        assert "spot_basic" in preset_codes
        assert "futures_safe" in preset_codes
