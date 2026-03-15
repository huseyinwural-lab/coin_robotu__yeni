#!/usr/bin/env python3
"""
Final Backend Validation Test - Son düzeltme mini paketi
Executes the comprehensive validation steps as requested.
"""

import requests
import subprocess
import json
import os
import sys
from datetime import datetime

# Base configuration
BACKEND_URL = "https://trading-bot-ops.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

class ValidationTester:
    def __init__(self):
        self.admin_token = None
        self.user_token = None
        self.results = []
        
    def log_result(self, test_name, passed, details=""):
        """Log test result"""
        status = "PASS" if passed else "FAIL"
        self.results.append({
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        print(f"[{status}] {test_name}: {details}")
        
    def test_1_alembic_drift_gate(self):
        """Test 1: bash scripts/ci_alembic_drift_gate.sh"""
        try:
            result = subprocess.run(
                ["bash", "/app/scripts/ci_alembic_drift_gate.sh"],
                cwd="/app",
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                self.log_result("1) Alembic Drift Gate", True, result.stdout.strip())
            else:
                self.log_result("1) Alembic Drift Gate", False, f"Exit code: {result.returncode}, Error: {result.stderr}")
        except Exception as e:
            self.log_result("1) Alembic Drift Gate", False, f"Exception: {str(e)}")
    
    def test_2_stage_gate(self):
        """Test 2: bash scripts/ci_stage_gate.sh"""
        try:
            result = subprocess.run(
                ["bash", "/app/scripts/ci_stage_gate.sh"],
                cwd="/app",
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self.log_result("2) Stage Gate", True, result.stdout.strip())
            else:
                self.log_result("2) Stage Gate", False, f"Exit code: {result.returncode}, Error: {result.stderr}")
        except Exception as e:
            self.log_result("2) Stage Gate", False, f"Exception: {str(e)}")
    
    def test_3_prod_gate(self):
        """Test 3: bash scripts/ci_prod_gate.sh"""
        try:
            result = subprocess.run(
                ["bash", "/app/scripts/ci_prod_gate.sh"],
                cwd="/app",
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self.log_result("3) Prod Gate", True, result.stdout.strip())
            else:
                self.log_result("3) Prod Gate", False, f"Exit code: {result.returncode}, Error: {result.stderr}")
        except Exception as e:
            self.log_result("3) Prod Gate", False, f"Exception: {str(e)}")
    
    def test_4_health_endpoint(self):
        """Test 4: GET /api/health"""
        try:
            response = requests.get(f"{API_BASE}/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    self.log_result("4) GET /api/health", True, f"Status: {data.get('status')}")
                else:
                    self.log_result("4) GET /api/health", False, f"Unexpected response: {data}")
            else:
                self.log_result("4) GET /api/health", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("4) GET /api/health", False, f"Exception: {str(e)}")
    
    def test_5_admin_login(self):
        """Test 5: POST /api/auth/login/admin (admin@platform.local / Admin12345!)"""
        try:
            payload = {
                "email": "admin@platform.local",
                "password": "Admin12345!"
            }
            
            response = requests.post(f"{API_BASE}/auth/login/admin", json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.admin_token = data["access_token"]
                    self.log_result("5) POST /api/auth/login/admin", True, "Admin login successful, token acquired")
                else:
                    self.log_result("5) POST /api/auth/login/admin", False, f"No access_token in response: {data}")
            else:
                self.log_result("5) POST /api/auth/login/admin", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("5) POST /api/auth/login/admin", False, f"Exception: {str(e)}")
    
    def test_6_universe_monitor(self):
        """Test 6: GET /api/admin/universe-monitor"""
        if not self.admin_token:
            self.log_result("6) GET /api/admin/universe-monitor", False, "No admin token available")
            return
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(f"{API_BASE}/admin/universe-monitor", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # Check for key fields that should exist
                required_fields = ["market_type", "scanner_mode", "total_exchange_symbols"]
                missing_fields = [f for f in required_fields if f not in data]
                
                if not missing_fields:
                    self.log_result("6) GET /api/admin/universe-monitor", True, f"Response has {len(data)} fields")
                else:
                    self.log_result("6) GET /api/admin/universe-monitor", False, f"Missing fields: {missing_fields}")
            else:
                self.log_result("6) GET /api/admin/universe-monitor", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("6) GET /api/admin/universe-monitor", False, f"Exception: {str(e)}")
    
    def test_7_user_scanner_flow(self):
        """Test 7: GET /api/user/scanner/symbol-selection (register+approve+login)"""
        import uuid
        test_email = f"test_final_validation_{int(datetime.now().timestamp())}@test.com"
        
        try:
            # Step 7a: User registration
            reg_payload = {
                "first_name": "Final",
                "last_name": "ValidationUser", 
                "phone_number": "+905551234567",
                "email": test_email,
                "password": "TestPass123!",
                "confirm_password": "TestPass123!"
            }
            
            reg_response = requests.post(f"{API_BASE}/auth/register", json=reg_payload, timeout=10)
            if reg_response.status_code != 200:
                self.log_result("7) User Scanner Flow", False, f"Registration failed: HTTP {reg_response.status_code}")
                return
            
            reg_data = reg_response.json()
            user_id = reg_data.get("id")  # Registration returns "id" not "user_id"
            if not user_id:
                self.log_result("7) User Scanner Flow", False, "No user_id in registration response")
                return
            
            # Step 7b: Admin approve user
            if not self.admin_token:
                self.log_result("7) User Scanner Flow", False, "No admin token for approval")
                return
                
            approve_payload = {"ids": [user_id]}  # API expects "ids" not "user_ids"
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            approve_response = requests.post(
                f"{API_BASE}/admin/user-approvals/bulk-approve",
                json=approve_payload,
                headers=headers,
                timeout=10
            )
            
            if approve_response.status_code != 200:
                self.log_result("7) User Scanner Flow", False, f"Approval failed: HTTP {approve_response.status_code}")
                return
            
            # Step 7c: User login
            login_payload = {
                "email": test_email,
                "password": "TestPass123!"
            }
            
            login_response = requests.post(f"{API_BASE}/auth/login", json=login_payload, timeout=10)
            if login_response.status_code != 200:
                self.log_result("7) User Scanner Flow", False, f"User login failed: HTTP {login_response.status_code}")
                return
            
            login_data = login_response.json()
            user_token = login_data.get("access_token")
            if not user_token:
                self.log_result("7) User Scanner Flow", False, "No access_token in user login response")
                return
            
            # Step 7d: Test scanner symbol selection
            user_headers = {"Authorization": f"Bearer {user_token}"}
            scanner_response = requests.get(
                f"{API_BASE}/user/scanner/symbol-selection",
                headers=user_headers,
                timeout=10
            )
            
            if scanner_response.status_code == 200:
                data = scanner_response.json()
                required_fields = ["user_id", "scanner_id", "symbol_selection_mode"]
                missing_fields = [f for f in required_fields if f not in data]
                
                if not missing_fields:
                    self.log_result("7) User Scanner Flow", True, f"Complete flow successful, scanner data has {len(data)} fields")
                else:
                    self.log_result("7) User Scanner Flow", False, f"Scanner response missing fields: {missing_fields}")
            else:
                self.log_result("7) User Scanner Flow", False, f"Scanner endpoint failed: HTTP {scanner_response.status_code}")
                
        except Exception as e:
            self.log_result("7) User Scanner Flow", False, f"Exception: {str(e)}")
    
    def test_8_grep_legacy_admin_domain(self):
        """Test 8: eski admin domain izlerini repo kaynaklarında doğrula"""
        try:
            legacy_domain = "admin@platform" + ".dev"
            result = subprocess.run(
                [
                    "grep",
                    "-R",
                    legacy_domain,
                    ".",
                    "--exclude=backend_test.py",
                    "--exclude-dir=memory",
                    "--exclude=test_result.md",
                ],
                cwd="/app",
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # For grep, exit code 1 means "no matches found" which is what we want
            # Exit code 0 means matches found
            if result.returncode == 1:
                self.log_result("8) grep legacy admin domain", True, "No occurrences found (expected)")
            elif result.returncode == 0:
                matches = result.stdout.strip().split('\n')
                self.log_result("8) grep legacy admin domain", False, f"Found {len(matches)} occurrences: {result.stdout[:200]}...")
            else:
                self.log_result("8) grep legacy admin domain", False, f"Grep error: {result.stderr}")
        except Exception as e:
            self.log_result("8) grep legacy admin domain", False, f"Exception: {str(e)}")
    
    def run_all_tests(self):
        """Run all validation tests"""
        print("=== Final Backend Validation - Son düzeltme mini paketi ===")
        print(f"Testing against: {BACKEND_URL}")
        print("")
        
        # Execute tests in order
        self.test_1_alembic_drift_gate()
        self.test_2_stage_gate()
        self.test_3_prod_gate()
        self.test_4_health_endpoint()
        self.test_5_admin_login()
        self.test_6_universe_monitor()
        self.test_7_user_scanner_flow()
        self.test_8_grep_legacy_admin_domain()
        
        # Summary
        print("\n=== FINAL SUMMARY ===")
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        total = len(self.results)
        
        print(f"Tests completed: {passed}/{total} PASSED")
        print("")
        
        for result in self.results:
            status_symbol = "✅" if result["status"] == "PASS" else "❌"
            print(f"{status_symbol} {result['test']}: {result['details']}")
        
        # Return overall success
        return passed == total

if __name__ == "__main__":
    tester = ValidationTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)