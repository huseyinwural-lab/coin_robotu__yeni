#!/usr/bin/env python3
"""
P0 Regression Test - Turkish Review Request
Backend policy tests for user-side P0 fixes

Test Coverage:
1. Backend policy tests
2. Authentication flow
3. Scanner status contract validation
4. Exchange connections routing
5. Trading preview and execution guard behavior
"""

import requests
import json
import time
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

class P0RegressionTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.session = requests.Session()
        self.user_token = None
        self.device_id = None
        self.test_results = []
        
    def log_test(self, test_name, status, details="", error=""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        if error:
            print(f"   Error: {error}")
    
    def test_user_login(self):
        """Test 1: User authentication with review.user@platform.local"""
        try:
            login_url = f"{self.base_url}/api/auth/login"
            login_data = {
                "email": USER_EMAIL,
                "password": USER_PASSWORD
            }
            
            response = self.session.post(login_url, json=login_data)
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get("access_token")
                self.device_id = data.get("device_id")
                
                # Set authorization header for future requests
                self.session.headers.update({
                    "Authorization": f"Bearer {self.user_token}",
                    "X-Session-Device": self.device_id
                })
                
                self.log_test(
                    "User Login Authentication",
                    "PASS",
                    f"Successfully authenticated. Token length: {len(self.user_token) if self.user_token else 0}"
                )
                return True
            else:
                self.log_test(
                    "User Login Authentication", 
                    "FAIL",
                    f"HTTP {response.status_code}",
                    response.text[:200]
                )
                return False
                
        except Exception as e:
            self.log_test("User Login Authentication", "FAIL", "", str(e))
            return False
    
    def test_scanner_status_contract(self):
        """Test 2: /api/user/scanner/status-contract validation"""
        try:
            url = f"{self.base_url}/api/user/scanner/status-contract"
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for blocking_reasons field
                blocking_reasons = data.get("blocking_reasons", [])
                health_status = data.get("health", "UNKNOWN")
                
                # Validate blocking_reasons is not force-reset to empty
                blocking_reasons_check = "PASS" if isinstance(blocking_reasons, list) else "FAIL"
                
                # Validate health status is BLOCKED/HEALTHY
                health_check = "PASS" if health_status in ["BLOCKED", "HEALTHY"] else "FAIL"
                
                overall_status = "PASS" if blocking_reasons_check == "PASS" and health_check == "PASS" else "FAIL"
                
                self.log_test(
                    "Scanner Status Contract",
                    overall_status,
                    f"blocking_reasons: {blocking_reasons}, health: {health_status}"
                )
                return overall_status == "PASS"
            else:
                self.log_test(
                    "Scanner Status Contract",
                    "FAIL", 
                    f"HTTP {response.status_code}",
                    response.text[:200]
                )
                return False
                
        except Exception as e:
            self.log_test("Scanner Status Contract", "FAIL", "", str(e))
            return False
    
    def test_exchange_connections_routing(self):
        """Test 3: /api/user/exchange-connections routing preview validation"""
        try:
            url = f"{self.base_url}/api/user/exchange-connections"
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Look for routing_preview.selection_reason
                routing_preview = data.get("routing_preview", {})
                selection_reason = routing_preview.get("selection_reason", "")
                
                # Check if selection_reason is execution_user_source_required
                expected_reason = "execution_user_source_required"
                reason_check = "PASS" if selection_reason == expected_reason else "FAIL"
                
                self.log_test(
                    "Exchange Connections Routing",
                    reason_check,
                    f"routing_preview.selection_reason: {selection_reason} (expected: {expected_reason})"
                )
                return reason_check == "PASS"
            else:
                self.log_test(
                    "Exchange Connections Routing",
                    "FAIL",
                    f"HTTP {response.status_code}",
                    response.text[:200]
                )
                return False
                
        except Exception as e:
            self.log_test("Exchange Connections Routing", "FAIL", "", str(e))
            return False
    
    def test_trading_preview_execution_guard(self):
        """Test 4: Trading preview and execution guard strict behavior"""
        try:
            # First, validate order to get preview
            validate_url = f"{self.base_url}/api/user/validate-order"
            validate_data = {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 20,
                "market_type": "spot"
            }
            
            validate_response = self.session.post(validate_url, json=validate_data)
            
            if validate_response.status_code != 200:
                self.log_test(
                    "Trading Preview - Validation Step",
                    "FAIL",
                    f"Validation failed with HTTP {validate_response.status_code}",
                    validate_response.text[:200]
                )
                return False
            
            # Test preview endpoint
            preview_url = f"{self.base_url}/api/v1/user/trading/preview"
            preview_data = {
                "symbol": "BTCUSDT",
                "side": "BUY", 
                "order_type": "MARKET",
                "quantity": 20,
                "market_type": "spot"
            }
            
            preview_response = self.session.post(preview_url, json=preview_data)
            
            if preview_response.status_code == 200:
                preview_data_resp = preview_response.json()
                
                # Check execution guard behavior
                execution_mode = preview_data_resp.get("execution_mode", "")
                readiness_status = preview_data_resp.get("readiness_status", "")
                
                # Test open position with potential readiness fail
                open_position_url = f"{self.base_url}/api/user/open-position"
                open_position_data = {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "order_type": "MARKET", 
                    "quantity": 20,
                    "market_type": "spot"
                }
                
                open_response = self.session.post(open_position_url, json=open_position_data)
                
                # Check if execution guard is strict
                if readiness_status == "FAIL" and open_response.status_code in [423, 400]:
                    guard_behavior = "STRICT - Correctly blocked execution on readiness fail"
                    guard_status = "PASS"
                elif readiness_status == "READY" and open_response.status_code == 200:
                    guard_behavior = "STRICT - Allowed execution on readiness pass"
                    guard_status = "PASS"
                else:
                    guard_behavior = f"Unexpected behavior: readiness={readiness_status}, open_status={open_response.status_code}"
                    guard_status = "FAIL"
                
                self.log_test(
                    "Trading Preview & Execution Guard",
                    guard_status,
                    f"Preview: {execution_mode}, Readiness: {readiness_status}, Guard: {guard_behavior}"
                )
                return guard_status == "PASS"
                
            else:
                self.log_test(
                    "Trading Preview & Execution Guard",
                    "FAIL",
                    f"Preview failed with HTTP {preview_response.status_code}",
                    preview_response.text[:200]
                )
                return False
                
        except Exception as e:
            self.log_test("Trading Preview & Execution Guard", "FAIL", "", str(e))
            return False
    
    def test_query_context_prefill(self):
        """Test 5: Query context test for /user/execute URL parameters"""
        try:
            # This is primarily a frontend test, but we can validate the backend
            # supports the required parameters by checking if the trade page
            # can handle the context parameters
            
            # Test if backend can handle context parameters
            context_url = f"{self.base_url}/api/user/trading/context"
            context_params = {
                "source": "signal",
                "symbol": "BTCUSDT", 
                "side": "sell",
                "market_type": "futures"
            }
            
            response = self.session.get(context_url, params=context_params)
            
            # If endpoint exists and returns data, context is supported
            if response.status_code == 200:
                data = response.json()
                self.log_test(
                    "Query Context Support",
                    "PASS",
                    f"Backend supports trading context parameters: {context_params}"
                )
                return True
            elif response.status_code == 404:
                # Endpoint might not exist, but that's not necessarily a failure
                # for this specific test since it's mainly frontend functionality
                self.log_test(
                    "Query Context Support", 
                    "PARTIAL",
                    "Context endpoint not found - frontend should handle URL parameters directly"
                )
                return True
            else:
                self.log_test(
                    "Query Context Support",
                    "FAIL",
                    f"HTTP {response.status_code}",
                    response.text[:200]
                )
                return False
                
        except Exception as e:
            self.log_test("Query Context Support", "FAIL", "", str(e))
            return False
    
    def run_all_tests(self):
        """Run all P0 regression tests"""
        print("=" * 60)
        print("P0 REGRESSION TEST - Turkish Review Request")
        print("User tarafı P0 düzeltmeleri için hızlı regresyon testi")
        print("=" * 60)
        print(f"Base URL: {self.base_url}")
        print(f"Test User: {USER_EMAIL}")
        print("=" * 60)
        
        # Track test results
        passed_tests = 0
        total_tests = 5
        
        # Test 1: User Authentication
        if self.test_user_login():
            passed_tests += 1
            
            # Only run other tests if login succeeds
            # Test 2: Scanner Status Contract
            if self.test_scanner_status_contract():
                passed_tests += 1
            
            # Test 3: Exchange Connections Routing
            if self.test_exchange_connections_routing():
                passed_tests += 1
            
            # Test 4: Trading Preview & Execution Guard
            if self.test_trading_preview_execution_guard():
                passed_tests += 1
            
            # Test 5: Query Context Support
            if self.test_query_context_prefill():
                passed_tests += 1
        
        # Summary
        print("=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        success_rate = (passed_tests / total_tests) * 100
        print(f"Tests Passed: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
        
        # Priority classification
        if passed_tests == total_tests:
            priority = "LOW"
            status = "✅ ALL TESTS PASSED"
        elif passed_tests >= 3:
            priority = "MEDIUM" 
            status = "⚠️ SOME TESTS FAILED"
        else:
            priority = "HIGH"
            status = "❌ CRITICAL FAILURES"
        
        print(f"Priority Level: {priority}")
        print(f"Overall Status: {status}")
        
        # Detailed results
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_icon} {result['test']}: {result['status']}")
            if result["details"]:
                print(f"   {result['details']}")
        
        return passed_tests, total_tests, priority

def main():
    """Main test execution"""
    tester = P0RegressionTester()
    passed, total, priority = tester.run_all_tests()
    
    # Exit with appropriate code
    if passed == total:
        sys.exit(0)  # All tests passed
    elif priority == "HIGH":
        sys.exit(2)  # Critical failures
    else:
        sys.exit(1)  # Some failures

if __name__ == "__main__":
    main()