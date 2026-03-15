#!/usr/bin/env python3

import requests
import json
import os
import sys
import uuid
from datetime import datetime

# Get backend URL from environment variable
BACKEND_URL = os.getenv("REACT_APP_BACKEND_URL", "https://market-scanner-prod.preview.emergentagent.com")
API_BASE = f"{BACKEND_URL}/api"

# Test credentials
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"

class BackendRegressionTest:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = []
        self.test_user_email = None
        self.test_user_password = "TestUser123!"
        
    def log_result(self, test_name, success, details, endpoint=None):
        """Log test result"""
        status = "PASS" if success else "FAIL"
        self.test_results.append({
            "test": test_name,
            "status": status,
            "details": details,
            "endpoint": endpoint,
            "timestamp": datetime.now().isoformat()
        })
        print(f"[{status}] {test_name}: {details}")
        if endpoint:
            print(f"    Endpoint: {endpoint}")
        
    def login_admin(self):
        """Test admin login with provided credentials"""
        try:
            response = self.session.post(
                f"{API_BASE}/auth/login/admin",
                json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    # Set authorization header for subsequent requests
                    self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
                    self.log_result("Admin Login", True, f"Successfully logged in as {ADMIN_EMAIL}", "POST /api/auth/login/admin")
                    return True
                else:
                    self.log_result("Admin Login", False, "No access token received", "POST /api/auth/login/admin")
                    return False
            else:
                self.log_result("Admin Login", False, f"Status {response.status_code}: {response.text}", "POST /api/auth/login/admin")
                return False
                
        except Exception as e:
            self.log_result("Admin Login", False, f"Exception: {str(e)}", "POST /api/auth/login/admin")
            return False

    def test_admin_create_endpoint(self):
        """Test POST /api/admin/users/admin-create - admin can create admin users (expect 201)"""
        try:
            # Generate unique email for test admin
            unique_id = str(uuid.uuid4())[:8]
            test_admin_email = f"test_admin_{unique_id}@test.com"
            
            response = self.session.post(
                f"{API_BASE}/admin/users/admin-create",
                json={
                    "email": test_admin_email,
                    "password": "TestAdmin123!",
                    "role": "admin"
                }
            )
            
            if response.status_code == 201:
                data = response.json()
                created_email = data.get("email")
                created_role = data.get("role")
                self.log_result("Admin Create - Success", True, 
                               f"Successfully created admin user: {created_email} with role: {created_role}",
                               "POST /api/admin/users/admin-create")
                return True
            else:
                self.log_result("Admin Create - Failed", False, 
                               f"Expected 201, got {response.status_code}: {response.text}",
                               "POST /api/admin/users/admin-create")
                return False
                
        except Exception as e:
            self.log_result("Admin Create - Exception", False, f"Exception: {str(e)}", "POST /api/admin/users/admin-create")
            return False

    def test_scope_separation_admin(self):
        """Test GET /api/admin/users?scope=admin - should return only super_admin/admin/ops roles"""
        try:
            response = self.session.get(f"{API_BASE}/admin/users?scope=admin")
            
            if response.status_code == 200:
                users = response.json()
                admin_roles = {"super_admin", "admin", "ops"}
                
                # Check all users have admin roles
                all_admin_roles = True
                non_admin_users = []
                
                for user in users:
                    user_role = user.get("role")
                    if user_role not in admin_roles:
                        all_admin_roles = False
                        non_admin_users.append(f"{user.get('email')} ({user_role})")
                
                if all_admin_roles:
                    roles_found = set(user.get("role") for user in users)
                    self.log_result("Scope Admin - Correct Filtering", True, 
                                   f"Found {len(users)} admin users with roles: {roles_found}",
                                   "GET /api/admin/users?scope=admin")
                    return True
                else:
                    self.log_result("Scope Admin - Wrong Roles", False, 
                                   f"Found non-admin users: {non_admin_users}",
                                   "GET /api/admin/users?scope=admin")
                    return False
            else:
                self.log_result("Scope Admin - Failed", False, 
                               f"Status {response.status_code}: {response.text}",
                               "GET /api/admin/users?scope=admin")
                return False
                
        except Exception as e:
            self.log_result("Scope Admin - Exception", False, f"Exception: {str(e)}", "GET /api/admin/users?scope=admin")
            return False

    def test_scope_separation_user(self):
        """Test GET /api/admin/users?scope=user - should return only role=user with approval_status=approved"""
        try:
            response = self.session.get(f"{API_BASE}/admin/users?scope=user")
            
            if response.status_code == 200:
                users = response.json()
                
                # Check all users have role=user and approval_status=approved
                all_valid_users = True
                invalid_users = []
                
                for user in users:
                    user_role = user.get("role")
                    approval_status = user.get("approval_status")
                    
                    if user_role != "user" or approval_status != "approved":
                        all_valid_users = False
                        invalid_users.append(f"{user.get('email')} (role:{user_role}, status:{approval_status})")
                
                if all_valid_users:
                    self.log_result("Scope User - Correct Filtering", True, 
                                   f"Found {len(users)} approved user accounts",
                                   "GET /api/admin/users?scope=user")
                    return True
                else:
                    self.log_result("Scope User - Wrong Filtering", False, 
                                   f"Found invalid users: {invalid_users}",
                                   "GET /api/admin/users?scope=user")
                    return False
            else:
                self.log_result("Scope User - Failed", False, 
                               f"Status {response.status_code}: {response.text}",
                               "GET /api/admin/users?scope=user")
                return False
                
        except Exception as e:
            self.log_result("Scope User - Exception", False, f"Exception: {str(e)}", "GET /api/admin/users?scope=user")
            return False

    def test_register_user_pending(self):
        """Test /api/auth/register - new user should be pending"""
        try:
            # Generate unique email for test user
            unique_id = str(uuid.uuid4())[:8]
            self.test_user_email = f"test_user_{unique_id}@test.com"
            
            response = self.session.post(
                f"{API_BASE}/auth/register",
                json={
                    "email": self.test_user_email,
                    "password": self.test_user_password
                }
            )
            
            if response.status_code == 200:
                user_data = response.json()
                approval_status = user_data.get("approval_status")
                
                if approval_status == "pending":
                    self.log_result("Register User - Pending Status", True, 
                                   f"User {self.test_user_email} registered with pending status",
                                   "POST /api/auth/register")
                    return True
                else:
                    self.log_result("Register User - Wrong Status", False, 
                                   f"Expected 'pending', got '{approval_status}'",
                                   "POST /api/auth/register")
                    return False
            else:
                self.log_result("Register User - Failed", False, 
                               f"Status {response.status_code}: {response.text}",
                               "POST /api/auth/register")
                return False
                
        except Exception as e:
            self.log_result("Register User - Exception", False, f"Exception: {str(e)}", "POST /api/auth/register")
            return False

    def test_login_user_pending_403(self):
        """Test /api/auth/login/user - pending user should get 403"""
        if not self.test_user_email:
            self.log_result("Login Pending User - Skipped", False, "No test user created", "POST /api/auth/login/user")
            return False
            
        try:
            response = self.session.post(
                f"{API_BASE}/auth/login/user",
                json={
                    "email": self.test_user_email,
                    "password": self.test_user_password
                }
            )
            
            if response.status_code == 403:
                self.log_result("Login Pending User - Correct 403", True, 
                               "Pending user correctly rejected with 403",
                               "POST /api/auth/login/user")
                return True
            else:
                self.log_result("Login Pending User - Wrong Status", False, 
                               f"Expected 403, got {response.status_code}: {response.text}",
                               "POST /api/auth/login/user")
                return False
                
        except Exception as e:
            self.log_result("Login Pending User - Exception", False, f"Exception: {str(e)}", "POST /api/auth/login/user")
            return False

    def test_approve_user_integration(self):
        """Test approval flow - find test user and approve, then check scope=user list"""
        if not self.test_user_email:
            self.log_result("User Approval Integration - Skipped", False, "No test user created", "Multiple endpoints")
            return False
            
        try:
            # First, find the test user in pending list
            response = self.session.get(f"{API_BASE}/auth/admin/user-approval-requests?status=pending")
            
            if response.status_code != 200:
                self.log_result("User Approval - Get Pending Failed", False, 
                               f"Status {response.status_code}: {response.text}",
                               "GET /api/auth/admin/user-approval-requests")
                return False
            
            pending_users = response.json()
            test_user_id = None
            
            for user in pending_users:
                if user.get("email") == self.test_user_email:
                    test_user_id = user.get("id")
                    break
            
            if not test_user_id:
                self.log_result("User Approval - User Not Found", False, 
                               f"Test user {self.test_user_email} not found in pending list",
                               "GET /api/auth/admin/user-approval-requests")
                return False
            
            # Approve the user
            response = self.session.post(f"{API_BASE}/auth/admin/user-approval-requests/{test_user_id}/approve")
            
            if response.status_code != 200:
                self.log_result("User Approval - Approve Failed", False, 
                               f"Status {response.status_code}: {response.text}",
                               "POST /api/auth/admin/user-approval-requests/{id}/approve")
                return False
            
            # Check if user now appears in scope=user list
            response = self.session.get(f"{API_BASE}/admin/users?scope=user")
            
            if response.status_code != 200:
                self.log_result("User Approval - Scope Check Failed", False, 
                               f"Status {response.status_code}: {response.text}",
                               "GET /api/admin/users?scope=user")
                return False
            
            approved_users = response.json()
            user_found = any(user.get("email") == self.test_user_email for user in approved_users)
            
            if user_found:
                self.log_result("User Approval Integration - Success", True, 
                               f"User {self.test_user_email} successfully approved and appears in scope=user",
                               "Full approval flow")
                return True
            else:
                self.log_result("User Approval Integration - Not in Scope", False, 
                               f"Approved user {self.test_user_email} not found in scope=user list",
                               "Full approval flow")
                return False
                
        except Exception as e:
            self.log_result("User Approval Integration - Exception", False, f"Exception: {str(e)}", "Full approval flow")
            return False

    def run_all_tests(self):
        """Run all backend regression tests"""
        print("=" * 80)
        print("BACKEND REGRESSION AND NEW FEATURE TESTING")
        print("=" * 80)
        print(f"Backend URL: {BACKEND_URL}")
        print(f"Admin Credentials: {ADMIN_EMAIL}")
        print("=" * 80)
        
        # Login first
        if not self.login_admin():
            print("\n❌ CRITICAL: Admin login failed - cannot continue with tests")
            return False
            
        print("\n🔄 Testing POST /api/admin/users/admin-create (admin role creating admin - expect 201)...")
        self.test_admin_create_endpoint()
        
        print("\n🔄 Testing GET /api/admin/users?scope=admin (should return super_admin/admin/ops only)...")
        self.test_scope_separation_admin()
        
        print("\n🔄 Testing GET /api/admin/users?scope=user (should return role=user, approved only)...")
        self.test_scope_separation_user()
        
        print("\n🔄 Testing POST /api/auth/register (new user should be pending)...")
        self.test_register_user_pending()
        
        print("\n🔄 Testing POST /api/auth/login/user (pending user should get 403)...")
        self.test_login_user_pending_403()
        
        print("\n🔄 Testing approval integration (approve user, check scope=user list)...")
        self.test_approve_user_integration()
        
        # Summary
        print("\n" + "=" * 80)
        print("BACKEND REGRESSION TEST RESULTS")
        print("=" * 80)
        
        passed = sum(1 for result in self.test_results if result["status"] == "PASS")
        failed = sum(1 for result in self.test_results if result["status"] == "FAIL")
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print(f"Success Rate: {(passed/total*100):.1f}%" if total > 0 else "N/A")
        
        # Detailed results by endpoint
        print("\n📊 RESULTS BY ENDPOINT:")
        print("-" * 40)
        
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌"
            endpoint = result.get("endpoint", "N/A")
            print(f"{status_icon} {result['test']}")
            print(f"    {endpoint}")
            if result["status"] == "FAIL":
                print(f"    Error: {result['details']}")
            print()
        
        if failed > 0:
            print("\n❌ FAILED TESTS SUMMARY:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"  - {result['test']}: {result['details']}")
        else:
            print("\n✅ ALL TESTS PASSED!")
        
        print("\n" + "=" * 80)
        
        return failed == 0


def main():
    """Main test runner"""
    tester = BackendRegressionTest()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()