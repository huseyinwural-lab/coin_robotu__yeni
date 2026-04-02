#!/usr/bin/env python3
"""
Futures BUY Timeout Issue Validation Test
Turkish Review Request: Futures BUY timeout sorunu için son doğrulama testi

Test Steps:
1) Login with review.user@platform.local / ReviewUser123!
2) Open /user/trade-entry 
3) Select Futures connection
4) Send BUY preview request
5) Wait 60 seconds for preview panel (don't give short timeout)
6) If validation_status is valid/approved, confirm it
7) Report results

Environment: http://127.0.0.1:3000 (Frontend), http://127.0.0.1:8001 (Backend)
"""

import requests
import json
import time
import sys
from datetime import datetime

# Configuration
FRONTEND_URL = "http://127.0.0.1:3000"
BACKEND_URL = "http://127.0.0.1:8001"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

class FuturesBuyTimeoutTest:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'FuturesBuyTimeoutTest/1.0'
        })
        self.auth_token = None
        self.test_results = []
        
    def log_result(self, step, status, message, details=None):
        """Log test result"""
        result = {
            'step': step,
            'status': status,
            'message': message,
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {step}: {status} - {message}")
        if details:
            for key, value in details.items():
                print(f"   {key}: {value}")
        print()

    def test_user_login(self):
        """Test 1: User Login"""
        try:
            login_url = f"{BACKEND_URL}/api/auth/login"
            login_data = {
                "email": USER_EMAIL,
                "password": USER_PASSWORD
            }
            
            print(f"🔐 Attempting user login: {USER_EMAIL}")
            response = self.session.post(login_url, json=login_data, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get('access_token')
                if self.auth_token:
                    # Set authorization header for future requests
                    self.session.headers.update({
                        'Authorization': f'Bearer {self.auth_token}'
                    })
                    self.log_result(
                        "Step 1: User Login", 
                        "PASS", 
                        f"Successfully authenticated as {USER_EMAIL}",
                        {
                            "token_length": len(self.auth_token),
                            "response_time": f"{response.elapsed.total_seconds():.2f}s"
                        }
                    )
                    return True
                else:
                    self.log_result("Step 1: User Login", "FAIL", "No access token in response")
                    return False
            else:
                self.log_result(
                    "Step 1: User Login", 
                    "FAIL", 
                    f"Login failed with status {response.status_code}",
                    {"response": response.text[:200]}
                )
                return False
                
        except Exception as e:
            self.log_result("Step 1: User Login", "FAIL", f"Login error: {str(e)}")
            return False

    def get_futures_connection(self):
        """Get futures connection for the user"""
        try:
            connections_url = f"{BACKEND_URL}/api/user/exchange-connections"
            response = self.session.get(connections_url, timeout=30)
            
            if response.status_code == 200:
                connections = response.json()
                print(f"📋 Found {len(connections)} total connections:")
                
                # Show all connections for debugging
                for i, conn in enumerate(connections):
                    print(f"   {i+1}. {conn.get('label', 'Unknown')} - market_type: {conn.get('market_type')}, active: {conn.get('is_active', False)}")
                
                # Look for futures connection (active or not)
                futures_connections = [conn for conn in connections if conn.get('market_type') == 'futures']
                
                if futures_connections:
                    # Prefer active futures connection, but use any if none active
                    active_futures = [conn for conn in futures_connections if conn.get('is_active', False)]
                    selected_connection = active_futures[0] if active_futures else futures_connections[0]
                    
                    print(f"🎯 Selected futures connection: {selected_connection.get('label', 'Unknown')} (active: {selected_connection.get('is_active', False)})")
                    return selected_connection
                else:
                    self.log_result(
                        "Step 2: Get Futures Connection", 
                        "FAIL", 
                        "No futures connection found (any market_type)",
                        {"available_connections": len(connections), "connection_types": [conn.get('market_type') for conn in connections]}
                    )
                    return None
                        
            else:
                self.log_result(
                    "Step 2: Get Futures Connection", 
                    "FAIL", 
                    f"Failed to get connections: {response.status_code}"
                )
                return None
                
        except Exception as e:
            self.log_result("Step 2: Get Futures Connection", "FAIL", f"Error: {str(e)}")
            return None

    def test_futures_buy_preview(self, connection_id):
        """Test 3: Futures BUY Preview Request with 60s timeout"""
        try:
            # First validate the order
            validate_url = f"{BACKEND_URL}/api/user/validate-order"
            validate_payload = {
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "size": 60.0,  # 60 USDT notional
                "size_mode": "usdt",
                "leverage": 1,
                "margin_mode": "isolated",
                "connection_id": connection_id
            }
            
            print(f"📊 Validating FUTURES BUY order...")
            validate_response = self.session.post(validate_url, json=validate_payload, timeout=30)
            
            if validate_response.status_code != 200:
                self.log_result(
                    "Step 3: Futures BUY Validation", 
                    "FAIL", 
                    f"Validation failed: {validate_response.status_code}",
                    {"response": validate_response.text[:200]}
                )
                return False
                
            validate_data = validate_response.json()
            if not validate_data.get('valid', False):
                self.log_result(
                    "Step 3: Futures BUY Validation", 
                    "FAIL", 
                    "Order validation failed",
                    {"violations": validate_data.get('violations', [])}
                )
                return False
                
            self.log_result(
                "Step 3: Futures BUY Validation", 
                "PASS", 
                "Order validation successful",
                {
                    "execution_mode": validate_data.get('execution_mode'),
                    "violations": len(validate_data.get('violations', []))
                }
            )
            
            # Now test preview with 60s timeout
            preview_url = f"{BACKEND_URL}/api/v1/user/trading/preview"
            preview_payload = {
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "size": 60.0,
                "size_mode": "usdt",
                "leverage": 1,
                "margin_mode": "isolated",
                "connection_id": connection_id
            }
            
            print(f"⏱️ Sending FUTURES BUY preview request with 60s timeout...")
            start_time = time.time()
            
            # Use 60 second timeout as requested
            preview_response = self.session.post(preview_url, json=preview_payload, timeout=60)
            
            response_time = time.time() - start_time
            
            if preview_response.status_code == 200:
                preview_data = preview_response.json()
                validation_status = preview_data.get('validation_status', 'unknown')
                
                # Check for intent_token in top level or nested in preview
                intent_token = preview_data.get('intent_token')
                if not intent_token and 'preview' in preview_data:
                    intent_token = preview_data['preview'].get('intent_token')
                
                # Check for validation_status in nested preview
                if validation_status == 'unknown' and 'preview' in preview_data:
                    validation_status = preview_data['preview'].get('validation_status', validation_status)
                
                self.log_result(
                    "Step 4: Futures BUY Preview (60s timeout)", 
                    "PASS", 
                    f"Preview request successful in {response_time:.1f}s",
                    {
                        "validation_status": validation_status,
                        "intent_token": intent_token[:20] + "..." if intent_token else 'N/A',
                        "response_time": f"{response_time:.1f}s",
                        "preview_keys": list(preview_data.keys()),
                        "nested_preview_keys": list(preview_data.get('preview', {}).keys()) if 'preview' in preview_data else []
                    }
                )
                
                # Check if validation_status is valid/approved OR if we have an intent_token (which means preview succeeded)
                if validation_status in ['valid', 'approved']:
                    # Update preview_data to include the nested intent_token if needed
                    if intent_token and not preview_data.get('intent_token'):
                        preview_data['intent_token'] = intent_token
                    return self.test_futures_buy_confirm(preview_data)
                elif validation_status == 'rejected':
                    # Preview was rejected - show rejection reasons
                    reject_reasons = []
                    if 'preview' in preview_data:
                        reject_reasons = preview_data['preview'].get('reject_reason_codes', [])
                    
                    self.log_result(
                        "Step 5: Validation Status Check", 
                        "FAIL", 
                        f"Preview was rejected with validation_status: '{validation_status}'",
                        {
                            "reject_reason_codes": reject_reasons,
                            "intent_token_present": bool(intent_token)
                        }
                    )
                    return False
                elif intent_token:
                    # We have intent_token but unknown validation status - try to proceed
                    self.log_result(
                        "Step 5: Validation Status Check", 
                        "WARN", 
                        f"validation_status is '{validation_status}' but intent_token present - proceeding",
                        {"intent_token_present": True}
                    )
                    # Update preview_data to include the nested intent_token if needed
                    if not preview_data.get('intent_token'):
                        preview_data['intent_token'] = intent_token
                    return self.test_futures_buy_confirm(preview_data)
                else:
                    self.log_result(
                        "Step 5: Validation Status Check", 
                        "FAIL", 
                        f"validation_status is '{validation_status}' and no intent_token present",
                        {
                            "preview_response_keys": list(preview_data.keys()),
                            "nested_preview_keys": list(preview_data.get('preview', {}).keys()) if 'preview' in preview_data else []
                        }
                    )
                    return False
                    
            else:
                self.log_result(
                    "Step 4: Futures BUY Preview (60s timeout)", 
                    "FAIL", 
                    f"Preview failed: {preview_response.status_code} in {response_time:.1f}s",
                    {"response": preview_response.text[:200]}
                )
                return False
                
        except requests.exceptions.Timeout:
            self.log_result(
                "Step 4: Futures BUY Preview (60s timeout)", 
                "FAIL", 
                "Preview request timed out after 60 seconds"
            )
            return False
        except Exception as e:
            self.log_result("Step 4: Futures BUY Preview (60s timeout)", "FAIL", f"Error: {str(e)}")
            return False

    def test_futures_buy_confirm(self, preview_data):
        """Test 5: Futures BUY Confirm Order"""
        try:
            intent_token = preview_data.get('intent_token')
            if not intent_token:
                self.log_result("Step 5: Futures BUY Confirm", "FAIL", "No intent_token in preview data")
                return False
                
            confirm_url = f"{BACKEND_URL}/api/user/open-position"
            confirm_payload = {
                "intent_token": intent_token
            }
            
            print(f"🚀 Confirming FUTURES BUY order...")
            confirm_response = self.session.post(confirm_url, json=confirm_payload, timeout=60)
            
            if confirm_response.status_code == 200:
                confirm_data = confirm_response.json()
                self.log_result(
                    "Step 5: Futures BUY Confirm", 
                    "PASS", 
                    "Order confirmation successful",
                    {
                        "execution_mode": confirm_data.get('execution_mode'),
                        "intent_status": confirm_data.get('intent_status'),
                        "order_id": confirm_data.get('order_id', 'N/A')
                    }
                )
                return True
            else:
                self.log_result(
                    "Step 5: Futures BUY Confirm", 
                    "FAIL", 
                    f"Confirmation failed: {confirm_response.status_code}",
                    {"response": confirm_response.text[:200]}
                )
                return False
                
        except Exception as e:
            self.log_result("Step 5: Futures BUY Confirm", "FAIL", f"Error: {str(e)}")
            return False

    def run_test(self):
        """Run the complete Futures BUY timeout test"""
        print("=" * 80)
        print("FUTURES BUY TIMEOUT ISSUE VALIDATION TEST")
        print("Turkish Review Request: Futures BUY timeout sorunu için son doğrulama testi")
        print("=" * 80)
        print(f"Frontend URL: {FRONTEND_URL}")
        print(f"Backend URL: {BACKEND_URL}")
        print(f"User: {USER_EMAIL}")
        print("=" * 80)
        print()
        
        # Test 1: User Login
        if not self.test_user_login():
            return self.generate_summary()
            
        # Test 2: Get Futures Connection
        futures_connection = self.get_futures_connection()
        if not futures_connection:
            return self.generate_summary()
            
        connection_id = futures_connection.get('id')
        connection_label = futures_connection.get('label', 'Unknown')
        
        self.log_result(
            "Step 2: Futures Connection Selection", 
            "PASS", 
            f"Futures connection found: {connection_label}",
            {
                "connection_id": connection_id,
                "market_type": futures_connection.get('market_type'),
                "venue": futures_connection.get('venue')
            }
        )
        
        # Test 3-5: Futures BUY Preview and Confirm
        self.test_futures_buy_preview(connection_id)
        
        return self.generate_summary()

    def generate_summary(self):
        """Generate test summary"""
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r['status'] == 'PASS'])
        failed_tests = len([r for r in self.test_results if r['status'] == 'FAIL'])
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%" if total_tests > 0 else "0%")
        print()
        
        # Detailed results
        for result in self.test_results:
            status_icon = "✅" if result['status'] == "PASS" else "❌" if result['status'] == "FAIL" else "⚠️"
            print(f"{status_icon} {result['step']}: {result['status']} - {result['message']}")
        
        print()
        print("=" * 80)
        print("RAPOR (REPORT)")
        print("=" * 80)
        
        # Check specific questions from review request
        buy_preview_success = any(
            r['step'].startswith('Step 4: Futures BUY Preview') and r['status'] == 'PASS' 
            for r in self.test_results
        )
        
        confirm_success = any(
            r['step'].startswith('Step 5: Futures BUY Confirm') and r['status'] == 'PASS' 
            for r in self.test_results
        )
        
        print(f"- BUY preview geldi mi? {'✅ EVET' if buy_preview_success else '❌ HAYIR'}")
        print(f"- confirm başarılı mı? {'✅ EVET' if confirm_success else '❌ HAYIR'}")
        
        if not buy_preview_success or not confirm_success:
            print("- başarısızsa tek kök neden:")
            for result in self.test_results:
                if result['status'] == 'FAIL':
                    print(f"  • {result['step']}: {result['message']}")
        
        print("=" * 80)
        
        return {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'success_rate': (passed_tests/total_tests*100) if total_tests > 0 else 0,
            'buy_preview_success': buy_preview_success,
            'confirm_success': confirm_success,
            'results': self.test_results
        }

if __name__ == "__main__":
    test = FuturesBuyTimeoutTest()
    summary = test.run_test()
    
    # Exit with appropriate code
    sys.exit(0 if summary['success_rate'] >= 80 else 1)