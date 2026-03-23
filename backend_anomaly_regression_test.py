#!/usr/bin/env python3
"""
Backend Regression Test for Phase-1 Anomaly Stabilization
Testing anomaly event submission with guardrail suppression, cooldown, and validation logic.

Base URL: https://deploy-blocker-6.preview.emergentagent.com
Test credentials: canary_1774010877@example.com / TestPass123!
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "https://deploy-blocker-6.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"
TEST_EMAIL = "canary_1774010877@example.com"
TEST_PASSWORD = "TestPass123!"

class AnomalyRegressionTest:
    def __init__(self):
        self.session = requests.Session()
        self.access_token = None
        self.test_results = []
        
    def log_result(self, test_name, passed, details):
        """Log test result with details"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.test_results.append({
            "test": test_name,
            "status": status,
            "passed": passed,
            "details": details
        })
        print(f"{status} - {test_name}: {details}")
        
    def login_and_get_token(self):
        """Test 1: Login and extract access token"""
        try:
            login_url = f"{API_BASE}/auth/login/user"
            login_data = {
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            }
            
            response = self.session.post(login_url, json=login_data)
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                if self.access_token:
                    # Set authorization header for future requests
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.access_token}"
                    })
                    self.log_result(
                        "Login and get token",
                        True,
                        f"Successfully logged in, token extracted (length: {len(self.access_token)})"
                    )
                    return True
                else:
                    self.log_result(
                        "Login and get token",
                        False,
                        "Login successful but no access_token in response"
                    )
                    return False
            else:
                self.log_result(
                    "Login and get token",
                    False,
                    f"Login failed with status {response.status_code}: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Login and get token",
                False,
                f"Exception during login: {str(e)}"
            )
            return False
    
    def test_guardrail_suppression(self):
        """Test 2: Guardrail suppression with fail_ratio=0.05, total_requests=40"""
        try:
            anomaly_url = f"{API_BASE}/user/scanner/runtime/anomaly-event"
            
            # Payload that should trigger guardrail suppression (fail_ratio too low)
            payload = {
                "source": "scanner_ui",
                "fail_ratio": 0.05,  # 5% - should be below guardrail threshold
                "total_requests": 40,
                "failed_requests": 2,  # 5% of 40
                "success_requests": 38,  # 95% of 40
                "trend_window_minutes": 15,
                "trend_points": [
                    {"minute_offset": 0, "success_count": 8, "fail_count": 0},
                    {"minute_offset": 1, "success_count": 8, "fail_count": 0},
                    {"minute_offset": 2, "success_count": 8, "fail_count": 1},
                    {"minute_offset": 3, "success_count": 8, "fail_count": 1},
                    {"minute_offset": 4, "success_count": 6, "fail_count": 0}
                ]
            }
            
            response = self.session.post(anomaly_url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                suppress_reason = data.get("suppress_reason")
                suppressed_count = data.get("suppressed_count")
                
                if (status == "suppressed" and 
                    suppress_reason == "guardrail_threshold" and 
                    suppressed_count is not None):
                    self.log_result(
                        "Guardrail suppression",
                        True,
                        f"Correctly suppressed: status={status}, reason={suppress_reason}, count={suppressed_count}"
                    )
                    return True
                else:
                    self.log_result(
                        "Guardrail suppression",
                        False,
                        f"Unexpected response: status={status}, reason={suppress_reason}, count={suppressed_count}"
                    )
                    return False
            else:
                self.log_result(
                    "Guardrail suppression",
                    False,
                    f"Request failed with status {response.status_code}: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Guardrail suppression",
                False,
                f"Exception during test: {str(e)}"
            )
            return False
    
    def test_valid_anomaly_log(self):
        """Test 3: Valid anomaly log with fail_ratio=0.2, total_requests=40"""
        try:
            anomaly_url = f"{API_BASE}/user/scanner/runtime/anomaly-event"
            
            # Payload that should be logged (fail_ratio above threshold)
            payload = {
                "source": "scanner_ui",
                "fail_ratio": 0.2,  # 20% - should be above guardrail threshold
                "total_requests": 40,
                "failed_requests": 8,  # 20% of 40
                "success_requests": 32,  # 80% of 40
                "trend_window_minutes": 15,
                "trend_points": [
                    {"minute_offset": 0, "success_count": 6, "fail_count": 2},
                    {"minute_offset": 1, "success_count": 6, "fail_count": 2},
                    {"minute_offset": 2, "success_count": 7, "fail_count": 1},
                    {"minute_offset": 3, "success_count": 7, "fail_count": 1},
                    {"minute_offset": 4, "success_count": 6, "fail_count": 2}
                ]
            }
            
            response = self.session.post(anomaly_url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                audit_log_id = data.get("audit_log_id")
                payload_hash = data.get("payload_hash")
                
                if (status == "logged" and 
                    audit_log_id is not None and 
                    payload_hash is not None):
                    self.log_result(
                        "Valid anomaly log",
                        True,
                        f"Correctly logged: status={status}, audit_log_id={audit_log_id}, payload_hash={payload_hash}"
                    )
                    # Store for cooldown test
                    self.valid_payload = payload
                    return True
                else:
                    self.log_result(
                        "Valid anomaly log",
                        False,
                        f"Unexpected response: status={status}, audit_log_id={audit_log_id}, payload_hash={payload_hash}"
                    )
                    return False
            else:
                self.log_result(
                    "Valid anomaly log",
                    False,
                    f"Request failed with status {response.status_code}: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Valid anomaly log",
                False,
                f"Exception during test: {str(e)}"
            )
            return False
    
    def test_cooldown_suppression(self):
        """Test 4: Cooldown suppression - immediately send same valid payload"""
        try:
            if not hasattr(self, 'valid_payload'):
                self.log_result(
                    "Cooldown suppression",
                    False,
                    "No valid payload from previous test to reuse"
                )
                return False
                
            anomaly_url = f"{API_BASE}/user/scanner/runtime/anomaly-event"
            
            # Send the same payload immediately to trigger cooldown
            response = self.session.post(anomaly_url, json=self.valid_payload)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                suppress_reason = data.get("suppress_reason")
                
                if (status == "suppressed" and 
                    suppress_reason == "cooldown_active"):
                    self.log_result(
                        "Cooldown suppression",
                        True,
                        f"Correctly suppressed due to cooldown: status={status}, reason={suppress_reason}"
                    )
                    return True
                else:
                    self.log_result(
                        "Cooldown suppression",
                        False,
                        f"Unexpected response: status={status}, reason={suppress_reason}"
                    )
                    return False
            else:
                self.log_result(
                    "Cooldown suppression",
                    False,
                    f"Request failed with status {response.status_code}: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Cooldown suppression",
                False,
                f"Exception during test: {str(e)}"
            )
            return False
    
    def test_invalid_consistency(self):
        """Test 5: Invalid consistency - failed_requests + success_requests > total_requests"""
        try:
            anomaly_url = f"{API_BASE}/user/scanner/runtime/anomaly-event"
            
            # Payload with invalid math (failed + success > total)
            payload = {
                "source": "scanner_ui",
                "fail_ratio": 0.2,
                "total_requests": 40,
                "failed_requests": 25,  # 25 + 20 = 45 > 40 (invalid)
                "success_requests": 20,
                "trend_window_minutes": 15,
                "trend_points": [
                    {"minute_offset": 0, "success_count": 4, "fail_count": 5},
                    {"minute_offset": 1, "success_count": 4, "fail_count": 5},
                    {"minute_offset": 2, "success_count": 4, "fail_count": 5},
                    {"minute_offset": 3, "success_count": 4, "fail_count": 5},
                    {"minute_offset": 4, "success_count": 4, "fail_count": 5}
                ]
            }
            
            response = self.session.post(anomaly_url, json=payload)
            
            if response.status_code == 422:
                # Should return validation error
                self.log_result(
                    "Invalid consistency",
                    True,
                    f"Correctly rejected invalid payload with 422 status: {response.text}"
                )
                return True
            else:
                self.log_result(
                    "Invalid consistency",
                    False,
                    f"Expected 422 but got {response.status_code}: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Invalid consistency",
                False,
                f"Exception during test: {str(e)}"
            )
            return False
    
    def test_health_endpoint(self):
        """Test 6: Ensure /api/health is still 200"""
        try:
            health_url = f"{API_BASE}/health"
            
            # Don't use session with auth headers for health check
            response = requests.get(health_url)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                if status == "ok":
                    self.log_result(
                        "Health endpoint",
                        True,
                        f"Health endpoint working correctly: status={status}"
                    )
                    return True
                else:
                    self.log_result(
                        "Health endpoint",
                        False,
                        f"Health endpoint returned unexpected status: {status}"
                    )
                    return False
            else:
                self.log_result(
                    "Health endpoint",
                    False,
                    f"Health endpoint failed with status {response.status_code}: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Health endpoint",
                False,
                f"Exception during health check: {str(e)}"
            )
            return False
    
    def run_all_tests(self):
        """Run all regression tests in sequence"""
        print("=" * 80)
        print("BACKEND REGRESSION TEST FOR PHASE-1 ANOMALY STABILIZATION")
        print("=" * 80)
        print(f"Base URL: {BASE_URL}")
        print(f"Test credentials: {TEST_EMAIL}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("=" * 80)
        
        # Test sequence
        tests = [
            self.login_and_get_token,
            self.test_guardrail_suppression,
            self.test_valid_anomaly_log,
            self.test_cooldown_suppression,
            self.test_invalid_consistency,
            self.test_health_endpoint
        ]
        
        passed_count = 0
        total_count = len(tests)
        
        for test_func in tests:
            if test_func():
                passed_count += 1
            print()  # Add spacing between tests
        
        # Summary
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        for result in self.test_results:
            print(f"{result['status']} - {result['test']}")
        
        print("=" * 80)
        success_rate = (passed_count / total_count) * 100
        print(f"OVERALL RESULT: {passed_count}/{total_count} tests passed ({success_rate:.1f}%)")
        
        if passed_count == total_count:
            print("🎉 ALL TESTS PASSED - Phase-1 anomaly stabilization working correctly")
        else:
            print("⚠️  SOME TESTS FAILED - Issues detected in anomaly stabilization")
        
        print("=" * 80)
        
        return passed_count == total_count

if __name__ == "__main__":
    test_runner = AnomalyRegressionTest()
    success = test_runner.run_all_tests()
    exit(0 if success else 1)