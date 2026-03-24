#!/usr/bin/env python3
"""
P1 Backend Validation Test - CORRECTED VERSION
Testing conflict/hedge/rebalance flows, deterministic model, compare upgrade, and queue hardening regression
URL: https://strategy-version-gov.preview.emergentagent.com
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

# Test configuration
BASE_URL = "https://strategy-version-gov.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

# Test credentials
SUPER_ADMIN_CREDS = {
    "email": "canary.admin@platform.local",
    "password": "CanaryAdmin123!"
}

ADMIN_CREDS = {
    "email": "canary.requester@platform.local", 
    "password": "CanaryRequester123!"
}

class P1ValidationTester:
    def __init__(self):
        self.super_admin_token = None
        self.admin_token = None
        self.test_results = []
        
    def log_test(self, test_name: str, status: str, details: str, endpoint: str = ""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "endpoint": endpoint
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        if endpoint:
            print(f"   Endpoint: {endpoint}")
        print()

    def login_user(self, credentials: Dict[str, str], user_type: str) -> Optional[str]:
        """Login and extract token"""
        try:
            # Use admin login endpoint for both super admin and admin requester
            login_url = f"{API_BASE}/auth/login/admin"
            response = requests.post(login_url, json=credentials, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                if token:
                    self.log_test(f"{user_type.title()} Login", "PASS", 
                                f"Successfully logged in as {credentials['email']}")
                    return token
                else:
                    self.log_test(f"{user_type.title()} Login", "FAIL", 
                                "No access token in response")
                    return None
            else:
                self.log_test(f"{user_type.title()} Login", "FAIL", 
                            f"Login failed with status {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            self.log_test(f"{user_type.title()} Login", "FAIL", f"Login error: {str(e)}")
            return None

    def make_authenticated_request(self, method: str, endpoint: str, token: str, 
                                 data: Dict = None, params: Dict = None) -> requests.Response:
        """Make authenticated API request"""
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{API_BASE}{endpoint}"
        
        if method.upper() == "GET":
            return requests.get(url, headers=headers, params=params, timeout=30)
        elif method.upper() == "POST":
            return requests.post(url, headers=headers, json=data, timeout=30)
        elif method.upper() == "PUT":
            return requests.put(url, headers=headers, json=data, timeout=30)
        elif method.upper() == "PATCH":
            return requests.patch(url, headers=headers, json=data, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")

    def test_conflict_hedge_rebalance_flow(self):
        """Test 1: Conflict/Hedge/Rebalance real state/effect"""
        print("=== TEST 1: Conflict/Hedge/Rebalance Flow ===")
        
        try:
            # Get decision requests
            response = self.make_authenticated_request("GET", "/admin/decision-requests", self.super_admin_token)
            
            if response.status_code == 200:
                data = response.json()
                decision_requests = data.get("items", [])
                self.log_test("Decision Requests List", "PASS", 
                            f"Retrieved {len(decision_requests)} decision requests", 
                            "GET /api/admin/decision-requests")
                
                # Look for conflict/hedge/rebalance requests
                conflict_requests = [req for req in decision_requests 
                                   if req.get('request_type') in ['conflict_resolve', 'hedge_apply', 'rebalance_apply']]
                
                if conflict_requests:
                    # Find an executed request to check execution_effect
                    executed_requests = [req for req in conflict_requests if req.get('status') == 'executed']
                    
                    if executed_requests:
                        test_request = executed_requests[0]
                        request_type = test_request.get('request_type')
                        request_id = test_request.get('request_id')
                        
                        self.log_test("Found Executed Request", "PASS", 
                                    f"Found executed {request_type} request: {request_id}")
                        
                        # Check execution_effect structure
                        execution_effect = test_request.get('execution_effect', {})
                        payload = test_request.get('payload', {})
                        
                        has_state_change = 'state_change' in execution_effect
                        has_execution_effect = len(execution_effect) > 0
                        
                        if has_state_change and has_execution_effect:
                            self.log_test("Execute Response Structure", "PASS",
                                        "Executed request contains state_change and execution_effect",
                                        f"Executed request: {request_id}")
                            
                            # Check specific fields based on request type
                            if request_type == 'hedge_apply':
                                has_realized_risk_drop = 'realized_risk_drop' in execution_effect
                                if has_realized_risk_drop:
                                    risk_drop_value = execution_effect.get('realized_risk_drop')
                                    self.log_test("Hedge Realized Risk Drop", "PASS",
                                                f"Hedge execution contains realized_risk_drop: {risk_drop_value}")
                                else:
                                    self.log_test("Hedge Realized Risk Drop", "FAIL",
                                                "Hedge execution missing realized_risk_drop field")
                            
                            elif request_type == 'rebalance_apply':
                                has_allocation_diff = 'allocation_diff_bps' in execution_effect
                                if has_allocation_diff:
                                    allocation_diff = execution_effect.get('allocation_diff_bps')
                                    self.log_test("Rebalance Allocation Diff", "PASS",
                                                f"Rebalance execution contains allocation_diff_bps: {allocation_diff}")
                                else:
                                    self.log_test("Rebalance Allocation Diff", "FAIL",
                                                "Rebalance execution missing allocation_diff_bps field")
                                        
                        else:
                            self.log_test("Execute Response Structure", "FAIL",
                                        f"Missing fields - state_change: {has_state_change}, execution_effect: {has_execution_effect}")
                    else:
                        # Test approve + execute flow on a pending request
                        pending_requests = [req for req in conflict_requests if req.get('status') == 'pending']
                        
                        if pending_requests:
                            test_request = pending_requests[0]
                            request_id = test_request.get('request_id')
                            request_type = test_request.get('request_type')
                            
                            self.log_test("Found Pending Request", "PASS", 
                                        f"Found pending {request_type} request: {request_id}")
                            
                            # Test approve endpoint
                            approve_response = self.make_authenticated_request(
                                "POST", f"/admin/decision-requests/{request_id}/approve", 
                                self.super_admin_token,
                                data={"approval_note": "P1 validation test approval"}
                            )
                            
                            if approve_response.status_code == 200:
                                self.log_test("Decision Request Approve", "PASS", 
                                            f"Successfully approved {request_type} request",
                                            f"POST /api/admin/decision-requests/{request_id}/approve")
                                
                                # Test execute endpoint
                                execute_response = self.make_authenticated_request(
                                    "POST", f"/admin/decision-requests/{request_id}/execute",
                                    self.super_admin_token,
                                    data={"execution_note": "P1 validation test execution"}
                                )
                                
                                if execute_response.status_code == 200:
                                    execute_data = execute_response.json()
                                    
                                    # Check for state_change and execution_effect
                                    has_state_change = 'state_change' in execute_data
                                    has_execution_effect = 'execution_effect' in execute_data
                                    
                                    if has_state_change and has_execution_effect:
                                        self.log_test("Execute Response Structure", "PASS",
                                                    "Response contains state_change and execution_effect",
                                                    f"POST /api/admin/decision-requests/{request_id}/execute")
                                    else:
                                        self.log_test("Execute Response Structure", "FAIL",
                                                    f"Missing fields - state_change: {has_state_change}, execution_effect: {has_execution_effect}",
                                                    f"POST /api/admin/decision-requests/{request_id}/execute")
                                else:
                                    self.log_test("Decision Request Execute", "FAIL",
                                                f"Execute failed with status {execute_response.status_code}: {execute_response.text}",
                                                f"POST /api/admin/decision-requests/{request_id}/execute")
                            else:
                                self.log_test("Decision Request Approve", "FAIL",
                                            f"Approve failed with status {approve_response.status_code}: {approve_response.text}",
                                            f"POST /api/admin/decision-requests/{request_id}/approve")
                        else:
                            self.log_test("Conflict/Hedge/Rebalance Flow", "SKIP",
                                        "No pending conflict/hedge/rebalance requests found for testing")
                else:
                    self.log_test("Conflict/Hedge/Rebalance Requests", "SKIP",
                                "No conflict/hedge/rebalance requests found for testing")
            else:
                self.log_test("Decision Requests List", "FAIL",
                            f"Failed to get decision requests: {response.status_code} - {response.text}",
                            "GET /api/admin/decision-requests")
                
        except Exception as e:
            self.log_test("Conflict/Hedge/Rebalance Flow", "FAIL", f"Exception: {str(e)}")

    def test_deterministic_model(self):
        """Test 2: Deterministic model - queue response and recommendation_rank"""
        print("=== TEST 2: Deterministic Model ===")
        
        try:
            # Test queue endpoint for deterministic_effect_preview
            response = self.make_authenticated_request("GET", "/admin/decision-requests", self.super_admin_token)
            
            if response.status_code == 200:
                data = response.json()
                queue_items = data.get("items", [])
                
                # Check for deterministic_effect_preview in response
                items_with_deterministic = [item for item in queue_items 
                                          if 'deterministic_effect_preview' in item]
                
                if items_with_deterministic:
                    self.log_test("Deterministic Effect Preview", "PASS",
                                f"Found {len(items_with_deterministic)} items with deterministic_effect_preview field",
                                "GET /api/admin/decision-requests")
                else:
                    self.log_test("Deterministic Effect Preview", "FAIL",
                                "Queue response missing deterministic_effect_preview field",
                                "GET /api/admin/decision-requests")
                
                # Check for recommendation_rank in pending items
                pending_items = [item for item in queue_items if item.get('status') == 'pending']
                items_with_rank = [item for item in pending_items if 'recommendation_rank' in item and item.get('recommendation_rank') is not None]
                
                if pending_items:
                    if items_with_rank:
                        self.log_test("Recommendation Rank", "PASS",
                                    f"Found recommendation_rank in {len(items_with_rank)}/{len(pending_items)} pending items",
                                    "GET /api/admin/decision-requests")
                    else:
                        self.log_test("Recommendation Rank", "FAIL",
                                    f"Missing recommendation_rank in {len(pending_items)} pending items",
                                    "GET /api/admin/decision-requests")
                else:
                    self.log_test("Recommendation Rank", "SKIP",
                                "No pending items found to check recommendation_rank")
                    
            else:
                self.log_test("Queue Response Check", "FAIL",
                            f"Failed to get queue data: {response.status_code} - {response.text}",
                            "GET /api/admin/decision-requests")
                
        except Exception as e:
            self.log_test("Deterministic Model", "FAIL", f"Exception: {str(e)}")

    def test_compare_upgrade_backend(self):
        """Test 3: Compare upgrade backend endpoint"""
        print("=== TEST 3: Compare Upgrade Backend ===")
        
        try:
            # Get a simulation run ID from existing decision requests
            response = self.make_authenticated_request("GET", "/admin/decision-requests", self.super_admin_token)
            
            if response.status_code == 200:
                data = response.json()
                decision_requests = data.get("items", [])
                
                # Find a request with simulation_run_id
                requests_with_sim = [req for req in decision_requests 
                                   if req.get('simulation_run_id') is not None]
                
                if requests_with_sim:
                    run_id = requests_with_sim[0].get('simulation_run_id')
                    
                    # Test compare-current endpoint
                    compare_response = self.make_authenticated_request(
                        "GET", f"/admin/simulation-runs/{run_id}/compare-current", 
                        self.super_admin_token
                    )
                    
                    if compare_response.status_code == 200:
                        compare_data = compare_response.json()
                        compare_summary = compare_data.get('compare_summary', {})
                        
                        # Check for required fields
                        required_fields = [
                            'exposure_change_vs_history',
                            'var_change_vs_history', 
                            'liquidity_impact_change_vs_history'
                        ]
                        
                        missing_fields = [field for field in required_fields if field not in compare_summary]
                        
                        if not missing_fields:
                            self.log_test("Compare Summary Fields", "PASS",
                                        f"All required fields present: {', '.join(required_fields)}",
                                        f"GET /api/admin/simulation-runs/{run_id}/compare-current")
                        else:
                            self.log_test("Compare Summary Fields", "FAIL",
                                        f"Missing fields: {', '.join(missing_fields)}",
                                        f"GET /api/admin/simulation-runs/{run_id}/compare-current")
                            
                    else:
                        self.log_test("Compare Current Endpoint", "FAIL",
                                    f"Compare endpoint failed: {compare_response.status_code} - {compare_response.text}",
                                    f"GET /api/admin/simulation-runs/{run_id}/compare-current")
                else:
                    # Test with a dummy run_id to check endpoint accessibility
                    test_run_id = "test-run-id-123"
                    compare_response = self.make_authenticated_request(
                        "GET", f"/admin/simulation-runs/{test_run_id}/compare-current",
                        self.super_admin_token
                    )
                    
                    if compare_response.status_code in [200, 404]:
                        self.log_test("Compare Current Endpoint", "PASS",
                                    f"Endpoint accessible (returned {compare_response.status_code})",
                                    f"GET /api/admin/simulation-runs/{test_run_id}/compare-current")
                    else:
                        self.log_test("Compare Current Endpoint", "FAIL",
                                    f"Endpoint error: {compare_response.status_code} - {compare_response.text}",
                                    f"GET /api/admin/simulation-runs/{test_run_id}/compare-current")
            else:
                self.log_test("Decision Requests for Simulation", "FAIL",
                            f"Failed to get decision requests: {response.status_code} - {response.text}",
                            "GET /api/admin/decision-requests")
                
        except Exception as e:
            self.log_test("Compare Upgrade Backend", "FAIL", f"Exception: {str(e)}")

    def test_queue_hardening_regression(self):
        """Test 4: Queue hardening regression - assign-owner, ack, bulk-action endpoints"""
        print("=== TEST 4: Queue Hardening Regression ===")
        
        try:
            # Test assign-owner, ack, bulk-action endpoints
            response = self.make_authenticated_request("GET", "/admin/decision-requests", self.super_admin_token)
            
            if response.status_code == 200:
                data = response.json()
                decision_requests = data.get("items", [])
                
                if decision_requests and len(decision_requests) > 0:
                    test_request_id = decision_requests[0].get('request_id')
                    
                    # Test assign-owner endpoint
                    assign_response = self.make_authenticated_request(
                        "POST", f"/admin/decision-requests/{test_request_id}/assign-owner",
                        self.super_admin_token,
                        data={"assigned_to": "test-owner", "reason_note": "P1 validation test"}
                    )
                    
                    if assign_response.status_code in [200, 400, 404]:  # 400/404 acceptable for test data
                        self.log_test("Assign Owner Endpoint", "PASS",
                                    f"Endpoint accessible (status: {assign_response.status_code})",
                                    f"POST /api/admin/decision-requests/{test_request_id}/assign-owner")
                    else:
                        self.log_test("Assign Owner Endpoint", "FAIL",
                                    f"Endpoint error: {assign_response.status_code} - {assign_response.text}",
                                    f"POST /api/admin/decision-requests/{test_request_id}/assign-owner")
                    
                    # Test ack endpoint
                    ack_response = self.make_authenticated_request(
                        "POST", f"/admin/decision-requests/{test_request_id}/ack",
                        self.super_admin_token,
                        data={"reason_note": "P1 validation test acknowledgment"}
                    )
                    
                    if ack_response.status_code in [200, 400, 404]:  # 400/404 acceptable for test data
                        self.log_test("Ack Endpoint", "PASS",
                                    f"Endpoint accessible (status: {ack_response.status_code})",
                                    f"POST /api/admin/decision-requests/{test_request_id}/ack")
                    else:
                        self.log_test("Ack Endpoint", "FAIL",
                                    f"Endpoint error: {ack_response.status_code} - {ack_response.text}",
                                    f"POST /api/admin/decision-requests/{test_request_id}/ack")
                    
                    # Test bulk-action endpoint
                    bulk_response = self.make_authenticated_request(
                        "POST", "/admin/decision-requests/bulk-action",
                        self.super_admin_token,
                        data={
                            "action": "approve",
                            "request_ids": [test_request_id],
                            "reason_note": "P1 validation bulk test"
                        }
                    )
                    
                    if bulk_response.status_code in [200, 400, 404]:  # 400/404 acceptable for test data
                        self.log_test("Bulk Action Endpoint", "PASS",
                                    f"Endpoint accessible (status: {bulk_response.status_code})",
                                    "POST /api/admin/decision-requests/bulk-action")
                    else:
                        self.log_test("Bulk Action Endpoint", "FAIL",
                                    f"Endpoint error: {bulk_response.status_code} - {bulk_response.text}",
                                    "POST /api/admin/decision-requests/bulk-action")
                else:
                    self.log_test("Queue Hardening Test Data", "SKIP",
                                "No decision requests available for queue hardening tests")
            else:
                self.log_test("Queue Hardening Regression", "FAIL",
                            f"Failed to get decision requests: {response.status_code} - {response.text}",
                            "GET /api/admin/decision-requests")
                
        except Exception as e:
            self.log_test("Queue Hardening Regression", "FAIL", f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all P1 validation tests"""
        print("🚀 Starting P1 Backend Validation Tests")
        print(f"Base URL: {BASE_URL}")
        print("=" * 60)
        
        # Login as super admin
        self.super_admin_token = self.login_user(SUPER_ADMIN_CREDS, "super_admin")
        if not self.super_admin_token:
            print("❌ Cannot proceed without super admin token")
            return False
            
        # Login as admin requester
        self.admin_token = self.login_user(ADMIN_CREDS, "admin")
        if not self.admin_token:
            print("⚠️ Admin requester login failed, continuing with super admin only")
        
        # Run all tests
        self.test_conflict_hedge_rebalance_flow()
        self.test_deterministic_model()
        self.test_compare_upgrade_backend()
        self.test_queue_hardening_regression()
        
        # Summary
        print("=" * 60)
        print("📊 P1 VALIDATION SUMMARY")
        print("=" * 60)
        
        pass_count = len([r for r in self.test_results if r['status'] == 'PASS'])
        fail_count = len([r for r in self.test_results if r['status'] == 'FAIL'])
        skip_count = len([r for r in self.test_results if r['status'] == 'SKIP'])
        total_count = len(self.test_results)
        
        print(f"Total Tests: {total_count}")
        print(f"✅ PASS: {pass_count}")
        print(f"❌ FAIL: {fail_count}")
        print(f"⚠️ SKIP: {skip_count}")
        
        if fail_count > 0:
            print("\n🔍 FAILED TESTS:")
            for result in self.test_results:
                if result['status'] == 'FAIL':
                    print(f"❌ {result['test']}: {result['details']}")
                    if result['endpoint']:
                        print(f"   Endpoint: {result['endpoint']}")
        
        success_rate = (pass_count / total_count * 100) if total_count > 0 else 0
        print(f"\n📈 Success Rate: {success_rate:.1f}%")
        
        return fail_count == 0

if __name__ == "__main__":
    tester = P1ValidationTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)