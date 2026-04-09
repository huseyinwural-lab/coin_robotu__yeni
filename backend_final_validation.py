#!/usr/bin/env python3
"""
Final Backend Validation for Turkish Review Request
Testing specific endpoints for risk orchestrator and user risk settings
"""

import requests
import json
import sys
from typing import Dict, Any, List, Tuple

# Base URL from frontend .env
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"

# Test credentials from review request
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

class BackendFinalValidator:
    def __init__(self):
        self.admin_token = None
        self.user_token = None
        self.session = requests.Session()
        self.session.timeout = 30
        
    def authenticate_admin(self) -> bool:
        """Authenticate admin user"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                print(f"✅ Admin authentication successful (token length: {len(self.admin_token)} chars)")
                return True
            else:
                print(f"❌ Admin authentication failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Admin authentication error: {str(e)}")
            return False
    
    def authenticate_user(self) -> bool:
        """Authenticate user"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/user",
                json={
                    "email": USER_EMAIL,
                    "password": USER_PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get("access_token")
                print(f"✅ User authentication successful (token length: {len(self.user_token)} chars)")
                return True
            else:
                print(f"❌ User authentication failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ User authentication error: {str(e)}")
            return False
    
    def test_admin_risk_orchestrator_blocked(self) -> Tuple[bool, str]:
        """Test 1: Admin risk orchestrator write blocked - should return 410 PURE_LIVE_410"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            response = self.session.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
                headers=headers,
                json={"test": "payload"}
            )
            
            if response.status_code == 410:
                response_text = response.text
                if "PURE_LIVE_410" in response_text:
                    return True, f"✅ PASS - Returns 410 with PURE_LIVE_410: {response_text}"
                else:
                    return False, f"❌ FAIL - Returns 410 but missing PURE_LIVE_410: {response_text}"
            else:
                return False, f"❌ FAIL - Expected 410, got {response.status_code}: {response.text}"
                
        except Exception as e:
            return False, f"❌ ERROR - Exception: {str(e)}"
    
    def test_user_risk_settings_fields(self) -> Tuple[bool, str]:
        """Test 2: User risk settings merged fields exist"""
        try:
            headers = {"Authorization": f"Bearer {self.user_token}"}
            
            response = self.session.get(
                f"{BASE_URL}/api/user-risk/settings",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Required merged fields
                required_fields = [
                    "reference_equity_usd",
                    "account_max_notional_pct",
                    "symbol_max_notional_pct",
                    "strategy_max_concurrent_positions",
                    "strategy_cooldown_seconds",
                    "max_order_frequency_per_min",
                    "max_order_burst_per_10s",
                    "duplicate_suppression_window_seconds"
                ]
                
                missing_fields = []
                present_fields = []
                
                for field in required_fields:
                    if field in data:
                        present_fields.append(field)
                    else:
                        missing_fields.append(field)
                
                if not missing_fields:
                    return True, f"✅ PASS - All {len(required_fields)} merged fields present: {', '.join(present_fields)}"
                else:
                    return False, f"❌ FAIL - Missing fields: {', '.join(missing_fields)}. Present: {', '.join(present_fields)}"
            else:
                return False, f"❌ FAIL - Expected 200, got {response.status_code}: {response.text}"
                
        except Exception as e:
            return False, f"❌ ERROR - Exception: {str(e)}"
    
    def test_user_risk_settings_update(self) -> Tuple[bool, str]:
        """Test 3: User risk settings update accepts merged payload"""
        try:
            headers = {"Authorization": f"Bearer {self.user_token}"}
            
            # First get current settings
            get_response = self.session.get(
                f"{BASE_URL}/api/user-risk/settings",
                headers=headers
            )
            
            if get_response.status_code != 200:
                return False, f"❌ FAIL - Cannot get current settings: {get_response.status_code}"
            
            current_data = get_response.json()
            
            # Create update payload with all merged fields (including required base fields)
            update_payload = {
                # Required base fields
                "allocation_pct": current_data.get("allocation_pct", 20),
                "trade_risk_pct": current_data.get("trade_risk_pct", 10),
                "daily_loss_limit_pct": current_data.get("daily_loss_limit_pct", 3),
                "compounding_enabled": current_data.get("compounding_enabled", True),
                # Merged fields to test
                "reference_equity_usd": 10000.0,
                "account_max_notional_pct": 0.8,
                "symbol_max_notional_pct": 0.2,
                "strategy_max_concurrent_positions": 5,
                "strategy_cooldown_seconds": 300,
                "max_order_frequency_per_min": 10,
                "max_order_burst_per_10s": 3,
                "duplicate_suppression_window_seconds": 60
            }
            
            # Update settings
            put_response = self.session.put(
                f"{BASE_URL}/api/user-risk/settings",
                headers=headers,
                json=update_payload
            )
            
            if put_response.status_code == 200:
                updated_data = put_response.json()
                
                # Verify updated values are echoed back (only check merged fields)
                merged_fields_to_check = {
                    "reference_equity_usd": 10000.0,
                    "account_max_notional_pct": 0.8,
                    "symbol_max_notional_pct": 0.2,
                    "strategy_max_concurrent_positions": 5,
                    "strategy_cooldown_seconds": 300,
                    "max_order_frequency_per_min": 10,
                    "max_order_burst_per_10s": 3,
                    "duplicate_suppression_window_seconds": 60
                }
                
                mismatches = []
                for key, expected_value in merged_fields_to_check.items():
                    if key in updated_data:
                        actual_value = updated_data[key]
                        if actual_value != expected_value:
                            mismatches.append(f"{key}: expected {expected_value}, got {actual_value}")
                    else:
                        mismatches.append(f"{key}: missing in response")
                
                if not mismatches:
                    return True, f"✅ PASS - Update successful, all values echoed correctly"
                else:
                    return False, f"❌ FAIL - Value mismatches: {'; '.join(mismatches)}"
            else:
                return False, f"❌ FAIL - Expected 200, got {put_response.status_code}: {put_response.text}"
                
        except Exception as e:
            return False, f"❌ ERROR - Exception: {str(e)}"
    
    def test_user_scanner_trade_actions(self) -> Tuple[bool, str]:
        """Test 4: User scanner/trade actions still available (not 410)"""
        try:
            headers = {"Authorization": f"Bearer {self.user_token}"}
            
            results = []
            
            # Test scanner-engine/run-async
            scanner_response = self.session.post(
                f"{BASE_URL}/api/user/scanner-engine/run-async",
                headers=headers,
                json={"test": "payload"}
            )
            
            if scanner_response.status_code == 410:
                results.append(f"❌ scanner-engine/run-async returns 410 (should not)")
            else:
                results.append(f"✅ scanner-engine/run-async returns {scanner_response.status_code} (not 410)")
            
            # Test execution/intent/preview
            preview_response = self.session.post(
                f"{BASE_URL}/api/user/execution/intent/preview",
                headers=headers,
                json={"test": "payload"}
            )
            
            if preview_response.status_code == 410:
                results.append(f"❌ execution/intent/preview returns 410 (should not)")
            else:
                results.append(f"✅ execution/intent/preview returns {preview_response.status_code} (not 410)")
            
            # Check if any returned 410
            failed_endpoints = [r for r in results if "❌" in r]
            
            if not failed_endpoints:
                return True, f"✅ PASS - Both endpoints available: {'; '.join(results)}"
            else:
                return False, f"❌ FAIL - Some endpoints return 410: {'; '.join(results)}"
                
        except Exception as e:
            return False, f"❌ ERROR - Exception: {str(e)}"
    
    def run_validation(self):
        """Run all validation tests"""
        print("🚀 FINAL BACKEND VALIDATION STARTING")
        print(f"Base URL: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print(f"User: {USER_EMAIL}")
        print("=" * 80)
        
        # Authenticate
        if not self.authenticate_admin():
            print("❌ Cannot proceed without admin authentication")
            return False
        
        if not self.authenticate_user():
            print("❌ Cannot proceed without user authentication")
            return False
        
        print()
        
        # Run tests
        tests = [
            ("Admin risk orchestrator write blocked", self.test_admin_risk_orchestrator_blocked),
            ("User risk settings merged fields exist", self.test_user_risk_settings_fields),
            ("User risk settings update accepts merged payload", self.test_user_risk_settings_update),
            ("User scanner/trade actions still available", self.test_user_scanner_trade_actions)
        ]
        
        results = []
        
        for test_name, test_func in tests:
            print(f"🧪 Testing: {test_name}")
            success, message = test_func()
            results.append((test_name, success, message))
            print(f"   {message}")
            print()
        
        # Summary
        print("=" * 80)
        print("📊 FINAL VALIDATION SUMMARY")
        print("=" * 80)
        
        passed = 0
        failed = 0
        
        for test_name, success, message in results:
            status = "PASS" if success else "FAIL"
            print(f"{status}: {test_name}")
            if success:
                passed += 1
            else:
                failed += 1
        
        print()
        print(f"✅ PASSED: {passed}")
        print(f"❌ FAILED: {failed}")
        print(f"📈 SUCCESS RATE: {(passed / len(results) * 100):.1f}%")
        
        if failed == 0:
            print("🎉 ALL TESTS PASSED - Backend validation successful!")
            return True
        else:
            print("⚠️ SOME TESTS FAILED - Backend validation incomplete")
            return False

def main():
    validator = BackendFinalValidator()
    success = validator.run_validation()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()