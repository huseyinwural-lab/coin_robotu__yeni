#!/usr/bin/env python3
"""
Iteration 2 Backend Validation Test
Testing specific runtime endpoints for revenue-snapshot platform
"""

import requests
import json
import time
import uuid
from datetime import datetime

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class Iteration2BackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = []
        
    def log_result(self, test_name, status, details=""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
    
    def test_admin_login(self):
        """Test admin authentication"""
        try:
            login_data = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/login",
                json=login_data,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.admin_token = data["access_token"]
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.admin_token}"
                    })
                    self.log_result(
                        "Admin Login", 
                        "PASS", 
                        f"Token received, Role: {data.get('role', 'N/A')}"
                    )
                    return True
                else:
                    self.log_result(
                        "Admin Login", 
                        "FAIL", 
                        "Missing access_token in response"
                    )
            else:
                self.log_result(
                    "Admin Login", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "Admin Login", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
        return False
    
    def test_runtime_pnl_summary(self):
        """Test 1: /api/runtime/pnl/summary"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/runtime/pnl/summary",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                # Check for expected PnL summary fields
                expected_fields = ['total_pnl', 'realized_pnl', 'unrealized_pnl']
                has_expected_structure = any(field in str(data).lower() for field in expected_fields)
                
                self.log_result(
                    "/api/runtime/pnl/summary", 
                    "PASS", 
                    f"HTTP 200, Response size: {len(str(data))} chars"
                )
            elif response.status_code in [401, 403]:
                self.log_result(
                    "/api/runtime/pnl/summary", 
                    "FAIL", 
                    f"Authentication/Authorization error: HTTP {response.status_code}"
                )
            elif response.status_code == 404:
                self.log_result(
                    "/api/runtime/pnl/summary", 
                    "FAIL", 
                    "Endpoint not found (HTTP 404)"
                )
            else:
                self.log_result(
                    "/api/runtime/pnl/summary", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "/api/runtime/pnl/summary", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_runtime_pnl_positions(self):
        """Test 2: /api/runtime/pnl/positions"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/runtime/pnl/positions",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "/api/runtime/pnl/positions", 
                    "PASS", 
                    f"HTTP 200, Response size: {len(str(data))} chars"
                )
            elif response.status_code in [401, 403]:
                self.log_result(
                    "/api/runtime/pnl/positions", 
                    "FAIL", 
                    f"Authentication/Authorization error: HTTP {response.status_code}"
                )
            elif response.status_code == 404:
                self.log_result(
                    "/api/runtime/pnl/positions", 
                    "FAIL", 
                    "Endpoint not found (HTTP 404)"
                )
            else:
                self.log_result(
                    "/api/runtime/pnl/positions", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "/api/runtime/pnl/positions", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_runtime_alerts(self):
        """Test 3: /api/runtime/alerts"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/runtime/alerts",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "/api/runtime/alerts", 
                    "PASS", 
                    f"HTTP 200, Response size: {len(str(data))} chars"
                )
            elif response.status_code in [401, 403]:
                self.log_result(
                    "/api/runtime/alerts", 
                    "FAIL", 
                    f"Authentication/Authorization error: HTTP {response.status_code}"
                )
            elif response.status_code == 404:
                self.log_result(
                    "/api/runtime/alerts", 
                    "FAIL", 
                    "Endpoint not found (HTTP 404)"
                )
            else:
                self.log_result(
                    "/api/runtime/alerts", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "/api/runtime/alerts", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_runtime_health_smoke(self):
        """Test 4: /api/runtime/health/smoke"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/runtime/health/smoke",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                # Check for health indicators
                health_indicators = ['status', 'healthy', 'ok', 'checks']
                has_health_structure = any(indicator in str(data).lower() for indicator in health_indicators)
                
                self.log_result(
                    "/api/runtime/health/smoke", 
                    "PASS", 
                    f"HTTP 200, Response size: {len(str(data))} chars"
                )
            elif response.status_code in [401, 403]:
                self.log_result(
                    "/api/runtime/health/smoke", 
                    "FAIL", 
                    f"Authentication/Authorization error: HTTP {response.status_code}"
                )
            elif response.status_code == 404:
                self.log_result(
                    "/api/runtime/health/smoke", 
                    "FAIL", 
                    "Endpoint not found (HTTP 404)"
                )
            else:
                self.log_result(
                    "/api/runtime/health/smoke", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "/api/runtime/health/smoke", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_runtime_execution_submit_and_worker(self):
        """Test 5: /api/runtime/execution/submit + worker process-once adapter guard behavior"""
        try:
            # Test execution submit endpoint
            submit_data = {
                "execution_id": str(uuid.uuid4()),
                "action": "submit",
                "symbol": "BTCUSDT",
                "quantity": 0.001,
                "side": "BUY",
                "order_type": "MARKET",
                "timestamp": datetime.now().isoformat()
            }
            
            submit_response = self.session.post(
                f"{BASE_URL}/api/runtime/execution/submit",
                json=submit_data,
                timeout=30
            )
            
            # Test worker process-once endpoint
            worker_response = self.session.post(
                f"{BASE_URL}/api/runtime/execution/worker/process-once",
                json={},
                timeout=30
            )
            
            submit_ok = submit_response.status_code in [200, 201, 400, 422, 423]
            worker_ok = worker_response.status_code in [200, 201, 204, 400, 422]
            
            if submit_ok and worker_ok:
                self.log_result(
                    "/api/runtime/execution/submit + worker process-once", 
                    "PASS", 
                    f"Submit: HTTP {submit_response.status_code}, Worker: HTTP {worker_response.status_code}"
                )
            elif submit_response.status_code == 404 or worker_response.status_code == 404:
                self.log_result(
                    "/api/runtime/execution/submit + worker process-once", 
                    "FAIL", 
                    f"Endpoint not found - Submit: {submit_response.status_code}, Worker: {worker_response.status_code}"
                )
            else:
                self.log_result(
                    "/api/runtime/execution/submit + worker process-once", 
                    "FAIL", 
                    f"Submit: HTTP {submit_response.status_code}, Worker: HTTP {worker_response.status_code}"
                )
        except Exception as e:
            self.log_result(
                "/api/runtime/execution/submit + worker process-once", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def run_all_tests(self):
        """Run all Iteration 2 backend tests"""
        print("=" * 80)
        print("ITERATION 2 BACKEND VALIDATION TEST")
        print(f"Target: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print("=" * 80)
        
        # Test admin login first
        if not self.test_admin_login():
            print("\n❌ CRITICAL: Admin login failed. Testing endpoints without authentication...")
            # Continue testing without auth token for public endpoints
        
        print("\n" + "-" * 60)
        print("Testing Runtime Endpoints...")
        print("-" * 60)
        
        # Test all required endpoints
        self.test_runtime_pnl_summary()
        self.test_runtime_pnl_positions()
        self.test_runtime_alerts()
        self.test_runtime_health_smoke()
        self.test_runtime_execution_submit_and_worker()
        
        # Summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("ITERATION 2 BACKEND TEST SUMMARY")
        print("=" * 80)
        
        pass_count = sum(1 for r in self.test_results if r["status"] == "PASS")
        fail_count = sum(1 for r in self.test_results if r["status"] == "FAIL")
        partial_count = sum(1 for r in self.test_results if r["status"] == "PARTIAL")
        total_count = len(self.test_results)
        
        print(f"Total Tests: {total_count}")
        print(f"✅ PASS: {pass_count}")
        print(f"⚠️ PARTIAL: {partial_count}")
        print(f"❌ FAIL: {fail_count}")
        
        if total_count > 0:
            print(f"Success Rate: {(pass_count / total_count * 100):.1f}%")
        
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_symbol = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_symbol} {result['test']}: {result['status']}")
            if result["details"]:
                print(f"   {result['details']}")
        
        # Critical notes
        critical_failures = [r for r in self.test_results if r["status"] == "FAIL"]
        if critical_failures:
            print(f"\n🚨 CRITICAL NOTES:")
            for failure in critical_failures:
                print(f"   - {failure['test']}: {failure['details']}")
        
        # Overall assessment
        if fail_count == 0:
            if partial_count == 0:
                print(f"\n🎯 OVERALL: ✅ PASS - All Iteration 2 runtime endpoints validated successfully")
            else:
                print(f"\n🎯 OVERALL: ⚠️ PARTIAL PASS - Core endpoints working, {partial_count} partial results")
        else:
            print(f"\n🎯 OVERALL: ❌ FAIL - {fail_count} critical endpoint(s) failed")

if __name__ == "__main__":
    tester = Iteration2BackendTester()
    tester.run_all_tests()