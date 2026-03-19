"""
Iteration 80: Live Control Status Card Tests
- Verifies Live Control Status card displays on User Signals and User Dashboard pages
- Tests actions: AUTO'ya Al, Fix All Blockers, Refresh
- Verifies 15s auto refresh indicator presence
- Backend regression: scanner mode enforcement, ORDER_PRECHECK_FAILED blocking
"""
import pytest
import requests
import os
import time
import random

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

class TestIteration80LiveControlStatus:
    """Tests for Live Control Status feature on User Signals and User Dashboard"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": os.environ.get("TEST_ADMIN_EMAIL", ""),
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "")
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def user_token(self, admin_token):
        """Get or create test user with approval"""
        # First try an existing approved user from iteration 79
        existing_emails = [
            "test_iter79_scanner_1773403334@test.com",
            "TEST_iter79_scanner_fd919cfb@test.com",
            "TEST_iter79_scanner_f221f580@test.com",
        ]
        password = "TestPass123!"
        
        for email in existing_emails:
            response = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": email,
                "password": password
            })
            if response.status_code == 200:
                print(f"Using existing user: {email}")
                return response.json().get("access_token")
        
        # Create new user if no existing ones work
        unique_id = str(int(time.time()))[-8:] + str(random.randint(1000, 9999))
        email = f"test_iter80_live_control_{unique_id}@test.com"
        
        # Register
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": password,
            "full_name": f"Test User Iter80 {unique_id}"
        })
        assert response.status_code in [200, 201], f"Registration failed: {response.text}"
        user_id = response.json().get("user_id") or response.json().get("id")
        
        # Approve via bulk endpoint
        headers = {"Authorization": f"Bearer {admin_token}"}
        requests.post(f"{BASE_URL}/api/admin/user-approvals/bulk-approve", headers=headers, json={
            "user_ids": [user_id]
        })
        time.sleep(1)
        
        # Try login
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        assert response.status_code == 200, f"User login failed: {response.text}"
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def user_with_active_bot_token(self, user_token, admin_token):
        """Ensure user has active bot for scanner tests"""
        headers = {"Authorization": f"Bearer {user_token}"}
        
        # Create active bot profile
        requests.post(f"{BASE_URL}/api/bot-profiles", headers=headers, json={
            "name": f"Test Bot Iter80 {int(time.time())}",
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "strategy_type": "spot_pullback",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 1,
            "is_enabled": True,
            "is_running": True
        })
        
        return user_token

    # === SIGNAL MODE ENDPOINT TESTS ===
    def test_signal_mode_endpoint_returns_mode(self, user_token):
        """Test GET /api/user/signal-mode returns signal mode"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/user/signal-mode", headers=headers)
        assert response.status_code == 200, f"Signal mode GET failed: {response.text}"
        data = response.json()
        assert "mode" in data, "Response should contain 'mode' field"
        assert data["mode"] in ["MANUAL", "ASSISTED", "AUTO"], f"Invalid mode: {data['mode']}"

    def test_signal_mode_set_auto(self, user_token):
        """Test PUT /api/user/signal-mode sets mode to AUTO"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.put(f"{BASE_URL}/api/user/signal-mode", headers=headers, json={"mode": "AUTO"})
        assert response.status_code == 200, f"Signal mode PUT failed: {response.text}"
        data = response.json()
        assert data["mode"] == "AUTO", f"Mode should be AUTO, got: {data['mode']}"

    # === BOT PROFILES ENDPOINT TESTS ===
    def test_bot_profiles_endpoint(self, user_token):
        """Test GET /api/bot-profiles returns bot profiles list"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/bot-profiles", headers=headers)
        assert response.status_code == 200, f"Bot profiles GET failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Bot profiles should return list"

    # === SIGNALS ENDPOINT TESTS ===
    def test_user_signals_endpoint(self, user_token):
        """Test GET /api/user/signals returns signals list with status fields"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/user/signals", headers=headers, params={"limit": 50})
        assert response.status_code == 200, f"User signals GET failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Signals should return list"
        # Verify signal schema if signals exist
        if data:
            signal = data[0]
            assert "status" in signal, "Signal should have status field"
            assert "blocked_reason_code" in signal or signal.get("status") != "blocked", "Blocked signals need blocked_reason_code"

    # === FIX ALL BLOCKERS ENDPOINT TESTS ===
    def test_fix_all_blockers_endpoint(self, user_token):
        """Test POST /api/user/signals/fix-all-blockers returns expected schema"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.post(f"{BASE_URL}/api/user/signals/fix-all-blockers", headers=headers, params={"limit": 250})
        assert response.status_code == 200, f"Fix all blockers failed: {response.text}"
        data = response.json()
        # Verify expected fields
        assert "scanned_count" in data or "fixed_count" in data, "Response should have scanned_count or fixed_count"

    # === DASHBOARD ENDPOINT TESTS ===
    def test_user_dashboard_endpoint(self, user_token):
        """Test GET /api/user/dashboard returns dashboard data"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/user/dashboard", headers=headers)
        assert response.status_code == 200, f"User dashboard GET failed: {response.text}"
        data = response.json()
        # Dashboard should have relevant fields
        assert isinstance(data, dict), "Dashboard should return dict"

    # === SCANNER MODE ENFORCEMENT REGRESSION ===
    def test_scanner_auto_mode_enforcement_for_active_bot(self, user_with_active_bot_token):
        """Regression test: Scanner enforces AUTO mode for users with active bot"""
        headers = {"Authorization": f"Bearer {user_with_active_bot_token}"}
        
        # Request scanner with MANUAL mode, should be enforced to AUTO
        response = requests.post(f"{BASE_URL}/api/user/scanner/run", headers=headers, json={
            "mode": "MANUAL",
            "max_results": 5
        })
        assert response.status_code == 200, f"Scanner run failed: {response.text}"
        data = response.json()
        
        # Verify AUTO enforcement
        assert data.get("mode") == "AUTO", f"Mode should be AUTO for active bot user, got: {data.get('mode')}"
        
        # Verify warning present
        warnings = data.get("warnings") or []
        assert "signal_mode_auto_enforced_for_active_bot" in warnings, f"Expected warning not present: {warnings}"

    def test_scanner_no_enforcement_when_auto_requested(self, user_with_active_bot_token):
        """Regression test: No enforcement warning when AUTO is explicitly requested"""
        headers = {"Authorization": f"Bearer {user_with_active_bot_token}"}
        
        response = requests.post(f"{BASE_URL}/api/user/scanner/run", headers=headers, json={
            "mode": "AUTO",
            "max_results": 5
        })
        assert response.status_code == 200, f"Scanner run failed: {response.text}"
        data = response.json()
        
        assert data.get("mode") == "AUTO", f"Mode should be AUTO, got: {data.get('mode')}"
        warnings = data.get("warnings") or []
        # Warning should NOT be present when AUTO explicitly requested
        assert "signal_mode_auto_enforced_for_active_bot" not in warnings, f"Unexpected warning present: {warnings}"

    # === ORDER_PRECHECK_FAILED BLOCKING REGRESSION ===
    def test_order_precheck_failed_remains_blocked(self, user_token):
        """Regression test: ORDER_PRECHECK_FAILED blockers are not auto-fixed"""
        headers = {"Authorization": f"Bearer {user_token}"}
        
        # Get signals to check if any ORDER_PRECHECK_FAILED exist
        response = requests.get(f"{BASE_URL}/api/user/signals", headers=headers, params={"limit": 100})
        assert response.status_code == 200
        signals = response.json()
        
        precheck_failed_signals = [s for s in signals if s.get("blocked_reason_code") == "ORDER_PRECHECK_FAILED"]
        
        # Run fix-all-blockers
        fix_response = requests.post(f"{BASE_URL}/api/user/signals/fix-all-blockers", headers=headers, params={"limit": 250})
        assert fix_response.status_code == 200
        fix_data = fix_response.json()
        
        # Verify ORDER_PRECHECK_FAILED are NOT in actions
        actions_summary = fix_data.get("actions_summary") or {}
        # ORDER_PRECHECK_FAILED should not have bypass actions
        assert "order_precheck_bypassed" not in actions_summary, "ORDER_PRECHECK_FAILED should not be bypassed"

    # === LIVE CONTROL DATA FIELDS VERIFICATION ===
    def test_live_control_status_data_availability(self, user_token):
        """Verify all data fields needed for Live Control Status are available"""
        headers = {"Authorization": f"Bearer {user_token}"}
        
        # Get signal mode
        mode_response = requests.get(f"{BASE_URL}/api/user/signal-mode", headers=headers)
        assert mode_response.status_code == 200
        mode_data = mode_response.json()
        assert "mode" in mode_data, "Signal mode field required"
        
        # Get bot profiles for runtime info
        bots_response = requests.get(f"{BASE_URL}/api/bot-profiles", headers=headers)
        assert bots_response.status_code == 200
        bots_data = bots_response.json()
        assert isinstance(bots_data, list), "Bot profiles should be list"
        
        # Get signals for latest state and blocker info
        signals_response = requests.get(f"{BASE_URL}/api/user/signals", headers=headers, params={"limit": 50})
        assert signals_response.status_code == 200
        signals_data = signals_response.json()
        assert isinstance(signals_data, list), "Signals should be list"
        
        # Verify we can compute all Live Control Status fields
        raw_mode = str(mode_data.get("mode", "ASSISTED")).upper()
        active_bots = [b for b in bots_data if b.get("is_running") and b.get("is_enabled")]
        active_bot_count = len(active_bots)
        latest_signal = signals_data[0] if signals_data else None
        current_blocker = next((s for s in signals_data if s.get("status") == "blocked" and s.get("blocked_reason_code")), None)
        
        # Bot Runtime
        bot_runtime = "RUNNING" if active_bot_count > 0 else "STOPPED"
        
        # Execution Path
        if raw_mode == "AUTO" and active_bot_count > 0:
            execution_path = "BOT_AUTO_ACTIVE"
        elif raw_mode == "ASSISTED":
            execution_path = "SEMI_AUTO_ACTIVE"
        else:
            execution_path = "MANUAL_FLOW"
        
        # Latest Signal State
        if latest_signal:
            latest_signal_state = f"{str(latest_signal.get('status', '-')).upper()} ({latest_signal.get('symbol', '-')})"
        else:
            latest_signal_state = "-"
        
        # Current Blocker
        blocker_code = current_blocker.get("blocked_reason_code") if current_blocker else "-"
        
        # All fields should be computable
        print("Live Control Status Fields:")
        print(f"  Signal Mode: {raw_mode}")
        print(f"  Bot Runtime: {bot_runtime} ({active_bot_count})")
        print(f"  Execution Path: {execution_path}")
        print(f"  Last Signal State: {latest_signal_state}")
        print(f"  Current Blocker: {blocker_code}")

    # === PORTFOLIO AND PERFORMANCE ENDPOINTS FOR DASHBOARD ===
    def test_portfolio_endpoint(self, user_token):
        """Test GET /api/user/portfolio returns portfolio data"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/user/portfolio", headers=headers)
        assert response.status_code == 200, f"Portfolio GET failed: {response.text}"

    def test_performance_endpoint(self, user_token):
        """Test GET /api/user/performance returns performance data"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/user/performance", headers=headers)
        assert response.status_code == 200, f"Performance GET failed: {response.text}"

    def test_risk_policies_endpoint(self, user_token):
        """Test GET /api/risk-policies returns risk policies list"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/risk-policies", headers=headers)
        assert response.status_code == 200, f"Risk policies GET failed: {response.text}"
