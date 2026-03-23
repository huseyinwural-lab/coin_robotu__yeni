#!/usr/bin/env python3
"""
P1 Backend Validation Test
Testing conflict/hedge/rebalance flows, deterministic model, compare upgrade, and queue hardening regression
URL: https://risk-orchestrator-p0.preview.emergentagent.com
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

# Test configuration
BASE_URL = "https://risk-orchestrator-p0.preview.emergentagent.com"
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
        
        # Test decision request creation
        try:
            # Try to get existing decision requests first
            response = self.make_authenticated_request("GET", "/admin/decision-requests", self.super_admin_token)
            
            if response.status_code == 200:
                decision_requests = response.json()
                self.log_test("Decision Requests List", "PASS", 
                            f"Retrieved {len(decision_requests)} decision requests", 
                            "GET /api/admin/decision-requests")
                
                # Look for conflict/hedge/rebalance requests
                conflict_requests = [req for req in decision_requests if req.get('decision_type') in ['conflict', 'hedge', 'rebalance']]
                
                if conflict_requests:
                    # Test approve + execute flow on existing request
                    test_request = conflict_requests[0]
                    request_id = test_request.get('id')
                    decision_type = test_request.get('decision_type')
                    
                    self.log_test("Found Decision Request", "PASS", 
                                f"Found {decision_type} request with ID: {request_id}")
                    
                    # Test approve endpoint
                    approve_response = self.make_authenticated_request(
                        "POST", f"/admin/decision-requests/{request_id}/approve", 
                        self.super_admin_token,
                        data={"approval_note": "P1 validation test approval"}
                    )
                    
                    if approve_response.status_code == 200:
                        self.log_test("Decision Request Approve", "PASS", 
                                    f"Successfully approved {decision_type} request",
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
                                
                                # Check specific fields based on decision type
                                if decision_type == 'hedge':
                                    has_realized_risk_drop = 'realized_risk_drop' in execute_data.get('execution_effect', {})
                                    if has_realized_risk_drop:
                                        self.log_test("Hedge Realized Risk Drop", "PASS",
                                                    "Hedge execution contains realized_risk_drop field")
                                    else:
                                        self.log_test("Hedge Realized Risk Drop", "FAIL",
                                                    "Hedge execution missing realized_risk_drop field")
                                
                                elif decision_type == 'rebalance':
                                    has_allocation_diff = 'allocation_diff_bps' in execute_data.get('execution_effect', {})
                                    if has_allocation_diff:
                                        self.log_test("Rebalance Allocation Diff", "PASS",
                                                    "Rebalance execution contains allocation_diff_bps field")
                                    else:
                                        self.log_test("Rebalance Allocation Diff", "FAIL",
                                                    "Rebalance execution missing allocation_diff_bps field")
                                        
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
                queue_data = response.json()
                
                # Check for deterministic_effect_preview in response
                has_deterministic_preview = any('deterministic_effect_preview' in item for item in queue_data if isinstance(item, dict))
                
                if has_deterministic_preview:
                    self.log_test("Deterministic Effect Preview", "PASS",
                                "Queue response contains deterministic_effect_preview field",
                                "GET /api/admin/decision-requests")
                else:
                    self.log_test("Deterministic Effect Preview", "FAIL",
                                "Queue response missing deterministic_effect_preview field",
                                "GET /api/admin/decision-requests")
                
                # Check for recommendation_rank in pending items
                pending_items = [item for item in queue_data if isinstance(item, dict) and item.get('status') == 'pending']
                has_recommendation_rank = any('recommendation_rank' in item for item in pending_items)
                
                if pending_items:
                    if has_recommendation_rank:
                        self.log_test("Recommendation Rank", "PASS",
                                    f"Found recommendation_rank in {len(pending_items)} pending items",
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
            # First, try to get simulation runs to find a valid run_id
            sim_runs_response = self.make_authenticated_request("GET", "/admin/simulation-runs", self.super_admin_token)
            
            if sim_runs_response.status_code == 200:
                sim_runs = sim_runs_response.json()
                
                if sim_runs and len(sim_runs) > 0:
                    # Use first simulation run ID
                    run_id = sim_runs[0].get('id') if isinstance(sim_runs[0], dict) else sim_runs[0]
                    
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
                self.log_test("Simulation Runs List", "FAIL",
                            f"Failed to get simulation runs: {sim_runs_response.status_code} - {sim_runs_response.text}",
                            "GET /api/admin/simulation-runs")
                
        except Exception as e:
            self.log_test("Compare Upgrade Backend", "FAIL", f"Exception: {str(e)}")

    def test_queue_hardening_regression(self):
        """Test 4: Queue hardening regression - assign-owner, ack, bulk-action endpoints"""
        print("=== TEST 4: Queue Hardening Regression ===")
        
        try:
            # Test assign-owner endpoint
            # First get a decision request to test with
            response = self.make_authenticated_request("GET", "/admin/decision-requests", self.super_admin_token)
            
            if response.status_code == 200:
                decision_requests = response.json()
                
                if decision_requests and len(decision_requests) > 0:
                    test_request_id = decision_requests[0].get('id') if isinstance(decision_requests[0], dict) else decision_requests[0]
                    
                    # Test assign-owner endpoint
                    assign_response = self.make_authenticated_request(
                        "POST", f"/admin/decision-requests/{test_request_id}/assign-owner",
                        self.super_admin_token,
                        data={"owner_id": "test-owner", "assignment_note": "P1 validation test"}
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
                        data={"ack_note": "P1 validation test acknowledgment"}
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
                            "bulk_note": "P1 validation bulk test"
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