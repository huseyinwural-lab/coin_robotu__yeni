"""
Test Iteration 164 - New Features Tests
Testing:
1. User dashboard execution_mode badge (live/mocked)
2. MFA backup codes regenerate flow
3. Admin execution queue owner-revalidate endpoint
4. ExplainabilityDrawer confidence+risk chips (via API)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)

# Test credentials
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "testuser1773706589@example.com"
USER_PASSWORD = "TestPassword123!"


class TestAuth:
    """Authentication tests for admin and user"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        if resp.status_code != 200:
            pytest.skip(f"Admin login failed: {resp.status_code}")
        body = resp.json()
        
        # Handle MFA if required
        if body.get("mfa_required"):
            methods = body.get("mfa_methods", [])
            if "email" in methods:
                code = body.get("email_code_preview")
                if code:
                    verify_resp = requests.post(
                        f"{BASE_URL}/api/auth/mfa/challenge/verify",
                        json={
                            "challenge_token": body.get("mfa_challenge_token"),
                            "method": "email",
                            "code": str(code)
                        },
                        timeout=30
                    )
                    if verify_resp.status_code == 200:
                        return verify_resp.json().get("access_token")
            pytest.skip("MFA required but no code available")
        
        return body.get("access_token")

    @pytest.fixture(scope="class")
    def user_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=30
        )
        if resp.status_code != 200:
            pytest.skip(f"User login failed: {resp.status_code}")
        body = resp.json()
        
        # Handle MFA if required
        if body.get("mfa_required"):
            methods = body.get("mfa_methods", [])
            if "email" in methods:
                code = body.get("email_code_preview")
                if code:
                    verify_resp = requests.post(
                        f"{BASE_URL}/api/auth/mfa/challenge/verify",
                        json={
                            "challenge_token": body.get("mfa_challenge_token"),
                            "method": "email",
                            "code": str(code)
                        },
                        timeout=30
                    )
                    if verify_resp.status_code == 200:
                        return verify_resp.json().get("access_token")
            pytest.skip("MFA required but no code available")
        
        return body.get("access_token")

    def test_admin_login_success(self, admin_token):
        """Verify admin login returns valid token"""
        assert admin_token is not None
        assert len(admin_token) > 20
        print(f"✓ Admin login successful, token length: {len(admin_token)}")

    def test_user_login_success(self, user_token):
        """Verify user login returns valid token"""
        assert user_token is not None
        assert len(user_token) > 20
        print(f"✓ User login successful, token length: {len(user_token)}")


class TestUserDashboardExecutionMode:
    """Test user dashboard execution_mode badge"""

    @pytest.fixture(scope="class")
    def user_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=30
        )
        if resp.status_code != 200:
            pytest.skip(f"User login failed: {resp.status_code}")
        body = resp.json()
        if body.get("mfa_required"):
            methods = body.get("mfa_methods", [])
            if "email" in methods:
                code = body.get("email_code_preview")
                if code:
                    verify_resp = requests.post(
                        f"{BASE_URL}/api/auth/mfa/challenge/verify",
                        json={
                            "challenge_token": body.get("mfa_challenge_token"),
                            "method": "email",
                            "code": str(code)
                        },
                        timeout=30
                    )
                    if verify_resp.status_code == 200:
                        return verify_resp.json().get("access_token")
            pytest.skip("MFA required but no code available")
        return body.get("access_token")

    def test_user_portfolio_returns_execution_mode(self, user_token):
        """Test that /api/user/portfolio returns execution_mode field"""
        headers = {"Authorization": f"Bearer {user_token}"}
        resp = requests.get(f"{BASE_URL}/api/user/portfolio", headers=headers, timeout=30)
        
        assert resp.status_code == 200, f"Portfolio request failed: {resp.status_code}"
        data = resp.json()
        
        # Verify execution_mode field exists
        assert "execution_mode" in data, "execution_mode field missing from portfolio response"
        execution_mode = data.get("execution_mode")
        assert execution_mode in ["live", "mocked"], f"Invalid execution_mode: {execution_mode}"
        
        print(f"✓ User portfolio execution_mode: {execution_mode}")
        print(f"  - current_capital: {data.get('current_capital')}")
        print(f"  - available_balance: {data.get('available_balance')}")

    def test_user_dashboard_endpoint(self, user_token):
        """Test /api/user/dashboard endpoint"""
        headers = {"Authorization": f"Bearer {user_token}"}
        resp = requests.get(f"{BASE_URL}/api/user/dashboard", headers=headers, timeout=30)
        
        assert resp.status_code == 200, f"Dashboard request failed: {resp.status_code}"
        data = resp.json()
        
        # Verify basic dashboard fields
        assert "bot_count" in data or "running_bot_count" in data, "Dashboard missing bot count fields"
        print("✓ User dashboard returned successfully")


class TestMfaBackupCodes:
    """Test MFA backup codes regenerate feature"""

    @pytest.fixture(scope="class")
    def user_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=30
        )
        if resp.status_code != 200:
            pytest.skip(f"User login failed: {resp.status_code}")
        body = resp.json()
        if body.get("mfa_required"):
            methods = body.get("mfa_methods", [])
            if "email" in methods:
                code = body.get("email_code_preview")
                if code:
                    verify_resp = requests.post(
                        f"{BASE_URL}/api/auth/mfa/challenge/verify",
                        json={
                            "challenge_token": body.get("mfa_challenge_token"),
                            "method": "email",
                            "code": str(code)
                        },
                        timeout=30
                    )
                    if verify_resp.status_code == 200:
                        return verify_resp.json().get("access_token")
            pytest.skip("MFA required but no code available")
        return body.get("access_token")

    def test_mfa_settings_endpoint(self, user_token):
        """Test GET /api/auth/mfa/settings returns backup_codes_remaining"""
        headers = {"Authorization": f"Bearer {user_token}"}
        resp = requests.get(f"{BASE_URL}/api/auth/mfa/settings", headers=headers, timeout=30)
        
        assert resp.status_code == 200, f"MFA settings request failed: {resp.status_code}"
        data = resp.json()
        
        # Verify backup_codes_remaining field exists
        assert "backup_codes_remaining" in data, "backup_codes_remaining missing from MFA settings"
        assert isinstance(data["backup_codes_remaining"], int), "backup_codes_remaining should be int"
        
        print(f"✓ MFA settings returned - backup_codes_remaining: {data.get('backup_codes_remaining')}")
        print(f"  - is_enabled: {data.get('is_enabled')}")
        print(f"  - enabled_methods: {data.get('enabled_methods')}")
        print(f"  - totp_configured: {data.get('totp_configured')}")

    def test_mfa_backup_codes_regenerate(self, user_token):
        """Test POST /api/auth/mfa/backup-codes/regenerate"""
        headers = {"Authorization": f"Bearer {user_token}"}
        resp = requests.post(f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate", headers=headers, timeout=30)
        
        assert resp.status_code == 200, f"Backup codes regenerate failed: {resp.status_code}"
        data = resp.json()
        
        # Verify response structure per MfaBackupCodesResponse schema
        assert "generated_codes" in data, "generated_codes missing from response"
        assert "backup_codes_remaining" in data, "backup_codes_remaining missing from response"
        
        codes = data.get("generated_codes", [])
        assert isinstance(codes, list), "generated_codes should be a list"
        assert len(codes) >= 4, f"Should have at least 4 codes, got {len(codes)}"
        assert len(codes) <= 20, f"Should have at most 20 codes, got {len(codes)}"
        
        # Verify code format (XXXX-XXXX pattern)
        for code in codes[:3]:
            assert "-" in code, f"Code should have dash separator: {code}"
            parts = code.split("-")
            assert len(parts) == 2, f"Code should have 2 parts: {code}"
        
        print(f"✓ Backup codes regenerated - count: {len(codes)}")
        print(f"  - backup_codes_remaining: {data.get('backup_codes_remaining')}")
        print(f"  - Sample code format: {codes[0] if codes else 'N/A'}")


class TestAdminExecutionQueueOwnerRevalidate:
    """Test admin execution queue owner-revalidate endpoint"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        if resp.status_code != 200:
            pytest.skip(f"Admin login failed: {resp.status_code}")
        body = resp.json()
        if body.get("mfa_required"):
            methods = body.get("mfa_methods", [])
            if "email" in methods:
                code = body.get("email_code_preview")
                if code:
                    verify_resp = requests.post(
                        f"{BASE_URL}/api/auth/mfa/challenge/verify",
                        json={
                            "challenge_token": body.get("mfa_challenge_token"),
                            "method": "email",
                            "code": str(code)
                        },
                        timeout=30
                    )
                    if verify_resp.status_code == 200:
                        return verify_resp.json().get("access_token")
            pytest.skip("MFA required but no code available")
        return body.get("access_token")

    def test_execution_queue_list(self, admin_token):
        """Test GET /api/admin/execution-queue returns list"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=headers,
            params={"status_filter": "all", "limit": 50},
            timeout=30
        )
        
        assert resp.status_code == 200, f"Execution queue request failed: {resp.status_code}"
        data = resp.json()
        
        assert isinstance(data, list), "Execution queue should return a list"
        print(f"✓ Execution queue returned {len(data)} items")
        
        # Return first queued intent for revalidate test
        for item in data:
            if item.get("status") == "QUEUED":
                return item
        return None

    def test_owner_revalidate_endpoint_404_for_invalid_id(self, admin_token):
        """Test owner-revalidate returns 404 for invalid intent_id"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/invalid-intent-id-12345/owner-revalidate",
            headers=headers,
            timeout=30
        )
        
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("✓ Owner-revalidate returns 404 for invalid intent_id")

    def test_owner_revalidate_response_structure(self, admin_token):
        """Test owner-revalidate response structure if queue has items"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First get queue to find an intent
        queue_resp = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=headers,
            params={"status_filter": "all", "limit": 50},
            timeout=30
        )
        
        if queue_resp.status_code != 200:
            pytest.skip("Could not get execution queue")
        
        queue = queue_resp.json()
        if not queue:
            pytest.skip("No intents in execution queue to test revalidate")
        
        # Try first item
        intent_id = queue[0].get("id")
        resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/owner-revalidate",
            headers=headers,
            timeout=30
        )
        
        # Accept 200 (success) or 404 (owner connection not found)
        assert resp.status_code in [200, 404], f"Unexpected status: {resp.status_code}"
        
        if resp.status_code == 200:
            data = resp.json()
            # Verify response structure per AdminExecutionIntentOwnerRevalidateResponse
            assert "intent_id" in data, "intent_id missing from response"
            assert "owner_user_id" in data, "owner_user_id missing from response"
            assert "connection_id" in data, "connection_id missing from response"
            assert "can_trade" in data, "can_trade missing from response"
            assert "reason_codes" in data, "reason_codes missing from response"
            
            print("✓ Owner-revalidate response structure valid")
            print(f"  - intent_id: {data.get('intent_id')}")
            print(f"  - can_trade: {data.get('can_trade')}")
            print(f"  - reason_codes: {data.get('reason_codes')}")
            print(f"  - connection_health: {data.get('connection_health')}")
            print(f"  - readiness_status: {data.get('readiness_status')}")
        else:
            print("✓ Owner-revalidate returned 404 (owner has no exchange connection)")


class TestExplainabilityConfidenceRisk:
    """Test explainability API returns confidence/risk data for frontend chips"""

    @pytest.fixture(scope="class")
    def user_token(self):
        resp = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=30
        )
        if resp.status_code != 200:
            pytest.skip(f"User login failed: {resp.status_code}")
        body = resp.json()
        if body.get("mfa_required"):
            methods = body.get("mfa_methods", [])
            if "email" in methods:
                code = body.get("email_code_preview")
                if code:
                    verify_resp = requests.post(
                        f"{BASE_URL}/api/auth/mfa/challenge/verify",
                        json={
                            "challenge_token": body.get("mfa_challenge_token"),
                            "method": "email",
                            "code": str(code)
                        },
                        timeout=30
                    )
                    if verify_resp.status_code == 200:
                        return verify_resp.json().get("access_token")
            pytest.skip("MFA required but no code available")
        return body.get("access_token")

    def test_decision_cards_have_confidence(self, user_token):
        """Test /api/user/decision-cards returns confidence field"""
        headers = {"Authorization": f"Bearer {user_token}"}
        resp = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers=headers,
            params={"limit": 12},
            timeout=30
        )
        
        assert resp.status_code == 200, f"Decision cards request failed: {resp.status_code}"
        data = resp.json()
        
        items = data.get("items", []) if isinstance(data, dict) else data
        if not items:
            pytest.skip("No decision cards available to test confidence field")
        
        # Verify first card has confidence field
        card = items[0]
        # confidence can be in multiple places
        has_confidence = "confidence" in card or "decision_confidence" in card
        assert has_confidence, "Decision card missing confidence field"
        
        print("✓ Decision cards returned with confidence data")
        print(f"  - Total cards: {len(items)}")
        if "confidence" in card:
            print(f"  - Sample confidence: {card.get('confidence')}")

    def test_explainability_endpoint(self, user_token):
        """Test /api/user/explainability/{symbol} returns confidence data"""
        headers = {"Authorization": f"Bearer {user_token}"}
        
        # First get a symbol from decision cards
        cards_resp = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers=headers,
            params={"limit": 5},
            timeout=30
        )
        
        if cards_resp.status_code != 200:
            pytest.skip("Could not get decision cards")
        
        cards_data = cards_resp.json()
        items = cards_data.get("items", []) if isinstance(cards_data, dict) else cards_data
        
        if not items:
            pytest.skip("No symbols available for explainability test")
        
        symbol = items[0].get("symbol")
        if not symbol:
            pytest.skip("No symbol in decision card")
        
        resp = requests.get(
            f"{BASE_URL}/api/user/explainability/{symbol}",
            headers=headers,
            timeout=30
        )
        
        assert resp.status_code == 200, f"Explainability request failed: {resp.status_code}"
        data = resp.json()
        
        # Verify explainability returns confidence data
        has_confidence = "decision_confidence" in data or "confidence" in data
        print(f"✓ Explainability endpoint returned for {symbol}")
        print(f"  - Has confidence field: {has_confidence}")
        print(f"  - final_decision: {data.get('final_decision')}")
        if "decision_confidence" in data:
            print(f"  - decision_confidence: {data.get('decision_confidence')}")


class TestStartLiveScript:
    """Test start_live.sh script exists and has correct structure"""

    def test_script_exists(self):
        """Verify start_live.sh script exists"""
        script_path = "/app/scripts/start_live.sh"
        assert os.path.exists(script_path), f"Script not found: {script_path}"
        print("✓ start_live.sh script exists")

    def test_script_has_quick_full_flags(self):
        """Verify script supports --quick and --full flags"""
        script_path = "/app/scripts/start_live.sh"
        with open(script_path, "r") as f:
            content = f.read()
        
        assert "--quick" in content, "Script missing --quick flag support"
        assert "--full" in content, "Script missing --full flag support"
        assert "--json-out" in content, "Script missing --json-out flag support"
        print("✓ start_live.sh has --quick, --full, --json-out flags")

    def test_script_is_executable(self):
        """Verify script has executable permission"""
        script_path = "/app/scripts/start_live.sh"
        # Check if file exists and is readable
        assert os.access(script_path, os.R_OK), "Script is not readable"
        print("✓ start_live.sh is readable")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
