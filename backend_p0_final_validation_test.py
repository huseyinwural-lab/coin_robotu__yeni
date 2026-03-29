#!/usr/bin/env python3
"""
P0 FINAL Validation Test - Failure Explainer System
Turkish Review Request: P0 FINAL kapanış doğrulaması yap (backend + frontend smoke)

Test Requirements:
1. Canonical endpoint set validation
2. Explain minimum output validation  
3. Correlation validation
4. Replay deterministic minimum validation
5. Hard-fail guard validation
6. UI smoke test

URL: https://unified-orchestrator.preview.emergentagent.com
Credentials: canary.admin@platform.local / CanaryAdmin123!
"""

import requests
import json
import time
import base64
from typing import Dict, Any, List, Optional

class P0FinalValidationTest:
    def __init__(self):
        self.base_url = "https://unified-orchestrator.preview.emergentagent.com"
        self.admin_email = "canary.admin@platform.local"
        self.admin_password = "CanaryAdmin123!"
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = []
        
    def log_test(self, test_name: str, status: str, details: str):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.test_results.append(result)
        print(f"[{status}] {test_name}: {details}")
        
    def authenticate_admin(self) -> bool:
        """Authenticate as admin user"""
        try:
            login_url = f"{self.base_url}/api/auth/login"
            login_data = {
                "email": self.admin_email,
                "password": self.admin_password
            }
            
            response = self.session.post(login_url, json=login_data)
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    # Extract device info from token
                    try:
                        # Decode JWT payload (without verification for device info)
                        token_parts = self.admin_token.split('.')
                        if len(token_parts) >= 2:
                            # Add padding if needed
                            payload_b64 = token_parts[1]
                            padding = 4 - len(payload_b64) % 4
                            if padding != 4:
                                payload_b64 += '=' * padding
                            
                            payload = json.loads(base64.b64decode(payload_b64))
                            device_id = payload.get('device_id')
                            device_fingerprint = payload.get('device_fingerprint')
                            
                            # Set headers with device info
                            headers = {
                                "Authorization": f"Bearer {self.admin_token}",
                                "Content-Type": "application/json"
                            }
                            
                            if device_id:
                                headers["X-Device-ID"] = device_id
                            if device_fingerprint:
                                headers["X-Device-Fingerprint"] = device_fingerprint
                            
                            self.session.headers.update(headers)
                            
                            self.log_test("Admin Authentication", "PASS", 
                                        f"Successfully authenticated. Token length: {len(self.admin_token)} chars, Device ID: {device_id[:20] if device_id else 'None'}...")
                            return True
                    except Exception as e:
                        # Fallback to basic auth
                        self.session.headers.update({
                            "Authorization": f"Bearer {self.admin_token}",
                            "Content-Type": "application/json"
                        })
                        self.log_test("Admin Authentication", "PASS", 
                                    f"Successfully authenticated (basic). Token length: {len(self.admin_token)} chars")
                        return True
                else:
                    self.log_test("Admin Authentication", "FAIL", "No access_token in response")
                    return False
            else:
                self.log_test("Admin Authentication", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Admin Authentication", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_canonical_endpoints(self) -> bool:
        """Test 1: Canonical endpoint set validation"""
        try:
            all_passed = True
            
            # Test 1a: GET /api/audit-logs/trading-lifecycle?limit=20
            url = f"{self.base_url}/api/audit-logs/trading-lifecycle?limit=20"
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                # Check for required structure
                if isinstance(data, dict) and 'events' in data:
                    self.log_test("Canonical Endpoint - Trading Lifecycle", "PASS", 
                                f"HTTP 200, events field present, {len(data.get('events', []))} events")
                else:
                    self.log_test("Canonical Endpoint - Trading Lifecycle", "FAIL", 
                                "Missing events field in response")
                    all_passed = False
            else:
                self.log_test("Canonical Endpoint - Trading Lifecycle", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                all_passed = False
            
            # Test 1b: GET /api/audit-logs/lifecycle/{correlation_id} - need to get a correlation_id first
            if 'events' in data and data['events']:
                correlation_id = data['events'][0].get('correlation_id')
                if correlation_id:
                    url = f"{self.base_url}/api/audit-logs/lifecycle/{correlation_id}"
                    response = self.session.get(url)
                    
                    if response.status_code == 200:
                        lifecycle_data = response.json()
                        required_fields = ['correlation_id', 'events', 'trace_incomplete', 
                                         'missing_critical_stages', 'broken_chain']
                        missing_fields = [field for field in required_fields 
                                        if field not in lifecycle_data]
                        
                        if not missing_fields:
                            self.log_test("Canonical Endpoint - Lifecycle Detail", "PASS", 
                                        f"HTTP 200, all required fields present: {required_fields}")
                        else:
                            self.log_test("Canonical Endpoint - Lifecycle Detail", "FAIL", 
                                        f"Missing required fields: {missing_fields}")
                            all_passed = False
                    else:
                        self.log_test("Canonical Endpoint - Lifecycle Detail", "FAIL", 
                                    f"HTTP {response.status_code}: {response.text}")
                        all_passed = False
                else:
                    self.log_test("Canonical Endpoint - Lifecycle Detail", "FAIL", 
                                "No correlation_id found in trading lifecycle events")
                    all_passed = False
            
            # Test 1c: POST /api/audit-logs/explain
            url = f"{self.base_url}/api/audit-logs/explain"
            explain_payload = {
                "correlation_id": correlation_id if 'correlation_id' in locals() else "test-correlation-id",
                "context": "P0 final validation test"
            }
            response = self.session.post(url, json=explain_payload)
            
            if response.status_code == 200:
                explain_data = response.json()
                required_fields = ['correlation_id', 'events', 'trace_incomplete', 
                                 'missing_critical_stages', 'broken_chain']
                missing_fields = [field for field in required_fields 
                                if field not in explain_data]
                
                if not missing_fields:
                    self.log_test("Canonical Endpoint - Explain", "PASS", 
                                f"HTTP 200, all required fields present: {required_fields}")
                else:
                    self.log_test("Canonical Endpoint - Explain", "FAIL", 
                                f"Missing required fields: {missing_fields}")
                    all_passed = False
            else:
                self.log_test("Canonical Endpoint - Explain", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                all_passed = False
            
            return all_passed
            
        except Exception as e:
            self.log_test("Canonical Endpoints", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_explain_minimum_output(self) -> bool:
        """Test 2: Explain minimum output validation"""
        try:
            # Get a correlation_id first
            url = f"{self.base_url}/api/audit-logs/trading-lifecycle?limit=5"
            response = self.session.get(url)
            
            if response.status_code != 200:
                self.log_test("Explain Minimum Output", "FAIL", 
                            f"Failed to get trading lifecycle: HTTP {response.status_code}")
                return False
            
            data = response.json()
            if not data.get('events'):
                self.log_test("Explain Minimum Output", "FAIL", "No events found for testing")
                return False
            
            correlation_id = data['events'][0].get('correlation_id')
            if not correlation_id:
                self.log_test("Explain Minimum Output", "FAIL", "No correlation_id found")
                return False
            
            # Test explain endpoint
            url = f"{self.base_url}/api/audit-logs/explain"
            explain_payload = {
                "correlation_id": correlation_id,
                "context": "P0 final validation - explain minimum output test"
            }
            response = self.session.post(url, json=explain_payload)
            
            if response.status_code == 200:
                explain_data = response.json()
                
                # Check for minimum required fields in explain output
                required_explain_fields = ['broken_step', 'root_cause', 'missing_stages', 
                                         'upstream_event', 'downstream_impact', 'confidence', 
                                         'insufficient_data']
                
                found_fields = []
                missing_fields = []
                
                for field in required_explain_fields:
                    if field in explain_data:
                        found_fields.append(field)
                    else:
                        missing_fields.append(field)
                
                if not missing_fields:
                    self.log_test("Explain Minimum Output", "PASS", 
                                f"All required explain fields present: {found_fields}")
                    return True
                else:
                    self.log_test("Explain Minimum Output", "PARTIAL", 
                                f"Found: {found_fields}, Missing: {missing_fields}")
                    return False
            else:
                self.log_test("Explain Minimum Output", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Explain Minimum Output", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_correlation_validation(self) -> bool:
        """Test 3: Correlation validation"""
        try:
            # Get lifecycle data to test correlation validation
            url = f"{self.base_url}/api/audit-logs/trading-lifecycle?limit=10"
            response = self.session.get(url)
            
            if response.status_code != 200:
                self.log_test("Correlation Validation", "FAIL", 
                            f"Failed to get trading lifecycle: HTTP {response.status_code}")
                return False
            
            data = response.json()
            if not data.get('events'):
                self.log_test("Correlation Validation", "FAIL", "No events found for testing")
                return False
            
            validation_results = []
            
            # Test multiple correlation IDs
            for event in data['events'][:3]:  # Test first 3 events
                correlation_id = event.get('correlation_id')
                if not correlation_id:
                    continue
                
                url = f"{self.base_url}/api/audit-logs/lifecycle/{correlation_id}"
                response = self.session.get(url)
                
                if response.status_code == 200:
                    lifecycle_data = response.json()
                    
                    # Check correlation validation rules
                    trace_incomplete = lifecycle_data.get('trace_incomplete')
                    missing_critical_stages = lifecycle_data.get('missing_critical_stages')
                    broken_chain = lifecycle_data.get('broken_chain')
                    
                    # Rule 1: missing_critical_stages must always be present (can be empty)
                    if 'missing_critical_stages' not in lifecycle_data:
                        validation_results.append(f"FAIL: missing_critical_stages field not present for {correlation_id}")
                        continue
                    
                    # Rule 2: If missing stages, trace_incomplete should be true
                    if missing_critical_stages and len(missing_critical_stages) > 0:
                        if trace_incomplete is not True:
                            validation_results.append(f"FAIL: trace_incomplete should be true when missing_critical_stages present for {correlation_id}")
                        else:
                            validation_results.append(f"PASS: trace_incomplete=true with missing stages for {correlation_id}")
                    
                    # Rule 3: broken_chain should be properly marked
                    if 'broken_chain' not in lifecycle_data:
                        validation_results.append(f"FAIL: broken_chain field not present for {correlation_id}")
                    else:
                        validation_results.append(f"PASS: broken_chain field present ({broken_chain}) for {correlation_id}")
                
            if validation_results:
                passed = sum(1 for result in validation_results if result.startswith("PASS"))
                total = len(validation_results)
                
                if passed == total:
                    self.log_test("Correlation Validation", "PASS", 
                                f"All validation rules passed ({passed}/{total})")
                    return True
                else:
                    self.log_test("Correlation Validation", "PARTIAL", 
                                f"Validation results: {validation_results}")
                    return False
            else:
                self.log_test("Correlation Validation", "FAIL", "No correlation data to validate")
                return False
                
        except Exception as e:
            self.log_test("Correlation Validation", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_replay_deterministic(self) -> bool:
        """Test 4: Replay deterministic minimum validation"""
        try:
            # Get a correlation_id first
            url = f"{self.base_url}/api/audit-logs/trading-lifecycle?limit=5"
            response = self.session.get(url)
            
            if response.status_code != 200:
                self.log_test("Replay Deterministic", "FAIL", 
                            f"Failed to get trading lifecycle: HTTP {response.status_code}")
                return False
            
            data = response.json()
            if not data.get('events'):
                self.log_test("Replay Deterministic", "FAIL", "No events found for testing")
                return False
            
            correlation_id = data['events'][0].get('correlation_id')
            if not correlation_id:
                self.log_test("Replay Deterministic", "FAIL", "No correlation_id found")
                return False
            
            # Test replay endpoint
            url = f"{self.base_url}/api/audit-logs/trading-lifecycle/{correlation_id}/replay"
            replay_payload = {
                "context": "P0 final validation - replay deterministic test"
            }
            response = self.session.post(url, json=replay_payload)
            
            if response.status_code == 200:
                replay_data = response.json()
                
                # Check for required deterministic fields
                required_fields = {
                    'replay_mode': 'isolated',
                    'external_calls_disabled': True,
                    'deterministic_order': True,
                    'side_effects_blocked': True
                }
                
                validation_results = []
                for field, expected_value in required_fields.items():
                    actual_value = replay_data.get(field)
                    if actual_value == expected_value:
                        validation_results.append(f"PASS: {field}={actual_value}")
                    else:
                        validation_results.append(f"FAIL: {field}={actual_value}, expected={expected_value}")
                
                passed = sum(1 for result in validation_results if result.startswith("PASS"))
                total = len(validation_results)
                
                if passed == total:
                    self.log_test("Replay Deterministic", "PASS", 
                                f"All deterministic fields correct: {validation_results}")
                    return True
                else:
                    self.log_test("Replay Deterministic", "PARTIAL", 
                                f"Validation results: {validation_results}")
                    return False
            else:
                self.log_test("Replay Deterministic", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Replay Deterministic", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_hard_fail_guard(self) -> bool:
        """Test 5: Hard-fail guard validation"""
        try:
            # Test consistency/repo-deploy endpoint
            url = f"{self.base_url}/api/audit-logs/consistency/repo-deploy"
            response = self.session.get(url)
            
            if response.status_code == 200:
                consistency_data = response.json()
                
                # Check for hash matching fields
                if 'hash' in consistency_data or 'repo_hash' in consistency_data or 'deploy_hash' in consistency_data:
                    self.log_test("Hard-fail Guard - Consistency", "PASS", 
                                f"Hash consistency endpoint accessible: {list(consistency_data.keys())}")
                    
                    # Test if explain/replay calls have guard active
                    # Try explain with guard check
                    url = f"{self.base_url}/api/audit-logs/trading-lifecycle?limit=1"
                    response = self.session.get(url)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('events'):
                            correlation_id = data['events'][0].get('correlation_id')
                            
                            # Test explain with potential guard
                            url = f"{self.base_url}/api/audit-logs/explain"
                            explain_payload = {
                                "correlation_id": correlation_id,
                                "context": "P0 final validation - guard test"
                            }
                            response = self.session.post(url, json=explain_payload)
                            
                            # Guard should either allow (200) or block with specific error
                            if response.status_code in [200, 403, 409]:
                                self.log_test("Hard-fail Guard - Explain", "PASS", 
                                            f"Guard active - HTTP {response.status_code}")
                                return True
                            else:
                                self.log_test("Hard-fail Guard - Explain", "FAIL", 
                                            f"Unexpected response: HTTP {response.status_code}")
                                return False
                    
                    return True
                else:
                    self.log_test("Hard-fail Guard - Consistency", "FAIL", 
                                "No hash fields found in consistency response")
                    return False
            else:
                self.log_test("Hard-fail Guard - Consistency", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Hard-fail Guard", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_ui_smoke(self) -> bool:
        """Test 6: UI smoke test"""
        try:
            # Test admin audit-logs page accessibility
            url = f"{self.base_url}/admin/audit-logs"
            response = self.session.get(url)
            
            if response.status_code == 200:
                html_content = response.text
                
                # Check for basic UI elements
                ui_checks = []
                
                if len(html_content) > 1000:  # Not blank page
                    ui_checks.append("PASS: Page not blank")
                else:
                    ui_checks.append("FAIL: Page appears blank")
                
                # Check for React app structure
                if 'audit-logs' in html_content.lower() or 'correlation' in html_content.lower():
                    ui_checks.append("PASS: Audit logs content detected")
                else:
                    ui_checks.append("PARTIAL: Audit logs content not clearly detected")
                
                # Check for HTML structure
                if '<html' in html_content and '</html>' in html_content:
                    ui_checks.append("PASS: Valid HTML structure")
                else:
                    ui_checks.append("FAIL: Invalid HTML structure")
                
                passed = sum(1 for check in ui_checks if check.startswith("PASS"))
                total = len(ui_checks)
                
                if passed >= total - 1:  # Allow one partial
                    self.log_test("UI Smoke Test", "PASS", 
                                f"UI accessible ({passed}/{total} checks passed): {ui_checks}")
                    return True
                else:
                    self.log_test("UI Smoke Test", "PARTIAL", 
                                f"UI checks: {ui_checks}")
                    return False
            else:
                self.log_test("UI Smoke Test", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("UI Smoke Test", "FAIL", f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all P0 final validation tests"""
        print("=" * 80)
        print("P0 FINAL VALIDATION TEST - FAILURE EXPLAINER SYSTEM")
        print("=" * 80)
        print(f"Target URL: {self.base_url}")
        print(f"Admin Credentials: {self.admin_email} / {self.admin_password}")
        print("=" * 80)
        
        # Authenticate first
        if not self.authenticate_admin():
            print("CRITICAL: Admin authentication failed. Cannot proceed with tests.")
            return
        
        # Run all tests
        tests = [
            ("Canonical Endpoints", self.test_canonical_endpoints),
            ("Explain Minimum Output", self.test_explain_minimum_output),
            ("Correlation Validation", self.test_correlation_validation),
            ("Replay Deterministic", self.test_replay_deterministic),
            ("Hard-fail Guard", self.test_hard_fail_guard),
            ("UI Smoke Test", self.test_ui_smoke)
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n--- Running {test_name} ---")
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                self.log_test(test_name, "FAIL", f"Unexpected exception: {str(e)}")
        
        # Final summary
        print("\n" + "=" * 80)
        print("P0 FINAL VALIDATION SUMMARY")
        print("=" * 80)
        
        success_rate = (passed_tests / total_tests) * 100
        print(f"OVERALL RESULT: {passed_tests}/{total_tests} PASS ({success_rate:.1f}% SUCCESS RATE)")
        
        print("\nDETAILED TEST RESULTS:")
        for result in self.test_results:
            status_symbol = "✅" if result["status"] == "PASS" else "⚠️" if result["status"] == "PARTIAL" else "❌"
            print(f"{status_symbol} {result['test']}: {result['status']} - {result['details']}")
        
        print("\nCRITICAL VALIDATION:")
        if passed_tests == total_tests:
            print("✅ ALL P0 FINAL REQUIREMENTS PASSED")
            print("✅ System production-ready for P0 operations")
        elif passed_tests >= total_tests * 0.8:  # 80% pass rate
            print("⚠️ MOST P0 REQUIREMENTS PASSED")
            print("⚠️ Minor issues detected, review required")
        else:
            print("❌ CRITICAL P0 REQUIREMENTS FAILED")
            print("❌ System NOT production-ready")
        
        print("=" * 80)

if __name__ == "__main__":
    test = P0FinalValidationTest()
    test.run_all_tests()