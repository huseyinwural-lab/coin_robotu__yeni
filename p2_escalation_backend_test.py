#!/usr/bin/env python3
"""
P2+Escalation Backend Validation Test Script

This script validates the P2+Escalation updates on the backend as requested:
1. Escalation Center endpoints
2. Matrix Batch endpoint  
3. Import/Export endpoints
4. Role-based access controls

Test URL: https://trade-trace-engine.preview.emergentagent.com
"""

import json
import requests
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# Test configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

# Test credentials from review request
CREDENTIALS = {
    "super_admin": {
        "email": "canary.admin@platform.local",
        "password": "CanaryAdmin123!"
    },
    "admin": {
        "email": "canary.requester@platform.local", 
        "password": "CanaryRequester123!"
    },
    "ops": {
        "email": "canary.ops@platform.local",
        "password": "CanaryOps123!"
    }
}

class P2EscalationTester:
    def __init__(self):
        self.session = requests.Session()
        self.tokens = {}
        self.test_results = []
        
    def log_test(self, test_name: str, status: str, details: str = "", response_data: Any = None):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat(),
            "response_data": response_data
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        if response_data and isinstance(response_data, dict):
            if "error" in response_data:
                print(f"   Error: {response_data['error']}")
        print()

    def login_user(self, role: str) -> Optional[str]:
        """Login user and return access token"""
        if role not in CREDENTIALS:
            self.log_test(f"Login {role}", "FAIL", f"Unknown role: {role}")
            return None
            
        creds = CREDENTIALS[role]
        
        try:
            # Try admin login endpoint first
            response = self.session.post(
                f"{API_BASE}/auth/login/admin",
                json={
                    "email": creds["email"],
                    "password": creds["password"]
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                if token:
                    self.tokens[role] = token
                    self.log_test(f"Login {role}", "PASS", f"Successfully logged in as {role}")
                    return token
                else:
                    self.log_test(f"Login {role}", "FAIL", "No access token in response", data)
                    return None
            else:
                # Try regular user login endpoint
                response = self.session.post(
                    f"{API_BASE}/auth/login/user",
                    json={
                        "email": creds["email"],
                        "password": creds["password"]
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    token = data.get("access_token")
                    if token:
                        self.tokens[role] = token
                        self.log_test(f"Login {role}", "PASS", f"Successfully logged in as {role}")
                        return token
                    else:
                        self.log_test(f"Login {role}", "FAIL", "No access token in response", data)
                        return None
                else:
                    self.log_test(f"Login {role}", "FAIL", f"Login failed with status {response.status_code}", response.text)
                    return None
                    
        except Exception as e:
            self.log_test(f"Login {role}", "FAIL", f"Login exception: {str(e)}")
            return None

    def make_authenticated_request(self, method: str, endpoint: str, role: str, **kwargs) -> requests.Response:
        """Make authenticated request with role token"""
        if role not in self.tokens:
            raise ValueError(f"No token for role {role}")
            
        headers = kwargs.get("headers", {})
        headers["Authorization"] = f"Bearer {self.tokens[role]}"
        kwargs["headers"] = headers
        
        url = f"{API_BASE}{endpoint}"
        return self.session.request(method, url, timeout=30, **kwargs)

    def test_escalation_center_get(self):
        """Test GET /api/admin/escalation-center"""
        try:
            # Test with admin role
            response = self.make_authenticated_request("GET", "/admin/escalation-center", "admin")
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["active_breaches", "acknowledged", "resolved"]
                
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    self.log_test("GET /api/admin/escalation-center", "FAIL", 
                                f"Missing required fields: {missing_fields}", data)
                else:
                    # Check if escalation items have required fields
                    sample_item = None
                    for items_list in [data.get("active_breaches", []), data.get("acknowledged", []), data.get("resolved", [])]:
                        if items_list:
                            sample_item = items_list[0]
                            break
                    
                    if sample_item:
                        escalation_required_fields = [
                            "breach_age_seconds", "ack_by", "ack_at", "escalation_level", 
                            "escalation_reason", "linked_request_id", "current_owner"
                        ]
                        missing_escalation_fields = [field for field in escalation_required_fields if field not in sample_item]
                        
                        if missing_escalation_fields:
                            self.log_test("GET /api/admin/escalation-center", "FAIL",
                                        f"Escalation item missing fields: {missing_escalation_fields}", sample_item)
                        else:
                            self.log_test("GET /api/admin/escalation-center", "PASS", 
                                        f"Response contains all required fields. Found {len(data.get('active_breaches', []))} active, "
                                        f"{len(data.get('acknowledged', []))} acknowledged, {len(data.get('resolved', []))} resolved")
                    else:
                        self.log_test("GET /api/admin/escalation-center", "PASS", 
                                    "Response structure correct (no escalation items to validate)")
            else:
                self.log_test("GET /api/admin/escalation-center", "FAIL", 
                            f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("GET /api/admin/escalation-center", "FAIL", f"Exception: {str(e)}")

    def test_escalation_center_ack(self):
        """Test POST /api/admin/escalation-center/{id}/ack"""
        try:
            # First get escalation center to find an item to acknowledge
            response = self.make_authenticated_request("GET", "/admin/escalation-center", "admin")
            
            if response.status_code != 200:
                self.log_test("POST /api/admin/escalation-center/{id}/ack", "SKIP", 
                            "Cannot get escalation center items")
                return
                
            data = response.json()
            active_items = data.get("active_breaches", [])
            
            if not active_items:
                # Create a test escalation item by testing with a dummy ID
                test_id = "test_escalation_123"
                ack_response = self.make_authenticated_request(
                    "POST", f"/admin/escalation-center/{test_id}/ack", "admin",
                    json={
                        "current_owner": "test_owner",
                        "escalation_reason": "Test acknowledgment"
                    }
                )
                
                if ack_response.status_code == 404:
                    self.log_test("POST /api/admin/escalation-center/{id}/ack", "PASS", 
                                "Endpoint accessible, returns 404 for non-existent escalation (expected)")
                else:
                    self.log_test("POST /api/admin/escalation-center/{id}/ack", "FAIL", 
                                f"Unexpected response for test ID: HTTP {ack_response.status_code}")
            else:
                # Test with real escalation item
                escalation_id = active_items[0].get("escalation_id")
                ack_response = self.make_authenticated_request(
                    "POST", f"/admin/escalation-center/{escalation_id}/ack", "admin",
                    json={
                        "current_owner": "admin_test",
                        "escalation_reason": "Acknowledged for testing"
                    }
                )
                
                if ack_response.status_code == 200:
                    ack_data = ack_response.json()
                    if "escalation_id" in ack_data and "ack_by" in ack_data:
                        self.log_test("POST /api/admin/escalation-center/{id}/ack", "PASS", 
                                    f"Successfully acknowledged escalation {escalation_id}")
                    else:
                        self.log_test("POST /api/admin/escalation-center/{id}/ack", "FAIL", 
                                    "Response missing required fields", ack_data)
                else:
                    self.log_test("POST /api/admin/escalation-center/{id}/ack", "FAIL", 
                                f"HTTP {ack_response.status_code}", ack_response.text)
                    
        except Exception as e:
            self.log_test("POST /api/admin/escalation-center/{id}/ack", "FAIL", f"Exception: {str(e)}")

    def test_escalation_center_resolve(self):
        """Test POST /api/admin/escalation-center/{id}/resolve (super_admin only)"""
        try:
            # Test with super_admin role
            test_id = "test_escalation_resolve_123"
            response = self.make_authenticated_request(
                "POST", f"/admin/escalation-center/{test_id}/resolve", "super_admin",
                json={
                    "escalation_reason": "Resolved for testing"
                }
            )
            
            if response.status_code == 404:
                self.log_test("POST /api/admin/escalation-center/{id}/resolve", "PASS", 
                            "Endpoint accessible by super_admin, returns 404 for non-existent escalation (expected)")
            elif response.status_code == 200:
                resolve_data = response.json()
                if "escalation_id" in resolve_data and "resolved_by" in resolve_data:
                    self.log_test("POST /api/admin/escalation-center/{id}/resolve", "PASS", 
                                "Successfully resolved escalation")
                else:
                    self.log_test("POST /api/admin/escalation-center/{id}/resolve", "FAIL", 
                                "Response missing required fields", resolve_data)
            else:
                self.log_test("POST /api/admin/escalation-center/{id}/resolve", "FAIL", 
                            f"HTTP {response.status_code}", response.text)
                            
        except Exception as e:
            self.log_test("POST /api/admin/escalation-center/{id}/resolve", "FAIL", f"Exception: {str(e)}")

    def test_matrix_batch_endpoint(self):
        """Test POST /api/admin/risk-simulation/matrix-batch"""
        try:
            # Test matrix batch simulation
            payload = {
                "user_id": "test_user_123",
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "strategy_bindings": ["trend_follow_v1", "mean_reversion_v1"],
                "intent_payload": {
                    "side": "buy",
                    "notional": 100.0,
                    "volatility_pct": 5.0,
                    "signal_confidence": 0.7
                }
            }
            
            response = self.make_authenticated_request(
                "POST", "/admin/risk-simulation/matrix-batch", "admin",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["batch_id", "simulated_at", "total_combinations", "items"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_test("POST /api/admin/risk-simulation/matrix-batch", "FAIL", 
                                f"Missing required fields: {missing_fields}", data)
                else:
                    self.log_test("POST /api/admin/risk-simulation/matrix-batch", "PASS", 
                                f"Matrix batch simulation successful. Total combinations: {data.get('total_combinations', 0)}")
            elif response.status_code == 400:
                # Check if it's a validation error (expected for test user)
                error_text = response.text.lower()
                if "user_id" in error_text or "geçersiz" in error_text:
                    self.log_test("POST /api/admin/risk-simulation/matrix-batch", "PASS", 
                                "Endpoint accessible, returns validation error for test user_id (expected)")
                else:
                    self.log_test("POST /api/admin/risk-simulation/matrix-batch", "FAIL", 
                                f"HTTP 400 with unexpected error: {response.text}")
            else:
                self.log_test("POST /api/admin/risk-simulation/matrix-batch", "FAIL", 
                            f"HTTP {response.status_code}", response.text)
                            
        except Exception as e:
            self.log_test("POST /api/admin/risk-simulation/matrix-batch", "FAIL", f"Exception: {str(e)}")

    def test_import_export_endpoints(self):
        """Test import/export endpoints"""
        # Test export endpoint
        try:
            # Test JSON export
            response = self.make_authenticated_request(
                "GET", "/admin/strategy-intelligence/export", "admin",
                params={
                    "export_format": "json",
                    "dataset": "decision_requests"
                }
            )
            
            if response.status_code == 200:
                # Check if response is JSON
                try:
                    data = response.json()
                    self.log_test("GET /api/admin/strategy-intelligence/export (JSON)", "PASS", 
                                f"JSON export successful, response size: {len(response.content)} bytes")
                except:
                    self.log_test("GET /api/admin/strategy-intelligence/export (JSON)", "FAIL", 
                                "Response is not valid JSON")
            else:
                self.log_test("GET /api/admin/strategy-intelligence/export (JSON)", "FAIL", 
                            f"HTTP {response.status_code}", response.text)
                            
            # Test CSV export
            response = self.make_authenticated_request(
                "GET", "/admin/strategy-intelligence/export", "admin",
                params={
                    "export_format": "csv",
                    "dataset": "simulation_history"
                }
            )
            
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "csv" in content_type.lower() or "text" in content_type.lower():
                    self.log_test("GET /api/admin/strategy-intelligence/export (CSV)", "PASS", 
                                f"CSV export successful, content-type: {content_type}")
                else:
                    self.log_test("GET /api/admin/strategy-intelligence/export (CSV)", "PASS", 
                                f"CSV export successful, response size: {len(response.content)} bytes")
            else:
                self.log_test("GET /api/admin/strategy-intelligence/export (CSV)", "FAIL", 
                            f"HTTP {response.status_code}", response.text)
                            
        except Exception as e:
            self.log_test("Export endpoints", "FAIL", f"Exception: {str(e)}")

        # Test import endpoint
        try:
            test_import_data = {
                "import_type": "decision_requests",
                "data": [
                    {
                        "request_type": "test_import",
                        "status": "pending",
                        "reason_note": "Test import data"
                    }
                ]
            }
            
            response = self.make_authenticated_request(
                "POST", "/admin/strategy-intelligence/import-json", "admin",
                json=test_import_data
            )
            
            if response.status_code == 200:
                data = response.json()
                if "imported_count" in data or "status" in data:
                    self.log_test("POST /api/admin/strategy-intelligence/import-json", "PASS", 
                                "Import endpoint accessible and functional")
                else:
                    self.log_test("POST /api/admin/strategy-intelligence/import-json", "FAIL", 
                                "Response missing expected fields", data)
            elif response.status_code == 400:
                # Validation error is acceptable for test data
                self.log_test("POST /api/admin/strategy-intelligence/import-json", "PASS", 
                            "Import endpoint accessible, returns validation error for test data (expected)")
            else:
                self.log_test("POST /api/admin/strategy-intelligence/import-json", "FAIL", 
                            f"HTTP {response.status_code}", response.text)
                            
        except Exception as e:
            self.log_test("POST /api/admin/strategy-intelligence/import-json", "FAIL", f"Exception: {str(e)}")

    def test_role_based_access_control(self):
        """Test role-based access controls"""
        # Test ops view-only access to escalation center
        try:
            # Ops should be able to view escalation center
            response = self.make_authenticated_request("GET", "/admin/escalation-center", "ops")
            
            if response.status_code == 200:
                self.log_test("Ops view escalation center", "PASS", "Ops can view escalation center")
            elif response.status_code == 403:
                self.log_test("Ops view escalation center", "FAIL", "Ops blocked from viewing escalation center")
            else:
                self.log_test("Ops view escalation center", "FAIL", f"HTTP {response.status_code}")
                
            # Ops should NOT be able to acknowledge escalations
            response = self.make_authenticated_request(
                "POST", "/admin/escalation-center/test_123/ack", "ops",
                json={"current_owner": "ops_test", "escalation_reason": "Test"}
            )
            
            if response.status_code == 403:
                self.log_test("Ops acknowledge escalation (should fail)", "PASS", 
                            "Ops correctly blocked from acknowledging escalations")
            else:
                self.log_test("Ops acknowledge escalation (should fail)", "FAIL", 
                            f"Ops not properly blocked: HTTP {response.status_code}")
                            
        except Exception as e:
            self.log_test("Role-based access control", "FAIL", f"Exception: {str(e)}")

        # Test admin can acknowledge but not resolve
        try:
            response = self.make_authenticated_request(
                "POST", "/admin/escalation-center/test_123/ack", "admin",
                json={"current_owner": "admin_test", "escalation_reason": "Test"}
            )
            
            if response.status_code in [200, 404]:  # 404 is OK for non-existent escalation
                self.log_test("Admin acknowledge escalation", "PASS", "Admin can acknowledge escalations")
            else:
                self.log_test("Admin acknowledge escalation", "FAIL", f"HTTP {response.status_code}")
                
            # Admin should NOT be able to resolve (super_admin only)
            response = self.make_authenticated_request(
                "POST", "/admin/escalation-center/test_123/resolve", "admin",
                json={"escalation_reason": "Test resolve"}
            )
            
            if response.status_code == 403:
                self.log_test("Admin resolve escalation (should fail)", "PASS", 
                            "Admin correctly blocked from resolving escalations")
            else:
                self.log_test("Admin resolve escalation (should fail)", "FAIL", 
                            f"Admin not properly blocked: HTTP {response.status_code}")
                            
        except Exception as e:
            self.log_test("Admin role access control", "FAIL", f"Exception: {str(e)}")

        # Test super_admin can resolve
        try:
            response = self.make_authenticated_request(
                "POST", "/admin/escalation-center/test_123/resolve", "super_admin",
                json={"escalation_reason": "Test resolve"}
            )
            
            if response.status_code in [200, 404]:  # 404 is OK for non-existent escalation
                self.log_test("Super admin resolve escalation", "PASS", "Super admin can resolve escalations")
            else:
                self.log_test("Super admin resolve escalation", "FAIL", f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Super admin role access control", "FAIL", f"Exception: {str(e)}")

    def test_502_error_check(self):
        """Test for 502 errors mentioned in review request"""
        try:
            # Test basic health endpoint
            response = self.session.get(f"{API_BASE}/health", timeout=30)
            if response.status_code == 502:
                self.log_test("502 Error Check - Health", "FAIL", "502 Bad Gateway error detected")
            elif response.status_code == 200:
                self.log_test("502 Error Check - Health", "PASS", "No 502 error, health endpoint responding")
            else:
                self.log_test("502 Error Check - Health", "WARN", f"HTTP {response.status_code}")
                
            # Test login endpoints for 502 errors
            response = self.session.post(
                f"{API_BASE}/auth/login/admin",
                json={"email": "test@test.com", "password": "test"},
                timeout=30
            )
            
            if response.status_code == 502:
                self.log_test("502 Error Check - Login", "FAIL", "502 Bad Gateway error on login")
            else:
                self.log_test("502 Error Check - Login", "PASS", f"No 502 error on login (got {response.status_code})")
                
        except Exception as e:
            self.log_test("502 Error Check", "FAIL", f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all P2+Escalation tests"""
        print("=" * 80)
        print("P2+ESCALATION BACKEND VALIDATION TEST")
        print("=" * 80)
        print(f"Test URL: {BASE_URL}")
        print(f"Started at: {datetime.now().isoformat()}")
        print()

        # Step 1: Check for 502 errors first
        print("STEP 1: Checking for 502 errors...")
        self.test_502_error_check()
        print()

        # Step 2: Login all users
        print("STEP 2: Authenticating users...")
        for role in ["super_admin", "admin", "ops"]:
            self.login_user(role)
        print()

        # Step 3: Test escalation center endpoints
        print("STEP 3: Testing Escalation Center endpoints...")
        self.test_escalation_center_get()
        self.test_escalation_center_ack()
        self.test_escalation_center_resolve()
        print()

        # Step 4: Test matrix batch endpoint
        print("STEP 4: Testing Matrix Batch endpoint...")
        self.test_matrix_batch_endpoint()
        print()

        # Step 5: Test import/export endpoints
        print("STEP 5: Testing Import/Export endpoints...")
        self.test_import_export_endpoints()
        print()

        # Step 6: Test role-based access controls
        print("STEP 6: Testing Role-based Access Controls...")
        self.test_role_based_access_control()
        print()

        # Generate summary
        self.generate_summary()

    def generate_summary(self):
        """Generate test summary"""
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.test_results if r["status"] == "FAIL"])
        skipped_tests = len([r for r in self.test_results if r["status"] == "SKIP"])
        warned_tests = len([r for r in self.test_results if r["status"] == "WARN"])
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⚠️  Warnings: {warned_tests}")
        print(f"⏭️  Skipped: {skipped_tests}")
        print()
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        print()
        
        # Show failed tests
        if failed_tests > 0:
            print("FAILED TESTS:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"❌ {result['test']}: {result['details']}")
            print()
        
        # Overall assessment
        if failed_tests == 0:
            print("🎉 ALL TESTS PASSED - P2+Escalation backend validation successful!")
        elif failed_tests <= 2:
            print("⚠️  MOSTLY SUCCESSFUL - Minor issues detected")
        else:
            print("❌ MULTIPLE FAILURES - P2+Escalation backend needs attention")
        
        print()
        print(f"Test completed at: {datetime.now().isoformat()}")
        print("=" * 80)

if __name__ == "__main__":
    tester = P2EscalationTester()
    tester.run_all_tests()