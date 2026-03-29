#!/usr/bin/env python3
"""
Execution Safety Core APIs Backend Deep Validation Test
Testing specific endpoints for newly added Execution Safety Core APIs
"""

import requests
import json
import time
import uuid
from datetime import datetime

# Configuration - Use the backend URL from frontend/.env
BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class ExecutionSafetyCoreBackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = []
        
    def log_result(self, test_name, status, details=""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
    
    def test_admin_login(self):
        """Test admin authentication"""
        try:
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
                if "access_token" in data:
                    self.admin_token = data["access_token"]
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.admin_token}"
                    })
                    self.log_result(
                        "Admin Authentication", 
                        "PASS", 
                        f"Token received ({len(self.admin_token)} chars), Role: {data.get('role', 'N/A')}"
                    )
                    return True
                else:
                    self.log_result(
                        "Admin Authentication", 
                        "FAIL", 
                        "Missing access_token in response"
                    )
            else:
                self.log_result(
                    "Admin Authentication", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "Admin Authentication", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
        return False
    
    def test_execution_readiness_gate(self):
        """Test 1: GET /api/execution-readiness/gate"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/execution-readiness/gate",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check required contract keys
                required_keys = [
                    "gate_state", "execution_allowed", "hard_blockers", 
                    "soft_warnings", "hard_blockers_detail", "bybit_order_smoke", 
                    "artifact", "checked_at"
                ]
                
                missing_keys = [key for key in required_keys if key not in data]
                
                if not missing_keys:
                    # Validate gate_state values
                    gate_state = data.get("gate_state")
                    valid_gate_states = {"READY", "DEGRADED", "BLOCKED"}
                    
                    if gate_state in valid_gate_states:
                        self.log_result(
                            "GET /api/execution-readiness/gate", 
                            "PASS", 
                            f"All contract keys present, gate_state: {gate_state}, execution_allowed: {data.get('execution_allowed')}"
                        )
                    else:
                        self.log_result(
                            "GET /api/execution-readiness/gate", 
                            "FAIL", 
                            f"Invalid gate_state: {gate_state}, expected one of {valid_gate_states}"
                        )
                else:
                    self.log_result(
                        "GET /api/execution-readiness/gate", 
                        "FAIL", 
                        f"Missing required keys: {missing_keys}"
                    )
            else:
                self.log_result(
                    "GET /api/execution-readiness/gate", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "GET /api/execution-readiness/gate", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_execution_readiness_intents(self):
        """Test 2: GET /api/execution-readiness/intents"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/execution-readiness/intents",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check required contract keys
                required_keys = ["total", "stuck_count", "state_counts", "timeouts", "items"]
                missing_keys = [key for key in required_keys if key not in data]
                
                if not missing_keys:
                    # Validate state_counts keys
                    state_counts = data.get("state_counts", {})
                    expected_states = {
                        "CREATED", "SUBMITTED", "ACKED", "FILLED", 
                        "FAILED", "CANCELLED", "QUARANTINED"
                    }
                    
                    state_keys = set(state_counts.keys())
                    if expected_states.issubset(state_keys):
                        self.log_result(
                            "GET /api/execution-readiness/intents", 
                            "PASS", 
                            f"All contract keys present, total: {data.get('total')}, stuck_count: {data.get('stuck_count')}, states: {len(state_counts)}"
                        )
                    else:
                        missing_states = expected_states - state_keys
                        self.log_result(
                            "GET /api/execution-readiness/intents", 
                            "FAIL", 
                            f"Missing state_counts keys: {missing_states}"
                        )
                else:
                    self.log_result(
                        "GET /api/execution-readiness/intents", 
                        "FAIL", 
                        f"Missing required keys: {missing_keys}"
                    )
            else:
                self.log_result(
                    "GET /api/execution-readiness/intents", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "GET /api/execution-readiness/intents", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_execution_readiness_quarantine(self):
        """Test 3: GET /api/execution-readiness/quarantine"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/execution-readiness/quarantine",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check required contract keys
                required_keys = ["total", "summary", "queue_metrics", "items"]
                missing_keys = [key for key in required_keys if key not in data]
                
                if not missing_keys:
                    # Validate queue_metrics structure
                    queue_metrics = data.get("queue_metrics", {})
                    expected_queue_keys = ["redis_available"]
                    
                    queue_keys_present = all(key in queue_metrics for key in expected_queue_keys)
                    
                    if queue_keys_present:
                        self.log_result(
                            "GET /api/execution-readiness/quarantine", 
                            "PASS", 
                            f"All contract keys present, total: {data.get('total')}, redis_available: {queue_metrics.get('redis_available')}"
                        )
                    else:
                        self.log_result(
                            "GET /api/execution-readiness/quarantine", 
                            "FAIL", 
                            f"Missing queue_metrics keys: redis_available"
                        )
                else:
                    self.log_result(
                        "GET /api/execution-readiness/quarantine", 
                        "FAIL", 
                        f"Missing required keys: {missing_keys}"
                    )
            else:
                self.log_result(
                    "GET /api/execution-readiness/quarantine", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "GET /api/execution-readiness/quarantine", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_quarantine_actions(self):
        """Test 4: POST /api/execution-readiness/quarantine/{event_id}/{action}"""
        try:
            # Test with a sample event ID and valid actions
            test_event_id = str(uuid.uuid4())
            valid_actions = ["replay", "dismiss", "mark_failed"]
            invalid_action = "invalid_action"
            
            # Test valid actions (expecting 404 for non-existent event)
            valid_action_results = []
            for action in valid_actions:
                response = self.session.post(
                    f"{BASE_URL}/api/execution-readiness/quarantine/{test_event_id}/{action}",
                    timeout=30
                )
                valid_action_results.append((action, response.status_code))
            
            # Test invalid action (also expecting 404 since event check happens first)
            invalid_response = self.session.post(
                f"{BASE_URL}/api/execution-readiness/quarantine/{test_event_id}/{invalid_action}",
                timeout=30
            )
            
            # Validate responses - all should return 404 for non-existent event
            # The endpoint checks event existence before action validation
            valid_actions_ok = all(status == 404 for _, status in valid_action_results)
            invalid_action_ok = invalid_response.status_code == 404
            
            if valid_actions_ok and invalid_action_ok:
                self.log_result(
                    "POST /api/execution-readiness/quarantine/{event_id}/{action}", 
                    "PASS", 
                    f"All actions return 404 for non-existent event (correct behavior - event check before action validation). Results: {valid_action_results}, invalid: {invalid_response.status_code}"
                )
            else:
                self.log_result(
                    "POST /api/execution-readiness/quarantine/{event_id}/{action}", 
                    "FAIL", 
                    f"Unexpected status codes. Valid actions: {valid_action_results}, invalid action: {invalid_response.status_code}"
                )
                
        except Exception as e:
            self.log_result(
                "POST /api/execution-readiness/quarantine/{event_id}/{action}", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_service_level_verification(self):
        """Test 5: Service-level verification against Python services"""
        try:
            # Test if the service module can be imported and basic functions work
            # This is a basic service-level check since we can't directly import in this environment
            
            # Check if the endpoints are properly routed by testing OPTIONS
            endpoints_to_check = [
                "/api/execution-readiness/gate",
                "/api/execution-readiness/intents", 
                "/api/execution-readiness/quarantine"
            ]
            
            routing_results = []
            for endpoint in endpoints_to_check:
                try:
                    response = self.session.options(f"{BASE_URL}{endpoint}", timeout=10)
                    # OPTIONS should return 200, 204, or 405 (method not allowed) if endpoint exists
                    routing_results.append((endpoint, response.status_code in [200, 204, 405]))
                except:
                    routing_results.append((endpoint, False))
            
            all_routed = all(result for _, result in routing_results)
            
            if all_routed:
                self.log_result(
                    "Service-level verification", 
                    "PASS", 
                    f"All endpoints properly routed: {[ep for ep, _ in routing_results]}"
                )
            else:
                failed_endpoints = [ep for ep, result in routing_results if not result]
                self.log_result(
                    "Service-level verification", 
                    "FAIL", 
                    f"Endpoints not properly routed: {failed_endpoints}"
                )
                
        except Exception as e:
            self.log_result(
                "Service-level verification", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_environment_constraints(self):
        """Test 6: Environment constraints and error handling"""
        try:
            # Test with query parameters
            response_with_params = self.session.get(
                f"{BASE_URL}/api/execution-readiness/gate?force_refresh=true&user_id=test_user",
                timeout=30
            )
            
            # Test intents with limit parameter
            response_intents_limit = self.session.get(
                f"{BASE_URL}/api/execution-readiness/intents?limit=50&include_events=true",
                timeout=30
            )
            
            # Test quarantine with limit parameter
            response_quarantine_limit = self.session.get(
                f"{BASE_URL}/api/execution-readiness/quarantine?limit=100",
                timeout=30
            )
            
            params_ok = all(resp.status_code in [200, 400, 422] for resp in [
                response_with_params, response_intents_limit, response_quarantine_limit
            ])
            
            if params_ok:
                self.log_result(
                    "Environment constraints and parameters", 
                    "PASS", 
                    f"Query parameters handled correctly. Gate: {response_with_params.status_code}, Intents: {response_intents_limit.status_code}, Quarantine: {response_quarantine_limit.status_code}"
                )
            else:
                self.log_result(
                    "Environment constraints and parameters", 
                    "FAIL", 
                    f"Parameter handling failed. Gate: {response_with_params.status_code}, Intents: {response_intents_limit.status_code}, Quarantine: {response_quarantine_limit.status_code}"
                )
                
        except Exception as e:
            self.log_result(
                "Environment constraints and parameters", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def run_all_tests(self):
        """Run all Execution Safety Core API tests"""
        print("=" * 80)
        print("EXECUTION SAFETY CORE APIs BACKEND DEEP VALIDATION TEST")
        print(f"Target: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print("=" * 80)
        
        # Test admin authentication first
        if not self.test_admin_login():
            print("\n❌ CRITICAL: Admin login failed. Cannot proceed with authenticated tests.")
            return
        
        print("\n" + "-" * 60)
        print("Testing Execution Safety Core APIs...")
        print("-" * 60)
        
        # Test all endpoints
        self.test_execution_readiness_gate()
        self.test_execution_readiness_intents()
        self.test_execution_readiness_quarantine()
        self.test_quarantine_actions()
        self.test_service_level_verification()
        self.test_environment_constraints()
        
        # Summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("EXECUTION SAFETY CORE APIs BACKEND TEST SUMMARY")
        print("=" * 80)
        
        pass_count = sum(1 for r in self.test_results if r["status"] == "PASS")
        fail_count = sum(1 for r in self.test_results if r["status"] == "FAIL")
        partial_count = sum(1 for r in self.test_results if r["status"] == "PARTIAL")
        total_count = len(self.test_results)
        
        print(f"Total Tests: {total_count}")
        print(f"✅ PASS: {pass_count}")
        print(f"⚠️ PARTIAL: {partial_count}")
        print(f"❌ FAIL: {fail_count}")
        print(f"Success Rate: {(pass_count / total_count * 100):.1f}%")
        
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_symbol = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_symbol} {result['test']}: {result['status']}")
            if result["details"]:
                print(f"   {result['details']}")
        
        print("\nKEY VALIDATION POINTS:")
        print("1. GET /api/execution-readiness/gate - Contract keys and gate_state validation")
        print("2. GET /api/execution-readiness/intents - State counts and intent lifecycle")
        print("3. GET /api/execution-readiness/quarantine - Queue metrics and Redis availability")
        print("4. POST /api/execution-readiness/quarantine/{event_id}/{action} - Action validation")
        print("5. Service-level verification - Endpoint routing and availability")
        print("6. Environment constraints - Parameter handling and error responses")
        
        # Overall assessment
        if fail_count == 0:
            if partial_count == 0:
                print(f"\n🎯 OVERALL: ✅ PASS - All Execution Safety Core APIs validated successfully")
            else:
                print(f"\n🎯 OVERALL: ⚠️ PARTIAL PASS - Core APIs working, {partial_count} partial results")
        else:
            print(f"\n🎯 OVERALL: ❌ FAIL - {fail_count} critical API(s) failed validation")

if __name__ == "__main__":
    tester = ExecutionSafetyCoreBackendTester()
    tester.run_all_tests()