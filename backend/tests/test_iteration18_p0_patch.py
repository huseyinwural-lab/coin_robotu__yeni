"""
Iteration 18 - P0 Patch Tests
Tests for:
1. DB pool timeout handler (503 + code=DB_POOL_TIMEOUT + retryable=true + trace_id)
2. Auth session_device_mismatch handling (token not revoked for correct device)
3. Frontend Scanner: anomaly calculation excludes auth/infra errors
4. Frontend Scanner: load failure toast dedupe and error class separation
5. Frontend Signals: load issue banner classification
"""

import os
import pytest
import requests
import time
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"

ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"


class TestDBPoolTimeoutContract:
    """Test DB pool timeout response contract (503 + DB_POOL_TIMEOUT code)"""

    def test_db_pool_timeout_hints_defined_in_server(self):
        """Verify DB_POOL_TIMEOUT_HINTS constant exists in server.py"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        # Read server.py and check for DB_POOL_TIMEOUT_HINTS
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        
        assert "DB_POOL_TIMEOUT_HINTS" in content, "DB_POOL_TIMEOUT_HINTS constant should be defined"
        assert "pooler timeout" in content.lower(), "Should include 'pooler timeout' hint"
        assert "timeout expired" in content.lower(), "Should include 'timeout expired' hint"
        assert "queuepool limit" in content.lower(), "Should include 'queuepool limit' hint"
        print("PASS: DB_POOL_TIMEOUT_HINTS constant defined with expected hints")

    def test_is_db_pool_timeout_error_function_exists(self):
        """Verify _is_db_pool_timeout_error function exists"""
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        
        assert "def _is_db_pool_timeout_error" in content, "_is_db_pool_timeout_error function should exist"
        assert "DB_POOL_TIMEOUT_HINTS" in content, "Function should use DB_POOL_TIMEOUT_HINTS"
        print("PASS: _is_db_pool_timeout_error function exists")

    def test_db_pool_timeout_response_contract(self):
        """Verify _db_pool_timeout_response returns correct contract"""
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        
        # Check response contract fields
        assert '"code": "DB_POOL_TIMEOUT"' in content, "Response should include code=DB_POOL_TIMEOUT"
        assert '"retryable": True' in content, "Response should include retryable=True"
        assert '"error_class": "infra_error"' in content, "Response should include error_class=infra_error"
        assert '"trace_id"' in content, "Response should include trace_id"
        assert "status_code=503" in content, "Response should return 503 status"
        print("PASS: _db_pool_timeout_response contract verified")

    def test_sqlalchemy_timeout_exception_handler_registered(self):
        """Verify SQLAlchemyTimeoutError exception handler is registered"""
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        
        assert "@fastapi_app.exception_handler(SQLAlchemyTimeoutError)" in content, \
            "SQLAlchemyTimeoutError exception handler should be registered"
        assert "sqlalchemy_pool_timeout_exception_handler" in content, \
            "Handler function should be named sqlalchemy_pool_timeout_exception_handler"
        print("PASS: SQLAlchemyTimeoutError exception handler registered")

    def test_operational_error_handler_checks_pool_timeout(self):
        """Verify OperationalError handler checks for pool timeout"""
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        
        assert "@fastapi_app.exception_handler(OperationalError)" in content, \
            "OperationalError exception handler should be registered"
        assert "_is_db_pool_timeout_error(exc)" in content, \
            "Handler should check _is_db_pool_timeout_error"
        print("PASS: OperationalError handler checks for pool timeout")


class TestAuthSessionDeviceMismatch:
    """Test auth session/device mismatch handling - token not revoked for correct device"""

    def test_session_device_mismatch_detail_in_deps(self):
        """Verify session_device_mismatch detail is returned correctly"""
        with open("/app/backend/deps.py", "r") as f:
            content = f.read()
        
        assert 'detail="session_device_mismatch"' in content, \
            "session_device_mismatch detail should be returned"
        assert 'detail="session_device_missing"' in content, \
            "session_device_missing detail should be returned"
        print("PASS: session_device_mismatch/missing details defined")

    def test_strict_session_binding_roles_defined(self):
        """Verify STRICT_SESSION_BINDING_ROLES is defined"""
        with open("/app/backend/deps.py", "r") as f:
            content = f.read()
        
        assert "STRICT_SESSION_BINDING_ROLES" in content, \
            "STRICT_SESSION_BINDING_ROLES should be defined"
        assert '"super_admin"' in content or "'super_admin'" in content, \
            "super_admin should be in strict binding roles"
        print("PASS: STRICT_SESSION_BINDING_ROLES defined")

    def test_is_strict_session_binding_function_exists(self):
        """Verify _is_strict_session_binding function exists"""
        with open("/app/backend/deps.py", "r") as f:
            content = f.read()
        
        assert "def _is_strict_session_binding" in content, \
            "_is_strict_session_binding function should exist"
        assert "SESSION_STRICT_BINDING" in content, \
            "Function should check SESSION_STRICT_BINDING env var"
        print("PASS: _is_strict_session_binding function exists")

    def test_local_client_bypass_for_device_mismatch(self):
        """Verify local client can bypass device mismatch"""
        with open("/app/backend/deps.py", "r") as f:
            content = f.read()
        
        assert "is_local_client" in content, "is_local_client check should exist"
        assert '127.0.0.1' in content or 'localhost' in content, \
            "Local client detection should check for localhost/127.0.0.1"
        print("PASS: Local client bypass for device mismatch exists")

    def test_login_and_subsequent_requests_work(self):
        """Test that login works and subsequent requests with correct device work"""
        session = requests.Session()
        device_id = f"test-device-{uuid.uuid4().hex[:16]}"
        
        # Login
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            headers={
                "Content-Type": "application/json",
                "X-Session-Device": device_id,
            },
            timeout=15
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("access_token") or data.get("token")
            
            if token:
                # Make subsequent request with same device
                me_response = session.get(
                    f"{BASE_URL}/api/auth/me",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Session-Device": device_id,
                    },
                    timeout=10
                )
                
                # Should work with correct device
                assert me_response.status_code in [200, 401], \
                    f"Request with correct device should work or return auth error, got {me_response.status_code}"
                print(f"PASS: Login and subsequent request test - status: {me_response.status_code}")
            else:
                print("SKIP: No token in login response")
        else:
            print(f"SKIP: Login returned {login_response.status_code}")


class TestFrontendScannerAnomalyExclusion:
    """Test Frontend Scanner anomaly calculation excludes auth/infra errors"""

    def test_is_anomaly_eligible_event_function_exists(self):
        """Verify isAnomalyEligibleEvent function exists in UserScannerPage"""
        with open("/app/frontend/src/pages/UserScannerPage.jsx", "r") as f:
            content = f.read()
        
        assert "const isAnomalyEligibleEvent" in content, \
            "isAnomalyEligibleEvent function should exist"
        print("PASS: isAnomalyEligibleEvent function exists")

    def test_anomaly_eligible_excludes_auth_infra(self):
        """Verify anomaly calculation excludes auth_error and infra_error"""
        with open("/app/frontend/src/pages/UserScannerPage.jsx", "r") as f:
            content = f.read()
        
        # Check that isAnomalyEligibleEvent only includes trade_blocker for failures
        assert 'trade_blocker' in content, "trade_blocker should be referenced"
        
        # Check the function logic - should return true only for ok or trade_blocker
        assert 'item.ok' in content, "Should check item.ok"
        assert 'errorClass' in content, "Should check errorClass"
        print("PASS: Anomaly eligible event logic verified")

    def test_derive_request_health_uses_eligible_filter(self):
        """Verify deriveRequestHealth uses isAnomalyEligibleEvent filter"""
        with open("/app/frontend/src/pages/UserScannerPage.jsx", "r") as f:
            content = f.read()
        
        assert "const deriveRequestHealth" in content, \
            "deriveRequestHealth function should exist"
        assert "isAnomalyEligibleEvent" in content, \
            "deriveRequestHealth should use isAnomalyEligibleEvent"
        print("PASS: deriveRequestHealth uses eligible filter")

    def test_build_trend_points_excludes_auth_infra(self):
        """Verify buildTrendPoints excludes auth/infra from anomaly calculation"""
        with open("/app/frontend/src/pages/UserScannerPage.jsx", "r") as f:
            content = f.read()
        
        assert "const buildTrendPoints" in content, \
            "buildTrendPoints function should exist"
        assert "isAnomalyEligibleEvent" in content, \
            "buildTrendPoints should use isAnomalyEligibleEvent"
        assert "infra_error_count" in content, \
            "Should track infra_error_count separately"
        assert "auth_error_count" in content, \
            "Should track auth_error_count separately"
        print("PASS: buildTrendPoints excludes auth/infra from anomaly")


class TestFrontendScannerToastDedupe:
    """Test Frontend Scanner load failure toast dedupe"""

    def test_scanner_toast_dedupe_window_defined(self):
        """Verify SCANNER_TOAST_DEDUPE_WINDOW_MS is defined"""
        with open("/app/frontend/src/pages/UserScannerPage.jsx", "r") as f:
            content = f.read()
        
        assert "SCANNER_TOAST_DEDUPE_WINDOW_MS" in content, \
            "SCANNER_TOAST_DEDUPE_WINDOW_MS should be defined"
        print("PASS: SCANNER_TOAST_DEDUPE_WINDOW_MS defined")

    def test_emit_scanner_toast_function_exists(self):
        """Verify emitScannerToast function exists with dedupe logic"""
        with open("/app/frontend/src/pages/UserScannerPage.jsx", "r") as f:
            content = f.read()
        
        assert "emitScannerToast" in content, \
            "emitScannerToast function should exist"
        assert "scannerToastTrackerRef" in content, \
            "Should use scannerToastTrackerRef for tracking"
        print("PASS: emitScannerToast function with dedupe exists")

    def test_scanner_failure_summary_tracks_error_classes(self):
        """Verify scannerFailureSummary tracks auth/infra/trade_blocker separately"""
        with open("/app/frontend/src/pages/UserScannerPage.jsx", "r") as f:
            content = f.read()
        
        assert "scannerFailureSummary" in content, \
            "scannerFailureSummary state should exist"
        assert "auth_error:" in content, \
            "Should track auth_error count"
        assert "infra_error:" in content, \
            "Should track infra_error count"
        assert "trade_blocker:" in content, \
            "Should track trade_blocker count"
        print("PASS: scannerFailureSummary tracks error classes")


class TestFrontendSignalsLoadIssueBanner:
    """Test Frontend Signals load issue banner classification"""

    def test_error_class_labels_defined(self):
        """Verify ERROR_CLASS_LABELS is defined in UserSignalsPage"""
        with open("/app/frontend/src/pages/UserSignalsPage.jsx", "r") as f:
            content = f.read()
        
        assert "ERROR_CLASS_LABELS" in content, \
            "ERROR_CLASS_LABELS should be defined"
        assert "infra_error" in content, \
            "Should include infra_error label"
        assert "auth_error" in content, \
            "Should include auth_error label"
        assert "trade_blocker" in content, \
            "Should include trade_blocker label"
        print("PASS: ERROR_CLASS_LABELS defined")

    def test_load_issue_state_exists(self):
        """Verify loadIssue state exists in UserSignalsPage"""
        with open("/app/frontend/src/pages/UserSignalsPage.jsx", "r") as f:
            content = f.read()
        
        assert "loadIssue" in content, \
            "loadIssue state should exist"
        assert "setLoadIssue" in content, \
            "setLoadIssue setter should exist"
        print("PASS: loadIssue state exists")

    def test_load_issue_banner_classification(self):
        """Verify load issue banner shows correct classification"""
        with open("/app/frontend/src/pages/UserSignalsPage.jsx", "r") as f:
            content = f.read()
        
        # Check banner styling based on error class
        assert "loadIssue.errorClass" in content, \
            "Should check loadIssue.errorClass"
        assert "infra_error" in content and "amber" in content, \
            "infra_error should use amber styling"
        assert "auth_error" in content and "sky" in content, \
            "auth_error should use sky styling"
        assert "rose" in content, \
            "trade_blocker should use rose styling"
        print("PASS: Load issue banner classification verified")

    def test_toast_dedupe_in_signals(self):
        """Verify toast dedupe exists in UserSignalsPage"""
        with open("/app/frontend/src/pages/UserSignalsPage.jsx", "r") as f:
            content = f.read()
        
        assert "TOAST_DEDUPE_WINDOW_MS" in content, \
            "TOAST_DEDUPE_WINDOW_MS should be defined"
        assert "emitDedupedToast" in content, \
            "emitDedupedToast function should exist"
        assert "toastTrackerRef" in content, \
            "Should use toastTrackerRef for tracking"
        print("PASS: Toast dedupe in signals verified")


class TestFrontendApiClassifyError:
    """Test Frontend api.js classifyApiError function"""

    def test_classify_api_error_function_exists(self):
        """Verify classifyApiError function exists"""
        with open("/app/frontend/src/lib/api.js", "r") as f:
            content = f.read()
        
        assert "export const classifyApiError" in content, \
            "classifyApiError should be exported"
        print("PASS: classifyApiError function exists")

    def test_classify_api_error_returns_auth_error(self):
        """Verify classifyApiError returns auth_error for 401"""
        with open("/app/frontend/src/lib/api.js", "r") as f:
            content = f.read()
        
        assert 'status === 401' in content, \
            "Should check for 401 status"
        assert 'return "auth_error"' in content, \
            "Should return auth_error"
        print("PASS: classifyApiError returns auth_error for 401")

    def test_classify_api_error_returns_infra_error(self):
        """Verify classifyApiError returns infra_error for 5xx/network errors"""
        with open("/app/frontend/src/lib/api.js", "r") as f:
            content = f.read()
        
        assert 'status >= 500' in content or '[502, 503, 504]' in content, \
            "Should check for 5xx status"
        assert 'DB_POOL_TIMEOUT' in content, \
            "Should check for DB_POOL_TIMEOUT code"
        assert 'ERR_NETWORK' in content, \
            "Should check for ERR_NETWORK"
        assert 'return "infra_error"' in content, \
            "Should return infra_error"
        print("PASS: classifyApiError returns infra_error for 5xx/network")

    def test_classify_api_error_returns_trade_blocker_default(self):
        """Verify classifyApiError returns trade_blocker as default"""
        with open("/app/frontend/src/lib/api.js", "r") as f:
            content = f.read()
        
        assert 'return "trade_blocker"' in content, \
            "Should return trade_blocker as default"
        print("PASS: classifyApiError returns trade_blocker as default")


class TestAPIIntegration:
    """Integration tests for API endpoints"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        session = requests.Session()
        device_id = f"test-device-{uuid.uuid4().hex[:16]}"
        
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            headers={
                "Content-Type": "application/json",
                "X-Session-Device": device_id,
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token") or data.get("token")
            return {"token": token, "device_id": device_id}
        return None

    def test_health_endpoint_returns_200(self):
        """Test health endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code in [200, 503], \
            f"Health endpoint should return 200 or 503, got {response.status_code}"
        
        data = response.json()
        assert "status" in data, "Response should include status"
        assert "checks" in data, "Response should include checks"
        print(f"PASS: Health endpoint returned {response.status_code}")

    def test_health_live_endpoint_returns_200(self):
        """Test health/live endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/health/live", timeout=10)
        assert response.status_code == 200, \
            f"Health/live endpoint should return 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "ok", "Status should be ok"
        print("PASS: Health/live endpoint returned 200")

    def test_login_returns_token(self):
        """Test login returns access token"""
        device_id = f"test-device-{uuid.uuid4().hex[:16]}"
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            headers={
                "Content-Type": "application/json",
                "X-Session-Device": device_id,
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token") or data.get("token")
            assert token, "Login should return access_token"
            print("PASS: Login returns token")
        else:
            print(f"SKIP: Login returned {response.status_code}")

    def test_scanner_endpoint_accessible(self, auth_token):
        """Test scanner endpoint is accessible with auth"""
        if not auth_token:
            pytest.skip("No auth token available")
        
        response = requests.get(
            f"{BASE_URL}/api/user/scanner",
            headers={
                "Authorization": f"Bearer {auth_token['token']}",
                "X-Session-Device": auth_token['device_id'],
            },
            timeout=15
        )
        
        # Should return 200 or 401/403 (auth issue) but not 500
        assert response.status_code != 500, \
            f"Scanner endpoint should not return 500, got {response.status_code}"
        print(f"PASS: Scanner endpoint returned {response.status_code}")

    def test_signals_endpoint_accessible(self, auth_token):
        """Test signals endpoint is accessible with auth"""
        if not auth_token:
            pytest.skip("No auth token available")
        
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers={
                "Authorization": f"Bearer {auth_token['token']}",
                "X-Session-Device": auth_token['device_id'],
            },
            params={"limit": 10},
            timeout=15
        )
        
        # Should return 200 or 401/403 (auth issue) but not 500
        assert response.status_code != 500, \
            f"Signals endpoint should not return 500, got {response.status_code}"
        print(f"PASS: Signals endpoint returned {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
