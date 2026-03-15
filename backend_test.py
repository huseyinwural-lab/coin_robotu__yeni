#!/usr/bin/env python3
"""
Son Düzeltme Mini Paketi Backend Doğrulaması
Comprehensive backend validation test script for the final patch package.
"""

import subprocess
import requests
import json
import time
import os
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://market-scanner-prod.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"

class BackendValidator:
    def __init__(self):
        self.admin_token = None
        self.user_token = None
        self.test_results = []
        self.failed_tests = []
        
    def log_result(self, test_name, status, details=""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status_emoji = "✅" if status == "PASS" else "❌"
        print(f"{status_emoji} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        
        if status == "FAIL":
            self.failed_tests.append(test_name)
    
    def run_script(self, script_path):
        """Execute bash script and return result"""
        try:
            result = subprocess.run(['bash', script_path], 
                                  capture_output=True, text=True, timeout=30)
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Script timed out"
        except Exception as e:
            return False, "", str(e)
    
    def test_ci_gates(self):
        """Test 1: Build/CI Gates"""
        print("\n=== TEST 1: BUILD/CI GATES ===")
        
        gates = [
            "/app/scripts/ci_alembic_drift_gate.sh",
            "/app/scripts/ci_stage_gate.sh", 
            "/app/scripts/ci_prod_gate.sh"
        ]
        
        for gate in gates:
            gate_name = os.path.basename(gate)
            success, stdout, stderr = self.run_script(gate)
            
            if success and "PASS" in stdout:
                self.log_result(f"CI Gate: {gate_name}", "PASS", stdout.strip())
            else:
                self.log_result(f"CI Gate: {gate_name}", "FAIL", f"stdout: {stdout}, stderr: {stderr}")
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        try:
            response = requests.get(f"{API_URL}/health", timeout=10)
            if response.status_code == 200 and response.json().get("status") == "ok":
                self.log_result("Health Endpoint", "PASS", f"Status: {response.status_code}, Response: {response.json()}")
                return True
            else:
                self.log_result("Health Endpoint", "FAIL", f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_result("Health Endpoint", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_admin_login(self):
        """Test admin login and store token"""
        try:
            payload = {
                "email": "admin@platform.local",
                "password": "Admin12345!"
            }
            response = requests.post(f"{API_URL}/auth/login/admin", json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.admin_token = data["access_token"]
                    self.log_result("Admin Login", "PASS", f"Token received: {self.admin_token[:20]}...")
                    return True
                else:
                    self.log_result("Admin Login", "FAIL", f"No access_token in response: {data}")
                    return False
            else:
                self.log_result("Admin Login", "FAIL", f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_result("Admin Login", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_admin_universe_monitor(self):
        """Test admin universe monitor endpoint"""
        if not self.admin_token:
            self.log_result("Admin Universe Monitor", "FAIL", "No admin token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(f"{API_URL}/admin/universe-monitor", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["market_type", "scanner_mode", "total_exchange_symbols", "symbols_evaluated_this_cycle"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    self.log_result("Admin Universe Monitor", "PASS", f"All required fields present. Data keys: {list(data.keys())}")
                    return True
                else:
                    self.log_result("Admin Universe Monitor", "FAIL", f"Missing fields: {missing_fields}")
                    return False
            else:
                self.log_result("Admin Universe Monitor", "FAIL", f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_result("Admin Universe Monitor", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_user_scanner_flow(self):
        """Test user scanner symbol selection with full registration flow"""
        try:
            # Step 1: Register new user
            user_email = f"test_user_{int(time.time())}@test.com"
            registration_payload = {
                "first_name": "Test",
                "last_name": "User", 
                "email": user_email,
                "phone": "+90555000000",
                "password": "TestPass123!",
                "password_confirm": "TestPass123!"
            }
            
            reg_response = requests.post(f"{API_URL}/auth/register", json=registration_payload, timeout=10)
            if reg_response.status_code != 200:
                self.log_result("User Scanner Flow", "FAIL", f"Registration failed: {reg_response.status_code}, {reg_response.text}")
                return False
                
            # Step 2: Admin approves user
            if not self.admin_token:
                self.log_result("User Scanner Flow", "FAIL", "No admin token for approval")
                return False
                
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Get pending users
            pending_response = requests.get(f"{API_URL}/admin/user-approvals?status_filter=pending", headers=headers, timeout=10)
            if pending_response.status_code != 200:
                self.log_result("User Scanner Flow", "FAIL", f"Failed to get pending users: {pending_response.text}")
                return False
                
            pending_users = pending_response.json()
            test_user = next((u for u in pending_users if u["email"] == user_email), None)
            
            if not test_user:
                self.log_result("User Scanner Flow", "FAIL", f"Test user {user_email} not found in pending list")
                return False
                
            # Approve user
            approve_payload = {"ids": [test_user["id"]]}
            approve_response = requests.post(f"{API_URL}/admin/user-approvals/bulk-approve", 
                                           json=approve_payload, headers=headers, timeout=10)
            if approve_response.status_code != 200:
                self.log_result("User Scanner Flow", "FAIL", f"User approval failed: {approve_response.text}")
                return False
                
            # Step 3: User login
            time.sleep(1)  # Brief delay for approval processing
            login_payload = {
                "email": user_email,
                "password": "TestPass123!"
            }
            
            login_response = requests.post(f"{API_URL}/auth/login", json=login_payload, timeout=10)
            if login_response.status_code != 200:
                self.log_result("User Scanner Flow", "FAIL", f"User login failed: {login_response.status_code}, {login_response.text}")
                return False
                
            user_data = login_response.json()
            if "access_token" not in user_data:
                self.log_result("User Scanner Flow", "FAIL", f"No access_token in user login response: {user_data}")
                return False
                
            self.user_token = user_data["access_token"]
            
            # Step 4: Test scanner symbol selection
            user_headers = {"Authorization": f"Bearer {self.user_token}"}
            scanner_response = requests.get(f"{API_URL}/user/scanner/symbol-selection", headers=user_headers, timeout=10)
            
            if scanner_response.status_code == 200:
                scanner_data = scanner_response.json()
                required_fields = ["user_id", "scanner_id", "symbol_selection_mode", "selected_symbols"]
                missing_fields = [field for field in required_fields if field not in scanner_data]
                
                if not missing_fields:
                    self.log_result("User Scanner Flow", "PASS", f"Complete flow successful. Scanner data fields: {list(scanner_data.keys())}")
                    return True
                else:
                    self.log_result("User Scanner Flow", "FAIL", f"Missing scanner fields: {missing_fields}")
                    return False
            else:
                self.log_result("User Scanner Flow", "FAIL", f"Scanner endpoint failed: {scanner_response.status_code}, {scanner_response.text}")
                return False
                
        except Exception as e:
            self.log_result("User Scanner Flow", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_endpoint_regressions(self):
        """Test 2: Endpoint Regressions"""
        print("\n=== TEST 2: ENDPOINT REGRESSIONS ===")
        
        # Health endpoint
        self.test_health_endpoint()
        
        # Admin login
        self.test_admin_login()
        
        # Admin universe monitor (requires admin token)
        self.test_admin_universe_monitor()
        
        # User scanner flow (registration + approval + login + scanner access)
        self.test_user_scanner_flow()
    
    def test_admin_profile_update(self):
        """Test admin profile update"""
        if not self.admin_token:
            self.log_result("Admin Profile Update", "FAIL", "No admin token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Test profile update
            profile_payload = {
                "first_name": "Admin",
                "last_name": "User",
                "email": "admin@platform.local"  # Keep same email
            }
            
            response = requests.patch(f"{API_URL}/auth/admin/profile", json=profile_payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                self.log_result("Admin Profile Update", "PASS", f"Profile updated successfully: {response.json()}")
                return True
            else:
                self.log_result("Admin Profile Update", "FAIL", f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_result("Admin Profile Update", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_admin_password_change(self):
        """Test admin password change"""
        if not self.admin_token:
            self.log_result("Admin Password Change", "FAIL", "No admin token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Test password change (change back to original)
            password_payload = {
                "current_password": "Admin12345!",
                "new_password": "Admin12345!",  # Keep same password for testing
                "confirm_password": "Admin12345!"
            }
            
            response = requests.post(f"{API_URL}/auth/admin/password/change", json=password_payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                self.log_result("Admin Password Change", "PASS", f"Password changed successfully: {response.json()}")
                return True
            else:
                self.log_result("Admin Password Change", "FAIL", f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_result("Admin Password Change", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_admin_self_update(self):
        """Test 3: Admin Self-Update"""
        print("\n=== TEST 3: ADMIN SELF-UPDATE ===")
        
        self.test_admin_profile_update()
        self.test_admin_password_change()
    
    def test_credential_cleanup(self):
        """Test 4: Credential Cleanup Check"""
        print("\n=== TEST 4: CREDENTIAL CLEANUP ===")
        
        try:
            # Search for old admin credential pattern in source files only
            result = subprocess.run(['find', '/app', '-name', '*.py', '-exec', 'grep', '-l', 'admin@platform.local', '{}', ';'], 
                                  capture_output=True, text=True)
            
            # Filter out this test file itself
            matches = [line for line in result.stdout.strip().split('\n') if line and 'backend_test.py' not in line]
            
            if not matches or (len(matches) == 1 and not matches[0]):
                self.log_result("Credential Cleanup", "PASS", "No admin@platform.local references found in source code")
            else:
                self.log_result("Credential Cleanup", "FAIL", f"Found admin@platform.local references in source files:\n{chr(10).join(matches)}")
                
        except Exception as e:
            self.log_result("Credential Cleanup", "FAIL", f"Exception: {str(e)}")
    
    def run_validation(self):
        """Run complete validation suite"""
        print("=== SON DÜZELTME MİNİ PAKETİ BACKEND DOĞRULAMASI ===")
        print(f"Testing against: {BASE_URL}")
        print(f"Start time: {datetime.now().isoformat()}")
        
        # Run all test suites
        self.test_ci_gates()
        self.test_endpoint_regressions()
        self.test_admin_self_update()
        self.test_credential_cleanup()
        
        # Final summary
        self.print_summary()
    
    def print_summary(self):
        """Print final test summary"""
        print("\n" + "="*60)
        print("FINAL VALIDATION SUMMARY")
        print("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.test_results if r["status"] == "FAIL"])
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%" if total_tests > 0 else "N/A")
        
        if self.failed_tests:
            print("\nFAILED TESTS:")
            for test in self.failed_tests:
                print(f"❌ {test}")
        else:
            print("\n✅ ALL TESTS PASSED!")
        
        print(f"\nTest completed at: {datetime.now().isoformat()}")
        
        return len(self.failed_tests) == 0

if __name__ == "__main__":
    validator = BackendValidator()
    success = validator.run_validation()
    sys.exit(0 if success else 1)