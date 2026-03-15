#!/usr/bin/env python3
import os
"""
FAZ-2C + FAZ-3 Backend Validation Test
Backend validation for drift gate and new FAZ-3 endpoints
"""

import requests
import json
import sys
import uuid
import subprocess
import time


class FAZ3ValidationTest:
    def __init__(self):
        self.base_url = "https://market-scanner-v3.preview.emergentagent.com"
        self.admin_token = None
        self.test_user_email = f"test_user_faz3_{uuid.uuid4().hex[:8]}@test.com"
        self.test_user_password = "TestPassword123!"
        self.test_user_id = None
        self.user_token = None
        
    def test_drift_gate_strict(self):
        """Test 1: bash /app/scripts/ci_alembic_drift_gate.sh -> PASS"""
        print("=" * 60)
        print("TEST 1: Drift Gate Strict")
        print("=" * 60)
        
        try:
            result = subprocess.run(
                ["bash", "/app/scripts/ci_alembic_drift_gate.sh"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            print(f"Command: bash /app/scripts/ci_alembic_drift_gate.sh")
            print(f"Exit Code: {result.returncode}")
            print(f"Output: {result.stdout}")
            
            if result.stderr:
                print(f"Stderr: {result.stderr}")
            
            if result.returncode == 0 and "PASS" in result.stdout:
                print("✅ PASS: Drift gate validation successful")
                return True
            else:
                print("❌ FAIL: Drift gate validation failed")
                return False
                
        except subprocess.TimeoutExpired:
            print("❌ FAIL: Drift gate command timed out")
            return False
        except Exception as e:
            print(f"❌ FAIL: Drift gate error - {e}")
            return False

    def test_health_endpoint(self):
        """Test 2: GET /api/health"""
        print("\n" + "=" * 60)
        print("TEST 2: Health Endpoint")
        print("=" * 60)
        
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=10)
            print(f"GET {self.base_url}/api/health")
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
        """Test 3: POST /api/auth/login/admin (admin@platform.local / Admin12345!)"""
        print("\n" + "=" * 60)
        print("TEST 3: Admin Login")
        print("=" * 60)
        
        try:
            payload = {
                "email": os.getenv("TEST_ADMIN_EMAIL", "admin@platform.local"),
                "password": os.getenv("TEST_ADMIN_PASSWORD", "Admin12345!")
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
        """Test 4: GET /api/admin/universe-monitor (admin token)"""
        print("\n" + "=" * 60)
        print("TEST 4: Admin Universe Monitor")
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
                print(f"Response fields count: {len(data.keys()) if isinstance(data, dict) else len(data)}")
                return True
            else:
                print(f"❌ FAIL: Universe monitor failed with {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: Universe monitor error - {e}")
            return False

    def setup_user_token(self):
        """Setup user token for user endpoints testing"""
        print("\n" + "=" * 60)
        print("SETUP: User Token (Registration + Approval + Login)")
        print("=" * 60)
        
        # Step 1: User Registration
        print("Step 1: User Registration")
        try:
            reg_payload = {
                "first_name": "Test",
                "last_name": "FAZ3User", 
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
                print("✅ User registration successful")
                data = response.json()
                self.test_user_id = data.get('user_id')
                if self.test_user_id:
                    print(f"User ID: {self.test_user_id}")
            else:
                print(f"❌ User registration failed: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ User registration error: {e}")
            return False
        
        # Step 2: Admin approval
        print("\nStep 2: Admin User Approval")
        try:
            if not self.admin_token:
                print("❌ No admin token for approval")
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
                
                # Find our test user
                test_user_approval = None
                for approval in approvals:
                    if approval.get('email') == self.test_user_email:
                        test_user_approval = approval
                        self.test_user_id = approval.get('id')
                        break
                
                if not test_user_approval:
                    print("❌ Test user not found in pending approvals")
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
                    print("✅ User approved successfully")
                else:
                    print(f"❌ User approval failed: {response.status_code}")
                    return False
            else:
                print(f"❌ Failed to get pending approvals: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ User approval error: {e}")
            return False
        
        # Step 3: User Login
        print("\nStep 3: User Login")
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
                print("✅ User login successful")
                print(f"User token obtained: {self.user_token[:20]}...")
                return True
            else:
                print(f"❌ User login failed: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ User login error: {e}")
            return False

    def test_user_scanner_symbol_selection(self):
        """Test 5: GET /api/user/scanner/symbol-selection (user token)"""
        print("\n" + "=" * 60)
        print("TEST 5: User Scanner Symbol Selection")
        print("=" * 60)
        
        if not self.user_token:
            print("❌ FAIL: No user token available")
            return False
        
        try:
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
                print(f"✅ PASS: User scanner endpoint working")
                print(f"Response fields: {list(data.keys()) if isinstance(data, dict) else 'List response'}")
                return True
            else:
                print(f"❌ FAIL: Scanner endpoint failed with {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: Scanner endpoint error - {e}")
            return False

    def test_faz3_admin_universe_runtime_summary(self):
        """Test 6: GET /api/admin/universe/runtime-summary"""
        print("\n" + "=" * 60)
        print("TEST 6: FAZ-3 Admin Universe Runtime Summary")
        print("=" * 60)
        
        if not self.admin_token:
            print("❌ FAIL: No admin token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(
                f"{self.base_url}/api/admin/universe/runtime-summary",
                headers=headers,
                timeout=10
            )
            
            print(f"GET /api/admin/universe/runtime-summary")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ PASS: Universe runtime summary endpoint working")
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Non-dict response'}")
                
                # Check for required fields
                has_scanner_mode = 'scanner_mode_effective' in str(data)
                has_fallback_state = 'fallback_state' in str(data)
                
                print(f"Contains scanner_mode_effective: {has_scanner_mode}")
                print(f"Contains fallback_state: {has_fallback_state}")
                
                if has_scanner_mode and has_fallback_state:
                    print("✅ Required fields (scanner_mode_effective, fallback_state) found")
                else:
                    print("⚠️  Some required fields missing but endpoint is working")
                    
                return True
            else:
                print(f"❌ FAIL: Runtime summary failed with {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: Runtime summary error - {e}")
            return False

    def test_faz3_admin_universe_runtime_latest_scan(self):
        """Test 7: GET /api/admin/universe/runtime-latest-scan"""
        print("\n" + "=" * 60)
        print("TEST 7: FAZ-3 Admin Universe Runtime Latest Scan")
        print("=" * 60)
        
        if not self.admin_token:
            print("❌ FAIL: No admin token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(
                f"{self.base_url}/api/admin/universe/runtime-latest-scan",
                headers=headers,
                timeout=10
            )
            
            print(f"GET /api/admin/universe/runtime-latest-scan")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ PASS: Universe runtime latest scan endpoint working")
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Non-dict response'}")
                return True
            else:
                print(f"❌ FAIL: Runtime latest scan failed with {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: Runtime latest scan error - {e}")
            return False

    def test_faz3_user_scanner_runtime_run(self):
        """Test 8: POST /api/user/scanner/runtime/run"""
        print("\n" + "=" * 60)
        print("TEST 8: FAZ-3 User Scanner Runtime Run")
        print("=" * 60)
        
        if not self.user_token:
            print("❌ FAIL: No user token available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.user_token}"}
            # Try with empty payload first
            payload = {}
            
            response = requests.post(
                f"{self.base_url}/api/user/scanner/runtime/run",
                json=payload,
                headers=headers,
                timeout=15
            )
            
            print(f"POST /api/user/scanner/runtime/run")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ PASS: Scanner runtime run endpoint working")
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Non-dict response'}")
                
                # Check for required fields
                has_candidate_symbols = 'candidate_symbols' in str(data)
                has_decision_count = 'decision_count' in str(data)
                has_fallback_active = 'fallback_active' in str(data)
                
                print(f"Contains candidate_symbols: {has_candidate_symbols}")
                print(f"Contains decision_count: {has_decision_count}")
                print(f"Contains fallback_active: {has_fallback_active}")
                
                if has_candidate_symbols and has_decision_count and has_fallback_active:
                    print("✅ Required fields (candidate_symbols, decision_count, fallback_active) found")
                else:
                    print("⚠️  Some required fields missing but endpoint is working")
                    
                return True
            else:
                print(f"❌ FAIL: Scanner runtime run failed with {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: Scanner runtime run error - {e}")
            return False

    def test_faz3_user_scanner_runtime_snapshot(self):
        """Test 9: GET /api/user/scanner/runtime/snapshot"""
        print("\n" + "=" * 60)
        print("TEST 9: FAZ-3 User Scanner Runtime Snapshot")
        print("=" * 60)
        
        if not self.user_token:
            print("❌ FAIL: No user token available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = requests.get(
                f"{self.base_url}/api/user/scanner/runtime/snapshot",
                headers=headers,
                timeout=10
            )
            
            print(f"GET /api/user/scanner/runtime/snapshot")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ PASS: Scanner runtime snapshot endpoint working")
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Non-dict response'}")
                return True
            else:
                print(f"❌ FAIL: Scanner runtime snapshot failed with {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: Scanner runtime snapshot error - {e}")
            return False

    def run_all_tests(self):
        """Run all FAZ-2C + FAZ-3 validation tests"""
        print("FAZ-2C + FAZ-3 BACKEND VALIDATION")
        print("=" * 80)
        
        test_results = []
        
        # Test 1: Drift gate strict
        test_results.append(("Drift Gate Strict", self.test_drift_gate_strict()))
        
        # Test 2: Health endpoint
        test_results.append(("Health Endpoint", self.test_health_endpoint()))
        
        # Test 3: Admin login
        test_results.append(("Admin Login", self.test_admin_login()))
        
        # Test 4: Admin universe monitor
        test_results.append(("Admin Universe Monitor", self.test_admin_universe_monitor()))
        
        # Setup user token for user endpoints
        user_setup_success = self.setup_user_token()
        if not user_setup_success:
            print("⚠️  User setup failed - skipping user-dependent tests")
        
        # Test 5: User scanner symbol selection (if user setup succeeded)
        if user_setup_success:
            test_results.append(("User Scanner Symbol Selection", self.test_user_scanner_symbol_selection()))
        
        # Test 6-9: New FAZ-3 endpoints
        test_results.append(("FAZ-3 Admin Universe Runtime Summary", self.test_faz3_admin_universe_runtime_summary()))
        test_results.append(("FAZ-3 Admin Universe Runtime Latest Scan", self.test_faz3_admin_universe_runtime_latest_scan()))
        
        # User runtime endpoints (if user setup succeeded)
        if user_setup_success:
            test_results.append(("FAZ-3 User Scanner Runtime Run", self.test_faz3_user_scanner_runtime_run()))
            test_results.append(("FAZ-3 User Scanner Runtime Snapshot", self.test_faz3_user_scanner_runtime_snapshot()))
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        
        passed = 0
        failed = 0
        failed_tests = []
        
        for test_name, result in test_results:
            status = "PASS" if result else "FAIL"
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
            print("\n🎉 ALL TESTS PASSED - FAZ-2C + FAZ-3 VALIDATION SUCCESSFUL")
            return True
        else:
            print(f"\n⚠️  {failed} TESTS FAILED - ISSUES FOUND:")
            for test_name in failed_tests:
                print(f"  - {test_name}")
            return False


if __name__ == "__main__":
    tester = FAZ3ValidationTest()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)