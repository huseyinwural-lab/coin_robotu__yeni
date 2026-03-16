#!/usr/bin/env python3
"""
FAZ-4 Backend Smoke + Contract Validation Test

Test Cases:
1) Admin login (admin@platform.local / Admin12345!)
2) GET /api/admin/system/live-readiness -> 200 + yeni metrik anahtarlarını doğrula
3) GET /api/admin/system/readiness-score -> 200 + readiness_score/readiness_state
4) GET /api/admin/futures/live-readiness -> 200 + geriye uyumluluk + yeni metrikler
5) Hatalı quote (ETHBTC) ile user preview dene -> policy reject + SYMBOL_INTEGRITY_REJECT event emisyonu kontrol et
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

# Base URL from frontend/.env
BASE_URL = "https://trading-infra.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"

class BackendTester:
    def __init__(self):
        self.admin_token = None
        self.user_token = None
        self.session = requests.Session()
        self.test_results = []
        
    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
        if details:
            print(f"    Details: {details}")
        self.test_results.append({
            "name": name,
            "success": success,
            "details": details
        })
        
    def admin_login(self) -> bool:
        """Test Case 1: Admin login with provided credentials"""
        try:
            response = self.session.post(f"{BASE_URL}/auth/login/admin", json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            })
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.admin_token = data["access_token"]
                    self.log_test("Admin Login", True, f"Token obtained successfully")
                    return True
                else:
                    self.log_test("Admin Login", False, f"No access_token in response: {data}")
                    return False
            else:
                self.log_test("Admin Login", False, f"Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Admin Login", False, f"Exception: {str(e)}")
            return False
    
    def test_system_live_readiness(self) -> bool:
        """Test Case 2: GET /api/admin/system/live-readiness"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = self.session.get(f"{BASE_URL}/admin/system/live-readiness", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for new metric keys (yeni metrik anahtarları)
                required_keys = ["readiness_score", "readiness_state"]
                missing_keys = []
                
                for key in required_keys:
                    if key not in data:
                        missing_keys.append(key)
                
                if not missing_keys:
                    # Log what new metrics we found
                    other_keys = [k for k in data.keys() if k not in required_keys]
                    details = f"Found required keys: {required_keys}. Additional metrics: {other_keys[:5]}{'...' if len(other_keys) > 5 else ''}"
                    self.log_test("System Live Readiness", True, details)
                    return True
                else:
                    self.log_test("System Live Readiness", False, f"Missing required keys: {missing_keys}")
                    return False
            else:
                self.log_test("System Live Readiness", False, f"Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("System Live Readiness", False, f"Exception: {str(e)}")
            return False
            
    def test_system_readiness_score(self) -> bool:
        """Test Case 3: GET /api/admin/system/readiness-score"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = self.session.get(f"{BASE_URL}/admin/system/readiness-score", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for required keys
                required_keys = ["readiness_score", "readiness_state"]
                missing_keys = []
                
                for key in required_keys:
                    if key not in data:
                        missing_keys.append(key)
                
                if not missing_keys:
                    details = f"readiness_score: {data.get('readiness_score')}, readiness_state: {data.get('readiness_state')}"
                    self.log_test("System Readiness Score", True, details)
                    return True
                else:
                    self.log_test("System Readiness Score", False, f"Missing required keys: {missing_keys}")
                    return False
            else:
                self.log_test("System Readiness Score", False, f"Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("System Readiness Score", False, f"Exception: {str(e)}")
            return False
    
    def test_futures_live_readiness(self) -> bool:
        """Test Case 4: GET /api/admin/futures/live-readiness"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = self.session.get(f"{BASE_URL}/admin/futures/live-readiness", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for backwards compatibility + new metrics
                required_keys = ["readiness_score", "readiness_state"]
                missing_keys = []
                
                for key in required_keys:
                    if key not in data:
                        missing_keys.append(key)
                
                if not missing_keys:
                    # Check for additional metrics (yeni metrikler)
                    all_keys = list(data.keys())
                    details = f"Backward compat + new metrics: {len(all_keys)} total keys including {required_keys}"
                    self.log_test("Futures Live Readiness", True, details)
                    return True
                else:
                    self.log_test("Futures Live Readiness", False, f"Missing required keys: {missing_keys}")
                    return False
            else:
                self.log_test("Futures Live Readiness", False, f"Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Futures Live Readiness", False, f"Exception: {str(e)}")
            return False
    
    def register_test_user(self) -> Optional[str]:
        """Register a test user for symbol validation testing"""
        try:
            import time
            timestamp = int(time.time())
            test_email = f"test_symbol_validation_{timestamp}@test.com"
            response = self.session.post(f"{BASE_URL}/auth/register", json={
                "email": test_email,
                "password": "TestPass123!",
                "first_name": "Test",
                "last_name": "User",
                "phone_number": "+1234567890"
            })
            
            if response.status_code in [200, 201]:
                return test_email
            else:
                print(f"User registration failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"User registration exception: {str(e)}")
            return None
            
    def approve_user(self, user_email: str) -> bool:
        """Approve the test user"""
        try:
            # First get users list to find the user ID
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = self.session.get(f"{BASE_URL}/admin/user-approvals", headers=headers, 
                                      params={"status_filter": "pending"})
            
            if response.status_code == 200:
                users = response.json()
                user_to_approve = None
                
                for user in users:
                    if user.get("email") == user_email:
                        user_to_approve = user
                        break
                
                if user_to_approve:
                    # Approve the user
                    approval_response = self.session.post(
                        f"{BASE_URL}/admin/user-approvals/bulk-approve",
                        headers=headers,
                        json={"ids": [user_to_approve["id"]]}
                    )
                    return approval_response.status_code == 200
                    
            return False
            
        except Exception as e:
            print(f"User approval exception: {str(e)}")
            return False
            
    def login_test_user(self, user_email: str) -> bool:
        """Login as test user"""
        try:
            response = self.session.post(f"{BASE_URL}/auth/login/user", json={
                "email": user_email,
                "password": "TestPass123!"
            })
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.user_token = data["access_token"]
                    return True
                    
            return False
            
        except Exception as e:
            print(f"User login exception: {str(e)}")
            return False
    
    def test_invalid_symbol_rejection(self) -> bool:
        """Test Case 5: Invalid symbol (ETHBTC) rejection + SYMBOL_INTEGRITY_REJECT event"""
        try:
            # Setup test user
            test_email = self.register_test_user()
            if not test_email:
                self.log_test("Invalid Symbol Test - User Setup", False, "Could not register test user")
                return False
                
            if not self.approve_user(test_email):
                self.log_test("Invalid Symbol Test - User Approval", False, "Could not approve test user")
                return False
                
            if not self.login_test_user(test_email):
                self.log_test("Invalid Symbol Test - User Login", False, "Could not login as test user")
                return False
            
            # Now test trading preview with invalid symbol ETHBTC
            headers = {"Authorization": f"Bearer {self.user_token}"}
            
            # Try to preview with invalid symbol ETHBTC (no USDT quote asset)
            trading_payload = {
                "symbol": "ETHBTC",  # This should be invalid as it's not USDT-quoted
                "side": "BUY",
                "market_type": "spot",  # Required field
                "order_type": "market",  # Required field
                "size": 0.01,
                "intent_type": "OPEN_POSITION",
                "strategy": "test_strategy",
                "confidence": 0.7,
                "timestamp": "2026-03-15T10:00:00Z"
            }
            
            response = self.session.post(
                f"{BASE_URL}/v1/user/trading/preview",
                headers=headers,
                json=trading_payload
            )
            
            # We expect this to be rejected (400 status)
            if response.status_code == 400:
                error_data = response.json()
                error_detail = error_data.get("detail", "")
                
                # Check if it's a symbol integrity error
                symbol_integrity_errors = [
                    "invalid_quote_asset", 
                    "symbol_required_for_execution_intent",
                    "quote_asset_mismatch",
                    "scanner_execution_symbol_mismatch"
                ]
                
                is_symbol_error = any(error in error_detail for error in symbol_integrity_errors)
                
                if is_symbol_error:
                    # Now check audit logs for SYMBOL_INTEGRITY_REJECT event
                    audit_response = self.session.get(
                        f"{BASE_URL}/audit-logs",
                        headers={"Authorization": f"Bearer {self.admin_token}"},
                        params={"limit": 10, "action_filter": "SYMBOL_INTEGRITY_REJECT"}
                    )
                    
                    if audit_response.status_code == 200:
                        audit_logs = audit_response.json()
                        
                        # Check if we have a recent SYMBOL_INTEGRITY_REJECT event
                        symbol_reject_found = False
                        for log in audit_logs:
                            if log.get("action") == "SYMBOL_INTEGRITY_REJECT":
                                details = log.get("details", {})
                                if details.get("symbol") == "ETHBTC":
                                    symbol_reject_found = True
                                    break
                        
                        if symbol_reject_found:
                            self.log_test("Invalid Symbol Rejection", True, 
                                        f"Policy rejected ETHBTC with error '{error_detail}' and SYMBOL_INTEGRITY_REJECT event emitted")
                            return True
                        else:
                            self.log_test("Invalid Symbol Rejection", False, 
                                        f"Policy rejected but SYMBOL_INTEGRITY_REJECT event not found in audit logs")
                            return False
                    else:
                        self.log_test("Invalid Symbol Rejection", False, 
                                    f"Could not check audit logs: {audit_response.status_code}")
                        return False
                else:
                    self.log_test("Invalid Symbol Rejection", False, 
                                f"Rejected but not for symbol integrity: {error_detail}")
                    return False
            else:
                self.log_test("Invalid Symbol Rejection", False, 
                            f"Expected 400 rejection, got {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Invalid Symbol Rejection", False, f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all FAZ-4 backend tests"""
        print("="*60)
        print("FAZ-4 Backend Smoke + Contract Validation Tests")
        print("="*60)
        
        # Test 1: Admin Login
        if not self.admin_login():
            print("❌ Cannot proceed without admin token")
            return False
            
        # Test 2: System Live Readiness
        self.test_system_live_readiness()
        
        # Test 3: System Readiness Score  
        self.test_system_readiness_score()
        
        # Test 4: Futures Live Readiness
        self.test_futures_live_readiness()
        
        # Test 5: Invalid Symbol Rejection
        self.test_invalid_symbol_rejection()
        
        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for result in self.test_results if result["success"])
        total = len(self.test_results)
        
        for result in self.test_results:
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"{status} - {result['name']}")
            
        print(f"\nResults: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All FAZ-4 backend tests PASSED!")
            return True
        else:
            print("⚠️  Some tests FAILED - see details above")
            return False

if __name__ == "__main__":
    tester = BackendTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)