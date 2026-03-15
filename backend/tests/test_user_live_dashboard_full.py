"""
Comprehensive User Live Dashboard Tests
Tests user-scoped live trading dashboard endpoints with all validation checks
"""

import os
import uuid
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

# Forbidden admin-scope tokens that should NOT appear in user responses
FORBIDDEN_ADMIN_TOKENS = [
    "queue_depth",
    "fallback_state",
    "global",
    "cluster_exposure",
    "admin_risk_config",
    "kill_switch",
    "raw_diagnostics",
    "risk_veto_distribution",
]


def _admin_headers() -> dict:
    """Get admin authorization headers"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    assert token, "admin access_token missing"
    return {"Authorization": f"Bearer {token}"}


def _register_approve_login(prefix: str, admin_headers: dict) -> dict:
    """Register a new user, approve them, and return their auth headers"""
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestUserPass123!"

    # Register
    register_resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert register_resp.status_code == 200, f"Register failed: {register_resp.text}"
    user_id = register_resp.json()["id"]

    # Approve
    approve_resp = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    assert approve_resp.status_code == 200, f"Approve failed: {approve_resp.text}"

    # Login
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]

    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "email": email,
        "user_id": user_id,
    }


def _create_bot(headers: dict, bot_name: str, symbol: str):
    """Create a bot profile for a user"""
    response = requests.post(
        f"{BASE_URL}/api/bot-profiles",
        headers=headers,
        json={
            "name": bot_name,
            "exchange": "binance",
            "market_type": "spot",
            "symbols": [symbol],
            "strategy_type": "spot_pullback_v1",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 1,
            "is_enabled": True,
        },
        timeout=20,
    )
    assert response.status_code == 200, f"Bot creation failed: {response.text}"
    return response.json()


@pytest.fixture(scope="module")
def test_context():
    """Setup test context with two users for scope testing"""
    admin_headers = _admin_headers()
    user_a = _register_approve_login("full_a", admin_headers)
    user_b = _register_approve_login("full_b", admin_headers)

    _create_bot(user_a["headers"], "full-bot-a", "FULLAUSDT")
    _create_bot(user_b["headers"], "full-bot-b", "FULLBUSDT")

    return {
        "admin_headers": admin_headers,
        "user_a_headers": user_a["headers"],
        "user_b_headers": user_b["headers"],
        "user_a_email": user_a["email"],
        "user_b_email": user_b["email"],
    }


# --- Endpoint Status Tests ---

class TestEndpointStatus:
    """Test that all user/live endpoints return 200 status"""

    @pytest.mark.parametrize("endpoint", [
        "/api/user/live/summary",
        "/api/user/live/positions",
        "/api/user/live/performance",
        "/api/user/live/risk",
        "/api/user/live/execution-quality",
        "/api/user/live/strategies",
        "/api/user/live/trades",
        "/api/user/live/daily-report",
    ])
    def test_endpoint_returns_200(self, test_context, endpoint):
        """Each endpoint should return 200 for authenticated user"""
        response = requests.get(
            f"{BASE_URL}{endpoint}",
            params={"window": "24h"},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200, f"{endpoint} failed: {response.text}"

    @pytest.mark.parametrize("format_type", ["json", "csv"])
    def test_export_endpoint_returns_200(self, test_context, format_type):
        """Export endpoint should return 200 for both formats"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/daily-report/export",
            params={"format": format_type, "window": "24h"},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200, f"Export {format_type} failed: {response.text}"


# --- Admin Scope Isolation Tests ---

class TestAdminScopeIsolation:
    """Test that admin-scope fields don't leak into user responses"""

    @pytest.mark.parametrize("endpoint", [
        "/api/user/live/summary",
        "/api/user/live/positions",
        "/api/user/live/performance",
        "/api/user/live/risk",
        "/api/user/live/execution-quality",
        "/api/user/live/strategies",
        "/api/user/live/trades",
        "/api/user/live/daily-report",
    ])
    def test_no_admin_fields_in_response(self, test_context, endpoint):
        """Verify no admin-scope fields appear in user responses"""
        response = requests.get(
            f"{BASE_URL}{endpoint}",
            params={"window": "24h"},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200
        payload_lower = str(response.json()).lower()

        for token in FORBIDDEN_ADMIN_TOKENS:
            assert token not in payload_lower, f"Admin token '{token}' leaked in {endpoint}"

    def test_export_json_no_admin_fields(self, test_context):
        """Verify JSON export doesn't contain admin-scope fields"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/daily-report/export",
            params={"format": "json", "window": "24h"},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200
        payload_lower = str(response.json()).lower()

        for token in FORBIDDEN_ADMIN_TOKENS:
            assert token not in payload_lower, f"Admin token '{token}' leaked in JSON export"

    def test_export_csv_no_admin_fields(self, test_context):
        """Verify CSV export doesn't contain admin-scope fields"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/daily-report/export",
            params={"format": "csv", "window": "24h"},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200
        content_lower = response.text.lower()

        for token in FORBIDDEN_ADMIN_TOKENS:
            assert token not in content_lower, f"Admin token '{token}' leaked in CSV export"


# --- User Scope Isolation Tests ---

class TestUserScopeIsolation:
    """Test that users can only see their own data"""

    def test_user_a_cannot_see_user_b_bot(self, test_context):
        """User A should not see User B's bot in summary"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/summary",
            params={"window": "1h"},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200
        payload_text = str(response.json())

        assert "full-bot-a" in payload_text, "User A should see their own bot"
        assert "full-bot-b" not in payload_text, "User A should NOT see User B's bot"

    def test_user_b_cannot_see_user_a_bot(self, test_context):
        """User B should not see User A's bot in summary"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/summary",
            params={"window": "1h"},
            headers=test_context["user_b_headers"],
            timeout=30,
        )
        assert response.status_code == 200
        payload_text = str(response.json())

        assert "full-bot-b" in payload_text, "User B should see their own bot"
        assert "full-bot-a" not in payload_text, "User B should NOT see User A's bot"

    def test_user_a_cannot_see_user_b_symbol_in_trades(self, test_context):
        """User A's trades should not contain User B's symbol"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/trades",
            params={"window": "24h"},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200
        payload_text = str(response.json())
        assert "FULLBUSDT" not in payload_text

    def test_export_contains_only_user_scope_data(self, test_context):
        """Export should only contain user's own data, not other users"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/daily-report/export",
            params={"format": "json", "window": "24h"},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200
        payload_text = str(response.json())

        # User A's export should not contain User B's email
        assert test_context["user_b_email"] not in payload_text


# --- Response Contract Tests ---

class TestResponseContract:
    """Test that responses have the expected structure"""

    def test_summary_has_required_keys(self, test_context):
        """Summary endpoint should have all required top-level keys"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/summary",
            params={"window": "1h"},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()

        required_keys = [
            "window", "generated_at", "bots", "open_positions",
            "performance", "risk", "execution", "strategies", "trades", "alerts"
        ]
        for key in required_keys:
            assert key in payload, f"Missing required key: {key}"

    def test_daily_report_has_required_keys(self, test_context):
        """Daily report should have all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/daily-report",
            params={"window": "24h"},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()

        required_keys = [
            "report_id", "date", "window", "trades_today", "win_rate",
            "pnl_today", "risk_per_trade_used", "own_portfolio_exposure",
            "own_execution_quality_score", "top_strategies", "recent_trades", "alerts"
        ]
        for key in required_keys:
            assert key in payload, f"Missing required key: {key}"

    def test_csv_export_has_correct_headers(self, test_context):
        """CSV export should have the correct column headers"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/daily-report/export",
            params={"format": "csv", "window": "24h"},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

        headers_line = response.text.split("\n")[0]
        expected_headers = [
            "date", "window", "trades_today", "win_rate", "pnl_today"
        ]
        for header in expected_headers:
            assert header in headers_line, f"Missing CSV header: {header}"


# --- Window Parameter Tests ---

class TestWindowParameter:
    """Test window parameter handling"""

    @pytest.mark.parametrize("window", ["1h", "6h", "24h"])
    def test_valid_window_values(self, test_context, window):
        """All valid window values should work"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/summary",
            params={"window": window},
            headers=test_context["user_a_headers"],
            timeout=30,
        )
        assert response.status_code == 200
        assert response.json()["window"] == window


# --- Admin Access Denied Tests ---

class TestAdminAccessDenied:
    """Test that admin users cannot access user-only endpoints"""

    def test_admin_cannot_access_user_live_endpoints(self, test_context):
        """Admin should get 403 when accessing user live endpoints"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/summary",
            params={"window": "1h"},
            headers=test_context["admin_headers"],
            timeout=30,
        )
        assert response.status_code == 403, "Admin should not access user-only endpoints"
