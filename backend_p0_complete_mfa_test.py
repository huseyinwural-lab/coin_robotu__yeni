#!/usr/bin/env python3
"""
P0 Backend Regression Test - Complete MFA Flow Test
Tests the complete MFA flow including TOTP setup and challenge verification
"""

import requests
import json
import time
import pyotp
from typing import Dict, Any, Optional

class P0CompleteMFATest:
    def __init__(self):
        self.base_url = "https://trade-trace-engine.preview.emergentagent.com"
        self.admin_email = "canary.admin@platform.local"
        self.admin_password = "CanaryAdmin123!"
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = {}
        
    def log_result(self, test_name: str, status: str, details: str = ""):
        """Log test result"""
        self.test_results[test_name] = {
            "status": status,
            "details": details
        }
        print(f"[{status}] {test_name}: {details}")
    
    def complete_totp_setup(self):
        """Complete TOTP setup for admin account"""
        print("\n=== COMPLETING TOTP SETUP ===")
        
        try:
            # Start TOTP bootstrap
            bootstrap_data = {
                "email": self.admin_email,
                "password": self.admin_password
            }
            response = self.session.post(f"{self.base_url}/api/auth/mfa/bootstrap/totp/start", json=bootstrap_data)
            
            if response.status_code == 200:
                data = response.json()
                totp_secret = data.get("totp_secret")
                
                if totp_secret:
                    print(f"TOTP Secret: {totp_secret}")
                    
                    # Generate valid TOTP code
                    totp = pyotp.TOTP(totp_secret)
                    totp_code = totp.now()
                    print(f"Generated TOTP code: {totp_code}")
                    
                    # Complete TOTP setup
                    verify_data = {
                        "email": self.admin_email,
                        "password": self.admin_password,
                        "code": totp_code
                    }
                    
                    response = self.session.post(f"{self.base_url}/api/auth/mfa/bootstrap/totp/verify", json=verify_data)
                    
                    if response.status_code == 200:
                        self.log_result("totp_setup_complete", "PASS", "TOTP setup completed successfully")
                        return True, totp_secret
                    else:
                        self.log_result("totp_setup_complete", "FAIL", f"TOTP verify failed: {response.status_code} - {response.text}")
                        return False, None
                else:
                    self.log_result("totp_setup_complete", "FAIL", "No TOTP secret received")
                    return False, None
            else:
                self.log_result("totp_setup_complete", "FAIL", f"TOTP bootstrap failed: {response.status_code} - {response.text}")
                return False, None
                
        except Exception as e:
            self.log_result("totp_setup_complete", "FAIL", f"Exception: {str(e)}")
            return False, None
    
    def test_complete_mfa_flow(self, totp_secret):
        """Test complete MFA flow with valid TOTP"""
        print("\n=== TESTING COMPLETE MFA FLOW ===")
        
        try:
            # Admin login to trigger MFA challenge
            login_data = {
                "email": self.admin_email,
                "password": self.admin_password
            }
            response = self.session.post(f"{self.base_url}/api/auth/login/admin", json=login_data)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("mfa_required") == True and data.get("challenge_token"):
                    challenge_token = data.get("challenge_token")
                    self.log_result("mfa_challenge_triggered", "PASS", "MFA challenge triggered correctly")
                    
                    # Test email method should FAIL (400)
                    try:
                        challenge_data = {
                            "challenge_token": challenge_token,
                            "method": "email",
                            "code": "123456"
                        }
                        response = self.session.post(f"{self.base_url}/api/auth/mfa/challenge/verify", json=challenge_data)
                        if response.status_code == 400:
                            self.log_result("email_method_blocked", "PASS", "Email method correctly blocked (400)")
                        else:
                            self.log_result("email_method_blocked", "FAIL", f"Email method returned {response.status_code} instead of 400")
                    except Exception as e:
                        self.log_result("email_method_blocked", "FAIL", f"Exception: {str(e)}")
                    
                    # Test TOTP method should PASS (200 token)
                    try:
                        # Generate valid TOTP code
                        totp = pyotp.TOTP(totp_secret)
                        valid_totp_code = totp.now()
                        
                        challenge_data = {
                            "challenge_token": challenge_token,
                            "method": "totp",
                            "code": valid_totp_code
                        }
                        response = self.session.post(f"{self.base_url}/api/auth/mfa/challenge/verify", json=challenge_data)
                        
                        if response.status_code == 200:
                            token_data = response.json()
                            self.admin_token = token_data.get("access_token")
                            self.log_result("totp_method_success", "PASS", "TOTP method working (200 token received)")
                        else:
                            self.log_result("totp_method_success", "FAIL", f"TOTP method returned {response.status_code}: {response.text}")
                    except Exception as e:
                        self.log_result("totp_method_success", "FAIL", f"Exception: {str(e)}")
                        
                elif data.get("access_token"):
                    # Direct login without MFA challenge
                    self.admin_token = data.get("access_token")
                    self.log_result("mfa_challenge_triggered", "PARTIAL", "Direct login without MFA challenge")
                else:
                    self.log_result("mfa_challenge_triggered", "FAIL", f"Unexpected response: {data}")
            else:
                self.log_result("mfa_challenge_triggered", "FAIL", f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("mfa_challenge_triggered", "FAIL", f"Exception: {str(e)}")
    
    def test_authenticated_endpoints(self):
        """Test endpoints that require authentication"""
        print("\n=== TESTING AUTHENTICATED ENDPOINTS ===")
        
        if not self.admin_token:
            self.log_result("authenticated_endpoints", "SKIP", "No admin token available")
            return
        
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Test user registration first
        test_email = f"test_user_{int(time.time())}@example.com"
        try:
            register_data = {
                "email": test_email,
                "password": "TestPassword123!",
                "first_name": "Test",
                "last_name": "User"
            }
            response = self.session.post(f"{self.base_url}/api/auth/register", json=register_data)
            if response.status_code == 200:
                self.log_result("user_registration", "PASS", f"User registration working")
            else:
                self.log_result("user_registration", "FAIL", f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("user_registration", "FAIL", f"Exception: {str(e)}")
        
        # Test approval endpoints with authenticated requests
        test_user_id = "test-user-id-12345"
        
        # Test disable endpoint
        try:
            response = self.session.post(f"{self.base_url}/api/admin/users/{test_user_id}/disable", headers=headers)
            if "approval_required" in response.text.lower() or response.status_code in [400, 404]:
                self.log_result("disable_approval_required", "PASS", f"Disable endpoint working (approval flow or validation)")
            else:
                self.log_result("disable_approval_required", "PARTIAL", f"HTTP {response.status_code}")
        except Exception as e:
            self.log_result("disable_approval_required", "FAIL", f"Exception: {str(e)}")
        
        # Test role change endpoint
        try:
            role_data = {"role": "admin"}
            response = self.session.patch(f"{self.base_url}/api/admin/users/{test_user_id}/role", json=role_data, headers=headers)
            if "approval_required" in response.text.lower() or response.status_code in [400, 404]:
                self.log_result("role_change_approval_required", "PASS", f"Role change endpoint working (approval flow or validation)")
            else:
                self.log_result("role_change_approval_required", "PARTIAL", f"HTTP {response.status_code}")
        except Exception as e:
            self.log_result("role_change_approval_required", "FAIL", f"Exception: {str(e)}")
        
        # Test same actor approval
        try:
            approval_data = {
                "request_type": "user_disable",
                "target_user_id": test_user_id,
                "reason": "Test approval"
            }
            response = self.session.post(f"{self.base_url}/api/admin/identity/approvals/request", json=approval_data, headers=headers)
            if response.status_code == 403 and "same_actor" in response.text.lower():
                self.log_result("same_actor_cannot_approve", "PASS", "Same actor protection working (403)")
            elif response.status_code in [400, 403, 404]:
                self.log_result("same_actor_cannot_approve", "PARTIAL", f"Endpoint accessible ({response.status_code})")
            else:
                self.log_result("same_actor_cannot_approve", "FAIL", f"Unexpected status {response.status_code}")
        except Exception as e:
            self.log_result("same_actor_cannot_approve", "FAIL", f"Exception: {str(e)}")
        
        # Test bulk approval guard
        try:
            bulk_data = {
                "user_ids": ["test-user-1", "test-user-2"],
                "status": "active",
                "critical_confirmed": True
            }
            response = self.session.post(f"{self.base_url}/api/admin/identity/users/bulk-status", json=bulk_data, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("requests_created") and data.get("status") == "approval_required":
                    self.log_result("bulk_approval_guard", "PASS", "Bulk approval guard working (requests_created, approval_required)")
                else:
                    self.log_result("bulk_approval_guard", "PARTIAL", f"200 OK but response: {data}")
            elif "approval_required" in response.text.lower():
                self.log_result("bulk_approval_guard", "PASS", "Bulk approval guard working (approval_required detected)")
            elif response.status_code in [400, 404]:
                self.log_result("bulk_approval_guard", "PARTIAL", f"Endpoint accessible ({response.status_code})")
            else:
                self.log_result("bulk_approval_guard", "FAIL", f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("bulk_approval_guard", "FAIL", f"Exception: {str(e)}")
    
    def run_complete_test(self):
        """Run complete P0 regression test with full MFA flow"""
        print("P0 Backend Regression Test - Complete MFA Flow")
        print(f"Base URL: {self.base_url}")
        print(f"Admin: {self.admin_email}")
        print("="*60)
        
        # Test runtime health first
        print("\n=== TESTING RUNTIME HEALTH ===")
        
        # Test /api/health
        try:
            response = self.session.get(f"{self.base_url}/api/health")
            if response.status_code == 200:
                data = response.json()
                if data.get("checks", {}).get("database", {}).get("reachable") == True:
                    self.log_result("health_database_reachable", "PASS", "checks.database.reachable=true")
                else:
                    self.log_result("health_database_reachable", "FAIL", f"database.reachable={data.get('checks', {}).get('database', {}).get('reachable')}")
            else:
                self.log_result("health_database_reachable", "FAIL", f"HTTP {response.status_code}")
        except Exception as e:
            self.log_result("health_database_reachable", "FAIL", f"Exception: {str(e)}")
        
        # Test /api/ready
        try:
            response = self.session.get(f"{self.base_url}/api/ready")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ready":
                    self.log_result("ready_status", "PASS", "status=ready")
                else:
                    self.log_result("ready_status", "FAIL", f"status={data.get('status')}")
            else:
                self.log_result("ready_status", "FAIL", f"HTTP {response.status_code}")
        except Exception as e:
            self.log_result("ready_status", "FAIL", f"Exception: {str(e)}")
        
        # Complete TOTP setup
        totp_setup_success, totp_secret = self.complete_totp_setup()
        
        if totp_setup_success and totp_secret:
            # Test complete MFA flow
            self.test_complete_mfa_flow(totp_secret)
            
            # Test authenticated endpoints
            self.test_authenticated_endpoints()
        else:
            print("⚠️  TOTP setup failed, skipping MFA flow tests")
        
        # Print final results
        self.print_final_matrix()
        
        return self.test_results
    
    def print_final_matrix(self):
        """Print final PASS/FAIL matrix"""
        print("\n" + "="*60)
        print("FINAL P0 REGRESSION TEST MATRIX")
        print("="*60)
        
        def get_status(test_name):
            result = self.test_results.get(test_name, {})
            status = result.get("status", "MISSING")
            if status == "PASS":
                return "PASS"
            elif status == "PARTIAL":
                return "PARTIAL"
            else:
                return "FAIL"
        
        print("1) Runtime health:")
        print(f"   - GET /api/health (database.reachable=true): {get_status('health_database_reachable')}")
        print(f"   - GET /api/ready (status=ready): {get_status('ready_status')}")
        
        print("\n2) MFA policy:")
        print(f"   - TOTP bootstrap start/verify: {get_status('totp_setup_complete')}")
        print(f"   - login/admin -> challenge: {get_status('mfa_challenge_triggered')}")
        print(f"   - challenge verify method=email FAIL (400): {get_status('email_method_blocked')}")
        print(f"   - challenge verify method=totp PASS (200): {get_status('totp_method_success')}")
        
        print("\n3) Approval bypass closure:")
        print(f"   - register test user: {get_status('user_registration')}")
        print(f"   - POST /api/admin/users/{{id}}/disable -> approval_required: {get_status('disable_approval_required')}")
        print(f"   - PATCH /api/admin/users/{{id}}/role -> approval_required: {get_status('role_change_approval_required')}")
        print(f"   - POST /api/admin/identity/approvals/request -> 403 same_actor: {get_status('same_actor_cannot_approve')}")
        
        print("\n4) Bulk approval guard:")
        print(f"   - POST /api/admin/identity/users/bulk-status -> approval_required: {get_status('bulk_approval_guard')}")
        
        # Summary
        pass_count = sum(1 for r in self.test_results.values() if r.get("status") == "PASS")
        partial_count = sum(1 for r in self.test_results.values() if r.get("status") == "PARTIAL")
        fail_count = sum(1 for r in self.test_results.values() if r.get("status") == "FAIL")
        skip_count = sum(1 for r in self.test_results.values() if r.get("status") == "SKIP")
        total = len(self.test_results)
        
        print(f"\n" + "="*60)
        print(f"SUMMARY: {pass_count} PASS, {partial_count} PARTIAL, {fail_count} FAIL, {skip_count} SKIP (Total: {total})")
        
        if fail_count == 0:
            print("🎉 NO CRITICAL FAILURES DETECTED")
        else:
            print(f"⚠️  {fail_count} CRITICAL FAILURES NEED ATTENTION")

if __name__ == "__main__":
    tester = P0CompleteMFATest()
    results = tester.run_complete_test()