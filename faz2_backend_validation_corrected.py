#!/usr/bin/env python3
"""
FAZ-2 Backend Deep Validation Test - CORRECTED VERSION
Comprehensive backend API validation for Phase-2 rollout/bulk/rollback operations
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://identity-control-1.preview.emergentagent.com"
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
OPS_EMAIL = "canary.ops@platform.local"
OPS_PASSWORD = "CanaryOps123!"

class Faz2BackendValidator:
    def __init__(self):
        self.session = requests.Session()
        self.super_admin_token = None
        self.ops_token = None
        self.test_results = []
        
    def log_test(self, test_name, status, details=None, error=None):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details,
            "error": error
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "⚠️" if status == "PARTIAL" else "❌"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        if error:
            print(f"   Error: {error}")
    
    def login_super_admin(self):
        """Login as super admin and extract token"""
        try:
            login_data = {
                "email": SUPER_ADMIN_EMAIL,
                "password": SUPER_ADMIN_PASSWORD
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=login_data,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.super_admin_token = data.get("access_token")
                self.log_test("Super Admin Login", "PASS", f"Token length: {len(self.super_admin_token) if self.super_admin_token else 0}")
                return True
            else:
                self.log_test("Super Admin Login", "FAIL", f"Status: {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_test("Super Admin Login", "FAIL", None, str(e))
            return False
    
    def login_ops_user(self):
        """Login as ops user and extract token"""
        try:
            login_data = {
                "email": OPS_EMAIL,
                "password": OPS_PASSWORD
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=login_data,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.ops_token = data.get("access_token")
                self.log_test("Ops User Login", "PASS", f"Token length: {len(self.ops_token) if self.ops_token else 0}")
                return True
            else:
                self.log_test("Ops User Login", "FAIL", f"Status: {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_test("Ops User Login", "FAIL", None, str(e))
            return False
    
    def test_strategy_control_overview(self):
        """Test 1: GET /api/admin/futures/strategy-control/overview"""
        try:
            headers = {"Authorization": f"Bearer {self.super_admin_token}"}
            
            response = self.session.get(
                f"{BASE_URL}/api/admin/futures/strategy-control/overview",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check required fields
                required_fields = ["phase_scope", "bulk_capabilities", "rollout_policy"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_test("Strategy Control Overview", "FAIL", None, f"Missing fields: {missing_fields}")
                    return False
                
                # Validate phase_scope
                expected_phase_scope = "phase_2_rollout_bulk_rollback"
                if data.get("phase_scope") != expected_phase_scope:
                    self.log_test("Strategy Control Overview", "FAIL", None, f"phase_scope: expected {expected_phase_scope}, got {data.get('phase_scope')}")
                    return False
                
                # Validate bulk_capabilities
                expected_capabilities = ["pause", "resume", "throttle"]
                actual_capabilities = data.get("bulk_capabilities", [])
                if set(actual_capabilities) != set(expected_capabilities):
                    self.log_test("Strategy Control Overview", "FAIL", None, f"bulk_capabilities: expected {expected_capabilities}, got {actual_capabilities}")
                    return False
                
                # Validate rollout_policy thresholds (corrected structure)
                rollout_policy = data.get("rollout_policy", {})
                auto_rollback_thresholds = rollout_policy.get("auto_rollback_thresholds", {})
                
                # Check health threshold (health_score_min should be 50)
                health_threshold = auto_rollback_thresholds.get("health_score_min")
                if health_threshold != 50.0:
                    self.log_test("Strategy Control Overview", "FAIL", None, f"health threshold: expected 50, got {health_threshold}")
                    return False
                
                # Check error threshold (error_rate_max_pct should be 3)
                error_threshold = auto_rollback_thresholds.get("error_rate_max_pct")
                if error_threshold != 3.0:
                    self.log_test("Strategy Control Overview", "FAIL", None, f"error threshold: expected 3, got {error_threshold}")
                    return False
                
                self.log_test("Strategy Control Overview", "PASS", f"phase_scope={data.get('phase_scope')}, bulk_capabilities={actual_capabilities}, thresholds=health:{health_threshold},error:{error_threshold}")
                return True
                
            else:
                self.log_test("Strategy Control Overview", "FAIL", f"Status: {response.status_code}", response.text[:500])
                return False
                
        except Exception as e:
            self.log_test("Strategy Control Overview", "FAIL", None, str(e))
            return False
    
    def test_rollout_precheck(self):
        """Test 2: GET /api/admin/futures/strategy/{id}/rollout-precheck"""
        try:
            headers = {"Authorization": f"Bearer {self.super_admin_token}"}
            
            # First get strategy list to find a strategy ID
            overview_response = self.session.get(
                f"{BASE_URL}/api/admin/futures/strategy-control/overview",
                headers=headers,
                timeout=30
            )
            
            if overview_response.status_code != 200:
                self.log_test("Rollout Precheck", "FAIL", None, "Could not get strategy list for testing")
                return False
            
            strategies = overview_response.json().get("strategies", [])
            if not strategies:
                self.log_test("Rollout Precheck", "FAIL", None, "No strategies available for testing")
                return False
            
            strategy_id = strategies[0].get("strategy_id")
            if not strategy_id:
                self.log_test("Rollout Precheck", "FAIL", None, "Could not extract strategy ID")
                return False
            
            # Test rollout precheck
            response = self.session.get(
                f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollout-precheck",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for required check types in the corrected structure
                expected_checks = ["health", "recent_error", "drift", "checklist"]
                
                precheck = data.get("precheck", {})
                checks = precheck.get("checks", {})
                
                checks_found = list(checks.keys()) if isinstance(checks, dict) else []
                missing_checks = [check for check in expected_checks if check not in checks_found]
                
                if missing_checks:
                    self.log_test("Rollout Precheck", "PARTIAL", f"Strategy: {strategy_id}, Found checks: {checks_found}, Missing: {missing_checks}")
                    return False
                else:
                    # Verify each check has proper structure
                    check_details = []
                    for check_name in expected_checks:
                        check_data = checks.get(check_name, {})
                        ok_status = check_data.get("ok", "unknown")
                        check_details.append(f"{check_name}:{ok_status}")
                    
                    self.log_test("Rollout Precheck", "PASS", f"Strategy: {strategy_id}, All required checks found: {', '.join(check_details)}")
                    return True
                
            else:
                self.log_test("Rollout Precheck", "FAIL", f"Strategy: {strategy_id}, Status: {response.status_code}", response.text[:500])
                return False
                
        except Exception as e:
            self.log_test("Rollout Precheck", "FAIL", None, str(e))
            return False
    
    def test_strategy_actions(self):
        """Test 3: POST promote-shadow/rollout/rollback actions"""
        try:
            headers = {"Authorization": f"Bearer {self.super_admin_token}"}
            
            # Get strategy ID
            overview_response = self.session.get(
                f"{BASE_URL}/api/admin/futures/strategy-control/overview",
                headers=headers,
                timeout=30
            )
            
            if overview_response.status_code != 200:
                self.log_test("Strategy Actions", "FAIL", None, "Could not get strategy list")
                return False
            
            strategies = overview_response.json().get("strategies", [])
            if not strategies:
                self.log_test("Strategy Actions", "FAIL", None, "No strategies available")
                return False
            
            strategy_id = strategies[0].get("strategy_id")
            
            # Test different action endpoints
            actions_to_test = [
                ("promote-shadow", "promote_shadow"),
                ("rollout", "rollout"),
                ("rollback", "rollback")
            ]
            
            all_passed = True
            action_results = []
            
            for action_path, action_name in actions_to_test:
                try:
                    payload = {
                        "reason": f"Test {action_name} action for Faz-2 validation",
                        "confirm_phrase": f"CONFIRM {action_name.upper()}"
                    }
                    
                    response = self.session.post(
                        f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/{action_path}",
                        headers=headers,
                        json=payload,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Check response contract
                        required_fields = ["status", "trace_id", "message", "state_snapshot"]
                        missing_fields = [field for field in required_fields if field not in data]
                        
                        if missing_fields:
                            action_results.append(f"{action_name}: FAIL (missing fields: {missing_fields})")
                            all_passed = False
                        else:
                            trace_id = data.get('trace_id', '')
                            trace_short = trace_id[:8] + "..." if len(trace_id) > 8 else trace_id
                            action_results.append(f"{action_name}: PASS (trace_id: {trace_short})")
                    else:
                        action_results.append(f"{action_name}: FAIL (status: {response.status_code})")
                        all_passed = False
                        
                except Exception as e:
                    action_results.append(f"{action_name}: FAIL (error: {str(e)[:50]})")
                    all_passed = False
            
            status = "PASS" if all_passed else "PARTIAL"
            self.log_test("Strategy Actions", status, f"Strategy: {strategy_id}, Results: {', '.join(action_results)}")
            return all_passed
            
        except Exception as e:
            self.log_test("Strategy Actions", "FAIL", None, str(e))
            return False
    
    def test_bulk_action_validation(self):
        """Test 4: POST /api/admin/futures/strategy/bulk-action validation"""
        try:
            headers = {"Authorization": f"Bearer {self.super_admin_token}"}
            
            # Get strategy IDs
            overview_response = self.session.get(
                f"{BASE_URL}/api/admin/futures/strategy-control/overview",
                headers=headers,
                timeout=30
            )
            
            if overview_response.status_code != 200:
                self.log_test("Bulk Action Validation", "FAIL", None, "Could not get strategy list")
                return False
            
            strategies = overview_response.json().get("strategies", [])
            if not strategies:
                self.log_test("Bulk Action Validation", "FAIL", None, "No strategies available")
                return False
            
            strategy_ids = [s.get("strategy_id") for s in strategies[:2]]  # Test with first 2 strategies
            
            # Test allowed actions (should succeed) - with confirm_phrase
            allowed_actions = ["pause", "resume", "throttle"]
            allowed_results = []
            
            for action in allowed_actions:
                try:
                    payload = {
                        "strategy_ids": strategy_ids,
                        "action": action,
                        "reason": f"Test bulk {action} for Faz-2 validation",
                        "confirm_phrase": f"CONFIRM BULK {action.upper()}"
                    }
                    
                    response = self.session.post(
                        f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
                        headers=headers,
                        json=payload,
                        timeout=30
                    )
                    
                    if response.status_code in [200, 202]:  # Accept both success codes
                        allowed_results.append(f"{action}: ACCEPTED")
                    else:
                        allowed_results.append(f"{action}: REJECTED (status: {response.status_code})")
                        
                except Exception as e:
                    allowed_results.append(f"{action}: ERROR ({str(e)[:30]})")
            
            # Test forbidden actions (should be rejected)
            forbidden_actions = ["disable", "decommission"]
            forbidden_results = []
            
            for action in forbidden_actions:
                try:
                    payload = {
                        "strategy_ids": strategy_ids,
                        "action": action,
                        "reason": f"Test bulk {action} for Faz-2 validation",
                        "confirm_phrase": f"CONFIRM BULK {action.upper()}"
                    }
                    
                    response = self.session.post(
                        f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
                        headers=headers,
                        json=payload,
                        timeout=30
                    )
                    
                    if response.status_code in [400, 403, 422]:  # Should be rejected
                        forbidden_results.append(f"{action}: CORRECTLY_REJECTED")
                    else:
                        forbidden_results.append(f"{action}: INCORRECTLY_ACCEPTED (status: {response.status_code})")
                        
                except Exception as e:
                    forbidden_results.append(f"{action}: ERROR ({str(e)[:30]})")
            
            # Evaluate results
            all_allowed_accepted = all("ACCEPTED" in result for result in allowed_results)
            all_forbidden_rejected = all("CORRECTLY_REJECTED" in result for result in forbidden_results)
            
            if all_allowed_accepted and all_forbidden_rejected:
                status = "PASS"
            else:
                status = "PARTIAL"
            
            details = f"Allowed: {', '.join(allowed_results)}; Forbidden: {', '.join(forbidden_results)}"
            self.log_test("Bulk Action Validation", status, details)
            
            return all_allowed_accepted and all_forbidden_rejected
            
        except Exception as e:
            self.log_test("Bulk Action Validation", "FAIL", None, str(e))
            return False
    
    def test_ops_access_control(self):
        """Test 5: Ops user access control for super_admin-only endpoints"""
        try:
            if not self.ops_token:
                self.log_test("Ops Access Control", "FAIL", None, "Ops token not available")
                return False
            
            headers = {"Authorization": f"Bearer {self.ops_token}"}
            
            # Test super_admin-only endpoint with ops token
            response = self.session.get(
                f"{BASE_URL}/api/admin/futures/strategy-control/overview",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 403:
                # Check if response indicates super_admin_only restriction
                response_text = response.text.lower()
                if "super_admin" in response_text or "forbidden" in response_text or "access" in response_text:
                    self.log_test("Ops Access Control", "PASS", "Ops user correctly blocked with 403")
                    return True
                else:
                    self.log_test("Ops Access Control", "PARTIAL", f"403 returned but unclear reason: {response.text[:100]}")
                    return True  # Still counts as pass since access was blocked
            else:
                self.log_test("Ops Access Control", "FAIL", f"Expected 403, got {response.status_code}", response.text[:200])
                return False
                
        except Exception as e:
            self.log_test("Ops Access Control", "FAIL", None, str(e))
            return False
    
    def run_all_tests(self):
        """Run all Faz-2 backend validation tests"""
        print("=" * 80)
        print("FAZ-2 BACKEND DEEP VALIDATION TEST - CORRECTED VERSION")
        print("=" * 80)
        print(f"Base URL: {BASE_URL}")
        print(f"Super Admin: {SUPER_ADMIN_EMAIL}")
        print(f"Ops User: {OPS_EMAIL}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("=" * 80)
        
        # Login phase
        print("\n🔐 AUTHENTICATION PHASE")
        super_admin_login_success = self.login_super_admin()
        ops_login_success = self.login_ops_user()
        
        if not super_admin_login_success:
            print("\n❌ CRITICAL: Super admin login failed. Cannot proceed with tests.")
            return False
        
        # Test phase
        print("\n🧪 TESTING PHASE")
        test_results = []
        
        test_results.append(self.test_strategy_control_overview())
        test_results.append(self.test_rollout_precheck())
        test_results.append(self.test_strategy_actions())
        test_results.append(self.test_bulk_action_validation())
        
        if ops_login_success:
            test_results.append(self.test_ops_access_control())
        else:
            self.log_test("Ops Access Control", "SKIP", "Ops login failed")
            test_results.append(False)
        
        # Summary
        print("\n" + "=" * 80)
        print("FAZ-2 BACKEND VALIDATION SUMMARY")
        print("=" * 80)
        
        passed_tests = sum(1 for result in test_results if result)
        total_tests = len(test_results)
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"Tests Passed: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
        
        # Detailed results
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_symbol = "✅" if result["status"] == "PASS" else "⚠️" if result["status"] == "PARTIAL" else "❌"
            print(f"{status_symbol} {result['test']}: {result['status']}")
            if result.get("details"):
                print(f"   {result['details']}")
            if result.get("error"):
                print(f"   Error: {result['error']}")
        
        # Final assessment
        print("\n" + "=" * 80)
        if success_rate >= 80:
            print("🎯 OVERALL RESULT: ✅ PASS - FAZ-2 backend validation successful")
        elif success_rate >= 60:
            print("🎯 OVERALL RESULT: ⚠️ PARTIAL - Some issues detected, review required")
        else:
            print("🎯 OVERALL RESULT: ❌ FAIL - Critical issues detected")
        
        print("=" * 80)
        
        return success_rate >= 80

if __name__ == "__main__":
    validator = Faz2BackendValidator()
    success = validator.run_all_tests()
    sys.exit(0 if success else 1)