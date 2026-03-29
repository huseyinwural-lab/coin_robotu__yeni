#!/usr/bin/env python3
"""
P1+P2 Readiness Hardening Backend Validation Test
Testing specific endpoints for futures live-readiness validation
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "https://unified-orchestrator.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class P1P2ReadinessHardeningTester:
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
                f"{BASE_URL}/api/auth/login",
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
                        f"Token received (length: {len(self.admin_token)} chars)"
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
    
    def test_futures_live_readiness(self):
        """Test 1: GET /api/admin/futures/live-readiness"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/admin/futures/live-readiness",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for required fields
                required_fields = [
                    "readiness_matrix",
                    "go_live_allowed", 
                    "execution_allowed"
                ]
                
                missing_fields = []
                for field in required_fields:
                    if field not in data:
                        missing_fields.append(field)
                
                # Check for nested validator fields
                has_nested_validators = False
                if "readiness_matrix" in data and isinstance(data["readiness_matrix"], dict):
                    for key, value in data["readiness_matrix"].items():
                        if isinstance(value, dict) and any(k.endswith("_validator") or "validator" in k for k in value.keys()):
                            has_nested_validators = True
                            break
                
                if missing_fields:
                    self.log_result(
                        "Futures Live Readiness (/api/admin/futures/live-readiness)", 
                        "FAIL", 
                        f"Missing required fields: {missing_fields}"
                    )
                elif not has_nested_validators:
                    self.log_result(
                        "Futures Live Readiness (/api/admin/futures/live-readiness)", 
                        "PARTIAL", 
                        "Required fields present but nested validator fields not detected"
                    )
                else:
                    # Check critical invariants
                    go_live_allowed = data.get("go_live_allowed", True)
                    execution_allowed = data.get("execution_allowed", True)
                    
                    # Look for UNKNOWN or FAIL states
                    has_blocking_issues = False
                    blocking_details = []
                    
                    if "readiness_matrix" in data:
                        matrix = data["readiness_matrix"]
                        for component, status in matrix.items():
                            if isinstance(status, dict):
                                for check, result in status.items():
                                    if result in ["UNKNOWN", "FAIL", "ERROR"]:
                                        has_blocking_issues = True
                                        blocking_details.append(f"{component}.{check}={result}")
                            elif status in ["UNKNOWN", "FAIL", "ERROR"]:
                                has_blocking_issues = True
                                blocking_details.append(f"{component}={status}")
                    
                    # Validate invariants
                    invariant_violations = []
                    if has_blocking_issues and (go_live_allowed or execution_allowed):
                        invariant_violations.append(f"Blocking issues detected ({blocking_details}) but go_live_allowed={go_live_allowed}, execution_allowed={execution_allowed}")
                    
                    if invariant_violations:
                        self.log_result(
                            "Futures Live Readiness (/api/admin/futures/live-readiness)", 
                            "FAIL", 
                            f"Invariant violations: {invariant_violations}"
                        )
                    else:
                        self.log_result(
                            "Futures Live Readiness (/api/admin/futures/live-readiness)", 
                            "PASS", 
                            f"All required fields present, nested validators detected, invariants valid. go_live_allowed={go_live_allowed}, execution_allowed={execution_allowed}"
                        )
            else:
                self.log_result(
                    "Futures Live Readiness (/api/admin/futures/live-readiness)", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "Futures Live Readiness (/api/admin/futures/live-readiness)", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_futures_readiness_history(self):
        """Test 2: GET /api/admin/futures/readiness/history?limit=20&days=14"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/admin/futures/readiness/history?limit=20&days=14",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for history analytics fields
                required_analytics = [
                    "top_blockers",
                    "failure_trend", 
                    "layer_failure_rate"
                ]
                
                missing_analytics = []
                for field in required_analytics:
                    if field not in data:
                        missing_analytics.append(field)
                
                if missing_analytics:
                    self.log_result(
                        "Futures Readiness History (/api/admin/futures/readiness/history)", 
                        "FAIL", 
                        f"Missing required analytics fields: {missing_analytics}"
                    )
                else:
                    # Validate structure
                    history_count = len(data.get("history", []))
                    self.log_result(
                        "Futures Readiness History (/api/admin/futures/readiness/history)", 
                        "PASS", 
                        f"All analytics fields present. History entries: {history_count}, top_blockers: {len(data.get('top_blockers', []))}, failure_trend points: {len(data.get('failure_trend', []))}"
                    )
            else:
                self.log_result(
                    "Futures Readiness History (/api/admin/futures/readiness/history)", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "Futures Readiness History (/api/admin/futures/readiness/history)", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_execution_readiness(self):
        """Test 3: GET /api/admin/execution-readiness"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/admin/execution-readiness",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for nested validator fields
                has_nested_validators = False
                validator_fields = []
                
                def check_nested_validators(obj, path=""):
                    nonlocal has_nested_validators, validator_fields
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            current_path = f"{path}.{key}" if path else key
                            if "validator" in key.lower() or key.endswith("_check") or key.endswith("_status"):
                                has_nested_validators = True
                                validator_fields.append(current_path)
                            if isinstance(value, (dict, list)):
                                check_nested_validators(value, current_path)
                    elif isinstance(obj, list):
                        for i, item in enumerate(obj):
                            check_nested_validators(item, f"{path}[{i}]")
                
                check_nested_validators(data)
                
                # Check for strategy_engine heartbeat validation
                strategy_engine_status = None
                heartbeat_status = None
                
                def find_strategy_engine_status(obj, path=""):
                    nonlocal strategy_engine_status, heartbeat_status
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            if "strategy_engine" in key.lower():
                                if isinstance(value, dict):
                                    for sub_key, sub_value in value.items():
                                        if "heartbeat" in sub_key.lower():
                                            heartbeat_status = sub_value
                                        if "status" in sub_key.lower():
                                            strategy_engine_status = sub_value
                                else:
                                    strategy_engine_status = value
                            elif "heartbeat" in key.lower() and "strategy" in str(obj).lower():
                                heartbeat_status = value
                            if isinstance(value, (dict, list)):
                                find_strategy_engine_status(value, f"{path}.{key}" if path else key)
                    elif isinstance(obj, list):
                        for item in obj:
                            find_strategy_engine_status(item, path)
                
                find_strategy_engine_status(data)
                
                # Validate critical invariants for strategy_engine
                strategy_engine_violations = []
                if strategy_engine_status == "PASS" and heartbeat_status in ["missing", "stale", "error", "MISSING", "STALE", "ERROR"]:
                    strategy_engine_violations.append(f"strategy_engine status is PASS but heartbeat is {heartbeat_status}")
                
                if not has_nested_validators:
                    self.log_result(
                        "Execution Readiness (/api/admin/execution-readiness)", 
                        "FAIL", 
                        "No nested validator fields detected in response"
                    )
                elif strategy_engine_violations:
                    self.log_result(
                        "Execution Readiness (/api/admin/execution-readiness)", 
                        "FAIL", 
                        f"Strategy engine invariant violations: {strategy_engine_violations}"
                    )
                else:
                    self.log_result(
                        "Execution Readiness (/api/admin/execution-readiness)", 
                        "PASS", 
                        f"Nested validator fields detected: {len(validator_fields)} fields. Strategy engine status: {strategy_engine_status}, heartbeat: {heartbeat_status}"
                    )
            else:
                self.log_result(
                    "Execution Readiness (/api/admin/execution-readiness)", 
                    "FAIL", 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result(
                "Execution Readiness (/api/admin/execution-readiness)", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def test_frontend_smoke(self):
        """Test 4: Frontend smoke test for /admin/futures/live-readiness"""
        try:
            # Test if the frontend URL is accessible
            frontend_url = BASE_URL.replace("/api", "")
            response = self.session.get(
                f"{frontend_url}/admin/futures/live-readiness",
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.text
                
                # Check for blank screen indicators
                is_blank = len(content.strip()) < 100 or "blank" in content.lower()
                
                # Check for expected UI elements (basic HTML structure)
                has_html_structure = "<html" in content and "<body" in content
                has_admin_content = "admin" in content.lower() or "readiness" in content.lower()
                
                if is_blank:
                    self.log_result(
                        "Frontend Smoke Test (/admin/futures/live-readiness)", 
                        "FAIL", 
                        f"Page appears blank (content length: {len(content)} chars)"
                    )
                elif not has_html_structure:
                    self.log_result(
                        "Frontend Smoke Test (/admin/futures/live-readiness)", 
                        "FAIL", 
                        "No proper HTML structure detected"
                    )
                else:
                    self.log_result(
                        "Frontend Smoke Test (/admin/futures/live-readiness)", 
                        "PASS", 
                        f"Page loads without blank screen (content length: {len(content)} chars, has admin content: {has_admin_content})"
                    )
            else:
                self.log_result(
                    "Frontend Smoke Test (/admin/futures/live-readiness)", 
                    "FAIL", 
                    f"HTTP {response.status_code}: Frontend not accessible"
                )
        except Exception as e:
            self.log_result(
                "Frontend Smoke Test (/admin/futures/live-readiness)", 
                "FAIL", 
                f"Exception: {str(e)}"
            )
    
    def run_all_tests(self):
        """Run all P1+P2 readiness hardening tests"""
        print("=" * 80)
        print("P1+P2 Readiness Hardening Backend Validation Test")
        print(f"Target: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print("=" * 80)
        
        # Test admin authentication first
        if not self.test_admin_login():
            print("\n❌ CRITICAL: Admin login failed. Cannot proceed with authenticated tests.")
            return
        
        print("\n" + "-" * 60)
        print("Testing P1+P2 Readiness Endpoints...")
        print("-" * 60)
        
        # Test backend API contracts
        self.test_futures_live_readiness()
        self.test_futures_readiness_history()
        self.test_execution_readiness()
        
        # Test frontend smoke
        self.test_frontend_smoke()
        
        # Summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("P1+P2 READINESS HARDENING TEST SUMMARY")
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
        
        # Overall assessment
        if fail_count == 0:
            if partial_count == 0:
                print(f"\n🎯 OVERALL: ✅ PASS - All P1+P2 readiness hardening requirements validated successfully")
            else:
                print(f"\n🎯 OVERALL: ⚠️ PARTIAL PASS - Core functionality working, {partial_count} partial results")
        else:
            print(f"\n🎯 OVERALL: ❌ FAIL - {fail_count} critical requirement(s) failed")
        
        print("\nKEY VALIDATIONS:")
        print("1. Backend API contracts: nested validator fields, readiness_matrix, history analytics")
        print("2. Critical invariants: UNKNOWN/FAIL blocking steps, strategy_engine heartbeat validation")
        print("3. Frontend smoke: /admin/futures/live-readiness page accessibility")

if __name__ == "__main__":
    tester = P1P2ReadinessHardeningTester()
    tester.run_all_tests()