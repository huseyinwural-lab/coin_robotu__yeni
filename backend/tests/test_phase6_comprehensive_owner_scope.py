"""
Phase 6 Task 1: Comprehensive Owner Scope Isolation Tests
Tests registration defaults, auth flows, and owner-scope isolation across all protected resources
"""

import os
import random
import string

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


def _unique_email(prefix: str = "phase6comp") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{prefix}_{suffix}@example.com"


def _register(email: str, password: str) -> dict:
    response = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 200, f"Registration failed: {response.text}"
    return response.json()


def _admin_token() -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


def _approve_user(user_id: str, admin_token: str):
    response = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, f"Approval failed: {response.text}"


def _login_user(email: str, password: str) -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, f"User login failed: {response.text}"
    return response.json()["access_token"]


# ============================================================
# TEST CLASS: Registration Defaults
# ============================================================
class TestRegistrationDefaults:
    """Verify registration creates user with correct defaults"""

    def test_register_returns_role_user(self):
        """POST /api/auth/register creates user with role=user"""
        email = _unique_email("role")
        password = "TestRole123!"
        data = _register(email, password)
        assert data["role"] == "user", f"Expected role=user, got {data['role']}"
        print(f"PASS: Registered user has role={data['role']}")

    def test_register_returns_pending_status(self):
        """POST /api/auth/register creates user with approval_status=pending"""
        email = _unique_email("status")
        password = "TestStatus123!"
        data = _register(email, password)
        assert data["approval_status"] == "pending", f"Expected pending, got {data['approval_status']}"
        print(f"PASS: Registered user has approval_status={data['approval_status']}")

    def test_register_returns_inactive(self):
        """POST /api/auth/register creates user with is_active=false"""
        email = _unique_email("active")
        password = "TestActive123!"
        data = _register(email, password)
        assert data["is_active"] is False, f"Expected is_active=False, got {data['is_active']}"
        print(f"PASS: Registered user has is_active={data['is_active']}")


# ============================================================
# TEST CLASS: Pending User Login Blocking
# ============================================================
class TestPendingUserBlocking:
    """Verify pending users are blocked from login"""

    def test_pending_user_gets_403(self):
        """POST /api/auth/login/user blocks pending users with 403"""
        email = _unique_email("blocked")
        password = "TestBlocked123!"
        _register(email, password)

        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": email, "password": password},
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        detail = response.json().get("detail", "")
        assert "onayı" in detail.lower(), f"Expected approval message, got: {detail}"
        print(f"PASS: Pending user blocked with 403, detail={detail}")


# ============================================================
# TEST CLASS: Admin Login
# ============================================================
class TestAdminLogin:
    """Verify admin login works"""

    def test_admin_login_success(self):
        """POST /api/auth/login/admin works for admin credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "admin"
        print(f"PASS: Admin login successful, role={data['user']['role']}")


# ============================================================
# TEST CLASS: Admin Approval Flow
# ============================================================
class TestAdminApprovalFlow:
    """Verify admin approval enables user login"""

    def test_approved_user_can_login(self):
        """Admin approval endpoint allows approved user login"""
        email = _unique_email("approval")
        password = "TestApproval123!"
        
        # Register
        user = _register(email, password)
        user_id = user["id"]
        
        # Verify blocked before approval
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": email, "password": password},
        )
        assert response.status_code == 403, "User should be blocked before approval"
        
        # Admin approves
        admin_token = _admin_token()
        _approve_user(user_id, admin_token)
        
        # Now user can login
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": email, "password": password},
        )
        assert response.status_code == 200, f"Approved user should be able to login: {response.text}"
        data = response.json()
        assert "access_token" in data
        print(f"PASS: Approved user can now login, email={email}")


# ============================================================
# TEST CLASS: Owner Scope Isolation - Bot Profiles
# ============================================================
class TestOwnerScopeBotProfiles:
    """Verify user B cannot access user A's bot profiles"""

    def test_user_cannot_list_other_users_bots(self):
        """User B cannot see user A's bots in list"""
        # Create and approve two users
        user_a_email = _unique_email("owner_bot_a")
        user_b_email = _unique_email("owner_bot_b")
        password = "OwnerBotTest123!"

        user_a = _register(user_a_email, password)
        user_b = _register(user_b_email, password)

        admin_token = _admin_token()
        _approve_user(user_a["id"], admin_token)
        _approve_user(user_b["id"], admin_token)

        user_a_token = _login_user(user_a_email, password)
        user_b_token = _login_user(user_b_email, password)

        # User A creates a bot
        create_response = requests.post(
            f"{BASE_URL}/api/bot-profiles",
            headers={"Authorization": f"Bearer {user_a_token}"},
            json={
                "name": "UserA Isolation Bot",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT"],
                "strategy_type": "trend_following",
                "timeframe": "15m",
                "trend_timeframe": "1h",
                "leverage": 1,
                "is_enabled": True,
            },
        )
        assert create_response.status_code == 200
        bot_id = create_response.json()["id"]

        # User B lists bots - should NOT see user A's bot
        list_response = requests.get(
            f"{BASE_URL}/api/bot-profiles",
            headers={"Authorization": f"Bearer {user_b_token}"},
        )
        assert list_response.status_code == 200
        bot_ids = [b["id"] for b in list_response.json()]
        assert bot_id not in bot_ids, "User B should not see User A's bot"
        print("PASS: User B cannot see User A's bot in list")

    def test_user_cannot_update_other_users_bot(self):
        """User B cannot update user A's bot"""
        user_a_email = _unique_email("update_a")
        user_b_email = _unique_email("update_b")
        password = "UpdateTest123!"

        user_a = _register(user_a_email, password)
        user_b = _register(user_b_email, password)

        admin_token = _admin_token()
        _approve_user(user_a["id"], admin_token)
        _approve_user(user_b["id"], admin_token)

        user_a_token = _login_user(user_a_email, password)
        user_b_token = _login_user(user_b_email, password)

        # User A creates bot
        create_response = requests.post(
            f"{BASE_URL}/api/bot-profiles",
            headers={"Authorization": f"Bearer {user_a_token}"},
            json={
                "name": "UserA Update Test Bot",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT"],
                "strategy_type": "trend_following",
                "timeframe": "15m",
                "trend_timeframe": "1h",
                "leverage": 1,
                "is_enabled": True,
            },
        )
        bot_id = create_response.json()["id"]

        # User B tries to update - should get 404
        update_response = requests.put(
            f"{BASE_URL}/api/bot-profiles/{bot_id}",
            headers={"Authorization": f"Bearer {user_b_token}"},
            json={
                "name": "Hijacked Bot",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["ETHUSDT"],
                "strategy_type": "trend_following",
                "timeframe": "15m",
                "trend_timeframe": "1h",
                "leverage": 1,
                "is_enabled": True,
            },
        )
        assert update_response.status_code == 404, f"Expected 404, got {update_response.status_code}"
        print("PASS: User B cannot update User A's bot (404)")


# ============================================================
# TEST CLASS: Owner Scope Isolation - Risk Policies
# ============================================================
class TestOwnerScopeRiskPolicies:
    """Verify user B cannot access user A's risk policies"""

    def test_user_cannot_list_other_users_policies(self):
        """User B cannot see user A's risk policies"""
        user_a_email = _unique_email("risk_a")
        user_b_email = _unique_email("risk_b")
        password = "RiskTest123!"

        user_a = _register(user_a_email, password)
        user_b = _register(user_b_email, password)

        admin_token = _admin_token()
        _approve_user(user_a["id"], admin_token)
        _approve_user(user_b["id"], admin_token)

        user_a_token = _login_user(user_a_email, password)
        user_b_token = _login_user(user_b_email, password)

        # User A creates risk policy
        create_response = requests.post(
            f"{BASE_URL}/api/risk-policies",
            headers={"Authorization": f"Bearer {user_a_token}"},
            json={
                "name": "UserA Risk Policy",
                "position_size_pct": 2.0,
                "atr_stop_multiplier": 2.0,
                "risk_reward_ratio": 2.0,
                "daily_loss_cutoff_pct": 5.0,
                "max_open_positions": 3,
                "max_leverage": 3,
            },
        )
        assert create_response.status_code == 200, f"Policy creation failed: {create_response.text}"
        policy_id = create_response.json()["id"]

        # User B lists policies - should NOT see user A's policy
        list_response = requests.get(
            f"{BASE_URL}/api/risk-policies",
            headers={"Authorization": f"Bearer {user_b_token}"},
        )
        assert list_response.status_code == 200
        policy_ids = [p["id"] for p in list_response.json()]
        assert policy_id not in policy_ids, "User B should not see User A's risk policy"
        print("PASS: User B cannot see User A's risk policy in list")

    def test_user_cannot_update_other_users_policy(self):
        """User B cannot update user A's risk policy"""
        user_a_email = _unique_email("riskup_a")
        user_b_email = _unique_email("riskup_b")
        password = "RiskUpTest123!"

        user_a = _register(user_a_email, password)
        user_b = _register(user_b_email, password)

        admin_token = _admin_token()
        _approve_user(user_a["id"], admin_token)
        _approve_user(user_b["id"], admin_token)

        user_a_token = _login_user(user_a_email, password)
        user_b_token = _login_user(user_b_email, password)

        # User A creates risk policy
        create_response = requests.post(
            f"{BASE_URL}/api/risk-policies",
            headers={"Authorization": f"Bearer {user_a_token}"},
            json={
                "name": "UserA Risk Update Policy",
                "position_size_pct": 2.0,
                "atr_stop_multiplier": 2.0,
                "risk_reward_ratio": 2.0,
                "daily_loss_cutoff_pct": 5.0,
                "max_open_positions": 3,
                "max_leverage": 3,
            },
        )
        policy_id = create_response.json()["id"]

        # User B tries to update - should get 404
        update_response = requests.put(
            f"{BASE_URL}/api/risk-policies/{policy_id}",
            headers={"Authorization": f"Bearer {user_b_token}"},
            json={
                "name": "Hijacked Policy",
                "position_size_pct": 100.0,
                "atr_stop_multiplier": 10.0,
                "risk_reward_ratio": 10.0,
                "daily_loss_cutoff_pct": 100.0,
                "max_open_positions": 100,
                "max_leverage": 125,
            },
        )
        assert update_response.status_code == 404, f"Expected 404, got {update_response.status_code}"
        print("PASS: User B cannot update User A's risk policy (404)")


# ============================================================
# TEST CLASS: Owner Scope Isolation - Pipeline Bot Start/Stop
# ============================================================
class TestOwnerScopePipeline:
    """Verify user B cannot start/stop user A's bots"""

    def test_user_cannot_start_other_users_bot(self):
        """User B cannot start user A's bot"""
        user_a_email = _unique_email("pipe_a")
        user_b_email = _unique_email("pipe_b")
        password = "PipeTest123!"

        user_a = _register(user_a_email, password)
        user_b = _register(user_b_email, password)

        admin_token = _admin_token()
        _approve_user(user_a["id"], admin_token)
        _approve_user(user_b["id"], admin_token)

        user_a_token = _login_user(user_a_email, password)
        user_b_token = _login_user(user_b_email, password)

        # User A creates bot
        create_response = requests.post(
            f"{BASE_URL}/api/bot-profiles",
            headers={"Authorization": f"Bearer {user_a_token}"},
            json={
                "name": "UserA Pipeline Bot",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT"],
                "strategy_type": "trend_following",
                "timeframe": "15m",
                "trend_timeframe": "1h",
                "leverage": 1,
                "is_enabled": True,
            },
        )
        bot_id = create_response.json()["id"]

        # User B tries to start User A's bot - should get 404
        start_response = requests.post(
            f"{BASE_URL}/api/pipeline/bots/{bot_id}/start",
            headers={"Authorization": f"Bearer {user_b_token}"},
        )
        assert start_response.status_code == 404, f"Expected 404, got {start_response.status_code}"
        print("PASS: User B cannot start User A's bot (404)")

    def test_user_cannot_stop_other_users_bot(self):
        """User B cannot stop user A's bot"""
        user_a_email = _unique_email("stop_a")
        user_b_email = _unique_email("stop_b")
        password = "StopTest123!"

        user_a = _register(user_a_email, password)
        user_b = _register(user_b_email, password)

        admin_token = _admin_token()
        _approve_user(user_a["id"], admin_token)
        _approve_user(user_b["id"], admin_token)

        user_a_token = _login_user(user_a_email, password)
        user_b_token = _login_user(user_b_email, password)

        # User A creates and starts bot
        create_response = requests.post(
            f"{BASE_URL}/api/bot-profiles",
            headers={"Authorization": f"Bearer {user_a_token}"},
            json={
                "name": "UserA Stop Test Bot",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT"],
                "strategy_type": "trend_following",
                "timeframe": "15m",
                "trend_timeframe": "1h",
                "leverage": 1,
                "is_enabled": True,
            },
        )
        bot_id = create_response.json()["id"]

        # User A starts the bot
        requests.post(
            f"{BASE_URL}/api/pipeline/bots/{bot_id}/start",
            headers={"Authorization": f"Bearer {user_a_token}"},
        )

        # User B tries to stop User A's bot - should get 404
        stop_response = requests.post(
            f"{BASE_URL}/api/pipeline/bots/{bot_id}/stop",
            headers={"Authorization": f"Bearer {user_b_token}"},
        )
        assert stop_response.status_code == 404, f"Expected 404, got {stop_response.status_code}"
        print("PASS: User B cannot stop User A's bot (404)")


# ============================================================
# TEST CLASS: Regression - Auth/Me Endpoint
# ============================================================
class TestRegressionAuthMe:
    """Verify auth/me endpoint still works"""

    def test_auth_me_returns_user_info(self):
        """GET /api/auth/me returns correct user info"""
        admin_token = _admin_token()
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Auth/me failed: {response.text}"
        data = response.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        print(f"PASS: /auth/me returns email={data['email']}, role={data['role']}")

    def test_auth_me_for_approved_user(self):
        """GET /api/auth/me works for approved user"""
        email = _unique_email("me_test")
        password = "MeTest123!"
        
        user = _register(email, password)
        admin_token = _admin_token()
        _approve_user(user["id"], admin_token)
        
        user_token = _login_user(email, password)
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200, f"Auth/me failed for user: {response.text}"
        data = response.json()
        assert data["email"] == email
        assert data["role"] == "user"
        assert data["approval_status"] == "approved"
        print("PASS: /auth/me returns correct info for approved user")


# ============================================================
# TEST CLASS: Regression - Approval Flow Endpoints
# ============================================================
class TestRegressionApprovalFlow:
    """Verify approval flow endpoints work"""

    def test_list_pending_approvals(self):
        """GET /api/auth/admin/user-approval-requests?status=pending works"""
        admin_token = _admin_token()
        response = requests.get(
            f"{BASE_URL}/api/auth/admin/user-approval-requests?status=pending",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"List pending failed: {response.text}"
        assert isinstance(response.json(), list)
        print(f"PASS: List pending approvals returns list with {len(response.json())} items")

    def test_list_approved_users(self):
        """GET /api/auth/admin/user-approval-requests?status=approved works"""
        admin_token = _admin_token()
        response = requests.get(
            f"{BASE_URL}/api/auth/admin/user-approval-requests?status=approved",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"List approved failed: {response.text}"
        assert isinstance(response.json(), list)
        print(f"PASS: List approved users returns list with {len(response.json())} items")

    def test_reject_user_flow(self):
        """POST /api/auth/admin/user-approval-requests/{id}/reject works"""
        email = _unique_email("reject")
        password = "RejectTest123!"
        
        user = _register(email, password)
        admin_token = _admin_token()
        
        response = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user['id']}/reject",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Reject failed: {response.text}"
        data = response.json()
        assert data["approval_status"] == "rejected"
        assert data["is_active"] is False
        print("PASS: Reject user sets status=rejected, is_active=False")


# ============================================================
# TEST CLASS: Owner Scope - Dashboard Isolation
# ============================================================
class TestOwnerScopeDashboard:
    """Verify dashboard shows only user's own data"""

    def test_dashboard_shows_user_specific_counts(self):
        """GET /api/dashboard/summary shows only user's bots"""
        user_a_email = _unique_email("dash_a")
        user_b_email = _unique_email("dash_b")
        password = "DashTest123!"

        user_a = _register(user_a_email, password)
        user_b = _register(user_b_email, password)

        admin_token = _admin_token()
        _approve_user(user_a["id"], admin_token)
        _approve_user(user_b["id"], admin_token)

        user_a_token = _login_user(user_a_email, password)
        user_b_token = _login_user(user_b_email, password)

        # User A creates bots
        for i in range(2):
            requests.post(
                f"{BASE_URL}/api/bot-profiles",
                headers={"Authorization": f"Bearer {user_a_token}"},
                json={
                    "name": f"UserA Dashboard Bot {i}",
                    "exchange": "binance",
                    "market_type": "spot",
                    "symbols": ["BTCUSDT"],
                    "strategy_type": "trend_following",
                    "timeframe": "15m",
                    "trend_timeframe": "1h",
                    "leverage": 1,
                    "is_enabled": True,
                },
            )

        # User B gets dashboard - should have 0 bots
        dash_b = requests.get(
            f"{BASE_URL}/api/dashboard/summary",
            headers={"Authorization": f"Bearer {user_b_token}"},
        )
        assert dash_b.status_code == 200
        data = dash_b.json()
        assert data["role"] == "user"
        assert data["metrics"]["bots"] == 0, f"User B should have 0 bots, got {data['metrics']['bots']}"
        print("PASS: User B dashboard shows 0 bots (own data only)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
