#!/usr/bin/env python3

import requests
import json
import os
import sys
from datetime import datetime
from typing import Optional

# Get backend URL from environment variable
BACKEND_URL = os.getenv("REACT_APP_BACKEND_URL", "https://user-signup-bot.preview.emergentagent.com")
API_BASE = f"{BACKEND_URL}/api"

# Test credentials
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"

# Test user credentials (found from existing users)
TEST_USER_EMAIL = "test_user_reg_1773349041@test.com"
TEST_USER_PASSWORD = "TestPassword123!"

class Iteration52Phase9ATest:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.user_token = None
        self.test_results = []
        
    def log_result(self, test_name, success, details):
        """Log test result"""
        status = "PASS" if success else "FAIL"
        self.test_results.append({
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        print(f"[{status}] {test_name}: {details}")
        
    def login_admin(self):
        """Test admin login with provided credentials"""
        try:
            response = self.session.post(
                f"{API_BASE}/auth/login",
                json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    # Set authorization header for subsequent requests
                    self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
                    self.log_result("Admin Login", True, f"Successfully logged in as {ADMIN_EMAIL}")
                    return True
                else:
                    self.log_result("Admin Login", False, "No access token received")
                    return False
            else:
                self.log_result("Admin Login", False, f"Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Login", False, f"Exception: {str(e)}")
            return False

    def create_test_user(self):
        """Login as test user for user endpoint testing"""
        try:
            # Create separate session for user
            user_session = requests.Session()
            response = user_session.post(
                f"{API_BASE}/auth/login",
                json={
                    "email": TEST_USER_EMAIL,
                    "password": TEST_USER_PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get("access_token")
                if self.user_token:
                    self.log_result("Test User Login", True, f"Successfully logged in as {TEST_USER_EMAIL}")
                    return True
                else:
                    self.log_result("Test User Login", False, "No access token received")
                    return False
            else:
                self.log_result("Test User Login", False, f"Status {response.status_code}: {response.text}")
                return False
                        
        except Exception as e:
            self.log_result("Test User Login", False, f"Exception: {str(e)}")
            return False

    def test_portfolio_risk_limits(self):
        """Test GET and PUT /api/admin/portfolio-risk/limits"""
        
        # Test 1: GET portfolio risk limits
        try:
            response = self.session.get(f"{API_BASE}/admin/portfolio-risk/limits")
            if response.status_code == 200:
                limits = response.json()
                self.log_result("Portfolio Risk Limits - GET", True, f"Retrieved limits: {json.dumps(limits, indent=2)}")
                
                # Store original limits for restore later
                original_limits = limits.copy()
                
                # Test 2: PUT portfolio risk limits
                try:
                    # Prepare update payload (modify one limit)
                    update_payload = original_limits.copy()
                    if "max_daily_loss_pct" in update_payload:
                        original_max_daily_loss = update_payload["max_daily_loss_pct"]
                        update_payload["max_daily_loss_pct"] = 5.0  # Test value
                    
                    response = self.session.put(
                        f"{API_BASE}/admin/portfolio-risk/limits",
                        json=update_payload
                    )
                    if response.status_code == 200:
                        updated_limits = response.json()
                        self.log_result("Portfolio Risk Limits - PUT", True, f"Updated limits successfully")
                        
                        # Restore original limits
                        if "max_daily_loss_pct" in original_limits:
                            original_limits["max_daily_loss_pct"] = original_max_daily_loss
                            self.session.put(
                                f"{API_BASE}/admin/portfolio-risk/limits", 
                                json=original_limits
                            )
                    else:
                        self.log_result("Portfolio Risk Limits - PUT", False, f"Status {response.status_code}: {response.text}")
                except Exception as e:
                    self.log_result("Portfolio Risk Limits - PUT", False, f"Exception: {str(e)}")
                    
            else:
                self.log_result("Portfolio Risk Limits - GET", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Portfolio Risk Limits - GET", False, f"Exception: {str(e)}")

    def test_portfolio_risk_clusters(self):
        """Test GET and POST /api/admin/portfolio-risk/clusters"""
        
        # Test 1: GET risk clusters
        try:
            response = self.session.get(f"{API_BASE}/admin/portfolio-risk/clusters")
            if response.status_code == 200:
                clusters = response.json()
                self.log_result("Portfolio Risk Clusters - GET", True, f"Retrieved {len(clusters)} clusters")
                
                # Test 2: POST create new risk cluster
                try:
                    # Create correct test cluster with all required fields
                    test_cluster = {
                        "cluster_id": "TEST_CLUSTER_IT52",
                        "symbols": ["BTCUSDT", "ETHUSDT"],
                        "cluster_type": "sector",
                        "correlation_score": 0.7,
                        "risk_weight": 1.5
                    }
                    
                    response = self.session.post(
                        f"{API_BASE}/admin/portfolio-risk/clusters",
                        json=test_cluster
                    )
                    if response.status_code == 200:
                        created_cluster = response.json()
                        self.log_result("Portfolio Risk Clusters - POST", True, f"Created cluster: {created_cluster.get('cluster_id')}")
                        
                        # Clean up - try to delete if there's a delete endpoint
                        # (This is optional cleanup)
                    else:
                        self.log_result("Portfolio Risk Clusters - POST", False, f"Status {response.status_code}: {response.text}")
                except Exception as e:
                    self.log_result("Portfolio Risk Clusters - POST", False, f"Exception: {str(e)}")
                    
            else:
                self.log_result("Portfolio Risk Clusters - GET", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Portfolio Risk Clusters - GET", False, f"Exception: {str(e)}")

    def test_portfolio_risk_dashboard(self):
        """Test GET /api/admin/portfolio-risk dashboard payload"""
        
        try:
            response = self.session.get(f"{API_BASE}/admin/portfolio-risk")
            if response.status_code == 200:
                dashboard = response.json()
                
                # Verify expected dashboard fields
                expected_fields = ["timestamp", "total_exposure", "cluster_exposure", "strategy_exposure", "risk_alerts"]
                missing_fields = [field for field in expected_fields if field not in dashboard]
                
                if not missing_fields:
                    total_exposure = dashboard.get("total_exposure")
                    cluster_exposure = dashboard.get("cluster_exposure", {})
                    strategy_exposure = dashboard.get("strategy_exposure", {})
                    risk_alerts = dashboard.get("risk_alerts", [])
                    
                    self.log_result("Portfolio Risk Dashboard - GET", True, 
                                   f"Total exposure: {total_exposure}, Clusters: {len(cluster_exposure)}, Strategies: {len(strategy_exposure)}, Alerts: {len(risk_alerts)}")
                else:
                    self.log_result("Portfolio Risk Dashboard - GET", False, f"Missing fields: {missing_fields}")
            else:
                self.log_result("Portfolio Risk Dashboard - GET", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Portfolio Risk Dashboard - GET", False, f"Exception: {str(e)}")

    def test_strategy_allocation(self):
        """Test GET and PUT /api/admin/strategy-allocation"""
        
        # Test 1: GET strategy allocation
        try:
            response = self.session.get(f"{API_BASE}/admin/strategy-allocation")
            if response.status_code == 200:
                allocations = response.json()
                self.log_result("Strategy Allocation - GET", True, f"Retrieved {len(allocations)} strategy allocations")
                
                # Test 2: PUT strategy allocation update (if we have strategies)
                if allocations:
                    try:
                        # Pick first strategy for testing
                        test_strategy = allocations[0]
                        strategy_id = test_strategy.get("strategy_id")
                        original_allocation = test_strategy.get("base_allocation", 0)
                        
                        # Update allocation
                        update_payload = {
                            "base_allocation": min(original_allocation + 1, 100),  # Small increment
                            "active": True
                        }
                        
                        response = self.session.put(
                            f"{API_BASE}/admin/strategy-allocation/{strategy_id}",
                            json=update_payload
                        )
                        if response.status_code == 200:
                            updated_allocation = response.json()
                            self.log_result("Strategy Allocation - PUT", True, f"Updated allocation for {strategy_id}")
                            
                            # Restore original allocation
                            restore_payload = {
                                "base_allocation": original_allocation,
                                "active": test_strategy.get("active", True)
                            }
                            self.session.put(
                                f"{API_BASE}/admin/strategy-allocation/{strategy_id}",
                                json=restore_payload
                            )
                        else:
                            self.log_result("Strategy Allocation - PUT", False, f"Status {response.status_code}: {response.text}")
                    except Exception as e:
                        self.log_result("Strategy Allocation - PUT", False, f"Exception: {str(e)}")
                else:
                    self.log_result("Strategy Allocation - PUT", False, "No strategies found to test allocation update")
                    
            else:
                self.log_result("Strategy Allocation - GET", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Strategy Allocation - GET", False, f"Exception: {str(e)}")

    def test_user_execution_intent_preview(self):
        """Test POST /api/user/execution/intent/preview with meta_strategy_summary + portfolio_risk_impact + gate_decision"""
        
        # Switch to user session
        if not self.user_token:
            self.log_result("User Execution Intent Preview", False, "No user token available")
            return
            
        user_session = requests.Session()
        user_session.headers.update({"Authorization": f"Bearer {self.user_token}"})
        
        try:
            # Create a sample execution intent preview request
            preview_payload = {
                "symbol": "BTCUSDT",
                "market_type": "spot",
                "side": "buy",
                "notional": 100.0,
                "strategy_binding": "spot_pullback_v1",
                "order_type": "market"
            }
            
            response = user_session.post(
                f"{API_BASE}/user/execution/intent/preview",
                json=preview_payload
            )
            if response.status_code == 200:
                preview = response.json()
                
                # Verify expected fields for Phase 9A
                expected_fields = [
                    "intent_id", "validation_status", "meta_strategy_summary", 
                    "portfolio_risk_impact", "gate_decision", "meta_engine_decision"
                ]
                
                present_fields = [field for field in expected_fields if field in preview]
                missing_fields = [field for field in expected_fields if field not in preview]
                
                if len(present_fields) >= 4:  # At least most critical fields present
                    meta_strategy = preview.get("meta_strategy_summary", {})
                    portfolio_risk = preview.get("portfolio_risk_impact", {})
                    gate_decision = preview.get("gate_decision")
                    meta_engine_decision = preview.get("meta_engine_decision")
                    
                    self.log_result("User Execution Intent Preview", True, 
                                   f"Preview successful - Gate: {gate_decision}, Meta Engine: {meta_engine_decision}, Meta Strategy fields: {len(meta_strategy)}, Portfolio Risk fields: {len(portfolio_risk)}")
                    
                    if missing_fields:
                        self.log_result("User Execution Intent Preview - Fields", False, f"Missing Phase9A fields: {missing_fields}")
                    else:
                        self.log_result("User Execution Intent Preview - Fields", True, "All Phase9A fields present")
                else:
                    self.log_result("User Execution Intent Preview", False, f"Missing critical fields: {missing_fields}")
            else:
                self.log_result("User Execution Intent Preview", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("User Execution Intent Preview", False, f"Exception: {str(e)}")

    def test_user_execution_intent_decision_trace(self):
        """Test GET /api/user/execution/intents/{id}/decision-trace for portfolio_risk_score + strategy_allocation_reason + meta_engine_decision"""
        
        # Switch to user session
        if not self.user_token:
            self.log_result("User Execution Decision Trace", False, "No user token available")
            return
            
        user_session = requests.Session()
        user_session.headers.update({"Authorization": f"Bearer {self.user_token}"})
        
        try:
            # First, try to get list of execution intents to find an ID
            response = user_session.get(f"{API_BASE}/user/execution/intents?limit=10")
            if response.status_code == 200:
                intents = response.json()
                
                if intents:
                    # Use first intent for decision trace testing
                    test_intent_id = intents[0].get("id")
                    
                    response = user_session.get(f"{API_BASE}/user/execution/intents/{test_intent_id}/decision-trace")
                    if response.status_code == 200:
                        decision_trace = response.json()
                        
                        # Check for Phase9A decision trace fields
                        timeline = decision_trace.get("timeline", [])
                        if timeline:
                            latest_trace = timeline[0] if timeline else decision_trace.get("latest_trace", {})
                            
                            # Phase9A fields can be at the top level of the trace object
                            phase9a_fields = []
                            if "portfolio_risk_score" in latest_trace:
                                phase9a_fields.append("portfolio_risk_score")
                            if "strategy_allocation_reason" in latest_trace:
                                phase9a_fields.append("strategy_allocation_reason")
                            if "meta_engine_decision" in latest_trace:
                                phase9a_fields.append("meta_engine_decision")
                            
                            # Also check context_payload and feature_snapshot for completeness
                            context_payload = latest_trace.get("context_payload", {})
                            feature_snapshot = latest_trace.get("feature_snapshot", {})
                            
                            if "portfolio_risk_score" in context_payload or "portfolio_risk_score" in feature_snapshot:
                                if "portfolio_risk_score" not in phase9a_fields:
                                    phase9a_fields.append("portfolio_risk_score (nested)")
                            if "strategy_allocation_reason" in context_payload or "strategy_allocation_reason" in feature_snapshot:
                                if "strategy_allocation_reason" not in phase9a_fields:
                                    phase9a_fields.append("strategy_allocation_reason (nested)")
                            if "meta_engine_decision" in context_payload or "meta_engine_decision" in feature_snapshot:
                                if "meta_engine_decision" not in phase9a_fields:
                                    phase9a_fields.append("meta_engine_decision (nested)")
                            
                            if phase9a_fields:
                                # Get actual values for verification
                                portfolio_risk_score = latest_trace.get("portfolio_risk_score")
                                strategy_allocation_reason = latest_trace.get("strategy_allocation_reason")
                                meta_engine_decision = latest_trace.get("meta_engine_decision")
                                
                                self.log_result("User Execution Decision Trace", True, 
                                               f"Phase9A fields found: {phase9a_fields}. Values - Portfolio Risk: {portfolio_risk_score}, Strategy Allocation: {strategy_allocation_reason}, Meta Engine: {meta_engine_decision}")
                            else:
                                self.log_result("User Execution Decision Trace", False, "No Phase9A fields found in decision trace")
                        else:
                            self.log_result("User Execution Decision Trace", False, "No timeline data in decision trace")
                    else:
                        self.log_result("User Execution Decision Trace", False, f"Status {response.status_code}: {response.text}")
                else:
                    self.log_result("User Execution Decision Trace", False, "No execution intents found to test decision trace")
            else:
                self.log_result("User Execution Decision Trace", False, f"Could not get intents list - Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("User Execution Decision Trace", False, f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all Iteration-52 Phase-9A backend tests"""
        print("=" * 80)
        print("ITERATION-52 PHASE-9A BACKEND REGRESSION + FEATURE VALIDATION")
        print("=" * 80)
        print(f"Backend URL: {BACKEND_URL}")
        print(f"Admin Credentials: {ADMIN_EMAIL}")
        print("=" * 80)
        
        # Login first
        if not self.login_admin():
            print("\n❌ CRITICAL: Admin login failed - cannot continue with tests")
            return False
            
        # Set up user testing
        if not self.create_test_user():
            print("\n⚠️  WARNING: User login failed - user endpoint tests will be skipped")
            
        # Run Backend API tests
        print("\n🔄 Testing GET/PUT /api/admin/portfolio-risk/limits...")
        self.test_portfolio_risk_limits()
        
        print("\n🔄 Testing GET/POST /api/admin/portfolio-risk/clusters...")  
        self.test_portfolio_risk_clusters()
        
        print("\n🔄 Testing GET /api/admin/portfolio-risk dashboard...")
        self.test_portfolio_risk_dashboard()
        
        print("\n🔄 Testing GET/PUT /api/admin/strategy-allocation...")
        self.test_strategy_allocation()
        
        print("\n🔄 Testing POST /api/user/execution/intent/preview...")
        self.test_user_execution_intent_preview()
        
        print("\n🔄 Testing GET /api/user/execution/intents/{id}/decision-trace...")
        self.test_user_execution_intent_decision_trace()
        
        # Summary
        print("\n" + "=" * 80)
        print("ITERATION-52 PHASE-9A TEST RESULTS")
        print("=" * 80)
        
        passed = sum(1 for result in self.test_results if result["status"] == "PASS")
        failed = sum(1 for result in self.test_results if result["status"] == "FAIL")
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print(f"Success Rate: {(passed/total*100):.1f}%" if total > 0 else "N/A")
        
        if failed > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"  - {result['test']}: {result['details']}")
        else:
            print("\n✅ ALL TESTS PASSED!")
        
        print("\n" + "=" * 80)
        
        return failed == 0


def main():
    """Main test runner"""
    tester = Iteration52Phase9ATest()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()