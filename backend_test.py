#!/usr/bin/env python3
"""
FAZ-2B Drift Closure Validation Test
Backend regression tests for API endpoints
"""

import requests
import json
import sys
import uuid


class FAZ2BValidationTest:
    def __init__(self):
        self.base_url = "https://market-scanner-prod.preview.emergentagent.com"
        self.admin_token = None
        self.test_user_email = f"test_user_faz2b_{uuid.uuid4().hex[:8]}@test.com"
        self.test_user_password = "TestPassword123!"
        self.test_user_id = None
        self.user_token = None
        
    def test_health_endpoint(self):
        """Test 1: GET /api/health"""
        print("=" * 60)
        print("TEST 1: Health Endpoint")
        print("=" * 60)
        
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=10)
            print(f"GET /api/health")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Response: {json.dumps(data, indent=2)}")
                if data.get('status') == 'ok':
                    print("✅ PASS: Health endpoint working correctly")
                    return True
                else:
                    print("❌ FAIL: Health endpoint returned wrong status")
                    return False
            else:
                print(f"❌ FAIL: Health endpoint returned {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: Health endpoint error - {e}")
            return False
    
    def test_admin_login(self):
        """Test 2: POST /api/auth/login/admin"""
        print("\n" + "=" * 60)
        print("TEST 2: Admin Login")
        print("=" * 60)
        
        try:
            payload = {
                "email": "admin@platform.dev",
                "password": "Admin12345!"
            }
            
            response = requests.post(
                f"{self.base_url}/api/auth/login/admin",
                json=payload,
                timeout=10
            )
            
            print(f"POST /api/auth/login/admin")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ PASS: Admin login successful")
                self.admin_token = data.get('access_token')
                print(f"Token obtained: {self.admin_token[:20]}...")
                return True
            else:
                print(f"❌ FAIL: Admin login failed with {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: Admin login error - {e}")
            return False
    
    def test_admin_universe_monitor(self):
        """Test 3: GET /api/admin/universe-monitor"""
        print("\n" + "=" * 60)
        print("TEST 3: Admin Universe Monitor")
        print("=" * 60)
        
        if not self.admin_token:
            print("❌ FAIL: No admin token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(
                f"{self.base_url}/api/admin/universe-monitor",
                headers=headers,
                timeout=10
            )
            
            print(f"GET /api/admin/universe-monitor")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ PASS: Universe monitor endpoint working")
                print(f"Response fields: {list(data.keys()) if isinstance(data, dict) else 'List response'}")
                return True
            else:
                print(f"❌ FAIL: Universe monitor failed with {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: Universe monitor error - {e}")
            return False
    
    def test_user_scanner_flow(self):
        """Test 4: User registration + admin approve + user login + scanner endpoint"""
        print("\n" + "=" * 60)
        print("TEST 4: User Scanner Flow")
        print("=" * 60)
        
        # Step 4a: User Registration
        print("Step 4a: User Registration")
        try:
            reg_payload = {
                "first_name": "Test",
                "last_name": "User",
                "email": self.test_user_email,
                "password": self.test_user_password,
                "phone": "+1234567890"
            }
            
            response = requests.post(
                f"{self.base_url}/api/auth/register",
                json=reg_payload,
                timeout=10
            )
            
            print(f"POST /api/auth/register")
            print(f"Status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                print("✅ PASS: User registration successful")
                data = response.json()
                self.test_user_id = data.get('user_id')
                if self.test_user_id:
                    print(f"User ID: {self.test_user_id}")
                else:
                    print("Warning: No user_id in response")
            else:
                print(f"❌ FAIL: User registration failed with {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: User registration error - {e}")
            return False
        
        # Step 4b: Find and approve the user
        print("\nStep 4b: Find and approve the user")
        try:
            if not self.admin_token:
                print("❌ FAIL: No admin token for approval")
                return False
            
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Get pending approvals
            response = requests.get(
                f"{self.base_url}/api/admin/user-approvals?status_filter=pending",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                approvals = response.json()
                print(f"Found {len(approvals)} pending approvals")
                
                # Find our test user
                test_user_approval = None
                for approval in approvals:
                    if approval.get('email') == self.test_user_email:
                        test_user_approval = approval
                        self.test_user_id = approval.get('id')
                        break
                
                if not test_user_approval:
                    print("❌ FAIL: Test user not found in pending approvals")
                    return False
                
                print(f"Found test user for approval: {self.test_user_id}")
                
                # Approve the user
                approve_payload = {"ids": [self.test_user_id]}
                response = requests.post(
                    f"{self.base_url}/api/admin/user-approvals/bulk-approve",
                    json=approve_payload,
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    print("✅ PASS: User approved successfully")
                else:
                    print(f"❌ FAIL: User approval failed with {response.status_code}")
                    print(f"Response: {response.text}")
                    return False
            else:
                print(f"❌ FAIL: Failed to get pending approvals: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: User approval error - {e}")
            return False
        
        # Step 4c: User Login
        print("\nStep 4c: User Login")
        try:
            login_payload = {
                "email": self.test_user_email,
                "password": self.test_user_password
            }
            
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json=login_payload,
                timeout=10
            )
            
            print(f"POST /api/auth/login")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get('access_token')
                print("✅ PASS: User login successful")
                print(f"User token obtained: {self.user_token[:20]}...")
            else:
                print(f"❌ FAIL: User login failed with {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: User login error - {e}")
            return False
        
        # Step 4d: Test Scanner Endpoint
        print("\nStep 4d: User Scanner Symbol Selection")
        try:
            if not self.user_token:
                print("❌ FAIL: No user token for scanner test")
                return False
            
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = requests.get(
                f"{self.base_url}/api/user/scanner/symbol-selection",
                headers=headers,
                timeout=10
            )
            
            print(f"GET /api/user/scanner/symbol-selection")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ PASS: User scanner endpoint working")
                print(f"Response fields: {list(data.keys()) if isinstance(data, dict) else 'List response'}")
                return True
            else:
                print(f"❌ FAIL: Scanner endpoint failed with {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: Scanner endpoint error - {e}")
            return False
    
    def run_all_tests(self):
        """Run all FAZ-2B validation tests"""
        print("FAZ-2B DRIFT CLOSURE VALIDATION")
        print("=" * 80)
        
        test_results = []
        
        # Test 1: Health endpoint
        test_results.append(("Health Endpoint", self.test_health_endpoint()))
        
        # Test 2: Admin login
        test_results.append(("Admin Login", self.test_admin_login()))
        
        # Test 3: Admin universe monitor
        test_results.append(("Admin Universe Monitor", self.test_admin_universe_monitor()))
        
        # Test 4: User scanner flow
        test_results.append(("User Scanner Flow", self.test_user_scanner_flow()))
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        
        passed = 0
        failed = 0
        failed_tests = []
        
        for test_name, result in test_results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name}: {status}")
            if result:
                passed += 1
            else:
                failed += 1
                failed_tests.append(test_name)
        
        print(f"\nTotal: {passed + failed} tests")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        
        if failed == 0:
            print("\n🎉 ALL TESTS PASSED - FAZ-2B DRIFT CLOSURE VALIDATION SUCCESSFUL")
            return True
        else:
            print(f"\n⚠️  {failed} TESTS FAILED - ISSUES FOUND:")
            for test_name in failed_tests:
                print(f"  - {test_name}")
            return False


if __name__ == "__main__":
    tester = FAZ2BValidationTest()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)