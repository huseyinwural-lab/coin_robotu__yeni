#!/usr/bin/env python3
"""
Final Backend Smoke/Regression Validation Test
Turkish Review Request: Final backend smoke/regression doğrulaması

Test Requirements:
1) Health endpoints: GET /api/health/live, /api/health/ready, /api/health => 200
2) Runtime timeline endpoint auth behavior:
   - admin login (/api/auth/login/admin)
   - Bearer + session header ile GET /api/runtime/ws/execution-timeline?limit=20 => 200 ve status alanı dolu
   - Authorization olmadan aynı endpoint => 401
3) Duplicate env risk doğrulaması:
   - /app/backend/.env içinde duplicate key yok mu kontrol et
4) Process health: ps çıktısında defunct/zombie process var mı raporla

Environment:
- Base URL: https://trade-trace-engine.preview.emergentagent.com
- Admin credential: canary.admin@platform.local / CanaryAdmin123!

Output format: PASS/FAIL + kısa bulgu listesi
"""

import requests
import json
import sys
import subprocess
import os
from typing import Dict, List, Tuple, Any
import time

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class BackendValidator:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.admin_session_id = None
        self.admin_device_id = None
        self.results = []
        
    def log_result(self, test_name: str, status: str, details: str = ""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.results.append(result)
        print(f"[{status}] {test_name}: {details}")
        
    def admin_login(self) -> bool:
        """Perform admin login and extract tokens"""
        try:
            login_url = f"{BASE_URL}/api/auth/login/admin"
            payload = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(login_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                self.admin_session_id = data.get("session_id")
                self.admin_device_id = data.get("device_id")
                
                if self.admin_token:
                    self.log_result("Admin Login", "PASS", f"Token length: {len(self.admin_token)} chars")
                    return True
                else:
                    self.log_result("Admin Login", "FAIL", "No access_token in response")
                    return False
            else:
                self.log_result("Admin Login", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Admin Login", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_health_endpoints(self) -> None:
        """Test 1: Health endpoints validation"""
        health_endpoints = [
            "/api/health/live",
            "/api/health/ready", 
            "/api/health"
        ]
        
        for endpoint in health_endpoints:
            try:
                url = f"{BASE_URL}{endpoint}"
                response = self.session.get(url, timeout=15)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        self.log_result(f"Health Endpoint {endpoint}", "PASS", f"HTTP 200, response: {json.dumps(data)[:100]}...")
                    except:
                        self.log_result(f"Health Endpoint {endpoint}", "PASS", f"HTTP 200, non-JSON response")
                else:
                    self.log_result(f"Health Endpoint {endpoint}", "FAIL", f"HTTP {response.status_code}")
                    
            except Exception as e:
                self.log_result(f"Health Endpoint {endpoint}", "FAIL", f"Exception: {str(e)}")
    
    def test_runtime_timeline_auth(self) -> None:
        """Test 2: Runtime timeline endpoint auth behavior"""
        timeline_url = f"{BASE_URL}/api/runtime/ws/execution-timeline"
        
        # Test with authentication
        if self.admin_token:
            try:
                headers = {
                    "Authorization": f"Bearer {self.admin_token}",
                    "Content-Type": "application/json"
                }
                
                # Add session headers if available
                if self.admin_session_id:
                    headers["X-Session-ID"] = self.admin_session_id
                if self.admin_device_id:
                    headers["X-Session-Device"] = self.admin_device_id
                
                params = {"limit": 20}
                response = self.session.get(timeline_url, headers=headers, params=params, timeout=15)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        status_field = data.get("status")
                        if status_field:
                            self.log_result("Runtime Timeline (Auth)", "PASS", f"HTTP 200, status='{status_field}'")
                        else:
                            self.log_result("Runtime Timeline (Auth)", "FAIL", "HTTP 200 but no 'status' field")
                    except:
                        self.log_result("Runtime Timeline (Auth)", "FAIL", "HTTP 200 but invalid JSON")
                else:
                    self.log_result("Runtime Timeline (Auth)", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
                    
            except Exception as e:
                self.log_result("Runtime Timeline (Auth)", "FAIL", f"Exception: {str(e)}")
        else:
            self.log_result("Runtime Timeline (Auth)", "FAIL", "No admin token available")
        
        # Test without authentication
        try:
            params = {"limit": 20}
            response = self.session.get(timeline_url, params=params, timeout=15)
            
            if response.status_code == 401:
                self.log_result("Runtime Timeline (No Auth)", "PASS", "HTTP 401 as expected")
            else:
                self.log_result("Runtime Timeline (No Auth)", "FAIL", f"Expected HTTP 401, got {response.status_code}")
                
        except Exception as e:
            self.log_result("Runtime Timeline (No Auth)", "FAIL", f"Exception: {str(e)}")
    
    def test_duplicate_env_keys(self) -> None:
        """Test 3: Check for duplicate environment keys"""
        env_file_path = "/app/backend/.env"
        
        try:
            if not os.path.exists(env_file_path):
                self.log_result("Duplicate Env Check", "FAIL", f"File not found: {env_file_path}")
                return
            
            with open(env_file_path, 'r') as f:
                lines = f.readlines()
            
            keys_seen = {}
            duplicates = []
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key = line.split('=')[0].strip()
                    if key in keys_seen:
                        duplicates.append(f"Line {line_num}: {key} (first seen at line {keys_seen[key]})")
                    else:
                        keys_seen[key] = line_num
            
            # Check specifically for the mentioned keys
            critical_keys = [
                "LIVE_TRADING_ENABLED",
                "BINANCE_LIVE_API_KEY", 
                "BINANCE_LIVE_API_SECRET",
                "BINANCE_SPOT_LIVE_BASE_URL",
                "BINANCE_FUTURES_LIVE_BASE_URL"
            ]
            
            critical_duplicates = [dup for dup in duplicates if any(key in dup for key in critical_keys)]
            
            if duplicates:
                self.log_result("Duplicate Env Check", "FAIL", f"Found {len(duplicates)} duplicates: {duplicates}")
            else:
                self.log_result("Duplicate Env Check", "PASS", f"No duplicate keys found in {len(keys_seen)} environment variables")
                
            if critical_duplicates:
                self.log_result("Critical Env Duplicates", "FAIL", f"Critical duplicates: {critical_duplicates}")
            else:
                self.log_result("Critical Env Duplicates", "PASS", "No critical key duplicates found")
                
        except Exception as e:
            self.log_result("Duplicate Env Check", "FAIL", f"Exception: {str(e)}")
    
    def test_process_health(self) -> None:
        """Test 4: Check for zombie/defunct processes"""
        try:
            # Check for zombie processes
            result = subprocess.run(
                ["ps", "-eo", "pid,ppid,state,comm,args"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                zombie_processes = []
                
                for line in lines[1:]:  # Skip header
                    if line.strip():
                        parts = line.split(None, 4)
                        if len(parts) >= 3:
                            state = parts[2]
                            if state == 'Z':  # Zombie state
                                zombie_processes.append(line.strip())
                
                if zombie_processes:
                    self.log_result("Process Health", "FAIL", f"Found {len(zombie_processes)} zombie processes: {zombie_processes}")
                else:
                    self.log_result("Process Health", "PASS", f"No zombie processes found (checked {len(lines)-1} processes)")
                    
            else:
                self.log_result("Process Health", "FAIL", f"ps command failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            self.log_result("Process Health", "FAIL", "ps command timed out")
        except Exception as e:
            self.log_result("Process Health", "FAIL", f"Exception: {str(e)}")
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all validation tests"""
        print("=== Final Backend Smoke/Regression Validation ===")
        print(f"Base URL: {BASE_URL}")
        print(f"Admin Credentials: {ADMIN_EMAIL}")
        print()
        
        # Step 1: Admin login
        if not self.admin_login():
            print("❌ Admin login failed - some tests may be skipped")
        
        # Step 2: Run all tests
        self.test_health_endpoints()
        self.test_runtime_timeline_auth()
        self.test_duplicate_env_keys()
        self.test_process_health()
        
        # Calculate summary
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r["status"] == "PASS"])
        failed_tests = total_tests - passed_tests
        
        summary = {
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "success_rate": f"{(passed_tests/total_tests*100):.1f}%" if total_tests > 0 else "0%",
            "overall_status": "PASS" if failed_tests == 0 else "FAIL",
            "results": self.results
        }
        
        return summary
    
    def print_summary(self, summary: Dict[str, Any]) -> None:
        """Print test summary in Turkish format"""
        print("\n" + "="*60)
        print("FINAL BACKEND SMOKE/REGRESSION VALIDATION SUMMARY")
        print("="*60)
        
        print(f"📊 Test Results: {summary['passed']}/{summary['total_tests']} PASS ({summary['success_rate']})")
        print(f"🎯 Overall Status: {summary['overall_status']}")
        
        print("\n📋 Detailed Results:")
        for result in self.results:
            status_icon = "✅" if result["status"] == "PASS" else "❌"
            print(f"{status_icon} {result['test']}: {result['details']}")
        
        print("\n🔍 Key Findings:")
        
        # Health endpoints
        health_results = [r for r in self.results if "Health Endpoint" in r["test"]]
        health_pass = len([r for r in health_results if r["status"] == "PASS"])
        print(f"• Health Endpoints: {health_pass}/3 working")
        
        # Runtime timeline auth
        timeline_results = [r for r in self.results if "Runtime Timeline" in r["test"]]
        timeline_pass = len([r for r in timeline_results if r["status"] == "PASS"])
        print(f"• Runtime Timeline Auth: {timeline_pass}/2 tests passed")
        
        # Environment duplicates
        env_results = [r for r in self.results if "Env" in r["test"]]
        env_pass = len([r for r in env_results if r["status"] == "PASS"])
        print(f"• Environment Duplicates: {env_pass}/{len(env_results)} checks passed")
        
        # Process health
        process_results = [r for r in self.results if "Process Health" in r["test"]]
        process_pass = len([r for r in process_results if r["status"] == "PASS"])
        print(f"• Process Health: {process_pass}/1 zombie check passed")
        
        print(f"\n🏁 FINAL RESULT: {summary['overall_status']}")
        if summary['overall_status'] == "FAIL":
            failed_tests = [r for r in self.results if r["status"] == "FAIL"]
            print(f"❌ Failed Tests ({len(failed_tests)}):")
            for test in failed_tests:
                print(f"   - {test['test']}: {test['details']}")

def main():
    """Main execution function"""
    validator = BackendValidator()
    
    try:
        summary = validator.run_all_tests()
        validator.print_summary(summary)
        
        # Exit with appropriate code
        exit_code = 0 if summary['overall_status'] == "PASS" else 1
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()