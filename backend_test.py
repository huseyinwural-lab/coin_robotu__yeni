#!/usr/bin/env python3

"""
Backend API Testing for user1773706589@example.com
==================================================
This script performs focused backend verification testing for the specified user
after latest fixes, testing the following requirements:

1. Login as user1773706589@example.com
2. Verify default Binance futures testnet connection can be revalidated successfully  
3. Verify `/api/user/validate-order` returns `execution_mode=live` for valid payload
4. Verify preview + `/api/user/open-position` returns 200 with `intent_status=QUEUED_FOR_APPROVAL` and `execution_mode=live` (not mocked, not 423)
5. Verify `/api/exchange/test-order` micro order still works and returns final_status FILLED

Expected outcome: Pass/Fail status for each test requirement
"""

import json
import requests
import sys
import traceback
from typing import Dict, Any
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://error-tracker-80.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

# Test user credentials
TEST_USER_EMAIL = "testuser1773837415@example.com"
TEST_USER_PASSWORD = "TestPassword123!"

class BackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Backend-Test-Agent/1.0'
        })
        self.user_token = None
        self.test_results = []
    
    def log_test(self, test_name: str, success: bool, message: str, details: Dict[str, Any] = None):
        """Log a test result"""
        result = {
            'test': test_name,
            'success': success,
            'message': message,
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name} - {message}")
        if details:
            print(f"     Details: {json.dumps(details, indent=4)}")
    
    def test_user_login(self) -> bool:
        """Test 1: Login as user1773706589@example.com"""
        try:
            login_payload = {
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            }
            
            response = self.session.post(f"{API_BASE}/auth/login", json=login_payload)
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get('access_token')
                if self.user_token:
                    self.session.headers.update({'Authorization': f'Bearer {self.user_token}'})
                    user_info = data.get('user', {})
                    self.log_test(
                        "User Login", 
                        True, 
                        f"Successfully logged in as {TEST_USER_EMAIL}",
                        {
                            'user_id': user_info.get('id'),
                            'email': user_info.get('email'),
                            'role': user_info.get('role')
                        }
                    )
                    return True
                else:
                    self.log_test("User Login", False, "No access_token received in response", {'response_data': data})
                    return False
            else:
                self.log_test(
                    "User Login", 
                    False, 
                    f"Login failed with status {response.status_code}", 
                    {'response_text': response.text}
                )
                return False
                
        except Exception as e:
            self.log_test("User Login", False, f"Exception occurred: {str(e)}")
            return False
    
    def test_exchange_connection_revalidation(self) -> bool:
        """Test 2: Verify default Binance futures testnet connection can be revalidated successfully"""
        try:
            # First, get user's exchange connections
            response = self.session.get(f"{API_BASE}/user/exchange-connections")
            
            if response.status_code != 200:
                self.log_test(
                    "Exchange Connection Revalidation", 
                    False, 
                    f"Failed to get exchange connections: {response.status_code}",
                    {'response_text': response.text}
                )
                return False
            
            connections = response.json()
            
            # Find default Binance futures testnet connection
            default_connection = None
            for conn in connections:
                if (conn.get('is_default', False) and 
                    conn.get('exchange', '').lower() == 'binance' and
                    conn.get('market_type', '').lower() == 'futures' and
                    conn.get('environment', '').lower() == 'testnet'):
                    default_connection = conn
                    break
            
            if not default_connection:
                self.log_test(
                    "Exchange Connection Revalidation", 
                    False, 
                    "No default Binance futures testnet connection found",
                    {'available_connections': connections}
                )
                return False
            
            # Try to revalidate the connection
            connection_id = default_connection['id']
            response = self.session.post(f"{API_BASE}/user/exchange-connections/{connection_id}/revalidate")
            
            if response.status_code == 200:
                revalidation_data = response.json()
                is_valid = revalidation_data.get('readiness_snapshot', {}).get('is_valid', False)
                can_trade = revalidation_data.get('readiness_snapshot', {}).get('can_trade', False)
                
                success = is_valid and can_trade
                self.log_test(
                    "Exchange Connection Revalidation", 
                    success, 
                    f"Revalidation {'successful' if success else 'failed'}: is_valid={is_valid}, can_trade={can_trade}",
                    {
                        'connection_id': connection_id,
                        'exchange': revalidation_data.get('exchange'),
                        'market_type': revalidation_data.get('market_type'),
                        'environment': revalidation_data.get('environment'),
                        'readiness_snapshot': revalidation_data.get('readiness_snapshot')
                    }
                )
                return success
            else:
                self.log_test(
                    "Exchange Connection Revalidation", 
                    False, 
                    f"Revalidation request failed with status {response.status_code}",
                    {'response_text': response.text}
                )
                return False
                
        except Exception as e:
            self.log_test("Exchange Connection Revalidation", False, f"Exception occurred: {str(e)}")
            return False
    
    def test_validate_order_endpoint(self) -> bool:
        """Test 3: Verify /api/user/validate-order returns execution_mode=live for valid payload"""
        try:
            # Valid order payload for validation
            validate_payload = {
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "price": 50000.0,
                "size": 0.001,
                "leverage": 1,
                "margin_mode": "isolated"
            }
            
            response = self.session.post(f"{API_BASE}/user/validate-order", json=validate_payload)
            
            if response.status_code == 200:
                validation_data = response.json()
                execution_mode = validation_data.get('execution_mode')
                valid = validation_data.get('valid', False)
                
                # Check if execution_mode is 'live' as expected
                success = execution_mode == 'live' and valid
                self.log_test(
                    "Validate Order Endpoint", 
                    success, 
                    f"Order validation {'successful' if success else 'failed'}: execution_mode={execution_mode}, valid={valid}",
                    {
                        'execution_mode': execution_mode,
                        'valid': valid,
                        'violations': validation_data.get('violations', []),
                        'full_response': validation_data
                    }
                )
                return success
            else:
                self.log_test(
                    "Validate Order Endpoint", 
                    False, 
                    f"Validation request failed with status {response.status_code}",
                    {'response_text': response.text}
                )
                return False
                
        except Exception as e:
            self.log_test("Validate Order Endpoint", False, f"Exception occurred: {str(e)}")
            return False
    
    def test_open_position_endpoint(self) -> bool:
        """Test 4: Verify preview + /api/user/open-position returns 200 with intent_status=QUEUED_FOR_APPROVAL and execution_mode=live"""
        try:
            # Step 1: Create a preview first (via execution intent preview)
            preview_payload = {
                "source_type": "manual_trade",
                "intent_type": "OPEN_POSITION",
                "market_type": "futures",
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "position_size_mode": "fixed_notional",
                "position_size_value": 10.0,
                "execution_mode": "live"
            }
            
            # Use user_execution preview endpoint
            preview_response = self.session.post(f"{API_BASE}/user/execution/intent/preview", json=preview_payload)
            
            if preview_response.status_code != 200:
                self.log_test(
                    "Open Position - Preview", 
                    False, 
                    f"Preview request failed with status {preview_response.status_code}",
                    {'response_text': preview_response.text}
                )
                return False
                
            preview_data = preview_response.json()
            intent_token = preview_data.get('intent_token')
            preview_hash = preview_data.get('preview_hash')
            
            if not intent_token or not preview_hash:
                self.log_test(
                    "Open Position - Preview", 
                    False, 
                    "Preview successful but missing intent_token or preview_hash",
                    {'preview_data': preview_data}
                )
                return False
            
            self.log_test(
                "Open Position - Preview", 
                True, 
                "Preview created successfully",
                {
                    'intent_id': preview_data.get('intent_id'),
                    'intent_token': intent_token,
                    'validation_status': preview_data.get('validation_status'),
                    'intent_status': preview_data.get('intent_status')
                }
            )
            
            # Step 2: Submit the open position request
            submit_payload = {
                "intent_token": intent_token,
                "preview_hash": preview_hash
            }
            
            submit_response = self.session.post(f"{API_BASE}/user/open-position", json=submit_payload)
            
            if submit_response.status_code == 200:
                submit_data = submit_response.json()
                intent_status = submit_data.get('intent_status')
                execution_mode = submit_data.get('execution_mode')
                
                # Check for expected values
                success = (
                    intent_status == 'QUEUED_FOR_APPROVAL' and 
                    execution_mode == 'live' and
                    submit_response.status_code != 423  # Not locked/blocked
                )
                
                self.log_test(
                    "Open Position Endpoint", 
                    success, 
                    f"Open position {'successful' if success else 'failed'}: intent_status={intent_status}, execution_mode={execution_mode}, status_code={submit_response.status_code}",
                    {
                        'intent_id': submit_data.get('intent_id'),
                        'intent_status': intent_status,
                        'execution_mode': execution_mode,
                        'queue_state': submit_data.get('queue_state'),
                        'reason_codes': submit_data.get('reason_codes', [])
                    }
                )
                return success
            else:
                self.log_test(
                    "Open Position Endpoint", 
                    False, 
                    f"Open position request failed with status {submit_response.status_code}",
                    {'response_text': submit_response.text}
                )
                return False
                
        except Exception as e:
            self.log_test("Open Position Endpoint", False, f"Exception occurred: {str(e)}")
            traceback.print_exc()
            return False
    
    def test_exchange_test_order(self) -> bool:
        """Test 5: Verify /api/exchange/test-order micro order works and returns final_status FILLED"""
        try:
            # Test order parameters for micro order
            test_params = {
                "exchange": "binance",
                "market_type": "futures", 
                "environment": "testnet",
                "symbol": "BTCUSDT",
                "leverage": 1,
                "margin_mode": "cross",
                "position_side": "BOTH",
                "quantity": 0.001  # Micro quantity
            }
            
            response = self.session.post(f"{API_BASE}/exchange/test-order", params=test_params)
            
            if response.status_code == 200:
                test_order_data = response.json()
                final_status = test_order_data.get('final_status')
                status = test_order_data.get('status')
                
                # Check if final_status is FILLED
                success = final_status == 'FILLED'
                self.log_test(
                    "Exchange Test Order", 
                    success, 
                    f"Test order {'successful' if success else 'failed'}: final_status={final_status}, status={status}",
                    {
                        'order_id': test_order_data.get('order_id'),
                        'exchange_order_id': test_order_data.get('exchange_order_id'),
                        'symbol': test_order_data.get('symbol'),
                        'final_status': final_status,
                        'status': status,
                        'executed_qty': test_order_data.get('executed_qty'),
                        'price_avg': test_order_data.get('price_avg'),
                        'execution_time_ms': test_order_data.get('execution_time_ms'),
                        'failure_code': test_order_data.get('failure_code')
                    }
                )
                return success
            else:
                self.log_test(
                    "Exchange Test Order", 
                    False, 
                    f"Test order request failed with status {response.status_code}",
                    {'response_text': response.text}
                )
                return False
                
        except Exception as e:
            self.log_test("Exchange Test Order", False, f"Exception occurred: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all backend tests in sequence"""
        print(f"Starting Backend API Testing for {TEST_USER_EMAIL}")
        print(f"Base URL: {BASE_URL}")
        print("=" * 80)
        
        # Test 1: User Login
        if not self.test_user_login():
            print("❌ Login failed - cannot proceed with other tests")
            return False
        
        # Test 2: Exchange Connection Revalidation  
        self.test_exchange_connection_revalidation()
        
        # Test 3: Validate Order Endpoint
        self.test_validate_order_endpoint()
        
        # Test 4: Open Position Endpoint
        self.test_open_position_endpoint()
        
        # Test 5: Exchange Test Order
        self.test_exchange_test_order()
        
        return True
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        passed = sum(1 for result in self.test_results if result['success'])
        total = len(self.test_results)
        
        for result in self.test_results:
            status = "✅ PASS" if result['success'] else "❌ FAIL"
            print(f"{status}: {result['test']}")
            if not result['success'] and result['message']:
                print(f"     Reason: {result['message']}")
        
        print(f"\nOverall Result: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED!")
            return True
        else:
            print(f"⚠️  {total - passed} test(s) failed")
            return False

def main():
    """Main entry point"""
    tester = BackendTester()
    
    try:
        tester.run_all_tests()
        success = tester.print_summary()
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n❌ Testing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error occurred: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()