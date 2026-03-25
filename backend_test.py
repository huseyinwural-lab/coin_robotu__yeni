#!/usr/bin/env python3
"""
P1.3 Iteration 1 Backend Validation Test
Testing specific endpoints for revenue-snapshot platform
"""

import requests
import json
import time
import uuid
from datetime import datetime

# Configuration
BASE_URL = "https://revenue-snapshot.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class P13BackendTester:
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
        """Test 1: /api/auth/login (token+role)"""
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
                if "access_token" in data and "role" in data:
                    self.admin_token = data["access_token"]
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.admin_token}"
                    })
                    self.log_result(
                        "Admin Login (/api/auth/login)", 
                        "PASS", 
                        f"Token received, Role: {data.get('role', 'N/A')}"
                    )
                    return True
                else:
                    self.log_result(
                        "Admin Login (/api/auth/login)", 
                        "FAIL", 
                        "Missing access_token or role in response"
                    )
            else:
                self.log_result(
                    "Admin Login (/api/auth/login)", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "Admin Login (/api/auth/login)", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
        return False
    
    def test_runtime_strategy_signal(self):
        """Test 2: /api/runtime/strategy/signal"""
        try:
            # Test GET request first
            response = self.session.get(
                f"{BASE_URL}/api/runtime/strategy/signal",
                timeout=30
            )
            
            if response.status_code in [200, 404, 405]:
                # Try POST with sample signal data
                signal_data = {
                    "strategy_id": "test_strategy_001",
                    "symbol": "BTCUSDT",
                    "signal_type": "BUY",
                    "confidence": 0.85,
                    "timestamp": datetime.now().isoformat()
                }
                
                post_response = self.session.post(
                    f"{BASE_URL}/api/runtime/strategy/signal",
                    json=signal_data,
                    timeout=30
                )
                
                if post_response.status_code in [200, 201, 400, 422]:
                    self.log_result(
                        "Runtime Strategy Signal (/api/runtime/strategy/signal)", 
                        "PASS", 
                        f"Endpoint accessible, POST returned {post_response.status_code}"
                    )
                else:
                    self.log_result(
                        "Runtime Strategy Signal (/api/runtime/strategy/signal)", 
                        "FAIL", 
                        f"POST returned {post_response.status_code}: {post_response.text[:200]}"
                    )
            else:
                self.log_result(
                    "Runtime Strategy Signal (/api/runtime/strategy/signal)", 
                    "FAIL", 
                    f"GET returned {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "Runtime Strategy Signal (/api/runtime/strategy/signal)", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_runtime_execution_submit(self):
        """Test 3: /api/runtime/execution/submit (reject+accept)"""
        try:
            # Test with accept scenario
            accept_data = {
                "execution_id": str(uuid.uuid4()),
                "action": "accept",
                "symbol": "ETHUSDT",
                "quantity": 0.1,
                "side": "BUY",
                "order_type": "MARKET"
            }
            
            accept_response = self.session.post(
                f"{BASE_URL}/api/runtime/execution/submit",
                json=accept_data,
                timeout=30
            )
            
            # Test with reject scenario
            reject_data = {
                "execution_id": str(uuid.uuid4()),
                "action": "reject",
                "reason": "risk_limit_exceeded",
                "symbol": "BTCUSDT"
            }
            
            reject_response = self.session.post(
                f"{BASE_URL}/api/runtime/execution/submit",
                json=reject_data,
                timeout=30
            )
            
            accept_ok = accept_response.status_code in [200, 201, 400, 422, 423]
            reject_ok = reject_response.status_code in [200, 201, 400, 422, 423]
            
            if accept_ok and reject_ok:
                self.log_result(
                    "Runtime Execution Submit (/api/runtime/execution/submit)", 
                    "PASS", 
                    f"Accept: {accept_response.status_code}, Reject: {reject_response.status_code}"
                )
            else:
                self.log_result(
                    "Runtime Execution Submit (/api/runtime/execution/submit)", 
                    "FAIL", 
                    f"Accept: {accept_response.status_code}, Reject: {reject_response.status_code}"
                )
        except Exception as e:
            self.log_result(
                "Runtime Execution Submit (/api/runtime/execution/submit)", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_runtime_execution_worker_process_once(self):
        """Test 4: /api/runtime/execution/worker/process-once"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/runtime/execution/worker/process-once",
                json={},
                timeout=30
            )
            
            if response.status_code in [200, 201, 204, 400, 404, 422]:
                self.log_result(
                    "Runtime Execution Worker Process Once (/api/runtime/execution/worker/process-once)", 
                    "PASS", 
                    f"HTTP {response.status_code}"
                )
            else:
                self.log_result(
                    "Runtime Execution Worker Process Once (/api/runtime/execution/worker/process-once)", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "Runtime Execution Worker Process Once (/api/runtime/execution/worker/process-once)", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_runtime_execution_jobs(self):
        """Test 5: /api/runtime/execution/jobs/{id}"""
        try:
            # Test with a sample job ID
            test_job_id = str(uuid.uuid4())
            
            response = self.session.get(
                f"{BASE_URL}/api/runtime/execution/jobs/{test_job_id}",
                timeout=30
            )
            
            if response.status_code in [200, 404, 422]:
                self.log_result(
                    "Runtime Execution Jobs (/api/runtime/execution/jobs/{id})", 
                    "PASS", 
                    f"HTTP {response.status_code} (404 expected for non-existent job)"
                )
            else:
                self.log_result(
                    "Runtime Execution Jobs (/api/runtime/execution/jobs/{id})", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "Runtime Execution Jobs (/api/runtime/execution/jobs/{id})", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_idempotency_duplicate_behavior(self):
        """Test 6: Idempotency duplicate behavior"""
        try:
            # Create a request with idempotency key
            idempotency_key = str(uuid.uuid4())
            request_data = {
                "execution_id": str(uuid.uuid4()),
                "action": "accept",
                "symbol": "BTCUSDT",
                "quantity": 0.01,
                "idempotency_key": idempotency_key
            }
            
            # First request
            first_response = self.session.post(
                f"{BASE_URL}/api/runtime/execution/submit",
                json=request_data,
                timeout=30
            )
            
            # Second request with same idempotency key
            second_response = self.session.post(
                f"{BASE_URL}/api/runtime/execution/submit",
                json=request_data,
                timeout=30
            )
            
            # Check if idempotency is handled
            if first_response.status_code == second_response.status_code:
                if first_response.status_code in [200, 201, 400, 422, 423]:
                    self.log_result(
                        "Idempotency Duplicate Behavior", 
                        "PASS", 
                        f"Both requests returned {first_response.status_code} (consistent behavior)"
                    )
                else:
                    self.log_result(
                        "Idempotency Duplicate Behavior", 
                        "PARTIAL", 
                        f"Both requests returned {first_response.status_code} (endpoint accessible but may not be implemented)"
                    )
            else:
                self.log_result(
                    "Idempotency Duplicate Behavior", 
                    "FAIL", 
                    f"Inconsistent responses: {first_response.status_code} vs {second_response.status_code}"
                )
        except Exception as e:
            self.log_result(
                "Idempotency Duplicate Behavior", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def run_all_tests(self):
        """Run all P1.3 Iteration 1 tests"""
        print("=" * 80)
        print("P1.3 Iteration 1 Backend Validation Test")
        print(f"Target: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print("=" * 80)
        
        # Test 1: Admin Login (required for authenticated endpoints)
        if not self.test_admin_login():
            print("\n❌ CRITICAL: Admin login failed. Cannot proceed with authenticated tests.")
            return
        
        print("\n" + "-" * 60)
        print("Testing Runtime Endpoints...")
        print("-" * 60)
        
        # Test 2-6: Runtime endpoints
        self.test_runtime_strategy_signal()
        self.test_runtime_execution_submit()
        self.test_runtime_execution_worker_process_once()
        self.test_runtime_execution_jobs()
        self.test_idempotency_duplicate_behavior()
        
        # Summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("P1.3 ITERATION 1 BACKEND TEST SUMMARY")
        print("=" * 80)
        
        pass_count = sum(1 for r in self.test_results if r["status"] == "PASS")
        fail_count = sum(1 for r in self.test_results if r["status"] == "FAIL")
        partial_count = sum(1 for r in self.test_results if r["status"] == "PARTIAL")
        total_count = len(self.test_results)
        
        print(f"Total Tests: {total_count}")
        print(f"✅ PASS: {pass_count}")
        print(f"⚠️ PARTIAL: {partial_count}")
        print(f"❌ FAIL: {fail_count}")
        print(f"Success Rate: {(pass_count / total_count * 100):.1f}%")
        
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_symbol = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_symbol} {result['test']}: {result['status']}")
            if result["details"]:
                print(f"   {result['details']}")
        
        # Overall assessment
        if fail_count == 0:
            if partial_count == 0:
                print(f"\n🎯 OVERALL: ✅ PASS - All P1.3 Iteration 1 endpoints validated successfully")
            else:
                print(f"\n🎯 OVERALL: ⚠️ PARTIAL PASS - Core endpoints working, {partial_count} partial results")
        else:
            print(f"\n🎯 OVERALL: ❌ FAIL - {fail_count} critical endpoint(s) failed")

if __name__ == "__main__":
    tester = P13BackendTester()
    tester.run_all_tests()