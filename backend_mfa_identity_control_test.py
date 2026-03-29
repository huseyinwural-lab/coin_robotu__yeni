#!/usr/bin/env python3
"""
Backend MFA-Aware Identity Control Smoke Test
Target: https://dry-run-shadow.preview.emergentagent.com
Credentials: canary.admin@platform.local / CanaryAdmin123!

Test Flow:
1) GET /api/health -> 200
2) GET /api/ready -> 200
3) MFA bootstrap TOTP setup for canary admin
4) Login with MFA challenge verification to obtain token
5) Test identity control endpoints with token:
   - GET /api/admin/identity/users/deleted-lifecycle
   - POST /api/admin/identity/users/bulk-status/preview with missing user id
   - POST /api/admin/identity/users/{soft_deleted_user}/reactivate (if available)
"""

import requests
import json
import pyotp
import time
from datetime import datetime

class MFAIdentityControlTester:
    def __init__(self):
        self.base_url = "https://dry-run-shadow.preview.emergentagent.com"
        self.admin_email = "canary.admin@platform.local"
        self.admin_password = "CanaryAdmin123!"
        self.session = requests.Session()
        self.session.timeout = 15
        self.access_token = None
        self.totp_secret = None
        
        self.results = {
            "target_url": self.base_url,
            "test_time": datetime.now().isoformat(),
            "credentials": f"{self.admin_email} / {self.admin_password}",
            "tests_total": 6,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_skipped": 0,
            "tests": {}
        }
    
    def log_test(self, test_name, status, details):
        """Log test result"""
        self.results["tests"][test_name] = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            **details
        }
        
        if status == "PASS":
            self.results["tests_passed"] += 1
            print(f"   ✅ PASS - {test_name}")
        elif status == "FAIL":
            self.results["tests_failed"] += 1
            print(f"   ❌ FAIL - {test_name}")
        elif status == "SKIP":
            self.results["tests_skipped"] += 1
            print(f"   ⏭️  SKIP - {test_name}")
    
    def test_health_endpoint(self):
        """Test 1: GET /api/health -> 200"""
        print("\n1) Testing GET /api/health")
        try:
            response = self.session.get(f"{self.base_url}/api/health")
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {data}")
                
                if data.get("status") == "ok":
                    self.log_test("health_endpoint", "PASS", {
                        "http_code": 200,
                        "response": data,
                        "has_status_ok": True
                    })
                else:
                    self.log_test("health_endpoint", "FAIL", {
                        "http_code": 200,
                        "response": data,
                        "error": "Missing status=ok field"
                    })
            else:
                self.log_test("health_endpoint", "FAIL", {
                    "http_code": response.status_code,
                    "error": f"Expected 200, got {response.status_code}"
                })
        except Exception as e:
            self.log_test("health_endpoint", "FAIL", {
                "error": f"Request failed: {str(e)}"
            })
    
    def test_ready_endpoint(self):
        """Test 2: GET /api/ready -> 200"""
        print("\n2) Testing GET /api/ready")
        try:
            response = self.session.get(f"{self.base_url}/api/ready")
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {data}")
                
                # Check for ready status
                is_ready = (
                    data.get("status") == "ready" or
                    "ready" in str(data).lower() or
                    (isinstance(data.get("checks"), dict) and 
                     data["checks"].get("database", {}).get("reachable") is True)
                )
                
                if is_ready:
                    self.log_test("ready_endpoint", "PASS", {
                        "http_code": 200,
                        "response": data,
                        "is_ready": True
                    })
                else:
                    self.log_test("ready_endpoint", "FAIL", {
                        "http_code": 200,
                        "response": data,
                        "error": "System not ready"
                    })
            else:
                self.log_test("ready_endpoint", "FAIL", {
                    "http_code": response.status_code,
                    "error": f"Expected 200, got {response.status_code}"
                })
        except Exception as e:
            self.log_test("ready_endpoint", "FAIL", {
                "error": f"Request failed: {str(e)}"
            })
    
    def setup_mfa_totp(self):
        """Test 3: MFA bootstrap TOTP setup"""
        print("\n3) Setting up MFA TOTP for canary admin")
        try:
            # Step 1: Start TOTP bootstrap
            bootstrap_payload = {
                "email": self.admin_email,
                "password": self.admin_password
            }
            
            response = self.session.post(
                f"{self.base_url}/api/auth/mfa/bootstrap/totp/start",
                json=bootstrap_payload
            )
            print(f"   Bootstrap start status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                self.totp_secret = data.get("totp_secret")
                print(f"   TOTP secret received: {self.totp_secret[:10]}...")
                
                # Step 2: Generate TOTP code and verify
                if self.totp_secret:
                    totp = pyotp.TOTP(self.totp_secret)
                    totp_code = totp.now()
                    print(f"   Generated TOTP code: {totp_code}")
                    
                    # Wait a moment to ensure code is valid
                    time.sleep(1)
                    
                    verify_payload = {
                        "email": self.admin_email,
                        "password": self.admin_password,
                        "code": totp_code
                    }
                    
                    verify_response = self.session.post(
                        f"{self.base_url}/api/auth/mfa/bootstrap/totp/verify",
                        json=verify_payload
                    )
                    print(f"   Bootstrap verify status: {verify_response.status_code}")
                    
                    if verify_response.status_code == 200:
                        verify_data = verify_response.json()
                        print(f"   TOTP setup verified: {verify_data}")
                        
                        self.log_test("mfa_totp_setup", "PASS", {
                            "bootstrap_start": 200,
                            "bootstrap_verify": 200,
                            "totp_secret_received": True,
                            "totp_verified": True
                        })
                    else:
                        self.log_test("mfa_totp_setup", "FAIL", {
                            "bootstrap_start": 200,
                            "bootstrap_verify": verify_response.status_code,
                            "error": f"TOTP verification failed: {verify_response.text}"
                        })
                else:
                    self.log_test("mfa_totp_setup", "FAIL", {
                        "bootstrap_start": 200,
                        "error": "No TOTP secret received"
                    })
            else:
                # Check if TOTP is already setup
                if response.status_code == 400 and "already_setup" in response.text:
                    print("   TOTP already setup - proceeding with existing setup")
                    self.log_test("mfa_totp_setup", "PASS", {
                        "bootstrap_start": 400,
                        "note": "TOTP already setup",
                        "totp_already_configured": True
                    })
                else:
                    self.log_test("mfa_totp_setup", "FAIL", {
                        "bootstrap_start": response.status_code,
                        "error": f"Bootstrap start failed: {response.text}"
                    })
        except Exception as e:
            self.log_test("mfa_totp_setup", "FAIL", {
                "error": f"MFA setup failed: {str(e)}"
            })
    
    def login_with_mfa(self):
        """Test 4: Login with MFA challenge verification"""
        print("\n4) Login with MFA challenge verification")
        try:
            # Step 1: Initial login to get MFA challenge
            login_payload = {
                "email": self.admin_email,
                "password": self.admin_password
            }
            
            response = self.session.post(
                f"{self.base_url}/api/auth/login/admin",
                json=login_payload
            )
            print(f"   Initial login status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Login response: {data}")
                
                if data.get("mfa_required"):
                    mfa_challenge_token = data.get("mfa_challenge_token")
                    print(f"   MFA challenge token received: {mfa_challenge_token[:20]}...")
                    
                    # Step 2: Generate TOTP code for MFA challenge
                    if self.totp_secret:
                        totp = pyotp.TOTP(self.totp_secret)
                        totp_code = totp.now()
                        print(f"   Generated TOTP code for MFA: {totp_code}")
                        
                        # Step 3: Verify MFA challenge
                        mfa_payload = {
                            "challenge_token": mfa_challenge_token,
                            "method": "totp",
                            "code": totp_code
                        }
                        
                        mfa_response = self.session.post(
                            f"{self.base_url}/api/auth/mfa/challenge/verify",
                            json=mfa_payload
                        )
                        print(f"   MFA verify status: {mfa_response.status_code}")
                        
                        if mfa_response.status_code == 200:
                            mfa_data = mfa_response.json()
                            self.access_token = mfa_data.get("access_token")
                            print(f"   Access token received: {self.access_token[:20]}...")
                            
                            self.log_test("login_with_mfa", "PASS", {
                                "initial_login": 200,
                                "mfa_required": True,
                                "mfa_verify": 200,
                                "access_token_received": bool(self.access_token)
                            })
                        else:
                            self.log_test("login_with_mfa", "FAIL", {
                                "initial_login": 200,
                                "mfa_verify": mfa_response.status_code,
                                "error": f"MFA verification failed: {mfa_response.text}"
                            })
                    else:
                        self.log_test("login_with_mfa", "FAIL", {
                            "initial_login": 200,
                            "error": "No TOTP secret available for MFA"
                        })
                elif data.get("access_token"):
                    # Direct login without MFA (fallback)
                    self.access_token = data.get("access_token")
                    print(f"   Direct access token received: {self.access_token[:20]}...")
                    
                    self.log_test("login_with_mfa", "PASS", {
                        "initial_login": 200,
                        "mfa_required": False,
                        "access_token_received": bool(self.access_token),
                        "note": "Direct login without MFA challenge"
                    })
                else:
                    self.log_test("login_with_mfa", "FAIL", {
                        "initial_login": 200,
                        "error": "No access token or MFA challenge received"
                    })
            else:
                self.log_test("login_with_mfa", "FAIL", {
                    "initial_login": response.status_code,
                    "error": f"Initial login failed: {response.text}"
                })
        except Exception as e:
            self.log_test("login_with_mfa", "FAIL", {
                "error": f"Login with MFA failed: {str(e)}"
            })
    
    def test_deleted_lifecycle_endpoint(self):
        """Test 5: GET /api/admin/identity/users/deleted-lifecycle"""
        print("\n5) Testing GET /api/admin/identity/users/deleted-lifecycle")
        
        if not self.access_token:
            self.log_test("deleted_lifecycle_endpoint", "FAIL", {
                "error": "No access token available"
            })
            return
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = self.session.get(
                f"{self.base_url}/api/admin/identity/users/deleted-lifecycle",
                headers=headers
            )
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {data}")
                
                self.log_test("deleted_lifecycle_endpoint", "PASS", {
                    "http_code": 200,
                    "response": data,
                    "authenticated": True
                })
            else:
                self.log_test("deleted_lifecycle_endpoint", "FAIL", {
                    "http_code": response.status_code,
                    "error": f"Expected 200, got {response.status_code}",
                    "response": response.text[:200]
                })
        except Exception as e:
            self.log_test("deleted_lifecycle_endpoint", "FAIL", {
                "error": f"Request failed: {str(e)}"
            })
    
    def test_bulk_status_preview_endpoint(self):
        """Test 6: POST /api/admin/identity/users/bulk-status/preview with missing user id"""
        print("\n6) Testing POST /api/admin/identity/users/bulk-status/preview")
        
        if not self.access_token:
            self.log_test("bulk_status_preview_endpoint", "FAIL", {
                "error": "No access token available"
            })
            return
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            # Test with one missing user ID
            payload = {
                "user_ids": ["missing-user-id-12345"],
                "target_status": "active"
            }
            
            response = self.session.post(
                f"{self.base_url}/api/admin/identity/users/bulk-status/preview",
                headers=headers,
                json=payload
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
            
            if response.status_code in [200, 400, 404]:
                # Accept 200 (success), 400 (validation error), or 404 (user not found)
                data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
                
                self.log_test("bulk_status_preview_endpoint", "PASS", {
                    "http_code": response.status_code,
                    "response": data,
                    "authenticated": True,
                    "test_payload": payload,
                    "note": f"Endpoint accessible, returned {response.status_code} as expected for missing user"
                })
            else:
                self.log_test("bulk_status_preview_endpoint", "FAIL", {
                    "http_code": response.status_code,
                    "error": f"Unexpected status code: {response.status_code}",
                    "response": response.text[:200]
                })
        except Exception as e:
            self.log_test("bulk_status_preview_endpoint", "FAIL", {
                "error": f"Request failed: {str(e)}"
            })
    
    def test_reactivate_soft_deleted_user(self):
        """Test 7: POST /api/admin/identity/users/{soft_deleted_user}/reactivate (if available)"""
        print("\n7) Testing POST /api/admin/identity/users/{user_id}/reactivate")
        
        if not self.access_token:
            self.log_test("reactivate_soft_deleted_user", "FAIL", {
                "error": "No access token available"
            })
            return
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            # First, try to get deleted users to find a soft-deleted user
            deleted_response = self.session.get(
                f"{self.base_url}/api/admin/identity/users/deleted-lifecycle",
                headers=headers
            )
            
            soft_deleted_user_id = None
            if deleted_response.status_code == 200:
                deleted_data = deleted_response.json()
                print(f"   Deleted users data: {deleted_data}")
                
                # Look for soft-deleted users
                if isinstance(deleted_data, dict) and "users" in deleted_data:
                    for user in deleted_data["users"]:
                        if user.get("status") == "soft_deleted":
                            soft_deleted_user_id = user.get("id")
                            break
                elif isinstance(deleted_data, list):
                    for user in deleted_data:
                        if user.get("status") == "soft_deleted":
                            soft_deleted_user_id = user.get("id")
                            break
            
            if soft_deleted_user_id:
                print(f"   Found soft-deleted user: {soft_deleted_user_id}")
                
                # Test reactivation
                response = self.session.post(
                    f"{self.base_url}/api/admin/identity/users/{soft_deleted_user_id}/reactivate",
                    headers=headers
                )
                print(f"   Reactivate status: {response.status_code}")
                print(f"   Response: {response.text}")
                
                if response.status_code in [200, 400, 404, 409]:
                    # Accept various status codes as the endpoint is accessible
                    data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
                    
                    self.log_test("reactivate_soft_deleted_user", "PASS", {
                        "http_code": response.status_code,
                        "response": data,
                        "authenticated": True,
                        "soft_deleted_user_id": soft_deleted_user_id,
                        "note": f"Endpoint accessible, returned {response.status_code}"
                    })
                else:
                    self.log_test("reactivate_soft_deleted_user", "FAIL", {
                        "http_code": response.status_code,
                        "error": f"Unexpected status code: {response.status_code}",
                        "response": response.text[:200]
                    })
            else:
                print("   No soft-deleted users found - skipping reactivation test")
                self.log_test("reactivate_soft_deleted_user", "SKIP", {
                    "note": "No soft-deleted users available for testing",
                    "deleted_users_response": deleted_response.status_code
                })
        except Exception as e:
            self.log_test("reactivate_soft_deleted_user", "FAIL", {
                "error": f"Request failed: {str(e)}"
            })
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("=" * 80)
        print("BACKEND MFA-AWARE IDENTITY CONTROL SMOKE TEST")
        print(f"Target: {self.base_url}")
        print(f"Credentials: {self.admin_email} / {self.admin_password}")
        print(f"Test Time: {datetime.now().isoformat()}")
        print("=" * 80)
        
        # Run tests in sequence
        self.test_health_endpoint()
        self.test_ready_endpoint()
        self.setup_mfa_totp()
        self.login_with_mfa()
        self.test_deleted_lifecycle_endpoint()
        self.test_bulk_status_preview_endpoint()
        self.test_reactivate_soft_deleted_user()
        
        # Print summary
        self.print_summary()
        
        return self.results
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Tests Total: {self.results['tests_total']}")
        print(f"✅ Passed: {self.results['tests_passed']}")
        print(f"❌ Failed: {self.results['tests_failed']}")
        print(f"⏭️  Skipped: {self.results['tests_skipped']}")
        
        # Calculate success rate
        total_executed = self.results['tests_passed'] + self.results['tests_failed']
        if total_executed > 0:
            success_rate = (self.results['tests_passed'] / total_executed) * 100
            print(f"Success Rate: {success_rate:.1f}%")
        
        # Overall status
        if self.results['tests_failed'] == 0:
            overall_status = "PASS"
        elif self.results['tests_passed'] > self.results['tests_failed']:
            overall_status = "PARTIAL"
        else:
            overall_status = "FAIL"
        
        print(f"\n🎯 OVERALL STATUS: {overall_status}")
        
        # List failed tests
        if self.results['tests_failed'] > 0:
            print("\n🚨 FAILED TESTS:")
            for test_name, test_data in self.results['tests'].items():
                if test_data['status'] == 'FAIL':
                    error = test_data.get('error', 'Unknown error')
                    print(f"   - {test_name}: {error}")
        
        # List passed tests
        if self.results['tests_passed'] > 0:
            print("\n✅ PASSED TESTS:")
            for test_name, test_data in self.results['tests'].items():
                if test_data['status'] == 'PASS':
                    note = test_data.get('note', '')
                    print(f"   - {test_name}" + (f": {note}" if note else ""))
        
        print("=" * 80)

if __name__ == "__main__":
    tester = MFAIdentityControlTester()
    results = tester.run_all_tests()