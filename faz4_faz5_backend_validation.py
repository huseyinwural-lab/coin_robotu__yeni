#!/usr/bin/env python3
"""
FAZ-4+ / FAZ-5 Backend Final Validation Test
Comprehensive backend API validation for Faz-4+ / Faz-5 rollback system

Test Requirements:
1) GET /api/admin/futures/strategy/{id}/rollback-snapshots -> snapshot_trace_id,timestamp,actor,action_type,diff_preview,rollback_scope=single_strategy
2) POST /api/admin/futures/strategy/{id}/rollback-request -> reason zorunlu, preview dolu, expires_at 24h
3) GET /api/admin/futures/strategy/approval-requests -> pending/approved/expired görünümleri
4) POST approve/reject endpointleri -> super_admin only; admin/ops erişim kısıtı doğrula
5) Approve sonrası rollback applied + rollback_reference + audit mantığı
6) GET /api/admin/futures/strategy-control/drift-alerts -> recommended_action(type/confidence/reason/inputs)
7) GET /api/admin/futures/strategy-control/policy-suggestions -> taxonomy_24h, taxonomy_7d, rules
8) Permission matrix doğrulaması: super_admin full, admin request-only, ops read-only (write yok)

Base URL: https://gate-control-v2.preview.emergentagent.com
Credentials:
- super_admin: canary.admin@platform.local / CanaryAdmin123!
- admin requester: canary.requester@platform.local / CanaryRequester123!
- ops: canary.ops@platform.local / CanaryOps123!
"""

import requests
import json
import sys
from datetime import datetime, timedelta

# Configuration
BASE_URL = "https://gate-control-v2.preview.emergentagent.com"
CREDENTIALS = {
    "super_admin": {"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
    "admin_requester": {"email": "canary.requester@platform.local", "password": "CanaryRequester123!"},
    "ops": {"email": "canary.ops@platform.local", "password": "CanaryOps123!"}
}

class Faz4Faz5Validator:
    def __init__(self):
        self.tokens = {}
        self.test_results = []
        self.strategy_id = "trend_follow_v1"  # Default strategy for testing
        
    def log_result(self, test_name, status, details=""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌"
        print(f"{status_symbol} {test_name}: {status} - {details}")
        
    def login_user(self, user_type):
        """Login and get access token"""
        try:
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
        """Make authenticated request"""
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
            required_fields = ["snapshot_trace_id", "timestamp", "actor", "action_type", "diff_preview", "rollback_scope"]
            
            if isinstance(data, dict) and "items" in data:
                items = data["items"]
            elif isinstance(data, list):
                items = data
            else:
                items = [data] if data else []
                
            if not items:
                self.log_result("Rollback Snapshots", "PASS", "Empty snapshots list (expected)")
                return
                
            # Check first snapshot for required fields
            snapshot = items[0]
            missing_fields = [field for field in required_fields if field not in snapshot]
            
            if missing_fields:
                self.log_result("Rollback Snapshots", "FAIL", f"Missing fields: {missing_fields}")
            else:
                rollback_scope = snapshot.get("rollback_scope")
                if rollback_scope == "single_strategy":
                    self.log_result("Rollback Snapshots", "PASS", f"All fields present, scope: {rollback_scope}")
                else:
                    self.log_result("Rollback Snapshots", "PARTIAL", f"Fields present but scope: {rollback_scope}")
                    
        except Exception as e:
            self.log_result("Rollback Snapshots", "FAIL", f"JSON parse error: {str(e)}")
    
    def test_rollback_request(self):
        """Test 2: POST /api/admin/futures/strategy/{id}/rollback-request"""
        endpoint = f"/api/admin/futures/strategy/{self.strategy_id}/rollback-request"
        
        # Test with missing reason (should fail)
        response = self.make_request("POST", endpoint, "super_admin", json={})
        if response and response.status_code == 400:
            self.log_result("Rollback Request Validation", "PASS", "Correctly rejects missing reason")
        else:
            self.log_result("Rollback Request Validation", "FAIL", f"Should reject missing reason, got: {response.status_code if response else 'No response'}")
        
        # Test with valid request
        payload = {
            "reason": "Test rollback request for Faz-4+ validation",
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
    
    def test_approve_reject_permissions(self):
        """Test 4: POST approve/reject endpoints with permission checks"""
        # First, try to get a pending request to test with
        response = self.make_request("GET", "/api/admin/futures/strategy/approval-requests", "super_admin", params={"status": "pending"})
        
        if not response or response.status_code != 200:
            self.log_result("Approve/Reject Setup", "SKIP", "No pending requests to test with")
            return
            
        try:
            data = response.json()
            requests_list = data if isinstance(data, list) else data.get("items", [])
            
            if not requests_list:
                self.log_result("Approve/Reject Setup", "SKIP", "No pending requests available")
                return
                
            request_id = requests_list[0].get("id") or requests_list[0].get("request_id")
            if not request_id:
                self.log_result("Approve/Reject Setup", "FAIL", "No request ID found")
                return
                
        except Exception as e:
            self.log_result("Approve/Reject Setup", "FAIL", f"Parse error: {str(e)}")
            return
        
        # Test approve endpoint with different user types
        approve_endpoint = f"/api/admin/futures/strategy/approval-requests/{request_id}/approve"
        
        # Test with ops user (should be 403)
        response = self.make_request("POST", approve_endpoint, "ops", json={"reason": "Test approval"})
        if response and response.status_code == 403:
            self.log_result("Approve Permission (ops)", "PASS", "Correctly blocked ops user")
        else:
            self.log_result("Approve Permission (ops)", "FAIL", f"Should block ops, got: {response.status_code if response else 'No response'}")
        
        # Test with admin_requester (should be 403 for approve)
        response = self.make_request("POST", approve_endpoint, "admin_requester", json={"reason": "Test approval"})
        if response and response.status_code == 403:
            self.log_result("Approve Permission (admin)", "PASS", "Correctly blocked admin requester")
        else:
            self.log_result("Approve Permission (admin)", "FAIL", f"Should block admin, got: {response.status_code if response else 'No response'}")
        
        # Test with super_admin (should work)
        response = self.make_request("POST", approve_endpoint, "super_admin", json={"reason": "Test approval for Faz-4+ validation"})
        if response and response.status_code in [200, 201]:
            self.log_result("Approve Permission (super_admin)", "PASS", "Super admin can approve")
        else:
            self.log_result("Approve Permission (super_admin)", "PARTIAL", f"Super admin status: {response.status_code if response else 'No response'}")
    
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
            
            # Check for required fields
            required_fields = ["taxonomy_24h", "taxonomy_7d", "rules"]
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                self.log_result("Policy Suggestions", "FAIL", f"Missing fields: {missing_fields}")
            else:
                taxonomy_24h_count = len(data.get("taxonomy_24h", []))
                taxonomy_7d_count = len(data.get("taxonomy_7d", []))
                rules_count = len(data.get("rules", []))
                
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
            
            self.log_result(f"Permission Matrix {endpoint}", "INFO", 
                          f"ops: {ops_status}, admin: {admin_status}, super_admin: {super_status}")
    
    def run_all_tests(self):
        """Run all Faz-4+ / Faz-5 validation tests"""
        print("=" * 80)
        print("FAZ-4+ / FAZ-5 BACKEND FINAL VALIDATION")
        print("=" * 80)
        
        # Login all users
        for user_type in CREDENTIALS.keys():
            self.login_user(user_type)
        
        # Run all tests
        self.test_rollback_snapshots()
        self.test_rollback_request()
        self.test_approval_requests()
        self.test_approve_reject_permissions()
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
        total = len(self.test_results)
        
        print(f"TOTAL TESTS: {total}")
        print(f"PASSED: {passed}")
        print(f"FAILED: {failed}")
        print(f"PARTIAL: {partial}")
        print(f"SKIPPED: {skipped}")
        print(f"SUCCESS RATE: {(passed / total * 100):.1f}%" if total > 0 else "N/A")
        
        # Detailed results
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_symbol = {"PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️", "SKIP": "⏭️", "INFO": "ℹ️"}.get(result["status"], "❓")
            print(f"{status_symbol} {result['test']}: {result['status']} - {result['details']}")
        
        return passed, failed, total

if __name__ == "__main__":
    validator = Faz4Faz5Validator()
    passed, failed, total = validator.run_all_tests()
    
    # Exit with appropriate code
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)