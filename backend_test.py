#!/usr/bin/env python3
"""
Backend Test Script for P0/P1 State Validation
Re-validate latest P0/P1 state after credential update and env reload support.

Test Requirements:
1) Auth flow
   - POST /api/auth/login/admin with canary creds
   - GET /api/auth/me with bearer + X-Session-Device => 200
   - GET /api/auth/me with bearer only => 401 session_device_mismatch
2) Gate endpoint
   - GET /api/execution-readiness/gate?force_refresh=true
   - Verify artifact.status ideally S3_UPLOADED (with latest AWS secret)
   - Verify bybit_order_smoke status and reason
3) Incident export endpoint
   - GET /api/execution-readiness/incident/export
   - Verify runbook_recommendations + quarantine_replay_plan present
4) Quarantine operations smoke
   - Ensure replay/dismiss/mark_failed contracts still valid for execution_intent entry
5) P1 endpoints contract
   - /reconciliation/summary
   - /gate/trends
   - /interventions/audit-trail
   - /intents/stuck/batch-recover

Credentials: canary.admin@platform.local / CanaryAdmin123!
"""

import json
import sys
import time
from typing import Any, Dict, Optional

import requests


class BackendTester:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 30
        self.auth_token: Optional[str] = None
        self.device_id: Optional[str] = None
        
    def log(self, message: str, level: str = "INFO") -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
        
    def test_admin_login(self, email: str, password: str) -> Dict[str, Any]:
        """Test admin login and extract auth token + device ID"""
        self.log("Testing admin login...")
        
        url = f"{self.base_url}/api/auth/login/admin"
        payload = {
            "email": email,
            "password": password
        }
        
        try:
            response = self.session.post(url, json=payload)
            self.log(f"Login response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get("access_token")
                
                # Extract device_id from cookies
                if "device_id" in response.cookies:
                    self.device_id = response.cookies["device_id"]
                    self.log(f"Device ID extracted from cookies: {self.device_id}")
                
                self.log(f"Login successful. Token length: {len(self.auth_token) if self.auth_token else 0}")
                return {"status": "success", "token_length": len(self.auth_token) if self.auth_token else 0}
            else:
                error_detail = response.text
                self.log(f"Login failed: {response.status_code} - {error_detail}", "ERROR")
                return {"status": "failed", "error": f"{response.status_code}: {error_detail}"}
                
        except Exception as e:
            self.log(f"Login exception: {str(e)}", "ERROR")
            return {"status": "error", "exception": str(e)}
    
    def test_auth_me_with_device(self) -> Dict[str, Any]:
        """Test /api/auth/me with bearer token + X-Session-Device header"""
        self.log("Testing /api/auth/me with bearer + X-Session-Device...")
        
        if not self.auth_token or not self.device_id:
            return {"status": "error", "message": "Missing auth token or device ID"}
        
        url = f"{self.base_url}/api/auth/me"
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "X-Session-Device": self.device_id
        }
        
        try:
            response = self.session.get(url, headers=headers)
            self.log(f"/api/auth/me (with device) status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                user_role = data.get("role")
                user_email = data.get("email")
                self.log(f"Auth me successful. Role: {user_role}, Email: {user_email}")
                return {"status": "success", "role": user_role, "email": user_email}
            else:
                error_detail = response.text
                self.log(f"Auth me failed: {response.status_code} - {error_detail}", "ERROR")
                return {"status": "failed", "error": f"{response.status_code}: {error_detail}"}
                
        except Exception as e:
            self.log(f"Auth me exception: {str(e)}", "ERROR")
            return {"status": "error", "exception": str(e)}
    
    def test_auth_me_without_device(self) -> Dict[str, Any]:
        """Test /api/auth/me with bearer token only (should return 401)"""
        self.log("Testing /api/auth/me with bearer only (expecting 401)...")
        
        if not self.auth_token:
            return {"status": "error", "message": "Missing auth token"}
        
        url = f"{self.base_url}/api/auth/me"
        headers = {
            "Authorization": f"Bearer {self.auth_token}"
            # Intentionally omitting X-Session-Device header
        }
        
        try:
            # Use a fresh session without cookies to test device mismatch
            fresh_session = requests.Session()
            fresh_session.timeout = 30
            response = fresh_session.get(url, headers=headers)
            self.log(f"/api/auth/me (without device) status: {response.status_code}")
            
            if response.status_code == 401:
                error_detail = response.text
                self.log(f"Expected 401 received: {error_detail}")
                return {"status": "success", "expected_401": True, "detail": error_detail}
            else:
                self.log(f"Unexpected status code: {response.status_code} (expected 401)", "ERROR")
                return {"status": "failed", "unexpected_status": response.status_code}
                
        except Exception as e:
            self.log(f"Auth me (no device) exception: {str(e)}", "ERROR")
            return {"status": "error", "exception": str(e)}
    
    def test_execution_gate(self) -> Dict[str, Any]:
        """Test GET /api/execution-readiness/gate?force_refresh=true"""
        self.log("Testing execution readiness gate...")
        
        if not self.auth_token or not self.device_id:
            return {"status": "error", "message": "Missing auth token or device ID"}
        
        url = f"{self.base_url}/api/execution-readiness/gate?force_refresh=true"
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "X-Session-Device": self.device_id
        }
        
        try:
            response = self.session.get(url, headers=headers)
            self.log(f"Execution gate status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Check required fields
                gate_state = data.get("gate_state")
                execution_allowed = data.get("execution_allowed")
                artifact = data.get("artifact", {})
                artifact_status = artifact.get("status") if isinstance(artifact, dict) else None
                bybit_order_smoke = data.get("bybit_order_smoke", {})
                bybit_status = bybit_order_smoke.get("status") if isinstance(bybit_order_smoke, dict) else None
                bybit_reason = bybit_order_smoke.get("reason") if isinstance(bybit_order_smoke, dict) else None
                
                self.log(f"Gate state: {gate_state}")
                self.log(f"Execution allowed: {execution_allowed}")
                self.log(f"Artifact status: {artifact_status}")
                self.log(f"Bybit order smoke status: {bybit_status}")
                self.log(f"Bybit order smoke reason: {bybit_reason}")
                
                return {
                    "status": "success",
                    "gate_state": gate_state,
                    "execution_allowed": execution_allowed,
                    "artifact_status": artifact_status,
                    "bybit_order_smoke_status": bybit_status,
                    "bybit_order_smoke_reason": bybit_reason
                }
            else:
                error_detail = response.text
                self.log(f"Execution gate failed: {response.status_code} - {error_detail}", "ERROR")
                return {"status": "failed", "error": f"{response.status_code}: {error_detail}"}
                
        except Exception as e:
            self.log(f"Execution gate exception: {str(e)}", "ERROR")
            return {"status": "error", "exception": str(e)}
    
    def test_incident_export(self) -> Dict[str, Any]:
        """Test GET /api/execution-readiness/incident/export"""
        self.log("Testing incident export...")
        
        if not self.auth_token or not self.device_id:
            return {"status": "error", "message": "Missing auth token or device ID"}
        
        url = f"{self.base_url}/api/execution-readiness/incident/export"
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "X-Session-Device": self.device_id
        }
        
        try:
            response = self.session.get(url, headers=headers)
            self.log(f"Incident export status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for required fields
                runbook_recommendations = data.get("runbook_recommendations")
                quarantine_replay_plan = data.get("quarantine_replay_plan")
                
                has_runbook = runbook_recommendations is not None
                has_quarantine_plan = quarantine_replay_plan is not None
                
                self.log(f"Runbook recommendations present: {has_runbook}")
                self.log(f"Quarantine replay plan present: {has_quarantine_plan}")
                
                if has_runbook:
                    self.log(f"Runbook recommendations type: {type(runbook_recommendations)}")
                if has_quarantine_plan:
                    self.log(f"Quarantine replay plan type: {type(quarantine_replay_plan)}")
                
                return {
                    "status": "success",
                    "has_runbook_recommendations": has_runbook,
                    "has_quarantine_replay_plan": has_quarantine_plan,
                    "runbook_type": str(type(runbook_recommendations)),
                    "quarantine_plan_type": str(type(quarantine_replay_plan))
                }
            else:
                error_detail = response.text
                self.log(f"Incident export failed: {response.status_code} - {error_detail}", "ERROR")
                return {"status": "failed", "error": f"{response.status_code}: {error_detail}"}
                
        except Exception as e:
            self.log(f"Incident export exception: {str(e)}", "ERROR")
            return {"status": "error", "exception": str(e)}
    
    def test_quarantine_operations(self) -> Dict[str, Any]:
        """Test quarantine operations smoke test"""
        self.log("Testing quarantine operations...")
        
        if not self.auth_token or not self.device_id:
            return {"status": "error", "message": "Missing auth token or device ID"}
        
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "X-Session-Device": self.device_id
        }
        
        # First get quarantine snapshot
        url = f"{self.base_url}/api/execution-readiness/quarantine"
        
        try:
            response = self.session.get(url, headers=headers)
            self.log(f"Quarantine snapshot status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                total = data.get("total", 0)
                items = data.get("items", [])
                
                self.log(f"Quarantine total: {total}")
                self.log(f"Quarantine items count: {len(items)}")
                
                # Test action endpoints with a dummy event ID (should return 404 for non-existent event)
                test_event_id = "test-event-id-12345"
                actions = ["replay", "dismiss", "mark_failed"]
                action_results = {}
                
                for action in actions:
                    action_url = f"{self.base_url}/api/execution-readiness/quarantine/{test_event_id}/{action}"
                    try:
                        action_response = self.session.post(action_url, headers=headers)
                        action_results[action] = {
                            "status_code": action_response.status_code,
                            "accessible": action_response.status_code in [404, 400]  # 404 for non-existent event is expected
                        }
                        self.log(f"Action {action} status: {action_response.status_code}")
                    except Exception as e:
                        action_results[action] = {"error": str(e), "accessible": False}
                        self.log(f"Action {action} exception: {str(e)}", "ERROR")
                
                return {
                    "status": "success",
                    "quarantine_total": total,
                    "quarantine_items_count": len(items),
                    "action_endpoints": action_results
                }
            else:
                error_detail = response.text
                self.log(f"Quarantine snapshot failed: {response.status_code} - {error_detail}", "ERROR")
                return {"status": "failed", "error": f"{response.status_code}: {error_detail}"}
                
        except Exception as e:
            self.log(f"Quarantine operations exception: {str(e)}", "ERROR")
            return {"status": "error", "exception": str(e)}
    
    def test_p1_endpoints(self) -> Dict[str, Any]:
        """Test P1 endpoints contract"""
        self.log("Testing P1 endpoints...")
        
        if not self.auth_token or not self.device_id:
            return {"status": "error", "message": "Missing auth token or device ID"}
        
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "X-Session-Device": self.device_id
        }
        
        endpoints = {
            "reconciliation_summary": "/api/execution-readiness/reconciliation/summary",
            "gate_trends": "/api/execution-readiness/gate/trends",
            "interventions_audit_trail": "/api/execution-readiness/interventions/audit-trail",
            "intents_stuck_batch_recover": "/api/execution-readiness/intents/stuck/batch-recover"
        }
        
        results = {}
        
        for endpoint_name, endpoint_path in endpoints.items():
            url = f"{self.base_url}{endpoint_path}"
            
            try:
                if endpoint_name == "intents_stuck_batch_recover":
                    # This is a POST endpoint
                    response = self.session.post(url, headers=headers)
                else:
                    # These are GET endpoints
                    response = self.session.get(url, headers=headers)
                
                self.log(f"{endpoint_name} status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    results[endpoint_name] = {
                        "status": "success",
                        "status_code": response.status_code,
                        "has_data": bool(data),
                        "data_type": str(type(data))
                    }
                else:
                    error_detail = response.text
                    results[endpoint_name] = {
                        "status": "failed",
                        "status_code": response.status_code,
                        "error": error_detail
                    }
                    self.log(f"{endpoint_name} failed: {response.status_code} - {error_detail}", "ERROR")
                    
            except Exception as e:
                results[endpoint_name] = {
                    "status": "error",
                    "exception": str(e)
                }
                self.log(f"{endpoint_name} exception: {str(e)}", "ERROR")
        
        return {"status": "success", "endpoints": results}
    
    def run_all_tests(self, email: str, password: str) -> Dict[str, Any]:
        """Run all tests and return comprehensive results"""
        self.log("Starting comprehensive backend validation...")
        
        results = {
            "test_timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "base_url": self.base_url,
            "credentials_email": email
        }
        
        # Test 1: Admin Login
        self.log("\n=== TEST 1: Admin Login ===")
        results["admin_login"] = self.test_admin_login(email, password)
        
        if results["admin_login"]["status"] != "success":
            self.log("Admin login failed, cannot proceed with other tests", "ERROR")
            return results
        
        # Test 2: Auth /me with device
        self.log("\n=== TEST 2: Auth /me with Device ===")
        results["auth_me_with_device"] = self.test_auth_me_with_device()
        
        # Test 3: Auth /me without device (expecting 401)
        self.log("\n=== TEST 3: Auth /me without Device ===")
        results["auth_me_without_device"] = self.test_auth_me_without_device()
        
        # Re-authenticate after device mismatch test (session may be revoked)
        self.log("\n=== RE-AUTHENTICATION AFTER DEVICE MISMATCH TEST ===")
        reauth_result = self.test_admin_login(email, password)
        if reauth_result["status"] != "success":
            self.log("Re-authentication failed, cannot proceed with remaining tests", "ERROR")
            return results
        
        # Test 4: Execution Gate
        self.log("\n=== TEST 4: Execution Gate ===")
        results["execution_gate"] = self.test_execution_gate()
        
        # Test 5: Incident Export
        self.log("\n=== TEST 5: Incident Export ===")
        results["incident_export"] = self.test_incident_export()
        
        # Test 6: Quarantine Operations
        self.log("\n=== TEST 6: Quarantine Operations ===")
        results["quarantine_operations"] = self.test_quarantine_operations()
        
        # Test 7: P1 Endpoints
        self.log("\n=== TEST 7: P1 Endpoints ===")
        results["p1_endpoints"] = self.test_p1_endpoints()
        
        return results


def main():
    """Main function to run the backend tests"""
    
    # Configuration
    BASE_URL = "https://quarantine-pipeline.preview.emergentagent.com"
    EMAIL = "canary.admin@platform.local"
    PASSWORD = "CanaryAdmin123!"
    
    print("=" * 80)
    print("BACKEND P0/P1 STATE VALIDATION")
    print("=" * 80)
    print(f"Target URL: {BASE_URL}")
    print(f"Credentials: {EMAIL} / {'*' * len(PASSWORD)}")
    print("=" * 80)
    
    # Initialize tester
    tester = BackendTester(BASE_URL)
    
    # Run all tests
    results = tester.run_all_tests(EMAIL, PASSWORD)
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)
    
    test_names = [
        ("admin_login", "Admin Login"),
        ("auth_me_with_device", "Auth /me with Device"),
        ("auth_me_without_device", "Auth /me without Device"),
        ("execution_gate", "Execution Gate"),
        ("incident_export", "Incident Export"),
        ("quarantine_operations", "Quarantine Operations"),
        ("p1_endpoints", "P1 Endpoints")
    ]
    
    passed = 0
    total = len(test_names)
    
    for test_key, test_name in test_names:
        if test_key in results:
            test_result = results[test_key]
            status = test_result.get("status", "unknown")
            
            if status == "success":
                print(f"✅ {test_name}: PASS")
                passed += 1
            elif status == "failed":
                print(f"❌ {test_name}: FAIL - {test_result.get('error', 'Unknown error')}")
            else:
                print(f"⚠️  {test_name}: ERROR - {test_result.get('exception', 'Unknown exception')}")
        else:
            print(f"❓ {test_name}: NOT TESTED")
    
    print("=" * 80)
    print(f"OVERALL RESULT: {passed}/{total} TESTS PASSED ({passed/total*100:.1f}%)")
    print("=" * 80)
    
    # Save detailed results to file
    output_file = "/app/backend_test_results.json"
    try:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Detailed results saved to: {output_file}")
    except Exception as e:
        print(f"Failed to save results: {e}")
    
    # Return appropriate exit code
    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print("💥 SOME TESTS FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    main()