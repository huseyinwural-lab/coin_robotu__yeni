"""
Iteration 77 - Fix All Blockers + Onboarding Wizard + Risk Policy Health Score Tests

Testing features:
1. POST /api/user/signals/fix-all-blockers endpoint exists and returns summary payload
2. Fix-all runs diagnose(auto_fix) against blocked signals and returns actions_summary + updated_signal_ids
3. Regression: signal approve/reject/diagnose routes unaffected
4. Regression: existing dashboard metrics and chart still load
5. Risk policy health card returns expected data
6. Onboarding wizard API flow (risk policy update)
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")

# Test user credentials - will be created and approved
TEST_USER_EMAIL = f"TEST_iter77_user_{uuid.uuid4().hex[:8]}@test.com"
TEST_USER_PASSWORD = "TestPass123!"


@pytest.fixture(scope="module")
def admin_auth():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    return {
        "token": data["access_token"],
        "user_id": data["user"]["id"]
    }


@pytest.fixture(scope="module")
def admin_client(admin_auth):
    """Admin authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_auth['token']}"
    })
    return session


@pytest.fixture(scope="module")
def test_user_auth(admin_client):
    """Create and approve a test user, then get their auth token"""
    # Step 1: Register test user
    register_response = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if register_response.status_code not in [200, 201]:
        # User may already exist from previous test run - try login
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        if login_response.status_code == 200:
            data = login_response.json()
            return {
                "token": data["access_token"],
                "user_id": data["user"]["id"],
                "email": TEST_USER_EMAIL
            }
        pytest.fail(f"Failed to register or login test user: {register_response.text}")
    
    # Step 2: Get user approval request ID
    approvals_response = admin_client.get(f"{BASE_URL}/api/auth/admin/user-approval-requests")
    assert approvals_response.status_code == 200
    approvals = approvals_response.json()
    
    user_approval = None
    for approval in approvals:
        if approval.get("email") == TEST_USER_EMAIL:
            user_approval = approval
            break
    
    # Step 3: Approve the user if found in pending
    if user_approval:
        approve_response = admin_client.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_approval['id']}/approve"
        )
        assert approve_response.status_code in [200, 400]  # 400 if already approved
    
    # Step 4: Login with test user
    login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    assert login_response.status_code == 200, f"Test user login failed: {login_response.text}"
    
    data = login_response.json()
    return {
        "token": data["access_token"],
        "user_id": data["user"]["id"],
        "email": TEST_USER_EMAIL
    }


@pytest.fixture(scope="module")
def user_client(test_user_auth):
    """User authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {test_user_auth['token']}"
    })
    return session


class TestFixAllBlockersEndpoint:
    """Tests for POST /api/user/signals/fix-all-blockers endpoint"""

    def test_fix_all_blockers_endpoint_exists(self, user_client):
        """Verify fix-all-blockers endpoint exists and returns 200"""
        response = user_client.post(f"{BASE_URL}/api/user/signals/fix-all-blockers", params={"limit": 50})
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"

    def test_fix_all_blockers_returns_correct_payload_schema(self, user_client):
        """Verify fix-all-blockers returns expected summary payload structure"""
        response = user_client.post(f"{BASE_URL}/api/user/signals/fix-all-blockers", params={"limit": 50})
        assert response.status_code == 200
        
        data = response.json()
        # Verify all expected fields are present
        assert "scanned_count" in data, "Missing scanned_count field"
        assert "blocked_before" in data, "Missing blocked_before field"
        assert "fixed_count" in data, "Missing fixed_count field"
        assert "remaining_blocked" in data, "Missing remaining_blocked field"
        assert "updated_signal_ids" in data, "Missing updated_signal_ids field"
        assert "actions_summary" in data, "Missing actions_summary field"
        
        # Verify field types
        assert isinstance(data["scanned_count"], int)
        assert isinstance(data["blocked_before"], int)
        assert isinstance(data["fixed_count"], int)
        assert isinstance(data["remaining_blocked"], int)
        assert isinstance(data["updated_signal_ids"], list)
        assert isinstance(data["actions_summary"], dict)

    def test_fix_all_blockers_with_limit_parameter(self, user_client):
        """Verify fix-all-blockers respects limit parameter"""
        response = user_client.post(f"{BASE_URL}/api/user/signals/fix-all-blockers", params={"limit": 10})
        assert response.status_code == 200
        
        data = response.json()
        # scanned_count should be <= limit
        assert data["scanned_count"] <= 10


class TestSignalDiagnoseRegression:
    """Regression tests for signal approve/reject/diagnose routes"""

    def test_signals_list_endpoint(self, user_client):
        """Verify GET /api/user/signals still works"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 50})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_signal_diagnose_endpoint_exists(self, user_client):
        """Verify diagnose endpoint format is correct"""
        # First get signals
        signals_response = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 50})
        assert signals_response.status_code == 200
        signals = signals_response.json()
        
        if not signals:
            pytest.skip("No signals available for diagnose test")
        
        # Try diagnose on first signal
        signal = signals[0]
        response = user_client.post(f"{BASE_URL}/api/user/signal/{signal['id']}/diagnose", params={"auto_fix": False})
        
        # Should be 200 or 400 (if signal already processed) or 404 (if signal not found)
        assert response.status_code in [200, 400, 404], f"Unexpected status: {response.status_code}"


class TestDashboardRegression:
    """Regression tests for dashboard endpoints"""

    def test_user_dashboard_endpoint(self, user_client):
        """Verify GET /api/user/dashboard returns expected metrics"""
        response = user_client.get(f"{BASE_URL}/api/user/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        # Verify key dashboard fields
        assert "bot_count" in data
        assert "running_bot_count" in data
        assert "risk_policy_count" in data
        assert "current_capital" in data
        assert "available_balance" in data
        assert "open_positions_count" in data
        assert "pending_signals_count" in data

    def test_user_portfolio_endpoint(self, user_client):
        """Verify GET /api/user/portfolio works"""
        response = user_client.get(f"{BASE_URL}/api/user/portfolio")
        assert response.status_code == 200
        
        data = response.json()
        assert "current_capital" in data

    def test_user_performance_endpoint(self, user_client):
        """Verify GET /api/user/performance works"""
        response = user_client.get(f"{BASE_URL}/api/user/performance")
        assert response.status_code == 200
        
        data = response.json()
        assert "win_rate" in data


class TestRiskPoliciesForOnboardingWizard:
    """Tests for risk policies API to support onboarding wizard"""

    def test_list_risk_policies(self, user_client):
        """Verify GET /api/risk-policies returns list"""
        response = user_client.get(f"{BASE_URL}/api/risk-policies")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)

    def test_risk_policy_contains_expected_fields(self, user_client):
        """Verify risk policy object has fields for health score calculation"""
        response = user_client.get(f"{BASE_URL}/api/risk-policies")
        assert response.status_code == 200
        policies = response.json()
        
        if not policies:
            pytest.skip("No risk policies available")
        
        policy = policies[0]
        # Fields used in health score calculation
        expected_fields = [
            "position_size_pct",
            "daily_loss_cutoff_pct",
            "max_open_positions",
            "max_leverage",
            "spread_limit_bps",
            "slippage_limit_bps",
            "min_liquidity_usdt"
        ]
        for field in expected_fields:
            assert field in policy, f"Missing field: {field}"

    def test_update_risk_policy_for_onboarding(self, user_client):
        """Verify PUT /api/risk-policies/{id} works for wizard save"""
        # First get existing policies
        policies_response = user_client.get(f"{BASE_URL}/api/risk-policies")
        assert policies_response.status_code == 200
        policies = policies_response.json()
        
        if not policies:
            pytest.skip("No risk policies available")
        
        policy = policies[0]
        policy_id = policy["id"]
        
        # Update with same values (idempotent test)
        update_payload = {
            "name": policy["name"],
            "position_size_pct": float(policy.get("position_size_pct", 1.5)),
            "atr_stop_multiplier": float(policy.get("atr_stop_multiplier", 1.5)),
            "risk_reward_ratio": float(policy.get("risk_reward_ratio", 2.0)),
            "daily_loss_cutoff_pct": float(policy.get("daily_loss_cutoff_pct", 3.0)),
            "max_open_positions": int(policy.get("max_open_positions", 3)),
            "max_leverage": int(policy.get("max_leverage", 2)),
            "spread_limit_bps": int(policy.get("spread_limit_bps", 30)),
            "slippage_limit_bps": int(policy.get("slippage_limit_bps", 40)),
            "min_liquidity_usdt": int(policy.get("min_liquidity_usdt", 100000)),
        }
        
        response = user_client.put(f"{BASE_URL}/api/risk-policies/{policy_id}", json=update_payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == policy_id


class TestScannerAndSignalFlow:
    """Tests for scanner run and signal creation flow"""

    def test_scanner_run_creates_signals(self, user_client):
        """Verify scanner run creates signals for fix-all to process"""
        response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 5,
            "symbol_source": "crypto",
            "symbol_selection_mode": "bot_scope"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert "run_id" in data
        assert "mode" in data
        assert "result_count" in data

    def test_signal_mode_endpoint(self, user_client):
        """Verify GET /api/user/signal-mode works"""
        response = user_client.get(f"{BASE_URL}/api/user/signal-mode")
        assert response.status_code == 200
        
        data = response.json()
        assert "mode" in data


class TestFixAllAfterScannerRun:
    """Test fix-all-blockers after scanner creates signals"""

    def test_scanner_then_fix_all_flow(self, user_client):
        """Run scanner to create signals, then test fix-all-blockers"""
        # Step 1: Run scanner
        scanner_response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 10,
            "symbol_source": "crypto",
            "symbol_selection_mode": "bot_scope"
        })
        assert scanner_response.status_code == 200
        
        # Step 2: Check signals exist
        signals_response = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 50})
        assert signals_response.status_code == 200
        signals = signals_response.json()
        
        # Step 3: Run fix-all-blockers
        fix_response = user_client.post(f"{BASE_URL}/api/user/signals/fix-all-blockers", params={"limit": 100})
        assert fix_response.status_code == 200
        
        data = fix_response.json()
        assert "scanned_count" in data
        assert "fixed_count" in data
        assert "actions_summary" in data
        print(f"Fix-all result: scanned={data['scanned_count']}, fixed={data['fixed_count']}, actions={data['actions_summary']}")
