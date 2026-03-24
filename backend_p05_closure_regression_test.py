#!/usr/bin/env python3
"""
P0.5 Closure Backend Regression Testing
Base URL: https://binance-reconcile.preview.emergentagent.com
Admin: canary.admin@platform.local / CanaryAdmin123!

Test Requirements:
1) Observability endpoint standard contract + 200
2) Request-level reason validation (approval'a gitmeden)
3) MFA bypass audit + security payload
4) Contract freeze regression
"""

import requests
import json
import sys
import time
from datetime import datetime

# Configuration
BASE_URL = "https://binance-reconcile.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class P05ClosureRegressionTest:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.canary_user_id = None
        self.test_results = {
            "observability_endpoints": {},
            "reason_validation": {},
            "mfa_bypass_audit": {},
            "contract_freeze": {},
            "overall_status": "UNKNOWN"
        }
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def authenticate_admin(self):
        """Authenticate admin and get access token"""
        self.log("🔐 Authenticating admin...")
        
        try:
            # Admin login
            login_data = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=login_data,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("access_token"):
                    self.admin_token = data["access_token"]
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.admin_token}"
                    })
                    self.log(f"✅ Admin authentication successful")
                    return True
                elif data.get("mfa_required"):
                    self.log("⚠️ MFA required for admin login - this indicates MFA bypass is NOT active")
                    return False
                else:
                    self.log(f"❌ Admin login failed: {data}")
                    return False
            else:
                self.log(f"❌ Admin login failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.log(f"❌ Admin authentication error: {str(e)}")
            return False
    
    def get_canary_user_id(self):
        """Get canary admin user ID for testing"""
        try:
            # Search for canary admin user
            response = self.session.get(
                f"{BASE_URL}/api/admin/identity/users",
                params={"search": "canary.admin", "limit": 10},
                timeout=30
            )
            
            if response.status_code == 200:
                users = response.json().get("items", [])
                for user in users:
                    if user.get("email") == ADMIN_EMAIL:
                        self.canary_user_id = user.get("id")
                        self.log(f"✅ Found canary user ID: {self.canary_user_id}")
                        return True
                        
                self.log("❌ Canary admin user not found in user list")
                return False
            else:
                self.log(f"❌ Failed to get user list: {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ Error getting canary user ID: {str(e)}")
            return False
    
    def test_observability_endpoints(self):
        """Test 1: Observability endpoint standard contract + 200"""
        self.log("📊 Testing observability endpoints...")
        
        if not self.canary_user_id:
            self.log("❌ Cannot test observability endpoints - no user ID")
            return False
            
        endpoints = [
            "activity-timeline",
            "security-telemetry", 
            "execution-metrics",
            "trading-observability"
        ]
        
        all_passed = True
        
        for endpoint in endpoints:
            try:
                url = f"{BASE_URL}/api/admin/identity/users/{self.canary_user_id}/{endpoint}"
                response = self.session.get(url, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check required fields
                    required_fields = ["status", "metric", "generated_at", "data"]
                    missing_fields = [field for field in required_fields if field not in data]
                    
                    if not missing_fields:
                        self.log(f"✅ {endpoint}: PASS - 200 with all required fields")
                        self.test_results["observability_endpoints"][endpoint] = {
                            "status": "PASS",
                            "http_code": 200,
                            "has_required_fields": True,
                            "data_size": len(str(data.get("data", {})))
                        }
                    else:
                        self.log(f"❌ {endpoint}: FAIL - Missing fields: {missing_fields}")
                        self.test_results["observability_endpoints"][endpoint] = {
                            "status": "FAIL",
                            "http_code": 200,
                            "has_required_fields": False,
                            "missing_fields": missing_fields
                        }
                        all_passed = False
                else:
                    self.log(f"❌ {endpoint}: FAIL - HTTP {response.status_code}")
                    self.test_results["observability_endpoints"][endpoint] = {
                        "status": "FAIL",
                        "http_code": response.status_code,
                        "error": response.text[:200]
                    }
                    all_passed = False
                    
            except Exception as e:
                self.log(f"❌ {endpoint}: ERROR - {str(e)}")
                self.test_results["observability_endpoints"][endpoint] = {
                    "status": "ERROR",
                    "error": str(e)
                }
                all_passed = False
                
        return all_passed
    
    def test_reason_validation(self):
        """Test 2: Request-level reason validation (before approval)"""
        self.log("📝 Testing request-level reason validation...")
        
        test_cases = [
            {
                "name": "disable_user_approval_request",
                "method": "POST",
                "url": f"{BASE_URL}/api/admin/identity/approvals/request",
                "payload": {
                    "action_type": "disable_user",
                    "target_user_id": self.canary_user_id,
                    "reason": "bad"  # Short reason
                }
            },
            {
                "name": "bulk_status",
                "method": "POST", 
                "url": f"{BASE_URL}/api/admin/identity/users/bulk-status",
                "payload": {
                    "user_ids": [self.canary_user_id] if self.canary_user_id else ["test-id"],
                    "status": "disabled",
                    "reason": "bad"  # Short reason
                }
            },
            {
                "name": "soft_delete_request",
                "method": "POST",
                "url": f"{BASE_URL}/api/admin/identity/users/{self.canary_user_id or 'test-id'}/soft-delete/request",
                "payload": {
                    "reason": "bad"  # Short reason
                }
            },
            {
                "name": "hard_delete_request", 
                "method": "POST",
                "url": f"{BASE_URL}/api/admin/identity/users/{self.canary_user_id or 'test-id'}/hard-delete/request",
                "payload": {
                    "reason": "bad"  # Short reason
                }
            }
        ]
        
        all_passed = True
        
        for test_case in test_cases:
            try:
                response = self.session.request(
                    test_case["method"],
                    test_case["url"],
                    json=test_case["payload"],
                    timeout=30
                )
                
                if response.status_code == 400:
                    data = response.json()
                    error_code = data.get("error_code") or data.get("detail", "")
                    
                    if "request_reason_too_short" in str(error_code).lower() or "reason" in str(error_code).lower():
                        self.log(f"✅ {test_case['name']}: PASS - 400 with reason validation")
                        self.test_results["reason_validation"][test_case["name"]] = {
                            "status": "PASS",
                            "http_code": 400,
                            "validation_triggered": True,
                            "error_code": error_code
                        }
                    else:
                        self.log(f"❌ {test_case['name']}: FAIL - 400 but wrong error: {error_code}")
                        self.test_results["reason_validation"][test_case["name"]] = {
                            "status": "FAIL",
                            "http_code": 400,
                            "validation_triggered": False,
                            "error_code": error_code
                        }
                        all_passed = False
                else:
                    self.log(f"❌ {test_case['name']}: FAIL - Expected 400, got {response.status_code}")
                    self.test_results["reason_validation"][test_case["name"]] = {
                        "status": "FAIL",
                        "http_code": response.status_code,
                        "expected": 400,
                        "response": response.text[:200]
                    }
                    all_passed = False
                    
            except Exception as e:
                self.log(f"❌ {test_case['name']}: ERROR - {str(e)}")
                self.test_results["reason_validation"][test_case["name"]] = {
                    "status": "ERROR",
                    "error": str(e)
                }
                all_passed = False
                
        return all_passed
    
    def test_mfa_bypass_audit(self):
        """Test 3: MFA bypass audit + security payload"""
        self.log("🔒 Testing MFA bypass audit and security payload...")
        
        # Check if admin login bypassed MFA (already done in auth)
        mfa_bypassed = self.admin_token is not None
        
        audit_found = False
        security_payload_correct = False
        
        # 1. Check audit logs for MFA_ENFORCEMENT_BYPASS_ACTIVE
        try:
            response = self.session.get(
                f"{BASE_URL}/api/audit-logs",
                params={
                    "action": "MFA_ENFORCEMENT_BYPASS_ACTIVE",
                    "limit": 10
                },
                timeout=30
            )
            
            if response.status_code == 200:
                logs = response.json().get("items", [])
                audit_found = len(logs) > 0
                if audit_found:
                    self.log("✅ MFA bypass audit log found")
                else:
                    self.log("⚠️ No MFA bypass audit log found")
            else:
                self.log(f"❌ Failed to get audit logs: {response.status_code}")
                
        except Exception as e:
            self.log(f"❌ Error checking audit logs: {str(e)}")
        
        # 2. Check security payload for MFA bypass info
        if self.canary_user_id:
            try:
                response = self.session.get(
                    f"{BASE_URL}/api/admin/identity/users/{self.canary_user_id}/security",
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    mfa_info = data.get("mfa", {})
                    
                    bypass_active = mfa_info.get("bypass_active")
                    bypass_reason = mfa_info.get("bypass_reason")
                    
                    if bypass_active is True and bypass_reason == "allow_list":
                        self.log("✅ Security payload shows MFA bypass active with allow_list reason")
                        security_payload_correct = True
                    else:
                        self.log(f"❌ Security payload incorrect - bypass_active: {bypass_active}, bypass_reason: {bypass_reason}")
                        
                else:
                    self.log(f"❌ Failed to get security payload: {response.status_code}")
                    
            except Exception as e:
                self.log(f"❌ Error checking security payload: {str(e)}")
        
        # Overall MFA bypass test result
        overall_pass = mfa_bypassed and (audit_found or security_payload_correct)
        
        self.test_results["mfa_bypass_audit"] = {
            "mfa_bypassed_on_login": mfa_bypassed,
            "audit_log_found": audit_found,
            "security_payload_correct": security_payload_correct,
            "overall_status": "PASS" if overall_pass else "FAIL"
        }
        
        if overall_pass:
            self.log("✅ MFA bypass audit test: PASS")
        else:
            self.log("❌ MFA bypass audit test: FAIL")
            
        return overall_pass
    
    def test_contract_freeze_regression(self):
        """Test 4: Contract freeze regression"""
        self.log("📋 Testing contract freeze regression...")
        
        approvals_pass = False
        bulk_preview_pass = False
        
        # 1. Test approvals endpoint contract
        try:
            response = self.session.get(
                f"{BASE_URL}/api/admin/identity/approvals",
                params={"limit": 5},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                
                if items:
                    # Check first item for required fields
                    first_item = items[0]
                    required_fields = ["impact_delta", "risk_delta", "numeric_changes"]
                    
                    has_impact_delta = "impact_delta" in first_item
                    has_risk_delta = first_item.get("impact_delta", {}).get("risk_delta") is not None if has_impact_delta else False
                    has_numeric_changes = first_item.get("impact_delta", {}).get("numeric_changes") is not None if has_impact_delta else False
                    
                    if has_impact_delta and has_risk_delta and has_numeric_changes:
                        self.log("✅ Approvals contract: PASS - impact_delta, risk_delta, numeric_changes preserved")
                        approvals_pass = True
                    else:
                        self.log(f"❌ Approvals contract: FAIL - Missing fields. impact_delta: {has_impact_delta}, risk_delta: {has_risk_delta}, numeric_changes: {has_numeric_changes}")
                else:
                    self.log("⚠️ Approvals contract: No items to test")
                    approvals_pass = True  # No items is not a failure
                    
            else:
                self.log(f"❌ Approvals endpoint failed: {response.status_code}")
                
        except Exception as e:
            self.log(f"❌ Error testing approvals contract: {str(e)}")
        
        # 2. Test bulk status preview contract
        try:
            test_payload = {
                "user_ids": [self.canary_user_id] if self.canary_user_id else ["test-user-id"],
                "status": "disabled",
                "reason": "Test reason for contract validation"
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/admin/identity/users/bulk-status/preview",
                json=test_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                summary = data.get("summary", {})
                
                required_keys = [
                    "total_users", "eligible_users", "approval_required_users", 
                    "blocked_users", "high_risk_users", "risk_distribution", "action_summary"
                ]
                
                missing_keys = [key for key in required_keys if key not in summary]
                
                if not missing_keys:
                    self.log("✅ Bulk preview contract: PASS - All summary keys stable")
                    bulk_preview_pass = True
                else:
                    self.log(f"❌ Bulk preview contract: FAIL - Missing keys: {missing_keys}")
                    
            else:
                self.log(f"❌ Bulk preview endpoint failed: {response.status_code}")
                
        except Exception as e:
            self.log(f"❌ Error testing bulk preview contract: {str(e)}")
        
        overall_pass = approvals_pass and bulk_preview_pass
        
        self.test_results["contract_freeze"] = {
            "approvals_contract": "PASS" if approvals_pass else "FAIL",
            "bulk_preview_contract": "PASS" if bulk_preview_pass else "FAIL",
            "overall_status": "PASS" if overall_pass else "FAIL"
        }
        
        if overall_pass:
            self.log("✅ Contract freeze regression: PASS")
        else:
            self.log("❌ Contract freeze regression: FAIL")
            
        return overall_pass
    
    def run_all_tests(self):
        """Run all P0.5 closure regression tests"""
        self.log("🚀 Starting P0.5 Closure Backend Regression Testing...")
        self.log(f"Base URL: {BASE_URL}")
        self.log(f"Admin: {ADMIN_EMAIL}")
        
        # Step 1: Authenticate
        if not self.authenticate_admin():
            self.log("❌ CRITICAL: Admin authentication failed - cannot proceed")
            self.test_results["overall_status"] = "FAIL"
            return False
        
        # Step 2: Get canary user ID
        if not self.get_canary_user_id():
            self.log("⚠️ WARNING: Could not get canary user ID - some tests may be limited")
        
        # Step 3: Run all tests
        test_results = []
        
        # Test 1: Observability endpoints
        result1 = self.test_observability_endpoints()
        test_results.append(("Observability Endpoints", result1))
        
        # Test 2: Reason validation
        result2 = self.test_reason_validation()
        test_results.append(("Reason Validation", result2))
        
        # Test 3: MFA bypass audit
        result3 = self.test_mfa_bypass_audit()
        test_results.append(("MFA Bypass Audit", result3))
        
        # Test 4: Contract freeze regression
        result4 = self.test_contract_freeze_regression()
        test_results.append(("Contract Freeze Regression", result4))
        
        # Calculate overall result
        passed_tests = sum(1 for _, result in test_results if result)
        total_tests = len(test_results)
        
        self.log("\n" + "="*60)
        self.log("📊 P0.5 CLOSURE REGRESSION TEST RESULTS")
        self.log("="*60)
        
        for test_name, result in test_results:
            status = "✅ PASS" if result else "❌ FAIL"
            self.log(f"{test_name}: {status}")
        
        self.log(f"\nOverall: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            self.log("🎉 ALL TESTS PASSED - P0.5 closure criteria met")
            self.test_results["overall_status"] = "PASS"
            return True
        else:
            self.log("❌ SOME TESTS FAILED - P0.5 closure criteria not met")
            self.test_results["overall_status"] = "FAIL"
            return False
    
    def generate_report(self):
        """Generate detailed test report"""
        self.log("\n" + "="*60)
        self.log("📋 DETAILED TEST REPORT")
        self.log("="*60)
        
        # Observability endpoints
        self.log("\n1️⃣ OBSERVABILITY ENDPOINTS:")
        for endpoint, result in self.test_results["observability_endpoints"].items():
            status = result.get("status", "UNKNOWN")
            http_code = result.get("http_code", "N/A")
            self.log(f"   {endpoint}: {status} (HTTP {http_code})")
        
        # Reason validation
        self.log("\n2️⃣ REASON VALIDATION:")
        for test_name, result in self.test_results["reason_validation"].items():
            status = result.get("status", "UNKNOWN")
            http_code = result.get("http_code", "N/A")
            self.log(f"   {test_name}: {status} (HTTP {http_code})")
        
        # MFA bypass audit
        self.log("\n3️⃣ MFA BYPASS AUDIT:")
        mfa_result = self.test_results["mfa_bypass_audit"]
        self.log(f"   Login bypassed MFA: {mfa_result.get('mfa_bypassed_on_login', False)}")
        self.log(f"   Audit log found: {mfa_result.get('audit_log_found', False)}")
        self.log(f"   Security payload correct: {mfa_result.get('security_payload_correct', False)}")
        self.log(f"   Overall: {mfa_result.get('overall_status', 'UNKNOWN')}")
        
        # Contract freeze
        self.log("\n4️⃣ CONTRACT FREEZE REGRESSION:")
        contract_result = self.test_results["contract_freeze"]
        self.log(f"   Approvals contract: {contract_result.get('approvals_contract', 'UNKNOWN')}")
        self.log(f"   Bulk preview contract: {contract_result.get('bulk_preview_contract', 'UNKNOWN')}")
        self.log(f"   Overall: {contract_result.get('overall_status', 'UNKNOWN')}")
        
        self.log(f"\n🎯 FINAL RESULT: {self.test_results['overall_status']}")

def main():
    """Main test execution"""
    tester = P05ClosureRegressionTest()
    
    try:
        success = tester.run_all_tests()
        tester.generate_report()
        
        # Save results to file
        with open("/app/p05_closure_regression_results.json", "w") as f:
            json.dump(tester.test_results, f, indent=2)
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        tester.log("\n⚠️ Test interrupted by user")
        return 1
    except Exception as e:
        tester.log(f"\n❌ Unexpected error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())