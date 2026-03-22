#!/usr/bin/env python3
"""
FAZ-3 Drift Action Center Backend Validation Test
Tests all drift alert endpoints and action contracts per review requirements.
"""

import requests
import json
import time
from typing import Dict, Any, List

# Test Configuration
BASE_URL = "https://audit-closure-dash.preview.emergentagent.com"
SUPER_ADMIN_CREDS = {
    "email": "canary.admin@platform.local",
    "password": "CanaryAdmin123!"
}
OPS_CREDS = {
    "email": "canary.ops@platform.local", 
    "password": "CanaryOps123!"
}

class DriftActionTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 30
        self.super_admin_token = None
        self.ops_token = None
        self.test_results = []
        
    def log_test(self, test_name: str, passed: bool, details: str):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.test_results.append({
            "test": test_name,
            "status": status,
            "passed": passed,
            "details": details
        })
        print(f"{status} - {test_name}: {details}")
        
    def login_super_admin(self) -> bool:
        """Login as super admin and extract token"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=SUPER_ADMIN_CREDS,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.super_admin_token = data.get("access_token")
                if self.super_admin_token:
                    self.log_test("Super Admin Login", True, f"Token extracted (length: {len(self.super_admin_token)})")
                    return True
                else:
                    self.log_test("Super Admin Login", False, "No access_token in response")
                    return False
            else:
                self.log_test("Super Admin Login", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Super Admin Login", False, f"Exception: {str(e)}")
            return False
            
    def login_ops(self) -> bool:
        """Login as ops user and extract token"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/user",
                json=OPS_CREDS,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.ops_token = data.get("access_token")
                if self.ops_token:
                    self.log_test("Ops User Login", True, f"Token extracted (length: {len(self.ops_token)})")
                    return True
                else:
                    self.log_test("Ops User Login", False, "No access_token in response")
                    return False
            else:
                self.log_test("Ops User Login", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Ops User Login", False, f"Exception: {str(e)}")
            return False
            
    def test_drift_alerts_endpoint(self) -> List[Dict]:
        """Test 1: GET /api/admin/futures/strategy-control/drift-alerts"""
        try:
            headers = {"Authorization": f"Bearer {self.super_admin_token}"}
            response = self.session.get(
                f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check required fields
                required_fields = ["items", "deep_link", "status"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_test("GET drift-alerts", False, f"Missing fields: {missing_fields}")
                    return []
                
                items = data.get("items", [])
                self.log_test("GET drift-alerts", True, 
                    f"Returns {len(items)} alerts with required fields: items, deep_link, status")
                return items
                
            else:
                self.log_test("GET drift-alerts", False, f"HTTP {response.status_code}: {response.text}")
                return []
                
        except Exception as e:
            self.log_test("GET drift-alerts", False, f"Exception: {str(e)}")
            return []
            
    def test_drift_action(self, action: str, alert_id: str, payload: Dict = None) -> Dict:
        """Test drift action endpoint"""
        try:
            headers = {"Authorization": f"Bearer {self.super_admin_token}"}
            url = f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts/{alert_id}/{action}"
            
            response = self.session.post(url, headers=headers, json=payload or {}, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check response contract
                required_fields = ["status", "trace_id", "message", "state_snapshot"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_test(f"POST {action}", False, f"Missing response fields: {missing_fields}")
                    return {}
                
                self.log_test(f"POST {action}", True, 
                    f"Response contract valid: {data.get('status')}, trace_id: {data.get('trace_id')[:8]}...")
                return data
                
            else:
                self.log_test(f"POST {action}", False, f"HTTP {response.status_code}: {response.text}")
                return {}
                
        except Exception as e:
            self.log_test(f"POST {action}", False, f"Exception: {str(e)}")
            return {}
            
    def test_mute_duration_validation(self, alert_id: str):
        """Test 4: Mute duration validation (only 1/24/168 hours)"""
        valid_durations = [1, 24, 168]
        invalid_durations = [2, 12, 48, 72, 336]
        
        # Test valid durations
        for duration in valid_durations:
            payload = {"duration_hours": duration, "reason": "Test mute"}
            result = self.test_drift_action("mute", alert_id, payload)
            if result.get("status") == "success":
                self.log_test(f"Mute duration {duration}h", True, "Valid duration accepted")
            else:
                self.log_test(f"Mute duration {duration}h", False, "Valid duration rejected")
                
        # Test invalid durations
        for duration in invalid_durations:
            payload = {"duration_hours": duration, "reason": "Test invalid mute"}
            try:
                headers = {"Authorization": f"Bearer {self.super_admin_token}"}
                url = f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts/{alert_id}/mute"
                response = self.session.post(url, headers=headers, json=payload, timeout=30)
                
                if response.status_code == 400 or response.status_code == 422:
                    self.log_test(f"Mute duration {duration}h validation", True, "Invalid duration properly rejected")
                else:
                    self.log_test(f"Mute duration {duration}h validation", False, 
                        f"Invalid duration not rejected: {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"Mute duration {duration}h validation", False, f"Exception: {str(e)}")
                
    def test_confirm_enforcement(self, alert_id: str):
        """Test 3: Confirm enforcement for ignore and disable actions"""
        
        # Test ignore with correct confirmation
        ignore_payload = {"confirmation": "IGNORE DRIFT ALERT", "reason": "Test ignore"}
        ignore_result = self.test_drift_action("ignore", alert_id, ignore_payload)
        
        # Test ignore with wrong confirmation
        try:
            headers = {"Authorization": f"Bearer {self.super_admin_token}"}
            url = f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts/{alert_id}/ignore"
            wrong_payload = {"confirmation": "WRONG PHRASE", "reason": "Test"}
            response = self.session.post(url, headers=headers, json=wrong_payload, timeout=30)
            
            if response.status_code == 400 or response.status_code == 422:
                self.log_test("Ignore confirmation enforcement", True, "Wrong confirmation properly rejected")
            else:
                self.log_test("Ignore confirmation enforcement", False, "Wrong confirmation not rejected")
                
        except Exception as e:
            self.log_test("Ignore confirmation enforcement", False, f"Exception: {str(e)}")
            
        # Test disable with correct confirmation
        disable_payload = {"confirmation": "DISABLE VIA DRIFT", "reason": "Test disable"}
        disable_result = self.test_drift_action("disable-strategy", alert_id, disable_payload)
        
        # Check for throttle->pause->disable chain info
        if disable_result.get("linked_action_result"):
            self.log_test("Disable chain info", True, "linked_action_result present in response")
        else:
            self.log_test("Disable chain info", False, "linked_action_result missing from response")
            
    def test_retrain_queued_job(self, alert_id: str):
        """Test 6: Retrain queued job response"""
        retrain_payload = {"reason": "Test retrain"}
        result = self.test_drift_action("retrain", alert_id, retrain_payload)
        
        if result:
            state_snapshot = result.get("state_snapshot", {})
            if (state_snapshot.get("retrain_status") == "queued" and 
                state_snapshot.get("retrain_job_id")):
                self.log_test("Retrain queued job", True, 
                    f"retrain_status=queued, job_id={state_snapshot.get('retrain_job_id')}")
            else:
                self.log_test("Retrain queued job", False, 
                    f"Missing retrain_status=queued or retrain_job_id in state_snapshot")
                    
    def test_ops_access_control(self):
        """Test 8: Ops user should get 403 on drift endpoints"""
        try:
            headers = {"Authorization": f"Bearer {self.ops_token}"}
            response = self.session.get(
                f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 403:
                self.log_test("Ops user 403 access control", True, "Ops user properly blocked with 403")
            else:
                self.log_test("Ops user 403 access control", False, 
                    f"Ops user not blocked: HTTP {response.status_code}")
                    
        except Exception as e:
            self.log_test("Ops user 403 access control", False, f"Exception: {str(e)}")
            
    def run_all_tests(self):
        """Run all FAZ-3 drift action center tests"""
        print("=== FAZ-3 DRIFT ACTION CENTER BACKEND VALIDATION ===")
        print(f"Base URL: {BASE_URL}")
        print(f"Super Admin: {SUPER_ADMIN_CREDS['email']}")
        print(f"Ops User: {OPS_CREDS['email']}")
        print()
        
        # Login tests
        if not self.login_super_admin():
            print("❌ CRITICAL: Super admin login failed, aborting tests")
            return
            
        if not self.login_ops():
            print("⚠️ WARNING: Ops login failed, will skip access control test")
            
        # Test 1: GET drift alerts endpoint
        alerts = self.test_drift_alerts_endpoint()
        
        if not alerts:
            print("⚠️ WARNING: No drift alerts found, using mock alert ID for action tests")
            alert_id = "test-alert-id"
        else:
            alert_id = alerts[0].get("id", "test-alert-id")
            print(f"Using alert ID: {alert_id}")
            
        # Test 2: Basic drift actions (ack)
        self.test_drift_action("ack", alert_id, {"reason": "Test acknowledgment"})
        
        # Test 3: Confirm enforcement
        self.test_confirm_enforcement(alert_id)
        
        # Test 4: Mute duration validation
        self.test_mute_duration_validation(alert_id)
        
        # Test 6: Retrain queued job
        self.test_retrain_queued_job(alert_id)
        
        # Test 8: Ops access control
        if self.ops_token:
            self.test_ops_access_control()
            
        # Summary
        self.print_summary()
        
    def print_summary(self):
        """Print test summary"""
        print("\n=== TEST SUMMARY ===")
        passed_tests = [t for t in self.test_results if t["passed"]]
        failed_tests = [t for t in self.test_results if not t["passed"]]
        
        print(f"Total Tests: {len(self.test_results)}")
        print(f"Passed: {len(passed_tests)}")
        print(f"Failed: {len(failed_tests)}")
        print(f"Success Rate: {len(passed_tests)/len(self.test_results)*100:.1f}%")
        
        if failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in failed_tests:
                print(f"  - {test['test']}: {test['details']}")
                
        print("\n✅ PASSED TESTS:")
        for test in passed_tests:
            print(f"  - {test['test']}: {test['details']}")
            
        # Overall result
        if len(failed_tests) == 0:
            print(f"\n🎯 OVERALL RESULT: ✅ PASS - All {len(self.test_results)} tests passed")
        else:
            print(f"\n🎯 OVERALL RESULT: ❌ FAIL - {len(failed_tests)} of {len(self.test_results)} tests failed")

if __name__ == "__main__":
    tester = DriftActionTester()
    tester.run_all_tests()