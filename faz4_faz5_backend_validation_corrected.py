#!/usr/bin/env python3
"""
FAZ-4+ / FAZ-5 Backend Final Validation Test (Corrected)
Comprehensive backend API validation for Faz-4+ / Faz-5 rollback system

Based on diagnostic findings:
- rollback-request requires snapshot_trace_id field
- policy-suggestions returns data in summary object
- Rate limiting requires careful request spacing
"""

import requests
import json
import sys
import time
from datetime import datetime, timedelta

# Configuration
BASE_URL = "https://gate-control-v2.preview.emergentagent.com"
CREDENTIALS = {
    "super_admin": {"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
    "admin_requester": {"email": "canary.requester@platform.local", "password": "CanaryRequester123!"},
    "ops": {"email": "canary.ops@platform.local", "password": "CanaryOps123!"}
}

class Faz4Faz5ValidatorCorrected:
    def __init__(self):
        self.tokens = {}
        self.test_results = []
        self.strategy_id = "trend_follow_v1"
        self.snapshot_trace_id = None  # Will be populated from snapshots
        
    def log_result(self, test_name, status, details=""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status} - {details}")
        
    def login_user(self, user_type):
        """Login and get access token with rate limiting"""
        try:
            time.sleep(1)  # Rate limiting
            creds = CREDENTIALS[user_type]
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": creds["email"], "password": creds["password"]},
                timeout=30
            )
            
            if response.status_code == 200:
                token = response.json().get("access_token")
                self.tokens[user_type] = token
                self.log_result(f"Login {user_type}", "PASS", f"Token length: {len(token) if token else 0}")
                return token
            else:
                self.log_result(f"Login {user_type}", "FAIL", f"Status: {response.status_code}")
                return None
                
        except Exception as e:
            self.log_result(f"Login {user_type}", "FAIL", f"Exception: {str(e)}")
            return None
    
    def make_request(self, method, endpoint, user_type, **kwargs):
        """Make authenticated request with rate limiting"""
        time.sleep(0.5)  # Rate limiting
        
        if user_type not in self.tokens:
            self.login_user(user_type)
            
        token = self.tokens.get(user_type)
        if not token:
            return None
            
        headers = {"Authorization": f"Bearer {token}"}
        if "headers" in kwargs:
            headers.update(kwargs["headers"])
        kwargs["headers"] = headers
        
        try:
            response = requests.request(method, f"{BASE_URL}{endpoint}", timeout=30, **kwargs)
            return response
        except Exception as e:
            print(f"Request failed: {str(e)}")
            return None
    
    def test_rollback_snapshots(self):
        """Test 1: GET /api/admin/futures/strategy/{id}/rollback-snapshots"""
        endpoint = f"/api/admin/futures/strategy/{self.strategy_id}/rollback-snapshots"
        response = self.make_request("GET", endpoint, "super_admin")
        
        if not response:
            self.log_result("Rollback Snapshots", "FAIL", "No response")
            return
            
        if response.status_code != 200:
            self.log_result("Rollback Snapshots", "FAIL", f"Status: {response.status_code}")
            return
            
        try:
            data = response.json()
            items = data.get("items", [])
            
            if not items:
                self.log_result("Rollback Snapshots", "PASS", "Empty snapshots list (expected)")
                return
                
            # Check first snapshot for required fields and capture snapshot_trace_id
            snapshot = items[0]
            required_fields = ["snapshot_trace_id", "timestamp", "actor", "action_type", "diff_preview", "rollback_scope"]
            missing_fields = [field for field in required_fields if field not in snapshot]
            
            # Capture snapshot_trace_id for later use
            self.snapshot_trace_id = snapshot.get("snapshot_trace_id")
            
            if missing_fields:
                self.log_result("Rollback Snapshots", "FAIL", f"Missing fields: {missing_fields}")
            else:
                rollback_scope = snapshot.get("rollback_scope")
                self.log_result("Rollback Snapshots", "PASS", 
                              f"All fields present, scope: {rollback_scope}, trace_id: {self.snapshot_trace_id}")
                    
        except Exception as e:
            self.log_result("Rollback Snapshots", "FAIL", f"JSON parse error: {str(e)}")
    
    def test_rollback_request(self):
        """Test 2: POST /api/admin/futures/strategy/{id}/rollback-request"""
        if not self.snapshot_trace_id:
            self.log_result("Rollback Request", "SKIP", "No snapshot_trace_id available")
            return
            
        endpoint = f"/api/admin/futures/strategy/{self.strategy_id}/rollback-request"
        
        # Test with missing reason (should fail)
        response = self.make_request("POST", endpoint, "super_admin", json={"snapshot_trace_id": self.snapshot_trace_id})
        if response and response.status_code == 422:
            self.log_result("Rollback Request Validation", "PASS", "Correctly rejects missing reason")
        else:
            self.log_result("Rollback Request Validation", "FAIL", 
                          f"Should reject missing reason, got: {response.status_code if response else 'No response'}")
        
        # Test with valid request
        payload = {
            "reason": "Test rollback request for Faz-4+ validation",
            "snapshot_trace_id": self.snapshot_trace_id,
            "preview": True
        }
        
        response = self.make_request("POST", endpoint, "super_admin", json=payload)
        
        if not response:
            self.log_result("Rollback Request", "FAIL", "No response")
            return
            
        if response.status_code not in [200, 201]:
            self.log_result("Rollback Request", "FAIL", f"Status: {response.status_code}, Body: {response.text[:200]}")
            return
            
        try:
            data = response.json()
            
            # Check for expires_at field (should be ~24h from now)
            if "expires_at" in data:
                expires_at = data["expires_at"]
                self.log_result("Rollback Request", "PASS", f"Request created with expires_at: {expires_at}")
            else:
                self.log_result("Rollback Request", "PARTIAL", "Request created but no expires_at field")
                
        except Exception as e:
            self.log_result("Rollback Request", "FAIL", f"JSON parse error: {str(e)}")
    
    def test_approval_requests(self):
        """Test 3: GET /api/admin/futures/strategy/approval-requests"""
        endpoint = "/api/admin/futures/strategy/approval-requests"
        
        # Test different status filters
        statuses = ["pending", "approved", "expired"]
        
        for status in statuses:
            response = self.make_request("GET", endpoint, "super_admin", params={"status": status})
            
            if not response:
                self.log_result(f"Approval Requests ({status})", "FAIL", "No response")
                continue
                
            if response.status_code != 200:
                self.log_result(f"Approval Requests ({status})", "FAIL", f"Status: {response.status_code}")
                continue
                
            try:
                data = response.json()
                count = len(data) if isinstance(data, list) else (data.get("total", 0) if isinstance(data, dict) else 0)
                self.log_result(f"Approval Requests ({status})", "PASS", f"Count: {count}")
                
            except Exception as e:
                self.log_result(f"Approval Requests ({status})", "FAIL", f"JSON parse error: {str(e)}")
    
    def test_drift_alerts(self):
        """Test 6: GET /api/admin/futures/strategy-control/drift-alerts"""
        endpoint = "/api/admin/futures/strategy-control/drift-alerts"
        response = self.make_request("GET", endpoint, "super_admin")
        
        if not response:
            self.log_result("Drift Alerts", "FAIL", "No response")
            return
            
        if response.status_code != 200:
            self.log_result("Drift Alerts", "FAIL", f"Status: {response.status_code}")
            return
            
        try:
            data = response.json()
            
            # Look for recommended_action fields
            alerts = data if isinstance(data, list) else data.get("items", [])
            
            if not alerts:
                self.log_result("Drift Alerts", "PASS", "No drift alerts (expected)")
                return
                
            # Check first alert for recommended_action structure
            alert = alerts[0]
            recommended_action = alert.get("recommended_action", {})
            
            required_fields = ["type", "confidence", "reason", "inputs"]
            missing_fields = [field for field in required_fields if field not in recommended_action]
            
            if missing_fields:
                self.log_result("Drift Alerts", "PARTIAL", f"Alert exists but missing recommended_action fields: {missing_fields}")
            else:
                self.log_result("Drift Alerts", "PASS", f"Recommended action fields present: {list(recommended_action.keys())}")
                
        except Exception as e:
            self.log_result("Drift Alerts", "FAIL", f"JSON parse error: {str(e)}")
    
    def test_policy_suggestions(self):
        """Test 7: GET /api/admin/futures/strategy-control/policy-suggestions"""
        endpoint = "/api/admin/futures/strategy-control/policy-suggestions"
        response = self.make_request("GET", endpoint, "super_admin")
        
        if not response:
            self.log_result("Policy Suggestions", "FAIL", "No response")
            return
            
        if response.status_code != 200:
            self.log_result("Policy Suggestions", "FAIL", f"Status: {response.status_code}")
            return
            
        try:
            data = response.json()
            
            # Check for required fields in summary object
            summary = data.get("summary", {})
            required_fields = ["taxonomy_24h", "taxonomy_7d", "rules"]
            missing_fields = [field for field in required_fields if field not in summary]
            
            if missing_fields:
                self.log_result("Policy Suggestions", "FAIL", f"Missing fields in summary: {missing_fields}")
            else:
                taxonomy_24h_count = len(summary.get("taxonomy_24h", {}))
                taxonomy_7d_count = len(summary.get("taxonomy_7d", {}))
                rules_count = len(summary.get("rules", []))
                
                self.log_result("Policy Suggestions", "PASS", 
                              f"taxonomy_24h: {taxonomy_24h_count}, taxonomy_7d: {taxonomy_7d_count}, rules: {rules_count}")
                
        except Exception as e:
            self.log_result("Policy Suggestions", "FAIL", f"JSON parse error: {str(e)}")
    
    def test_permission_matrix(self):
        """Test 8: Permission matrix validation"""
        # Test key endpoints with different user types
        test_endpoints = [
            ("/api/admin/futures/strategy-control/drift-alerts", "GET"),
            ("/api/admin/futures/strategy-control/policy-suggestions", "GET"),
            (f"/api/admin/futures/strategy/{self.strategy_id}/rollback-snapshots", "GET")
        ]
        
        for endpoint, method in test_endpoints:
            # Test with ops user (should be read-only or blocked)
            response = self.make_request(method, endpoint, "ops")
            ops_status = response.status_code if response else "No response"
            
            # Test with admin_requester (should have limited access)
            response = self.make_request(method, endpoint, "admin_requester")
            admin_status = response.status_code if response else "No response"
            
            # Test with super_admin (should have full access)
            response = self.make_request(method, endpoint, "super_admin")
            super_status = response.status_code if response else "No response"
            
            # Evaluate permission matrix
            if super_status == 200:
                if ops_status == 403 and admin_status == 403:
                    permission_result = "PASS - Super admin only"
                elif ops_status == 200 and admin_status == 200:
                    permission_result = "PASS - Read access for all"
                else:
                    permission_result = f"PARTIAL - Mixed permissions"
            else:
                permission_result = f"FAIL - Super admin blocked"
            
            self.log_result(f"Permission Matrix {endpoint.split('/')[-1]}", "INFO", 
                          f"{permission_result} (ops: {ops_status}, admin: {admin_status}, super_admin: {super_status})")
    
    def run_all_tests(self):
        """Run all Faz-4+ / Faz-5 validation tests"""
        print("=" * 80)
        print("FAZ-4+ / FAZ-5 BACKEND FINAL VALIDATION (CORRECTED)")
        print("=" * 80)
        
        # Login all users
        for user_type in CREDENTIALS.keys():
            self.login_user(user_type)
        
        # Run all tests in order
        self.test_rollback_snapshots()
        self.test_rollback_request()
        self.test_approval_requests()
        self.test_drift_alerts()
        self.test_policy_suggestions()
        self.test_permission_matrix()
        
        # Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = sum(1 for r in self.test_results if r["status"] == "FAIL")
        partial = sum(1 for r in self.test_results if r["status"] == "PARTIAL")
        skipped = sum(1 for r in self.test_results if r["status"] == "SKIP")
        info = sum(1 for r in self.test_results if r["status"] == "INFO")
        total = passed + failed + partial + skipped
        
        print(f"TOTAL TESTS: {total}")
        print(f"PASSED: {passed}")
        print(f"FAILED: {failed}")
        print(f"PARTIAL: {partial}")
        print(f"SKIPPED: {skipped}")
        print(f"INFO: {info}")
        print(f"SUCCESS RATE: {(passed / total * 100):.1f}%" if total > 0 else "N/A")
        
        # Key findings
        print("\nKEY FINDINGS:")
        key_tests = [
            "Rollback Snapshots",
            "Rollback Request",
            "Drift Alerts", 
            "Policy Suggestions"
        ]
        
        for test_name in key_tests:
            result = next((r for r in self.test_results if r["test"] == test_name), None)
            if result:
                status_symbol = {"PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️", "SKIP": "⏭️"}.get(result["status"], "❓")
                print(f"{status_symbol} {test_name}: {result['status']}")
        
        return passed, failed, total

if __name__ == "__main__":
    validator = Faz4Faz5ValidatorCorrected()
    passed, failed, total = validator.run_all_tests()
    
    # Exit with appropriate code
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)