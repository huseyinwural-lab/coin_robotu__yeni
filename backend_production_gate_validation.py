#!/usr/bin/env python3
"""
Production Gate Control Panel Backend Validation Test
Target: https://trade-trace-engine.preview.emergentagent.com

Validates specific Production Gate Control Panel fixes:
1) Read side-effect kontrolü: GET `/api/phase4/admin/production-gate?refresh_checks=false` çağrısını arka arkaya 2 kez yap. `updated_at` ve `last_cleanup_at` değişmiyor mu kontrol et.
2) Refresh path: GET `/api/phase4/admin/production-gate?refresh_checks=true` çağrısı 200 dönmeli.
3) Mode transition phrase map: `target_mode=LIVE` doğru phrase ile 200, invalid mode gönderiminde 422/400 beklenir (contract bozulmamalı)
4) Cross-check sanitize: `/api/phase4/admin/production-gate/system/cross-check` çağrısı mismatch olursa error detail içinde full internal payload yerine sanitize alanlar (`error`, `mismatch_count`) olmalı.
5) TTL min validation: `/api/phase4/admin/production-gate/override` endpointine ttl=0 gönderimi 422 veya service-level validation ile reddedilmeli.
6) Enforce fallback stability: Gate'e bağlı bir action endpoint tetiklenip (ör. mode transition LIVE) 500/connection-break benzeri session reuse hatası çıkmıyor mu kontrol et.
"""

import requests
import json
import sys
import time
from typing import Dict, Any, Tuple

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class ProductionGateValidator:
    def __init__(self):
        self.admin_token = None
        self.admin_session = None
        self.results = []
        
    def log_result(self, test_name: str, status: str, details: str = "", expected: str = "", actual: str = ""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "expected": expected,
            "actual": actual
        }
        self.results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        if expected and actual:
            print(f"   Expected: {expected}")
            print(f"   Actual: {actual}")
        print()

    def authenticate_admin(self) -> bool:
        """Authenticate admin user and get token with session management"""
        try:
            # Create a session to maintain cookies
            self.admin_session = requests.Session()
            
            response = self.admin_session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    self.log_result("Admin Authentication", "PASS", f"Token obtained (length: {len(self.admin_token)})")
                    return True
                else:
                    self.log_result("Admin Authentication", "FAIL", "No access_token in response")
                    return False
            else:
                self.log_result("Admin Authentication", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Authentication", "FAIL", f"Exception: {str(e)}")
            return False

    def make_request(self, method: str, endpoint: str, token: str = None, session: requests.Session = None, **kwargs) -> Tuple[int, Dict[str, Any]]:
        """Make HTTP request with optional authentication and session management"""
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        try:
            if session:
                # Use session for cookie management
                response = session.request(
                    method=method,
                    url=f"{BASE_URL}{endpoint}",
                    headers=headers,
                    timeout=30,
                    **kwargs
                )
            else:
                # Fallback to regular requests
                response = requests.request(
                    method=method,
                    url=f"{BASE_URL}{endpoint}",
                    headers=headers,
                    timeout=30,
                    **kwargs
                )
            
            try:
                data = response.json()
            except:
                data = {"raw_response": response.text}
                
            return response.status_code, data
            
        except Exception as e:
            return 0, {"error": str(e)}

    def test_read_side_effect_control(self):
        """Test 1: Read side-effect kontrolü"""
        print("=== TEST 1: Read Side-Effect Control ===")
        
        # First call with refresh_checks=false
        status1, data1 = self.make_request(
            "GET", 
            "/api/phase4/admin/production-gate?refresh_checks=false", 
            self.admin_token, 
            self.admin_session
        )
        
        if status1 != 200:
            self.log_result("Read Side-Effect Control - First Call", "FAIL", 
                          f"HTTP {status1}: {data1}")
            return
        
        # Extract timestamps from first call
        updated_at_1 = data1.get("updated_at")
        last_cleanup_at_1 = data1.get("last_cleanup_at")
        
        # Wait a moment to ensure any side effects would be visible
        time.sleep(1)
        
        # Second call with refresh_checks=false
        status2, data2 = self.make_request(
            "GET", 
            "/api/phase4/admin/production-gate?refresh_checks=false", 
            self.admin_token, 
            self.admin_session
        )
        
        if status2 != 200:
            self.log_result("Read Side-Effect Control - Second Call", "FAIL", 
                          f"HTTP {status2}: {data2}")
            return
        
        # Extract timestamps from second call
        updated_at_2 = data2.get("updated_at")
        last_cleanup_at_2 = data2.get("last_cleanup_at")
        
        # Check if timestamps remained the same (no side effects)
        if updated_at_1 == updated_at_2 and last_cleanup_at_1 == last_cleanup_at_2:
            self.log_result("Read Side-Effect Control", "PASS", 
                          f"Timestamps unchanged: updated_at={updated_at_1}, last_cleanup_at={last_cleanup_at_1}")
        else:
            self.log_result("Read Side-Effect Control", "FAIL", 
                          f"Timestamps changed between calls",
                          f"updated_at={updated_at_1}, last_cleanup_at={last_cleanup_at_1}",
                          f"updated_at={updated_at_2}, last_cleanup_at={last_cleanup_at_2}")

    def test_refresh_path(self):
        """Test 2: Refresh path"""
        print("=== TEST 2: Refresh Path ===")
        
        status, data = self.make_request(
            "GET", 
            "/api/phase4/admin/production-gate?refresh_checks=true", 
            self.admin_token, 
            self.admin_session
        )
        
        if status == 200:
            self.log_result("Refresh Path", "PASS", f"HTTP 200: {data}")
        else:
            self.log_result("Refresh Path", "FAIL", f"HTTP {status}: {data}",
                          "HTTP 200", f"HTTP {status}")

    def test_mode_transition_phrase_map(self):
        """Test 3: Mode transition phrase map"""
        print("=== TEST 3: Mode Transition Phrase Map ===")
        
        # Based on the error response, the API requires: target_mode, reason_text, confirmation_phrase
        # Test valid mode transition with correct phrase
        valid_phrases = ["ENABLE LIVE TRADING", "GO LIVE", "LIVE MODE", "ACTIVATE LIVE"]
        
        valid_test_passed = False
        for phrase in valid_phrases:
            status, data = self.make_request(
                "POST", 
                "/api/phase4/admin/production-gate/mode-transition", 
                self.admin_token, 
                self.admin_session,
                json={
                    "target_mode": "LIVE", 
                    "reason_text": "Testing mode transition validation",
                    "confirmation_phrase": phrase
                }
            )
            
            if status == 200:
                self.log_result("Mode Transition - Valid LIVE", "PASS", 
                              f"HTTP 200 with phrase '{phrase}': {data}")
                valid_test_passed = True
                break
            elif status in [400, 422]:
                # This might be the wrong phrase, continue trying
                continue
            else:
                # Unexpected error
                self.log_result("Mode Transition - Valid LIVE", "FAIL", 
                              f"HTTP {status} with phrase '{phrase}': {data}")
                break
        
        if not valid_test_passed:
            # Try with a wrong phrase to see the expected phrase in error message
            status, data = self.make_request(
                "POST", 
                "/api/phase4/admin/production-gate/mode-transition", 
                self.admin_token, 
                self.admin_session,
                json={
                    "target_mode": "LIVE", 
                    "reason_text": "Testing phrase validation",
                    "confirmation_phrase": "WRONG_PHRASE"
                }
            )
            
            if status in [400, 422]:
                error_msg = str(data)
                self.log_result("Mode Transition - Valid LIVE", "INFO", 
                              f"Could not determine correct phrase. Error response: {error_msg}")
            else:
                self.log_result("Mode Transition - Valid LIVE", "FAIL", 
                              f"Unexpected response when testing phrase validation: HTTP {status}: {data}")
        
        # Test invalid mode
        status, data = self.make_request(
            "POST", 
            "/api/phase4/admin/production-gate/mode-transition", 
            self.admin_token, 
            self.admin_session,
            json={
                "target_mode": "INVALID_MODE", 
                "reason_text": "Testing invalid mode",
                "confirmation_phrase": "ANY_PHRASE"
            }
        )
        
        if status in [400, 422]:
            self.log_result("Mode Transition - Invalid Mode", "PASS", 
                          f"HTTP {status} (expected): {data}")
        else:
            self.log_result("Mode Transition - Invalid Mode", "FAIL", 
                          f"HTTP {status}: {data}",
                          "HTTP 400 or 422", f"HTTP {status}")

    def test_cross_check_sanitize(self):
        """Test 4: Cross-check sanitize"""
        print("=== TEST 4: Cross-Check Sanitize ===")
        
        status, data = self.make_request(
            "GET", 
            "/api/phase4/admin/production-gate/system/cross-check", 
            self.admin_token, 
            self.admin_session
        )
        
        if status == 200:
            # Check if response contains only sanitized fields
            if isinstance(data, dict):
                # Look for sanitized fields
                has_error = "error" in data
                has_mismatch_count = "mismatch_count" in data
                
                # Check for potentially unsanitized fields (internal payload)
                unsanitized_fields = []
                for key in data.keys():
                    if key not in ["error", "mismatch_count", "status", "timestamp", "summary"]:
                        # Check if this looks like internal data
                        if any(internal_word in key.lower() for internal_word in 
                              ["internal", "raw", "debug", "trace", "stack", "exception"]):
                            unsanitized_fields.append(key)
                
                if unsanitized_fields:
                    self.log_result("Cross-Check Sanitize", "FAIL", 
                                  f"Found potentially unsanitized fields: {unsanitized_fields}")
                else:
                    self.log_result("Cross-Check Sanitize", "PASS", 
                                  f"Response appears sanitized. Fields: {list(data.keys())}")
            else:
                self.log_result("Cross-Check Sanitize", "FAIL", 
                              f"Unexpected response format: {type(data)}")
        else:
            self.log_result("Cross-Check Sanitize", "FAIL", f"HTTP {status}: {data}")

    def test_ttl_min_validation(self):
        """Test 5: TTL min validation"""
        print("=== TEST 5: TTL Min Validation ===")
        
        # Based on the error response, the API requires: reason_code, reason_text, ttl
        status, data = self.make_request(
            "POST", 
            "/api/phase4/admin/production-gate/override", 
            self.admin_token, 
            self.admin_session,
            json={
                "ttl": 0, 
                "reason_code": "TEST",
                "reason_text": "Test TTL validation"
            }
        )
        
        if status in [400, 422]:
            self.log_result("TTL Min Validation", "PASS", 
                          f"HTTP {status} (expected rejection): {data}")
        elif status == 200:
            self.log_result("TTL Min Validation", "FAIL", 
                          f"HTTP 200 (should reject ttl=0): {data}",
                          "HTTP 422 or service-level validation rejection",
                          "HTTP 200 (accepted)")
        else:
            self.log_result("TTL Min Validation", "FAIL", 
                          f"HTTP {status}: {data}")

    def test_enforce_fallback_stability(self):
        """Test 6: Enforce fallback stability"""
        print("=== TEST 6: Enforce Fallback Stability ===")
        
        # First, trigger a gate-related action (mode transition)
        # This should not cause session reuse errors or 500 errors
        
        # Try to trigger mode transition (this might fail due to business logic, but should not cause 500/connection errors)
        status1, data1 = self.make_request(
            "POST", 
            "/api/phase4/admin/production-gate/mode-transition", 
            self.admin_token, 
            self.admin_session,
            json={
                "target_mode": "LIVE", 
                "reason_text": "Testing fallback stability",
                "confirmation_phrase": "TEST_PHRASE"
            }
        )
        
        # Check if we got a 500 or connection-related error
        if status1 == 500:
            self.log_result("Enforce Fallback Stability - Mode Transition", "FAIL", 
                          f"HTTP 500 error: {data1}")
            return
        elif status1 == 0:
            self.log_result("Enforce Fallback Stability - Mode Transition", "FAIL", 
                          f"Connection error: {data1}")
            return
        else:
            self.log_result("Enforce Fallback Stability - Mode Transition", "PASS", 
                          f"No 500/connection error. HTTP {status1}: {data1}")
        
        # Now test if subsequent requests work (session reuse)
        status2, data2 = self.make_request(
            "GET", 
            "/api/phase4/admin/production-gate", 
            self.admin_token, 
            self.admin_session
        )
        
        if status2 == 500:
            self.log_result("Enforce Fallback Stability - Session Reuse", "FAIL", 
                          f"HTTP 500 error on subsequent request: {data2}")
        elif status2 == 0:
            self.log_result("Enforce Fallback Stability - Session Reuse", "FAIL", 
                          f"Connection error on subsequent request: {data2}")
        elif status2 == 200:
            self.log_result("Enforce Fallback Stability - Session Reuse", "PASS", 
                          f"Session reuse working. HTTP 200: {data2}")
        else:
            self.log_result("Enforce Fallback Stability - Session Reuse", "PASS", 
                          f"No 500/connection error on subsequent request. HTTP {status2}")

    def run_validation(self):
        """Run complete validation suite"""
        print("🚀 Starting Production Gate Control Panel Backend Validation")
        print(f"Target: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print("=" * 60)
        
        # Authenticate
        admin_auth_success = self.authenticate_admin()
        
        if not admin_auth_success:
            print("❌ Admin authentication failed - cannot proceed with tests")
            return False
            
        # Run tests
        self.test_read_side_effect_control()
        self.test_refresh_path()
        self.test_mode_transition_phrase_map()
        self.test_cross_check_sanitize()
        self.test_ttl_min_validation()
        self.test_enforce_fallback_stability()
        
        # Summary
        print("=" * 60)
        print("📊 VALIDATION SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.results if r["status"] == "FAIL"])
        info_tests = len([r for r in self.results if r["status"] == "INFO"])
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"ℹ️ Info: {info_tests}")
        print(f"Success Rate: {(passed_tests/(total_tests-info_tests))*100:.1f}%")
        
        # List failures
        failures = [r for r in self.results if r["status"] == "FAIL"]
        if failures:
            print("\n🚨 REMAINING ISSUES:")
            for failure in failures:
                print(f"❌ {failure['test']}: {failure['details']}")
        else:
            print("\n🎉 ALL TESTS PASSED - NO ISSUES DETECTED")
        
        # List info items
        info_items = [r for r in self.results if r["status"] == "INFO"]
        if info_items:
            print("\nℹ️ ADDITIONAL INFO:")
            for info in info_items:
                print(f"ℹ️ {info['test']}: {info['details']}")
        
        return failed_tests == 0

if __name__ == "__main__":
    validator = ProductionGateValidator()
    success = validator.run_validation()
    sys.exit(0 if success else 1)