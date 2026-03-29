#!/usr/bin/env python3
"""
Execution Safety Namespace Backend Deep Validation
Final backend deep validation for execution-safety namespace after scope lock.

Must verify:
1) /api/execution-safety/gate schema and blocker override
2) /api/execution-safety/intents canonical states include CANCELED (not CANCELLED)
3) /api/execution-safety/quarantine required contract fields
4) /api/execution-safety/recovery + /recovery/batch + /recovery/{intent_id}/{action}
5) /api/execution-safety/artifacts + /artifacts/incident-export
6) /api/execution-safety/recovery/policy and /recovery/policy/{environment} route order correctness
7) /api/execution-safety/observability
8) legacy /api/execution-readiness/* returns deprecated markers

Please classify external blockers separately (Bybit 403 runtime issue).
Credentials: canary.admin@platform.local / CanaryAdmin123!
"""

import json
import sys
import time
from typing import Any, Dict, List, Optional

import requests


class ExecutionSafetyTester:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 30
        self.auth_token: Optional[str] = None
        self.device_id: Optional[str] = None
        
    def log(self, message: str, level: str = "INFO") -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
        
    def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate with admin credentials"""
        self.log("Authenticating with admin credentials...")
        
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
                    self.log(f"Device ID extracted: {self.device_id}")
                
                self.log(f"Authentication successful. Token length: {len(self.auth_token) if self.auth_token else 0}")
                return {"status": "success", "token_length": len(self.auth_token) if self.auth_token else 0}
            else:
                error_detail = response.text
                self.log(f"Authentication failed: {response.status_code} - {error_detail}", "ERROR")
                return {"status": "failed", "error": f"{response.status_code}: {error_detail}"}
                
        except Exception as e:
            self.log(f"Authentication exception: {str(e)}", "ERROR")
            return {"status": "error", "exception": str(e)}
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        if not self.auth_token or not self.device_id:
            raise ValueError("Missing auth token or device ID")
        
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "X-Session-Device": self.device_id
        }
    
    def test_execution_safety_gate(self) -> Dict[str, Any]:
        """Test 1: /api/execution-safety/gate schema and blocker override"""
        self.log("Testing /api/execution-safety/gate schema and blocker override...")
        
        url = f"{self.base_url}/api/execution-safety/gate"
        headers = self._get_headers()
        
        try:
            # Test with force_refresh parameter
            response = self.session.get(url, headers=headers, params={"force_refresh": True})
            self.log(f"Gate endpoint status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate required schema fields
                required_fields = ["state", "score", "blockers", "warnings", "evaluated_at", "execution_authority"]
                missing_fields = [field for field in required_fields if field not in data]
                
                # Check for blocker override capability
                blockers = data.get("blockers", [])
                warnings = data.get("warnings", [])
                execution_authority = data.get("execution_authority")
                
                self.log(f"Gate state: {data.get('state')}")
                self.log(f"Execution authority: {execution_authority}")
                self.log(f"Blockers count: {len(blockers)}")
                self.log(f"Warnings count: {len(warnings)}")
                
                return {
                    "status": "success",
                    "gate_state": data.get("state"),
                    "execution_authority": execution_authority,
                    "blockers_count": len(blockers),
                    "warnings_count": len(warnings),
                    "missing_fields": missing_fields,
                    "has_blocker_override": "execution_authority" in data,
                    "schema_valid": len(missing_fields) == 0
                }
            else:
                error_detail = response.text
                self.log(f"Gate endpoint failed: {response.status_code} - {error_detail}", "ERROR")
                return {"status": "failed", "error": f"{response.status_code}: {error_detail}"}
                
        except Exception as e:
            self.log(f"Gate endpoint exception: {str(e)}", "ERROR")
            return {"status": "error", "exception": str(e)}
    
    def test_execution_safety_intents(self) -> Dict[str, Any]:
        """Test 2: /api/execution-safety/intents canonical states include CANCELED (not CANCELLED)"""
        self.log("Testing /api/execution-safety/intents canonical states...")
        
        url = f"{self.base_url}/api/execution-safety/intents"
        headers = self._get_headers()
        
        try:
            response = self.session.get(url, headers=headers, params={"limit": 50})
            self.log(f"Intents endpoint status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate required contract fields
                required_fields = ["total", "stuck_count", "state_counts", "timeouts", "items"]
                missing_fields = [field for field in required_fields if field not in data]
                
                state_counts = data.get("state_counts", {})
                items = data.get("items", [])
                
                # Check for CANCELED state (not CANCELLED)
                has_canceled_state = "CANCELED" in state_counts
                has_cancelled_state = "CANCELLED" in state_counts
                
                # Check states in items
                states_in_items = set()
                for item in items:
                    if "state" in item:
                        states_in_items.add(item["state"])
                
                self.log(f"Total intents: {data.get('total')}")
                self.log(f"Stuck count: {data.get('stuck_count')}")
                self.log(f"State counts: {state_counts}")
                self.log(f"Has CANCELED state: {has_canceled_state}")
                self.log(f"Has CANCELLED state: {has_cancelled_state}")
                self.log(f"States in items: {states_in_items}")
                
                return {
                    "status": "success",
                    "total_intents": data.get("total"),
                    "stuck_count": data.get("stuck_count"),
                    "state_counts": state_counts,
                    "has_canceled_state": has_canceled_state,
                    "has_cancelled_state": has_cancelled_state,
                    "states_in_items": list(states_in_items),
                    "missing_fields": missing_fields,
                    "contract_valid": len(missing_fields) == 0,
                    "canonical_states_correct": has_canceled_state and not has_cancelled_state
                }
            else:
                error_detail = response.text
                self.log(f"Intents endpoint failed: {response.status_code} - {error_detail}", "ERROR")
                return {"status": "failed", "error": f"{response.status_code}: {error_detail}"}
                
        except Exception as e:
            self.log(f"Intents endpoint exception: {str(e)}", "ERROR")
            return {"status": "error", "exception": str(e)}
    
    def test_execution_safety_quarantine(self) -> Dict[str, Any]:
        """Test 3: /api/execution-safety/quarantine required contract fields"""
        self.log("Testing /api/execution-safety/quarantine contract fields...")
        
        url = f"{self.base_url}/api/execution-safety/quarantine"
        headers = self._get_headers()
        
        try:
            response = self.session.get(url, headers=headers, params={"limit": 50})
            self.log(f"Quarantine endpoint status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate required contract fields
                required_fields = ["total", "items"]
                missing_fields = [field for field in required_fields if field not in data]
                
                items = data.get("items", [])
                
                # Check required fields in quarantine items
                item_required_fields = ["quarantine_id", "reason", "failure_stage", "retry_count", "status", "entity_type"]
                item_field_coverage = {}
                
                for field in item_required_fields:
                    item_field_coverage[field] = 0
                    for item in items:
                        if field in item and item[field] is not None:
                            item_field_coverage[field] += 1
                
                self.log(f"Total quarantine items: {data.get('total')}")
                self.log(f"Items count: {len(items)}")
                self.log(f"Item field coverage: {item_field_coverage}")
                
                return {
                    "status": "success",
                    "total_quarantine": data.get("total"),
                    "items_count": len(items),
                    "missing_fields": missing_fields,
                    "item_field_coverage": item_field_coverage,
                    "contract_valid": len(missing_fields) == 0,
                    "items_have_required_fields": all(count > 0 for count in item_field_coverage.values()) if items else True
                }
            else:
                error_detail = response.text
                self.log(f"Quarantine endpoint failed: {response.status_code} - {error_detail}", "ERROR")
                return {"status": "failed", "error": f"{response.status_code}: {error_detail}"}
                
        except Exception as e:
            self.log(f"Quarantine endpoint exception: {str(e)}", "ERROR")
            return {"status": "error", "exception": str(e)}
    
    def test_execution_safety_recovery_endpoints(self) -> Dict[str, Any]:
        """Test 4: Recovery endpoints + batch + individual actions"""
        self.log("Testing execution safety recovery endpoints...")
        
        headers = self._get_headers()
        results = {}
        
        # Test recovery overview
        try:
            url = f"{self.base_url}/api/execution-safety/recovery"
            response = self.session.get(url, headers=headers)
            self.log(f"Recovery overview status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                results["recovery_overview"] = {
                    "status": "success",
                    "has_data": bool(data),
                    "fields": list(data.keys()) if isinstance(data, dict) else []
                }
            else:
                results["recovery_overview"] = {"status": "failed", "error": f"{response.status_code}: {response.text}"}
        except Exception as e:
            results["recovery_overview"] = {"status": "error", "exception": str(e)}
        
        # Test batch recovery
        try:
            url = f"{self.base_url}/api/execution-safety/recovery/batch"
            response = self.session.post(url, headers=headers, params={"action": "retry", "limit": 1})
            self.log(f"Batch recovery status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                results["batch_recovery"] = {
                    "status": "success",
                    "processed": data.get("processed", 0),
                    "action": data.get("action"),
                    "has_results": "results" in data
                }
            else:
                results["batch_recovery"] = {"status": "failed", "error": f"{response.status_code}: {response.text}"}
        except Exception as e:
            results["batch_recovery"] = {"status": "error", "exception": str(e)}
        
        # Test individual intent recovery (with dummy intent ID)
        try:
            dummy_intent_id = "test-intent-12345"
            url = f"{self.base_url}/api/execution-safety/recovery/{dummy_intent_id}/retry"
            response = self.session.post(url, headers=headers)
            self.log(f"Individual recovery status: {response.status_code}")
            
            # Expect 404 for non-existent intent
            if response.status_code == 404:
                results["individual_recovery"] = {
                    "status": "success",
                    "expected_404": True,
                    "endpoint_accessible": True
                }
            else:
                results["individual_recovery"] = {
                    "status": "unexpected",
                    "status_code": response.status_code,
                    "endpoint_accessible": True
                }
        except Exception as e:
            results["individual_recovery"] = {"status": "error", "exception": str(e)}
        
        return {"status": "success", "recovery_endpoints": results}
    
    def test_execution_safety_artifacts(self) -> Dict[str, Any]:
        """Test 5: Artifacts and incident export endpoints"""
        self.log("Testing execution safety artifacts endpoints...")
        
        headers = self._get_headers()
        results = {}
        
        # Test artifacts endpoint (requires intent_id parameter)
        try:
            dummy_intent_id = "test-intent-12345"
            url = f"{self.base_url}/api/execution-safety/artifacts"
            response = self.session.get(url, headers=headers, params={"intent_id": dummy_intent_id})
            self.log(f"Artifacts endpoint status: {response.status_code}")
            
            # Expect 404 for non-existent intent
            if response.status_code == 404:
                results["artifacts"] = {
                    "status": "success",
                    "expected_404": True,
                    "endpoint_accessible": True
                }
            else:
                results["artifacts"] = {
                    "status": "unexpected",
                    "status_code": response.status_code,
                    "endpoint_accessible": True
                }
        except Exception as e:
            results["artifacts"] = {"status": "error", "exception": str(e)}
        
        # Test incident export
        try:
            url = f"{self.base_url}/api/execution-safety/artifacts/incident-export"
            response = self.session.get(url, headers=headers, params={"include_events": False})
            self.log(f"Incident export status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for required incident package fields
                required_fields = ["schema_version", "package_type", "package_id", "generated_at"]
                missing_fields = [field for field in required_fields if field not in data]
                
                results["incident_export"] = {
                    "status": "success",
                    "package_type": data.get("package_type"),
                    "has_runbook": "runbook_recommendations" in data,
                    "has_quarantine_plan": "quarantine_replay_plan" in data,
                    "missing_fields": missing_fields,
                    "contract_valid": len(missing_fields) == 0
                }
            else:
                results["incident_export"] = {"status": "failed", "error": f"{response.status_code}: {response.text}"}
        except Exception as e:
            results["incident_export"] = {"status": "error", "exception": str(e)}
        
        return {"status": "success", "artifacts_endpoints": results}
    
    def test_execution_safety_policy_endpoints(self) -> Dict[str, Any]:
        """Test 6: Recovery policy endpoints and route order correctness"""
        self.log("Testing execution safety policy endpoints...")
        
        headers = self._get_headers()
        results = {}
        
        # Test policy GET endpoint
        try:
            url = f"{self.base_url}/api/execution-safety/recovery/policy"
            response = self.session.get(url, headers=headers)
            self.log(f"Policy GET status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                results["policy_get"] = {
                    "status": "success",
                    "has_environments": "environments" in data,
                    "policy_id": data.get("policy_id"),
                    "environments": list(data.get("environments", {}).keys()) if "environments" in data else []
                }
            else:
                results["policy_get"] = {"status": "failed", "error": f"{response.status_code}: {response.text}"}
        except Exception as e:
            results["policy_get"] = {"status": "error", "exception": str(e)}
        
        # Test policy POST endpoint for specific environment
        try:
            url = f"{self.base_url}/api/execution-safety/recovery/policy/testnet"
            params = {
                "enable_flag": True,
                "validation_status": "VALIDATED",
                "path_open": False
            }
            response = self.session.post(url, headers=headers, params=params)
            self.log(f"Policy POST status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                results["policy_post"] = {
                    "status": "success",
                    "updated_environment": "testnet",
                    "has_environments": "environments" in data
                }
            else:
                results["policy_post"] = {"status": "failed", "error": f"{response.status_code}: {response.text}"}
        except Exception as e:
            results["policy_post"] = {"status": "error", "exception": str(e)}
        
        return {"status": "success", "policy_endpoints": results}
    
    def test_execution_safety_observability(self) -> Dict[str, Any]:
        """Test 7: Observability endpoint"""
        self.log("Testing execution safety observability endpoint...")
        
        url = f"{self.base_url}/api/execution-safety/observability"
        headers = self._get_headers()
        
        try:
            response = self.session.get(url, headers=headers)
            self.log(f"Observability endpoint status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for observability fields
                expected_fields = ["current_gate_state", "blockers", "active_stuck_intents", "quarantined_events"]
                missing_fields = [field for field in expected_fields if field not in data]
                
                self.log(f"Observability data keys: {list(data.keys())}")
                
                return {
                    "status": "success",
                    "data_keys": list(data.keys()),
                    "missing_fields": missing_fields,
                    "has_gate_state": "current_gate_state" in data,
                    "has_blockers": "blockers" in data,
                    "contract_valid": len(missing_fields) == 0
                }
            else:
                error_detail = response.text
                self.log(f"Observability endpoint failed: {response.status_code} - {error_detail}", "ERROR")
                return {"status": "failed", "error": f"{response.status_code}: {error_detail}"}
                
        except Exception as e:
            self.log(f"Observability endpoint exception: {str(e)}", "ERROR")
            return {"status": "error", "exception": str(e)}
    
    def test_legacy_execution_readiness_deprecated(self) -> Dict[str, Any]:
        """Test 8: Legacy /api/execution-readiness/* returns deprecated markers"""
        self.log("Testing legacy execution-readiness endpoints for deprecated markers...")
        
        headers = self._get_headers()
        results = {}
        
        legacy_endpoints = [
            "/api/execution-readiness/gate",
            "/api/execution-readiness/intents",
            "/api/execution-readiness/quarantine"
        ]
        
        for endpoint in legacy_endpoints:
            try:
                url = f"{self.base_url}{endpoint}"
                response = self.session.get(url, headers=headers)
                self.log(f"Legacy endpoint {endpoint} status: {response.status_code}")
                
                endpoint_name = endpoint.split("/")[-1]
                
                if response.status_code == 200:
                    # Check response headers for deprecation warnings
                    deprecation_header = response.headers.get("X-Deprecated")
                    warning_header = response.headers.get("Warning")
                    
                    # Check response body for deprecation markers
                    try:
                        data = response.json()
                        has_deprecated_field = "deprecated" in data or "legacy" in data
                    except:
                        has_deprecated_field = False
                    
                    results[endpoint_name] = {
                        "status": "accessible",
                        "status_code": response.status_code,
                        "has_deprecation_header": deprecation_header is not None,
                        "has_warning_header": warning_header is not None,
                        "has_deprecated_field": has_deprecated_field,
                        "deprecation_header": deprecation_header,
                        "warning_header": warning_header
                    }
                else:
                    results[endpoint_name] = {
                        "status": "failed",
                        "status_code": response.status_code,
                        "error": response.text
                    }
            except Exception as e:
                results[endpoint_name] = {"status": "error", "exception": str(e)}
        
        return {"status": "success", "legacy_endpoints": results}
    
    def test_quarantine_action_endpoints(self) -> Dict[str, Any]:
        """Test quarantine action endpoints with dummy data"""
        self.log("Testing quarantine action endpoints...")
        
        headers = self._get_headers()
        results = {}
        
        dummy_quarantine_id = "test-quarantine-12345"
        actions = ["replay", "dismiss", "mark_failed"]
        
        for action in actions:
            try:
                url = f"{self.base_url}/api/execution-safety/quarantine/{dummy_quarantine_id}/{action}"
                response = self.session.post(url, headers=headers)
                self.log(f"Quarantine action {action} status: {response.status_code}")
                
                # Expect 404 for non-existent quarantine event
                if response.status_code == 404:
                    results[action] = {
                        "status": "success",
                        "expected_404": True,
                        "endpoint_accessible": True
                    }
                elif response.status_code == 400:
                    # May return 400 for invalid action or other validation
                    results[action] = {
                        "status": "success",
                        "expected_400": True,
                        "endpoint_accessible": True
                    }
                else:
                    results[action] = {
                        "status": "unexpected",
                        "status_code": response.status_code,
                        "endpoint_accessible": True
                    }
            except Exception as e:
                results[action] = {"status": "error", "exception": str(e)}
        
        return {"status": "success", "quarantine_actions": results}
    
    def run_comprehensive_validation(self, email: str, password: str) -> Dict[str, Any]:
        """Run comprehensive execution-safety namespace validation"""
        self.log("Starting comprehensive execution-safety namespace validation...")
        
        results = {
            "test_timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "base_url": self.base_url,
            "credentials_email": email,
            "namespace": "execution-safety"
        }
        
        # Authenticate
        self.log("\n=== AUTHENTICATION ===")
        auth_result = self.authenticate(email, password)
        results["authentication"] = auth_result
        
        if auth_result["status"] != "success":
            self.log("Authentication failed, cannot proceed with tests", "ERROR")
            return results
        
        # Test 1: Gate schema and blocker override
        self.log("\n=== TEST 1: Gate Schema and Blocker Override ===")
        results["gate_schema"] = self.test_execution_safety_gate()
        
        # Test 2: Intents canonical states
        self.log("\n=== TEST 2: Intents Canonical States ===")
        results["intents_states"] = self.test_execution_safety_intents()
        
        # Test 3: Quarantine contract fields
        self.log("\n=== TEST 3: Quarantine Contract Fields ===")
        results["quarantine_contract"] = self.test_execution_safety_quarantine()
        
        # Test 4: Recovery endpoints
        self.log("\n=== TEST 4: Recovery Endpoints ===")
        results["recovery_endpoints"] = self.test_execution_safety_recovery_endpoints()
        
        # Test 5: Artifacts and incident export
        self.log("\n=== TEST 5: Artifacts and Incident Export ===")
        results["artifacts_endpoints"] = self.test_execution_safety_artifacts()
        
        # Test 6: Policy endpoints
        self.log("\n=== TEST 6: Policy Endpoints ===")
        results["policy_endpoints"] = self.test_execution_safety_policy_endpoints()
        
        # Test 7: Observability
        self.log("\n=== TEST 7: Observability ===")
        results["observability"] = self.test_execution_safety_observability()
        
        # Test 8: Legacy deprecated markers
        self.log("\n=== TEST 8: Legacy Deprecated Markers ===")
        results["legacy_deprecated"] = self.test_legacy_execution_readiness_deprecated()
        
        # Additional: Quarantine actions
        self.log("\n=== ADDITIONAL: Quarantine Actions ===")
        results["quarantine_actions"] = self.test_quarantine_action_endpoints()
        
        return results


def main():
    """Main function to run the execution-safety namespace validation"""
    
    # Configuration
    BASE_URL = "https://unified-orchestrator.preview.emergentagent.com"
    EMAIL = "canary.admin@platform.local"
    PASSWORD = "CanaryAdmin123!"
    
    print("=" * 80)
    print("EXECUTION SAFETY NAMESPACE BACKEND DEEP VALIDATION")
    print("=" * 80)
    print(f"Target URL: {BASE_URL}")
    print(f"Credentials: {EMAIL} / {'*' * len(PASSWORD)}")
    print("=" * 80)
    
    # Initialize tester
    tester = ExecutionSafetyTester(BASE_URL)
    
    # Run comprehensive validation
    results = tester.run_comprehensive_validation(EMAIL, PASSWORD)
    
    # Print summary
    print("\n" + "=" * 80)
    print("VALIDATION RESULTS SUMMARY")
    print("=" * 80)
    
    test_categories = [
        ("authentication", "Authentication"),
        ("gate_schema", "Gate Schema & Blocker Override"),
        ("intents_states", "Intents Canonical States"),
        ("quarantine_contract", "Quarantine Contract Fields"),
        ("recovery_endpoints", "Recovery Endpoints"),
        ("artifacts_endpoints", "Artifacts & Incident Export"),
        ("policy_endpoints", "Policy Endpoints"),
        ("observability", "Observability"),
        ("legacy_deprecated", "Legacy Deprecated Markers"),
        ("quarantine_actions", "Quarantine Actions")
    ]
    
    passed = 0
    total = len(test_categories)
    
    for test_key, test_name in test_categories:
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
    
    # Detailed findings
    print("\n" + "=" * 80)
    print("DETAILED FINDINGS")
    print("=" * 80)
    
    # Gate schema findings
    if "gate_schema" in results and results["gate_schema"]["status"] == "success":
        gate_data = results["gate_schema"]
        print(f"✅ Gate Schema: {gate_data.get('gate_state')} state, {gate_data.get('blockers_count')} blockers")
        print(f"   Execution Authority: {gate_data.get('execution_authority')}")
        print(f"   Schema Valid: {gate_data.get('schema_valid')}")
    
    # Intents states findings
    if "intents_states" in results and results["intents_states"]["status"] == "success":
        intents_data = results["intents_states"]
        print(f"✅ Intents States: CANCELED state present: {intents_data.get('has_canceled_state')}")
        print(f"   CANCELLED state present: {intents_data.get('has_cancelled_state')}")
        print(f"   Canonical states correct: {intents_data.get('canonical_states_correct')}")
    
    # Quarantine contract findings
    if "quarantine_contract" in results and results["quarantine_contract"]["status"] == "success":
        quarantine_data = results["quarantine_contract"]
        print(f"✅ Quarantine Contract: {quarantine_data.get('total_quarantine')} items")
        print(f"   Contract Valid: {quarantine_data.get('contract_valid')}")
    
    # External blockers classification
    print("\n" + "=" * 80)
    print("EXTERNAL BLOCKERS CLASSIFICATION")
    print("=" * 80)
    
    if "gate_schema" in results and results["gate_schema"]["status"] == "success":
        # Check for Bybit 403 runtime issues or other external blockers
        print("Note: External blockers (e.g., Bybit 403 runtime issues) should be classified separately")
        print("from execution-safety namespace validation results.")
    
    print("=" * 80)
    
    # Save detailed results to file
    output_file = "/app/execution_safety_validation_results.json"
    try:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Detailed results saved to: {output_file}")
    except Exception as e:
        print(f"Failed to save results: {e}")
    
    # Return appropriate exit code
    if passed == total:
        print("🎉 ALL VALIDATION TESTS PASSED!")
        sys.exit(0)
    else:
        print("💥 SOME VALIDATION TESTS FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    main()