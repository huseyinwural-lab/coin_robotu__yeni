#!/usr/bin/env python3
"""
FAZ-2C + FAZ-3 Backend Test Package
Quick validation of critical endpoints
"""

import requests
import subprocess
import sys
import json
from typing import Dict, Any, Tuple

# Configuration
BASE_URL = "https://market-scanner-prod.preview.emergentagent.com"
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"

class BackendTester:
    def __init__(self):
        self.admin_token = None
        self.user_token = None
        self.results = []
        
    def log_result(self, test_name: str, status: str, details: str = ""):
        """Log test result"""
        self.results.append({
            "test": test_name,
            "status": status,
            "details": details
        })
        print(f"{status}: {test_name} - {details}")
    
    def run_drift_gate(self) -> bool:
        """Test 1: Drift gate strict"""
        try:
            result = subprocess.run(
                ["bash", "/app/scripts/ci_alembic_drift_gate.sh"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self.log_result("Drift Gate Strict", "PASS", result.stdout.strip())
                return True
            else:
                self.log_result("Drift Gate Strict", "FAIL", result.stderr.strip())
                return False
        except Exception as e:
            self.log_result("Drift Gate Strict", "FAIL", f"Error: {e}")
            return False
    
    def test_health_endpoint(self) -> bool:
        """Test 2.1: Health endpoint"""
        try:
            response = requests.get(f"{BASE_URL}/api/health", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    self.log_result("Health Endpoint", "PASS", "Status: ok")
                    return True
                else:
                    self.log_result("Health Endpoint", "FAIL", f"Unexpected response: {data}")
                    return False
            else:
                self.log_result("Health Endpoint", "FAIL", f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Health Endpoint", "FAIL", f"Error: {e}")
            return False
    
    def test_admin_login(self) -> bool:
        """Test 2.2: Admin login"""
        try:
            payload = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = requests.post(f"{BASE_URL}/api/auth/login/admin", json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.admin_token = data["access_token"]
                    self.log_result("Admin Login", "PASS", "Token obtained")
                    return True
                else:
                    self.log_result("Admin Login", "FAIL", f"No access_token in response: {data}")
                    return False
            else:
                self.log_result("Admin Login", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_result("Admin Login", "FAIL", f"Error: {e}")
            return False
    
    def test_universe_monitor(self) -> bool:
        """Test 2.3: Universe monitor"""
        if not self.admin_token:
            self.log_result("Universe Monitor", "FAIL", "No admin token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(f"{BASE_URL}/api/admin/universe-monitor", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                field_count = len(data)
                self.log_result("Universe Monitor", "PASS", f"{field_count} fields returned")
                return True
            else:
                self.log_result("Universe Monitor", "FAIL", f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Universe Monitor", "FAIL", f"Error: {e}")
            return False
    
    def test_user_scanner_flow(self) -> bool:
        """Test 2.4: User scanner symbol selection (simplified)"""
        # For speed, we'll use existing test user from previous tests
        test_email = "test_user_reg_1773349041@test.com"
        test_password = "TestPassword123!"
        
        try:
            # Try user login first
            payload = {
                "email": test_email,
                "password": test_password
            }
            
            response = requests.post(f"{BASE_URL}/api/auth/login", json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    user_token = data["access_token"]
                    
                    # Test scanner endpoint
                    headers = {"Authorization": f"Bearer {user_token}"}
                    scanner_response = requests.get(f"{BASE_URL}/api/user/scanner/symbol-selection", headers=headers, timeout=10)
                    
                    if scanner_response.status_code == 200:
                        scanner_data = scanner_response.json()
                        field_count = len(scanner_data)
                        self.log_result("User Scanner Flow", "PASS", f"Scanner data: {field_count} fields")
                        return True
                    else:
                        self.log_result("User Scanner Flow", "FAIL", f"Scanner HTTP {scanner_response.status_code}")
                        return False
                else:
                    self.log_result("User Scanner Flow", "FAIL", "No user access_token")
                    return False
            else:
                self.log_result("User Scanner Flow", "FAIL", f"User login HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_result("User Scanner Flow", "FAIL", f"Error: {e}")
            return False
    
    def test_runtime_summary(self) -> bool:
        """Test 3.1: Runtime summary"""
        if not self.admin_token:
            self.log_result("Runtime Summary", "FAIL", "No admin token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(f"{BASE_URL}/api/admin/universe/runtime-summary", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # Check for key fields
                required_fields = ["scanner_mode_effective", "fallback_state"]
                missing_fields = [f for f in required_fields if f not in data]
                
                if not missing_fields:
                    field_count = len(data)
                    self.log_result("Runtime Summary", "PASS", f"{field_count} fields, key fields present")
                    return True
                else:
                    self.log_result("Runtime Summary", "FAIL", f"Missing fields: {missing_fields}")
                    return False
            else:
                self.log_result("Runtime Summary", "FAIL", f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Runtime Summary", "FAIL", f"Error: {e}")
            return False
    
    def test_runtime_latest_scan(self) -> bool:
        """Test 3.2: Runtime latest scan"""
        if not self.admin_token:
            self.log_result("Runtime Latest Scan", "FAIL", "No admin token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(f"{BASE_URL}/api/admin/universe/runtime-latest-scan", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                field_count = len(data)
                self.log_result("Runtime Latest Scan", "PASS", f"{field_count} fields returned")
                return True
            else:
                self.log_result("Runtime Latest Scan", "FAIL", f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Runtime Latest Scan", "FAIL", f"Error: {e}")
            return False
    
    def test_user_runtime_run(self) -> bool:
        """Test 3.3: User runtime run"""
        # Get user token first
        test_email = "test_user_reg_1773349041@test.com"
        test_password = "TestPassword123!"
        
        try:
            # User login
            payload = {
                "email": test_email,
                "password": test_password
            }
            
            response = requests.post(f"{BASE_URL}/api/auth/login", json=payload, timeout=10)
            
            if response.status_code != 200:
                self.log_result("User Runtime Run", "FAIL", f"User login HTTP {response.status_code}")
                return False
                
            data = response.json()
            user_token = data.get("access_token")
            
            if not user_token:
                self.log_result("User Runtime Run", "FAIL", "No user access_token")
                return False
            
            # Test runtime run
            headers = {"Authorization": f"Bearer {user_token}"}
            run_response = requests.post(f"{BASE_URL}/api/user/scanner/runtime/run", headers=headers, timeout=10)
            
            if run_response.status_code == 200:
                run_data = run_response.json()
                # Check for key fields
                required_fields = ["candidate_symbols", "decision_count", "fallback_active"]
                missing_fields = [f for f in required_fields if f not in run_data]
                
                if not missing_fields:
                    field_count = len(run_data)
                    self.log_result("User Runtime Run", "PASS", f"{field_count} fields, key fields present")
                    return True
                else:
                    self.log_result("User Runtime Run", "FAIL", f"Missing fields: {missing_fields}")
                    return False
            else:
                self.log_result("User Runtime Run", "FAIL", f"HTTP {run_response.status_code}")
                return False
        except Exception as e:
            self.log_result("User Runtime Run", "FAIL", f"Error: {e}")
            return False
    
    def test_user_runtime_snapshot(self) -> bool:
        """Test 3.4: User runtime snapshot"""
        # Get user token first
        test_email = "test_user_reg_1773349041@test.com"
        test_password = "TestPassword123!"
        
        try:
            # User login
            payload = {
                "email": test_email,
                "password": test_password
            }
            
            response = requests.post(f"{BASE_URL}/api/auth/login", json=payload, timeout=10)
            
            if response.status_code != 200:
                self.log_result("User Runtime Snapshot", "FAIL", f"User login HTTP {response.status_code}")
                return False
                
            data = response.json()
            user_token = data.get("access_token")
            
            if not user_token:
                self.log_result("User Runtime Snapshot", "FAIL", "No user access_token")
                return False
            
            # Test runtime snapshot
            headers = {"Authorization": f"Bearer {user_token}"}
            snapshot_response = requests.get(f"{BASE_URL}/api/user/scanner/runtime/snapshot", headers=headers, timeout=10)
            
            if snapshot_response.status_code == 200:
                snapshot_data = snapshot_response.json()
                field_count = len(snapshot_data)
                self.log_result("User Runtime Snapshot", "PASS", f"{field_count} fields returned")
                return True
            else:
                self.log_result("User Runtime Snapshot", "FAIL", f"HTTP {snapshot_response.status_code}")
                return False
        except Exception as e:
            self.log_result("User Runtime Snapshot", "FAIL", f"Error: {e}")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests in sequence"""
        print("="*50)
        print("FAZ-2C + FAZ-3 Backend Test Package")
        print("="*50)
        
        test_functions = [
            self.run_drift_gate,
            self.test_health_endpoint,
            self.test_admin_login,
            self.test_universe_monitor,
            self.test_user_scanner_flow,
            self.test_runtime_summary,
            self.test_runtime_latest_scan,
            self.test_user_runtime_run,
            self.test_user_runtime_snapshot
        ]
        
        passed = 0
        total = len(test_functions)
        
        for test_func in test_functions:
            if test_func():
                passed += 1
        
        print("="*50)
        print(f"SONUÇ: {passed}/{total} PASSED")
        
        if passed == total:
            print("GENEL DURUM: ✅ ALL PASS")
        else:
            print("GENEL DURUM: ❌ SOME FAILED")
        
        return {
            "total_tests": total,
            "passed": passed,
            "failed": total - passed,
            "success_rate": passed / total,
            "results": self.results
        }

def main():
    tester = BackendTester()
    results = tester.run_all_tests()
    
    # Exit with error code if any tests failed
    if results["failed"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()