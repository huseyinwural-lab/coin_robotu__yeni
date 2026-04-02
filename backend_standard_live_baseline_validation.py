#!/usr/bin/env python3
"""
Backend Standard Live Baseline Validation Test
Target: https://trade-trace-engine.preview.emergentagent.com

Validates acceptance points:
1) Admin baseline is unblocked
2) Platform readiness endpoints  
3) Standard policy checks
4) User flow preparedness
"""

import requests
import json
import sys
from typing import Dict, Any, Tuple

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

class BaselineValidator:
    def __init__(self):
        self.admin_token = None
        self.user_token = None
        self.admin_session = None
        self.user_session = None
        self.results = []
        
    def log_result(self, test_name: str, status: str, details: str = "", expected: str = "", actual: str = ""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "expected": expected,
            "actual": actual
        }
        self.results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        if expected and actual:
            print(f"   Expected: {expected}")
            print(f"   Actual: {actual}")
        print()

    def authenticate_admin(self) -> bool:
        """Authenticate admin user and get token with session management"""
        try:
            # Create a session to maintain cookies
            self.admin_session = requests.Session()
            
            response = self.admin_session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    self.log_result("Admin Authentication", "PASS", f"Token obtained (length: {len(self.admin_token)})")
                    return True
                else:
                    self.log_result("Admin Authentication", "FAIL", "No access_token in response")
                    return False
            else:
                self.log_result("Admin Authentication", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Authentication", "FAIL", f"Exception: {str(e)}")
            return False

    def authenticate_user(self) -> bool:
        """Authenticate user and get token with session management"""
        try:
            # Create a session to maintain cookies
            self.user_session = requests.Session()
            
            response = self.user_session.post(
                f"{BASE_URL}/api/auth/login/user",
                json={"email": USER_EMAIL, "password": USER_PASSWORD},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get("access_token")
                if self.user_token:
                    self.log_result("User Authentication", "PASS", f"Token obtained (length: {len(self.user_token)})")
                    return True
                else:
                    self.log_result("User Authentication", "FAIL", "No access_token in response")
                    return False
            else:
                self.log_result("User Authentication", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("User Authentication", "FAIL", f"Exception: {str(e)}")
            return False

    def make_request(self, method: str, endpoint: str, token: str = None, session: requests.Session = None, **kwargs) -> Tuple[int, Dict[str, Any]]:
        """Make HTTP request with optional authentication and session management"""
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        try:
            if session:
                # Use session for cookie management
                response = session.request(
                    method=method,
                    url=f"{BASE_URL}{endpoint}",
                    headers=headers,
                    timeout=30,
                    **kwargs
                )
            else:
                # Fallback to regular requests
                response = requests.request(
                    method=method,
                    url=f"{BASE_URL}{endpoint}",
                    headers=headers,
                    timeout=30,
                    **kwargs
                )
            
            try:
                data = response.json()
            except:
                data = {"raw_response": response.text}
                
            return response.status_code, data
            
        except Exception as e:
            return 0, {"error": str(e)}

    def test_admin_baseline_unblocked(self):
        """Test 1: Admin baseline is unblocked"""
        print("=== TEST 1: Admin Baseline Unblocked ===")
        
        # 1.1: GET /api/admin/release-gate
        status, data = self.make_request("GET", "/api/admin/release-gate", self.admin_token, self.admin_session)
        if status == 200:
            gate_status = data.get("status")
            override_active = data.get("override_active")
            
            if gate_status == "PASS" and override_active == False:
                self.log_result("Release Gate", "PASS", 
                              f"status={gate_status}, override_active={override_active}")
            else:
                self.log_result("Release Gate", "FAIL",
                              f"status={gate_status}, override_active={override_active}",
                              "status=PASS, override_active=false",
                              f"status={gate_status}, override_active={override_active}")
        else:
            self.log_result("Release Gate", "FAIL", f"HTTP {status}: {data}")

        # 1.2: GET /api/admin/execution-readiness
        status, data = self.make_request("GET", "/api/admin/execution-readiness", self.admin_token, self.admin_session)
        if status == 200:
            final_status = data.get("final_status")
            mode = data.get("mode")
            go_live_allowed = data.get("go_live_allowed")
            
            if final_status == "READY" and mode == "LIVE" and go_live_allowed == True:
                self.log_result("Execution Readiness", "PASS",
                              f"final_status={final_status}, mode={mode}, go_live_allowed={go_live_allowed}")
            else:
                self.log_result("Execution Readiness", "FAIL",
                              f"final_status={final_status}, mode={mode}, go_live_allowed={go_live_allowed}",
                              "final_status=READY, mode=LIVE, go_live_allowed=true",
                              f"final_status={final_status}, mode={mode}, go_live_allowed={go_live_allowed}")
        else:
            self.log_result("Execution Readiness", "FAIL", f"HTTP {status}: {data}")

        # 1.3: GET /api/phase4/admin/production-gate
        status, data = self.make_request("GET", "/api/phase4/admin/production-gate", self.admin_token, self.admin_session)
        if status == 200:
            effective_state = data.get("effective_state")
            deploy_allowed = data.get("deploy_allowed")
            blocked_reason_codes = data.get("blocked_reason_codes", [])
            
            if effective_state == "GO" and deploy_allowed == True and len(blocked_reason_codes) == 0:
                self.log_result("Production Gate", "PASS",
                              f"effective_state={effective_state}, deploy_allowed={deploy_allowed}, blocked_reason_codes={blocked_reason_codes}")
            else:
                self.log_result("Production Gate", "FAIL",
                              f"effective_state={effective_state}, deploy_allowed={deploy_allowed}, blocked_reason_codes={blocked_reason_codes}",
                              "effective_state=GO, deploy_allowed=true, blocked_reason_codes=[]",
                              f"effective_state={effective_state}, deploy_allowed={deploy_allowed}, blocked_reason_codes={blocked_reason_codes}")
        else:
            self.log_result("Production Gate", "FAIL", f"HTTP {status}: {data}")

    def test_platform_readiness(self):
        """Test 2: Platform readiness endpoints"""
        print("=== TEST 2: Platform Readiness ===")
        
        # 2.1: GET /api/health
        status, data = self.make_request("GET", "/api/health")
        if status == 200:
            self.log_result("Health Endpoint", "PASS", f"HTTP 200: {data}")
        else:
            self.log_result("Health Endpoint", "FAIL", f"HTTP {status}: {data}")

        # 2.2: GET /api/ready
        status, data = self.make_request("GET", "/api/ready")
        if status == 200:
            ready_status = data.get("status")
            if ready_status == "ready":
                self.log_result("Ready Endpoint", "PASS", f"status={ready_status}")
            else:
                self.log_result("Ready Endpoint", "FAIL", f"status={ready_status}",
                              "status=ready", f"status={ready_status}")
        else:
            self.log_result("Ready Endpoint", "FAIL", f"HTTP {status}: {data}")

    def test_standard_policy_checks(self):
        """Test 3: Standard policy checks"""
        print("=== TEST 3: Standard Policy Checks ===")
        
        # 3.1: GET /api/phase4/live-config
        status, data = self.make_request("GET", "/api/phase4/live-config", self.admin_token, self.admin_session)
        if status == 200:
            canary_enabled = data.get("canary_enabled")
            symbol_whitelist = data.get("symbol_whitelist", [])
            disable_futures = data.get("disable_futures")
            trading_enabled = data.get("trading_enabled")
            
            if (canary_enabled == False and len(symbol_whitelist) == 0 and 
                disable_futures == False and trading_enabled == True):
                self.log_result("Live Config", "PASS",
                              f"canary_enabled={canary_enabled}, symbol_whitelist={symbol_whitelist}, disable_futures={disable_futures}, trading_enabled={trading_enabled}")
            else:
                self.log_result("Live Config", "FAIL",
                              f"canary_enabled={canary_enabled}, symbol_whitelist={symbol_whitelist}, disable_futures={disable_futures}, trading_enabled={trading_enabled}",
                              "canary_enabled=false, symbol_whitelist=[], disable_futures=false, trading_enabled=true",
                              f"canary_enabled={canary_enabled}, symbol_whitelist={symbol_whitelist}, disable_futures={disable_futures}, trading_enabled={trading_enabled}")
        else:
            self.log_result("Live Config", "FAIL", f"HTTP {status}: {data}")

        # 3.2: GET /api/venues/admin/credential-rules
        status, data = self.make_request("GET", "/api/venues/admin/credential-rules", self.admin_token, self.admin_session)
        if status == 200:
            binance_spot_live_found = False
            binance_futures_live_found = False
            
            # Debug: Print all rules to understand the structure
            # print(f"DEBUG: Found {len(data) if isinstance(data, list) else 0} credential rules")
            # print(f"DEBUG: Full credential rules response: {json.dumps(data, indent=2)}")
            # for i, rule in enumerate(data if isinstance(data, list) else []):
            #     print(f"  Rule {i}: {rule}")
            #     print(f"    venue={rule.get('venue')}, market_type={rule.get('market_type')}, environment={rule.get('environment')}")
            #     print(f"    exchange={rule.get('exchange')}, preferred_source={rule.get('preferred_source')}, fallback_enabled={rule.get('fallback_enabled')}")
            
            if isinstance(data, list):
                for rule in data:
                    exchange = rule.get("exchange")  # Changed from venue to exchange
                    market_type = rule.get("market_type")
                    environment = rule.get("environment")
                    preferred_source = rule.get("preferred_source")
                    fallback_enabled = rule.get("fallback_enabled")
                    
                    if exchange == "binance" and environment == "live":
                        if market_type == "spot":
                            binance_spot_live_found = True
                            if preferred_source == "user" and fallback_enabled == False:
                                self.log_result("Binance Live Spot Credential Rules", "PASS",
                                              f"preferred_source={preferred_source}, fallback_enabled={fallback_enabled}")
                            else:
                                self.log_result("Binance Live Spot Credential Rules", "FAIL",
                                              f"preferred_source={preferred_source}, fallback_enabled={fallback_enabled}",
                                              "preferred_source=user, fallback_enabled=false",
                                              f"preferred_source={preferred_source}, fallback_enabled={fallback_enabled}")
                        elif market_type == "futures":
                            binance_futures_live_found = True
                            if preferred_source == "user" and fallback_enabled == False:
                                self.log_result("Binance Live Futures Credential Rules", "PASS",
                                              f"preferred_source={preferred_source}, fallback_enabled={fallback_enabled}")
                            else:
                                self.log_result("Binance Live Futures Credential Rules", "FAIL",
                                              f"preferred_source={preferred_source}, fallback_enabled={fallback_enabled}",
                                              "preferred_source=user, fallback_enabled=false",
                                              f"preferred_source={preferred_source}, fallback_enabled={fallback_enabled}")
                
                if not binance_spot_live_found:
                    self.log_result("Binance Live Spot Credential Rules", "FAIL", "Rule not found")
                if not binance_futures_live_found:
                    self.log_result("Binance Live Futures Credential Rules", "FAIL", "Rule not found")
            else:
                self.log_result("Credential Rules", "FAIL", f"Unexpected response format: {data}")
        else:
            self.log_result("Credential Rules", "FAIL", f"HTTP {status}: {data}")

        # 3.3: GET /api/venues/admin/allowed-markets
        status, data = self.make_request("GET", "/api/venues/admin/allowed-markets", self.admin_token, self.admin_session)
        if status == 200:
            binance_spot_live_found = False
            binance_futures_live_found = False
            
            # Debug: Print all markets to understand the structure
            # print(f"DEBUG: Found {len(data) if isinstance(data, list) else 0} allowed markets")
            # print(f"DEBUG: Full allowed markets response: {json.dumps(data, indent=2)}")
            # for i, market in enumerate(data if isinstance(data, list) else []):
            #     print(f"  Market {i}: {market}")
            #     print(f"    venue={market.get('venue')}, market_type={market.get('market_type')}, environment={market.get('environment')}")
            #     print(f"    exchange={market.get('exchange')}, enabled={market.get('enabled')}")
            
            if isinstance(data, list):
                for market in data:
                    exchange_code = market.get("exchange_code")  # Changed from exchange to exchange_code
                    market_type = market.get("market_type")
                    environment = market.get("environment")
                    enabled = market.get("enabled")
                    
                    if exchange_code == "binance" and environment == "live":
                        if market_type == "spot":
                            binance_spot_live_found = True
                            if enabled == True:
                                self.log_result("Binance Live Spot Allowed Markets", "PASS", f"enabled={enabled}")
                            else:
                                self.log_result("Binance Live Spot Allowed Markets", "FAIL", f"enabled={enabled}",
                                              "enabled=true", f"enabled={enabled}")
                        elif market_type == "futures":
                            binance_futures_live_found = True
                            if enabled == True:
                                self.log_result("Binance Live Futures Allowed Markets", "PASS", f"enabled={enabled}")
                            else:
                                self.log_result("Binance Live Futures Allowed Markets", "FAIL", f"enabled={enabled}",
                                              "enabled=true", f"enabled={enabled}")
                
                if not binance_spot_live_found:
                    self.log_result("Binance Live Spot Allowed Markets", "FAIL", "Market not found")
                if not binance_futures_live_found:
                    self.log_result("Binance Live Futures Allowed Markets", "FAIL", "Market not found")
            else:
                self.log_result("Allowed Markets", "FAIL", f"Unexpected response format: {data}")
        else:
            self.log_result("Allowed Markets", "FAIL", f"HTTP {status}: {data}")

    def test_user_flow_preparedness(self):
        """Test 4: User flow preparedness"""
        print("=== TEST 4: User Flow Preparedness ===")
        
        # User login already tested in authenticate_user()
        
        # 4.1: GET /api/exchange/validate for futures live
        status, data = self.make_request("GET", "/api/exchange/validate", self.user_token, self.user_session,
                                       params={"exchange": "binance", "market_type": "futures", "environment": "live"})
        
        if status in [200, 403]:
            self.log_result("Exchange Validate Futures Live", "PASS", 
                          f"HTTP {status} (acceptable): {data}")
        else:
            self.log_result("Exchange Validate Futures Live", "FAIL", 
                          f"HTTP {status}: {data}",
                          "HTTP 200 or 403 (route healthy)",
                          f"HTTP {status}")

    def run_validation(self):
        """Run complete validation suite"""
        print("🚀 Starting Backend Standard Live Baseline Validation")
        print(f"Target: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print(f"User: {USER_EMAIL}")
        print("=" * 60)
        
        # Authenticate
        admin_auth_success = self.authenticate_admin()
        user_auth_success = self.authenticate_user()
        
        if not admin_auth_success:
            print("❌ Admin authentication failed - cannot proceed with admin tests")
            return False
            
        if not user_auth_success:
            print("❌ User authentication failed - cannot proceed with user tests")
            
        # Run tests
        self.test_admin_baseline_unblocked()
        self.test_platform_readiness()
        self.test_standard_policy_checks()
        
        if user_auth_success:
            self.test_user_flow_preparedness()
        else:
            self.log_result("User Flow Preparedness", "SKIP", "User authentication failed")
        
        # Summary
        print("=" * 60)
        print("📊 VALIDATION SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.results if r["status"] == "FAIL"])
        skipped_tests = len([r for r in self.results if r["status"] == "SKIP"])
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⚠️ Skipped: {skipped_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        # List failures
        failures = [r for r in self.results if r["status"] == "FAIL"]
        if failures:
            print("\n🚨 REMAINING BLOCKERS:")
            for failure in failures:
                print(f"❌ {failure['test']}: {failure['details']}")
        else:
            print("\n🎉 ALL TESTS PASSED - NO BLOCKERS DETECTED")
        
        return failed_tests == 0

if __name__ == "__main__":
    validator = BaselineValidator()
    success = validator.run_validation()
    sys.exit(0 if success else 1)