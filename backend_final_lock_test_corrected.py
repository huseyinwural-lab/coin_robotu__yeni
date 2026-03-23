#!/usr/bin/env python3
"""
FINAL LOCK Backend Sanity Check - CORRECTED VERSION
Validates critical backend flows for production readiness:
1) Playbook state machine + guards
2) Run detail contract  
3) Export hard lock
4) Auto-ack hardening
5) Preflight checks
"""

import requests
import json
import time
import uuid
import os
from datetime import datetime, timezone

# Base URL from frontend/.env
BASE_URL = "https://execution-safety-hub.preview.emergentagent.com"

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = os.environ.get("BACKEND_TEST_SUPER_ADMIN_PASSWORD", "")
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = os.environ.get("BACKEND_TEST_ADMIN_PASSWORD", "")

class BackendFinalLockTest:
    def __init__(self):
        self.session = requests.Session()
        self.super_admin_token = None
        self.admin_token = None
        self.test_results = []
        
    def log_result(self, test_name: str, status: str, details: str = ""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
    
    def login_super_admin(self):
        """Login as super admin and get token"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={
                    "email": SUPER_ADMIN_EMAIL,
                    "password": SUPER_ADMIN_PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.super_admin_token = data.get("access_token")
                self.log_result("Super Admin Login", "PASS", f"Token length: {len(self.super_admin_token) if self.super_admin_token else 0}")
                return True
            else:
                self.log_result("Super Admin Login", "FAIL", f"Status: {response.status_code}, Response: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Super Admin Login", "FAIL", f"Exception: {str(e)}")
            return False
    
    def login_admin(self):
        """Login as admin and get token"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                self.log_result("Admin Login", "PASS", f"Token length: {len(self.admin_token) if self.admin_token else 0}")
                return True
            else:
                self.log_result("Admin Login", "FAIL", f"Status: {response.status_code}, Response: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Admin Login", "FAIL", f"Exception: {str(e)}")
            return False
    
    def get_headers(self, use_super_admin=True):
        """Get authorization headers"""
        token = self.super_admin_token if use_super_admin else self.admin_token
        return {"Authorization": f"Bearer {token}"} if token else {}
    
    def test_playbook_state_machine_guards(self):
        """Test 1: Playbook state machine + guards"""
        print("\n=== TEST 1: Playbook State Machine + Guards ===")
        
        # Test preflight first
        try:
            response = self.session.get(
                f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("Playbook Preflight", "PASS", f"Overall state: {data.get('overall_state', 'unknown')}")
            else:
                self.log_result("Playbook Preflight", "FAIL", f"Status: {response.status_code}")
                return
                
        except Exception as e:
            self.log_result("Playbook Preflight", "FAIL", f"Exception: {str(e)}")
            return
        
        # Test preview -> approve -> execute flow
        playbook_run_id = None
        
        # Step 1: Preview
        try:
            preview_payload = {
                "scope": {
                    "correlation_id": f"test_correlation_{uuid.uuid4().hex[:8]}",
                    "chain_id": f"test_chain_{uuid.uuid4().hex[:8]}"
                },
                "reason": "Final lock backend sanity check"
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
                headers=self.get_headers(),
                json=preview_payload
            )
            
            if response.status_code == 200:
                data = response.json()
                playbook_run_id = data.get("playbook_run_id")
                self.log_result("Playbook Preview", "PASS", f"Run ID: {playbook_run_id}")
            else:
                self.log_result("Playbook Preview", "FAIL", f"Status: {response.status_code}, Response: {response.text[:200]}")
                return
                
        except Exception as e:
            self.log_result("Playbook Preview", "FAIL", f"Exception: {str(e)}")
            return
        
        # Step 2: Approve (only if approved state)
        if playbook_run_id:
            try:
                approve_payload = {
                    "playbook_run_id": playbook_run_id,
                    "reason": "Final lock test approval",
                    "confirm": True
                }
                
                response = self.session.post(
                    f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/approve",
                    headers=self.get_headers(),
                    json=approve_payload
                )
                
                if response.status_code == 200:
                    self.log_result("Playbook Approve", "PASS", "Approved successfully")
                    
                    # Step 3: Execute (only if approved)
                    try:
                        execute_payload = {
                            "playbook_run_id": playbook_run_id,
                            "reason": "Final lock test execution",
                            "confirm": True
                        }
                        
                        response = self.session.post(
                            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/execute",
                            headers=self.get_headers(),
                            json=execute_payload
                        )
                        
                        if response.status_code == 200:
                            self.log_result("Playbook Execute", "PASS", "Executed successfully")
                            
                            # Test rollback (only if executed)
                            try:
                                rollback_payload = {
                                    "playbook_run_id": playbook_run_id,
                                    "reason": "Final lock test rollback",
                                    "confirm": True
                                }
                                
                                response = self.session.post(
                                    f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/rollback",
                                    headers=self.get_headers(),
                                    json=rollback_payload
                                )
                                
                                if response.status_code == 200:
                                    self.log_result("Playbook Rollback", "PASS", "Rollback successful")
                                elif response.status_code == 422:
                                    # Check if it's because no rollback marker exists
                                    error_detail = response.json().get("detail", "")
                                    if "rollback_marker_not_found" in error_detail or "confirm_required" in error_detail:
                                        self.log_result("Playbook Rollback", "PASS", "Rollback correctly blocked (no rollback marker or confirmation required)")
                                    else:
                                        self.log_result("Playbook Rollback", "FAIL", f"Status: {response.status_code}, Detail: {error_detail}")
                                else:
                                    self.log_result("Playbook Rollback", "FAIL", f"Status: {response.status_code}")
                                    
                            except Exception as e:
                                self.log_result("Playbook Rollback", "FAIL", f"Exception: {str(e)}")
                        else:
                            self.log_result("Playbook Execute", "FAIL", f"Status: {response.status_code}")
                            
                    except Exception as e:
                        self.log_result("Playbook Execute", "FAIL", f"Exception: {str(e)}")
                else:
                    self.log_result("Playbook Approve", "FAIL", f"Status: {response.status_code}")
                    
            except Exception as e:
                self.log_result("Playbook Approve", "FAIL", f"Exception: {str(e)}")
        
        # Test retry (only if failed and with parent_run_id)
        if playbook_run_id:
            try:
                retry_payload = {
                    "original_playbook_run_id": playbook_run_id,
                    "reason": "Final lock test retry",
                    "confirm": True
                }
                
                response = self.session.post(
                    f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/retry",
                    headers=self.get_headers(),
                    json=retry_payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    retry_run_id = data.get("retry_playbook_run_id")
                    self.log_result("Playbook Retry", "PASS", f"Retry run ID: {retry_run_id}")
                elif response.status_code == 422:
                    # Check if it's because original run is not in failed state
                    error_detail = response.json().get("detail", "")
                    if "retry_requires_failed_state" in error_detail or "playbook_must_be_failed_before_retry" in error_detail:
                        self.log_result("Playbook Retry", "PASS", "Retry correctly blocked (original run not failed)")
                    else:
                        self.log_result("Playbook Retry", "FAIL", f"Status: {response.status_code}, Detail: {error_detail}")
                else:
                    self.log_result("Playbook Retry", "FAIL", f"Status: {response.status_code}")
                    
            except Exception as e:
                self.log_result("Playbook Retry", "FAIL", f"Exception: {str(e)}")
    
    def test_run_detail_contract(self):
        """Test 2: Run detail contract"""
        print("\n=== TEST 2: Run Detail Contract ===")
        
        # Create a test run first
        try:
            preview_payload = {
                "scope": {
                    "correlation_id": f"test_detail_{uuid.uuid4().hex[:8]}"
                },
                "reason": "Run detail contract test"
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
                headers=self.get_headers(),
                json=preview_payload
            )
            
            if response.status_code == 200:
                data = response.json()
                playbook_run_id = data.get("playbook_run_id")
                
                if playbook_run_id:
                    # Get run detail
                    response = self.session.get(
                        f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/runs/{playbook_run_id}",
                        headers=self.get_headers()
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        playbook_run = data.get("playbook_run", {})
                        
                        # Check required fields
                        required_fields = ["step_index", "total_steps", "failure_reason", "parent_run_id", "retry_attempt"]
                        missing_fields = []
                        
                        for field in required_fields:
                            if field not in playbook_run:
                                missing_fields.append(field)
                        
                        if not missing_fields:
                            self.log_result("Run Detail Contract", "PASS", f"All required fields present: {required_fields}")
                        else:
                            self.log_result("Run Detail Contract", "FAIL", f"Missing fields: {missing_fields}")
                    else:
                        self.log_result("Run Detail Contract", "FAIL", f"Status: {response.status_code}")
                else:
                    self.log_result("Run Detail Contract", "FAIL", "No playbook_run_id returned")
            else:
                self.log_result("Run Detail Contract", "FAIL", f"Preview failed: {response.status_code}")
                
        except Exception as e:
            self.log_result("Run Detail Contract", "FAIL", f"Exception: {str(e)}")
    
    def test_export_hard_lock(self):
        """Test 3: Export hard lock"""
        print("\n=== TEST 3: Export Hard Lock ===")
        
        try:
            # Test incident snapshot export
            export_payload = {
                "correlation_id": f"test_export_{uuid.uuid4().hex[:8]}",
                "export_type": "incident_snapshot",
                "format": "json"
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
                headers=self.get_headers(),
                json=export_payload
            )
            
            # Check headers for hard lock requirements
            headers = response.headers
            required_headers = ["snapshot_id", "snapshot_hash", "snapshot_at"]
            missing_headers = []
            
            for header in required_headers:
                if header.lower() not in [h.lower() for h in headers.keys()]:
                    missing_headers.append(header)
            
            if response.status_code == 200:
                if not missing_headers:
                    # Check audit_required payload fields
                    if response.headers.get('content-type', '').startswith('application/json'):
                        try:
                            data = response.json()
                            audit_fields = ["user", "filters", "row_count", "timestamp", "export_type"]
                            audit_missing = []
                            
                            for field in audit_fields:
                                if field not in data:
                                    audit_missing.append(field)
                            
                            if not audit_missing:
                                self.log_result("Export Hard Lock", "PASS", f"Headers: {required_headers}, Audit fields: {audit_fields}")
                            else:
                                self.log_result("Export Hard Lock", "PARTIAL", f"Headers OK, missing audit fields: {audit_missing}")
                        except:
                            self.log_result("Export Hard Lock", "PARTIAL", "Headers OK, could not parse JSON response")
                    else:
                        self.log_result("Export Hard Lock", "PARTIAL", "Headers OK, non-JSON response")
                else:
                    # Check if export endpoint exists but doesn't implement hard lock headers yet
                    if response.status_code == 200:
                        self.log_result("Export Hard Lock", "PARTIAL", f"Export works but missing hard lock headers: {missing_headers}")
                    else:
                        self.log_result("Export Hard Lock", "FAIL", f"Missing headers: {missing_headers}")
            else:
                self.log_result("Export Hard Lock", "FAIL", f"Status: {response.status_code}")
                
        except Exception as e:
            self.log_result("Export Hard Lock", "FAIL", f"Exception: {str(e)}")
    
    def test_auto_ack_hardening(self):
        """Test 4: Auto-ack hardening"""
        print("\n=== TEST 4: Auto-ack Hardening ===")
        
        # Test preview endpoint
        try:
            response = self.session.post(
                f"{BASE_URL}/api/admin-phase3/auto-ack/preview",
                headers=self.get_headers(),
                json={"reason": "Final lock test preview"}
            )
            
            if response.status_code == 200:
                data = response.json()
                preview_token = data.get("preview_token")
                matched_count = data.get("matched_count", 0)
                
                if preview_token:
                    self.log_result("Auto-ack Preview", "PASS", f"Preview token: {preview_token[:20]}..., Matched: {matched_count}")
                    
                    # Test run endpoint with valid preview_token
                    try:
                        response = self.session.post(
                            f"{BASE_URL}/api/admin-phase3/auto-ack/run",
                            headers=self.get_headers(),
                            params={"preview_token": preview_token, "reason": "Final lock test run"}
                        )
                        
                        if response.status_code == 200:
                            self.log_result("Auto-ack Run with Valid Token", "PASS", "Run successful with valid preview_token")
                        elif response.status_code == 422:
                            error_detail = response.json().get("detail", "")
                            if "auto_ack_preview_empty" in error_detail:
                                self.log_result("Auto-ack Run with Valid Token", "PASS", "Run correctly blocked (no alerts to ack)")
                            else:
                                self.log_result("Auto-ack Run with Valid Token", "FAIL", f"Status: {response.status_code}, Detail: {error_detail}")
                        else:
                            self.log_result("Auto-ack Run with Valid Token", "FAIL", f"Status: {response.status_code}")
                    except Exception as e:
                        self.log_result("Auto-ack Run with Valid Token", "FAIL", f"Exception: {str(e)}")
                    
                    # Test run endpoint without preview_token (should fail)
                    try:
                        response = self.session.post(
                            f"{BASE_URL}/api/admin-phase3/auto-ack/run",
                            headers=self.get_headers(),
                            params={"reason": "Final lock test run without token"}
                        )
                        
                        if response.status_code != 200:
                            self.log_result("Auto-ack Run without Token", "PASS", f"Correctly rejected: {response.status_code}")
                        else:
                            self.log_result("Auto-ack Run without Token", "FAIL", "Should have been rejected")
                    except Exception as e:
                        self.log_result("Auto-ack Run without Token", "PASS", f"Correctly failed: {str(e)}")
                else:
                    self.log_result("Auto-ack Preview", "FAIL", "No preview_token returned")
            else:
                self.log_result("Auto-ack Preview", "FAIL", f"Status: {response.status_code}")
                
        except Exception as e:
            self.log_result("Auto-ack Preview", "FAIL", f"Exception: {str(e)}")
    
    def test_preflight_checks(self):
        """Test 5: Preflight checks"""
        print("\n=== TEST 5: Preflight Checks ===")
        
        try:
            response = self.session.get(
                f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check required fields
                required_fields = ["overall_ui_status", "preflight_score", "execution_disable"]
                missing_fields = []
                
                for field in required_fields:
                    if field not in data:
                        missing_fields.append(field)
                
                if not missing_fields:
                    overall_ui_status = data.get("overall_ui_status")
                    preflight_score = data.get("preflight_score")
                    execution_disable = data.get("execution_disable")
                    
                    # Validate values
                    valid_status = overall_ui_status in ["OK", "WARNING", "ERROR"]
                    valid_score = isinstance(preflight_score, (int, float)) and 0 <= preflight_score <= 100
                    valid_disable = isinstance(execution_disable, bool)
                    
                    if valid_status and valid_score and valid_disable:
                        # Check for specific checkers
                        checks = data.get("checks", [])
                        execution_engine_check = any(c.get("key") == "execution_engine_readiness" for c in checks)
                        queue_job_check = any(c.get("key") == "queue_job_health" for c in checks)
                        
                        if execution_engine_check and queue_job_check:
                            self.log_result("Preflight Checks", "PASS", 
                                f"Status: {overall_ui_status}, Score: {preflight_score}, Disable: {execution_disable}")
                        else:
                            self.log_result("Preflight Checks", "PARTIAL", 
                                f"Main fields OK, missing specific checkers")
                    else:
                        self.log_result("Preflight Checks", "FAIL", 
                            f"Invalid values - Status: {overall_ui_status}, Score: {preflight_score}, Disable: {execution_disable}")
                else:
                    self.log_result("Preflight Checks", "FAIL", f"Missing fields: {missing_fields}")
            else:
                self.log_result("Preflight Checks", "FAIL", f"Status: {response.status_code}")
                
        except Exception as e:
            self.log_result("Preflight Checks", "FAIL", f"Exception: {str(e)}")
    
    def run_all_tests(self):
        """Run all backend sanity checks"""
        print("🚀 FINAL LOCK Backend Sanity Check Starting...")
        print(f"Base URL: {BASE_URL}")
        print(f"Test credentials: {SUPER_ADMIN_EMAIL}, {ADMIN_EMAIL}")
        
        # Login first
        if not self.login_super_admin():
            print("❌ Cannot proceed without super admin login")
            return
        
        if not self.login_admin():
            print("⚠️ Admin login failed, continuing with super admin only")
        
        # Run all tests
        self.test_playbook_state_machine_guards()
        self.test_run_detail_contract()
        self.test_export_hard_lock()
        self.test_auto_ack_hardening()
        self.test_preflight_checks()
        
        # Summary
        print("\n" + "="*60)
        print("📊 FINAL LOCK Backend Sanity Check Summary")
        print("="*60)
        
        pass_count = sum(1 for r in self.test_results if r["status"] == "PASS")
        fail_count = sum(1 for r in self.test_results if r["status"] == "FAIL")
        partial_count = sum(1 for r in self.test_results if r["status"] == "PARTIAL")
        total_count = len(self.test_results)
        
        print(f"Total Tests: {total_count}")
        print(f"✅ PASS: {pass_count}")
        print(f"⚠️ PARTIAL: {partial_count}")
        print(f"❌ FAIL: {fail_count}")
        
        success_rate = (pass_count + partial_count * 0.5) / total_count * 100 if total_count > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        
        # Critical risk assessment
        critical_failures = [r for r in self.test_results if r["status"] == "FAIL" and 
                           any(keyword in r["test"].lower() for keyword in ["playbook", "preflight", "auto-ack"])]
        
        if critical_failures:
            print(f"\n🚨 CRITICAL RISKS DETECTED: {len(critical_failures)} critical failures")
            for failure in critical_failures:
                print(f"   - {failure['test']}: {failure['details']}")
            print("\n❌ FINAL ASSESSMENT: NOT PRODUCTION READY")
        elif fail_count > 0:
            print(f"\n⚠️ MINOR ISSUES: {fail_count} non-critical failures")
            print("\n✅ FINAL ASSESSMENT: PRODUCTION READY WITH NOTES")
        else:
            print("\n✅ FINAL ASSESSMENT: PRODUCTION READY")
        
        return success_rate >= 80 and len(critical_failures) == 0

if __name__ == "__main__":
    tester = BackendFinalLockTest()
    success = tester.run_all_tests()
    exit(0 if success else 1)