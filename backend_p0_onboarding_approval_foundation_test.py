#!/usr/bin/env python3
"""
P0 Onboarding+Approval Foundation Backend Regression Test

Test cases:
1) GET /api/admin/onboarding/{user_id}/context -> KYC/AML/risk + precheck + decision_engine fields present?
2) Hard block: KYC/AML/risk completion before approve attempt should reject
3) KYC lifecycle: upload (pdf/jpg/png) + review -> kyc_status updates?
4) Risk foundation update -> decision engine thresholds working (<35 auto_approve, >=35 manual review)?
5) Decision reason mandatory? confirm token mandatory?
6) Immutable decision log append-only: new log added after decision?
7) Bulk approve disabled?
8) /api/admin/audit/export working?
9) /api/ready status PASS?

Target: https://dry-run-shadow.preview.emergentagent.com
Admin credentials: canary.admin@platform.local / CanaryAdmin123!
"""

import requests
import json
import io
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

# Configuration
BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class P0OnboardingApprovalFoundationTest:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.test_results: List[Tuple[str, bool, str]] = []
        
    def log_result(self, test_name: str, passed: bool, evidence: str):
        """Log test result with evidence"""
        status = "PASS" if passed else "FAIL"
        self.test_results.append((test_name, passed, evidence))
        print(f"[{status}] {test_name}: {evidence}")
        
    def authenticate_admin(self) -> bool:
        """Authenticate as admin and get token"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
                    return True
            
            return False
        except Exception as e:
            print(f"Admin authentication failed: {e}")
            return False
    
    def create_test_user(self) -> str:
        """Create a test user for onboarding tests"""
        try:
            timestamp = int(time.time())
            test_email = f"onboarding_test_{timestamp}@example.com"
            
            # Register user
            response = self.session.post(
                f"{BASE_URL}/api/auth/register",
                json={
                    "email": test_email,
                    "password": "TestPassword123!",
                    "first_name": "Test",
                    "last_name": "User"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                # Get user ID by searching users
                users_response = self.session.get(f"{BASE_URL}/api/admin/users", timeout=30)
                if users_response.status_code == 200:
                    users = users_response.json()
                    for user in users:
                        if user.get("email") == test_email:
                            return user.get("id")
            
            return None
        except Exception as e:
            print(f"Failed to create test user: {e}")
            return None
    
    def test_1_onboarding_context_fields(self) -> bool:
        """Test 1: GET /api/admin/onboarding/{user_id}/context -> KYC/AML/risk + precheck + decision_engine fields present?"""
        try:
            user_id = self.create_test_user()
            if not user_id:
                self.log_result("T1-Context-Fields", False, "Failed to create test user")
                return False
            
            response = self.session.get(f"{BASE_URL}/api/admin/onboarding/{user_id}/context", timeout=30)
            
            if response.status_code != 200:
                self.log_result("T1-Context-Fields", False, f"HTTP {response.status_code}")
                return False
            
            data = response.json()
            
            # Check required fields
            required_fields = [
                # KYC fields
                "kyc_status", "kyc_documents",
                # AML fields  
                "aml_flag", "aml_reason",
                # Risk fields
                "risk_score", "risk_flags",
                # Precheck fields
                "trading_eligibility", "approval_disabled", "approval_disable_reasons",
                # Decision engine fields
                "decision_engine"
            ]
            
            missing_fields = []
            for field in required_fields:
                if field not in data:
                    missing_fields.append(field)
            
            if missing_fields:
                self.log_result("T1-Context-Fields", False, f"Missing fields: {missing_fields}")
                return False
            
            # Check decision_engine structure
            decision_engine = data.get("decision_engine", {})
            required_engine_fields = ["recommended_action", "auto_approve", "why_approving"]
            missing_engine_fields = [f for f in required_engine_fields if f not in decision_engine]
            
            if missing_engine_fields:
                self.log_result("T1-Context-Fields", False, f"Missing decision_engine fields: {missing_engine_fields}")
                return False
            
            self.log_result("T1-Context-Fields", True, f"All required fields present. Decision engine: {decision_engine.get('recommended_action')}")
            return True
            
        except Exception as e:
            self.log_result("T1-Context-Fields", False, f"Exception: {str(e)}")
            return False
    
    def test_2_hard_block_incomplete_kyc_aml(self) -> bool:
        """Test 2: Hard block: KYC/AML/risk completion before approve attempt should reject"""
        try:
            user_id = self.create_test_user()
            if not user_id:
                self.log_result("T2-Hard-Block", False, "Failed to create test user")
                return False
            
            # Try to approve without completing KYC/AML/risk
            response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/decision",
                json={
                    "decision": "approve",
                    "reason": "Test approval attempt without KYC/AML completion",
                    "confirm_token": "CONFIRM"
                },
                timeout=30
            )
            
            # Should be rejected (409 Conflict or 400 Bad Request)
            if response.status_code in [409, 400]:
                error_data = response.json()
                if "approval_disabled" in str(error_data) or "reasons" in error_data:
                    self.log_result("T2-Hard-Block", True, f"Correctly rejected: HTTP {response.status_code}, {error_data}")
                    return True
            
            self.log_result("T2-Hard-Block", False, f"Should have been rejected but got HTTP {response.status_code}")
            return False
            
        except Exception as e:
            self.log_result("T2-Hard-Block", False, f"Exception: {str(e)}")
            return False
    
    def test_3_kyc_lifecycle_upload_review(self) -> bool:
        """Test 3: KYC lifecycle: upload (pdf/jpg/png) + review -> kyc_status updates?"""
        try:
            user_id = self.create_test_user()
            if not user_id:
                self.log_result("T3-KYC-Lifecycle", False, "Failed to create test user")
                return False
            
            # Create a dummy PDF file
            pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000074 00000 n \n0000000120 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n179\n%%EOF"
            
            # Upload KYC document
            files = {"file": ("test_kyc.pdf", io.BytesIO(pdf_content), "application/pdf")}
            upload_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/kyc-documents",
                files=files,
                timeout=30
            )
            
            if upload_response.status_code != 200:
                self.log_result("T3-KYC-Lifecycle", False, f"Upload failed: HTTP {upload_response.status_code}")
                return False
            
            upload_data = upload_response.json()
            document_id = upload_data.get("document_id")
            
            if not document_id:
                self.log_result("T3-KYC-Lifecycle", False, "No document_id returned from upload")
                return False
            
            # Review the document (approve it)
            review_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/kyc-documents/{document_id}/review",
                json={
                    "review_status": "approved",
                    "review_note": "Test document approved for regression testing"
                },
                timeout=30
            )
            
            if review_response.status_code != 200:
                self.log_result("T3-KYC-Lifecycle", False, f"Review failed: HTTP {review_response.status_code}")
                return False
            
            review_data = review_response.json()
            kyc_status = review_data.get("kyc_status")
            
            if kyc_status == "verified":
                self.log_result("T3-KYC-Lifecycle", True, f"KYC status updated to 'verified' after document approval")
                return True
            else:
                self.log_result("T3-KYC-Lifecycle", False, f"KYC status is '{kyc_status}', expected 'verified'")
                return False
            
        except Exception as e:
            self.log_result("T3-KYC-Lifecycle", False, f"Exception: {str(e)}")
            return False
    
    def test_4_risk_foundation_decision_engine_thresholds(self) -> bool:
        """Test 4: Risk foundation update -> decision engine thresholds working (<35 auto_approve, >=35 manual review)?"""
        try:
            user_id = self.create_test_user()
            if not user_id:
                self.log_result("T4-Risk-Thresholds", False, "Failed to create test user")
                return False
            
            # Test case 1: Risk score < 35 should trigger auto_approve
            low_risk_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/risk-foundation",
                json={
                    "risk_score": 25.0,
                    "aml_flag": "clear",
                    "api_key_validity": "valid",
                    "balance_usd": 1000.0,
                    "country_code": "US",
                    "leverage_permission": True,
                    "futures_capability": True,
                    "spot_capability": True
                },
                timeout=30
            )
            
            if low_risk_response.status_code != 200:
                self.log_result("T4-Risk-Thresholds", False, f"Low risk update failed: HTTP {low_risk_response.status_code}")
                return False
            
            low_risk_data = low_risk_response.json()
            low_risk_engine = low_risk_data.get("decision_engine", {})
            
            if not low_risk_engine.get("auto_approve"):
                self.log_result("T4-Risk-Thresholds", False, f"Risk score 25 should auto_approve but got: {low_risk_engine}")
                return False
            
            # Test case 2: Risk score >= 35 should trigger manual review
            high_risk_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/risk-foundation",
                json={
                    "risk_score": 45.0,
                    "aml_flag": "clear",
                    "api_key_validity": "valid",
                    "balance_usd": 1000.0,
                    "country_code": "US",
                    "leverage_permission": True,
                    "futures_capability": True,
                    "spot_capability": True
                },
                timeout=30
            )
            
            if high_risk_response.status_code != 200:
                self.log_result("T4-Risk-Thresholds", False, f"High risk update failed: HTTP {high_risk_response.status_code}")
                return False
            
            high_risk_data = high_risk_response.json()
            high_risk_engine = high_risk_data.get("decision_engine", {})
            
            if high_risk_engine.get("auto_approve"):
                self.log_result("T4-Risk-Thresholds", False, f"Risk score 45 should NOT auto_approve but got: {high_risk_engine}")
                return False
            
            self.log_result("T4-Risk-Thresholds", True, f"Thresholds working: <35 auto_approve={low_risk_engine.get('auto_approve')}, >=35 auto_approve={high_risk_engine.get('auto_approve')}")
            return True
            
        except Exception as e:
            self.log_result("T4-Risk-Thresholds", False, f"Exception: {str(e)}")
            return False
    
    def test_5_decision_reason_confirm_token_mandatory(self) -> bool:
        """Test 5: Decision reason mandatory? confirm token mandatory?"""
        try:
            user_id = self.create_test_user()
            if not user_id:
                self.log_result("T5-Mandatory-Fields", False, "Failed to create test user")
                return False
            
            # Test 1: Missing reason should fail
            no_reason_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/decision",
                json={
                    "decision": "approve",
                    "reason": "",  # Empty reason
                    "confirm_token": "CONFIRM"
                },
                timeout=30
            )
            
            if no_reason_response.status_code != 400:
                self.log_result("T5-Mandatory-Fields", False, f"Empty reason should fail but got HTTP {no_reason_response.status_code}")
                return False
            
            # Test 2: Missing confirm token should fail
            no_token_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/decision",
                json={
                    "decision": "approve",
                    "reason": "Valid reason for testing",
                    "confirm_token": ""  # Empty token
                },
                timeout=30
            )
            
            if no_token_response.status_code != 400:
                self.log_result("T5-Mandatory-Fields", False, f"Empty confirm_token should fail but got HTTP {no_token_response.status_code}")
                return False
            
            # Test 3: Wrong confirm token should fail
            wrong_token_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/decision",
                json={
                    "decision": "approve",
                    "reason": "Valid reason for testing",
                    "confirm_token": "WRONG"  # Wrong token
                },
                timeout=30
            )
            
            if wrong_token_response.status_code != 400:
                self.log_result("T5-Mandatory-Fields", False, f"Wrong confirm_token should fail but got HTTP {wrong_token_response.status_code}")
                return False
            
            self.log_result("T5-Mandatory-Fields", True, "Reason and confirm_token validation working correctly")
            return True
            
        except Exception as e:
            self.log_result("T5-Mandatory-Fields", False, f"Exception: {str(e)}")
            return False
    
    def test_6_immutable_decision_log_append_only(self) -> bool:
        """Test 6: Immutable decision log append-only: new log added after decision?"""
        try:
            user_id = self.create_test_user()
            if not user_id:
                self.log_result("T6-Decision-Log", False, "Failed to create test user")
                return False
            
            # Set up user for approval (complete KYC/AML/risk)
            # Upload and approve KYC document
            pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000074 00000 n \n0000000120 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n179\n%%EOF"
            files = {"file": ("test_kyc.pdf", io.BytesIO(pdf_content), "application/pdf")}
            upload_response = self.session.post(f"{BASE_URL}/api/admin/onboarding/{user_id}/kyc-documents", files=files, timeout=30)
            
            if upload_response.status_code == 200:
                upload_data = upload_response.json()
                document_id = upload_data.get("document_id")
                if document_id:
                    self.session.post(
                        f"{BASE_URL}/api/admin/onboarding/{user_id}/kyc-documents/{document_id}/review",
                        json={"review_status": "approved", "review_note": "Test approval"},
                        timeout=30
                    )
            
            # Update risk foundation
            self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/risk-foundation",
                json={
                    "risk_score": 25.0,
                    "aml_flag": "clear",
                    "api_key_validity": "valid",
                    "balance_usd": 1000.0,
                    "country_code": "US",
                    "leverage_permission": True,
                    "futures_capability": True,
                    "spot_capability": True
                },
                timeout=30
            )
            
            # Get initial audit export to count existing logs
            initial_export_response = self.session.get(f"{BASE_URL}/api/admin/audit/export", timeout=30)
            if initial_export_response.status_code != 200:
                self.log_result("T6-Decision-Log", False, f"Initial audit export failed: HTTP {initial_export_response.status_code}")
                return False
            
            initial_csv = initial_export_response.text
            initial_log_count = len(initial_csv.split('\n')) - 1  # Subtract header row
            
            # Make a decision
            decision_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/decision",
                json={
                    "decision": "approve",
                    "reason": "Test decision for log verification",
                    "confirm_token": "CONFIRM"
                },
                timeout=30
            )
            
            if decision_response.status_code != 200:
                self.log_result("T6-Decision-Log", False, f"Decision failed: HTTP {decision_response.status_code}")
                return False
            
            decision_data = decision_response.json()
            decision_log_id = decision_data.get("decision_log_id")
            
            if not decision_log_id:
                self.log_result("T6-Decision-Log", False, "No decision_log_id returned")
                return False
            
            # Get updated audit export to verify new log was added
            time.sleep(1)  # Brief delay to ensure log is written
            updated_export_response = self.session.get(f"{BASE_URL}/api/admin/audit/export", timeout=30)
            if updated_export_response.status_code != 200:
                self.log_result("T6-Decision-Log", False, f"Updated audit export failed: HTTP {updated_export_response.status_code}")
                return False
            
            updated_csv = updated_export_response.text
            updated_log_count = len(updated_csv.split('\n')) - 1  # Subtract header row
            
            if updated_log_count > initial_log_count:
                # Verify the new log contains our decision
                if decision_log_id in updated_csv:
                    self.log_result("T6-Decision-Log", True, f"New decision log appended: {decision_log_id}, count increased from {initial_log_count} to {updated_log_count}")
                    return True
                else:
                    self.log_result("T6-Decision-Log", False, f"Log count increased but decision_log_id {decision_log_id} not found in export")
                    return False
            else:
                self.log_result("T6-Decision-Log", False, f"Log count did not increase: {initial_log_count} -> {updated_log_count}")
                return False
            
        except Exception as e:
            self.log_result("T6-Decision-Log", False, f"Exception: {str(e)}")
            return False
    
    def test_7_bulk_approve_disabled(self) -> bool:
        """Test 7: Bulk approve disabled?"""
        try:
            # Check if bulk approve endpoint exists and is disabled
            # This would typically be a POST to /api/admin/onboarding/bulk-approve or similar
            
            # Try common bulk approve endpoint patterns
            bulk_endpoints = [
                "/api/admin/onboarding/bulk-approve",
                "/api/admin/onboarding/bulk/approve",
                "/api/admin/user-approvals/bulk-approve"
            ]
            
            for endpoint in bulk_endpoints:
                response = self.session.post(
                    f"{BASE_URL}{endpoint}",
                    json={"user_ids": ["test-user-id"], "reason": "test", "confirm_token": "CONFIRM"},
                    timeout=30
                )
                
                # If endpoint exists but returns 404/405, it's disabled
                if response.status_code in [404, 405]:
                    self.log_result("T7-Bulk-Disabled", True, f"Bulk approve endpoint {endpoint} disabled: HTTP {response.status_code}")
                    return True
                elif response.status_code == 200:
                    self.log_result("T7-Bulk-Disabled", False, f"Bulk approve endpoint {endpoint} is enabled: HTTP {response.status_code}")
                    return False
            
            # If no bulk endpoints found, assume bulk approve is disabled
            self.log_result("T7-Bulk-Disabled", True, "No bulk approve endpoints found - bulk approve disabled")
            return True
            
        except Exception as e:
            self.log_result("T7-Bulk-Disabled", False, f"Exception: {str(e)}")
            return False
    
    def test_8_audit_export_working(self) -> bool:
        """Test 8: /api/admin/audit/export working?"""
        try:
            response = self.session.get(f"{BASE_URL}/api/admin/audit/export", timeout=30)
            
            if response.status_code != 200:
                self.log_result("T8-Audit-Export", False, f"HTTP {response.status_code}")
                return False
            
            # Check content type
            content_type = response.headers.get("content-type", "")
            if "text/csv" not in content_type:
                self.log_result("T8-Audit-Export", False, f"Wrong content-type: {content_type}")
                return False
            
            # Check CSV content
            csv_content = response.text
            if not csv_content or len(csv_content.split('\n')) < 2:
                self.log_result("T8-Audit-Export", False, "Empty or invalid CSV content")
                return False
            
            # Check CSV headers
            headers = csv_content.split('\n')[0]
            required_headers = ["log_id", "user_id", "decision", "actor_user_id", "created_at"]
            missing_headers = [h for h in required_headers if h not in headers]
            
            if missing_headers:
                self.log_result("T8-Audit-Export", False, f"Missing CSV headers: {missing_headers}")
                return False
            
            self.log_result("T8-Audit-Export", True, f"CSV export working, content-type: {content_type}, rows: {len(csv_content.split(chr(10))) - 1}")
            return True
            
        except Exception as e:
            self.log_result("T8-Audit-Export", False, f"Exception: {str(e)}")
            return False
    
    def test_9_ready_status_pass(self) -> bool:
        """Test 9: /api/ready status PASS?"""
        try:
            response = self.session.get(f"{BASE_URL}/api/ready", timeout=30)
            
            if response.status_code != 200:
                self.log_result("T9-Ready-Status", False, f"HTTP {response.status_code}")
                return False
            
            data = response.json()
            status = data.get("status")
            
            if status != "ready":
                self.log_result("T9-Ready-Status", False, f"Status is '{status}', expected 'ready'")
                return False
            
            # Check if preview_smoke_gate is passing
            checks = data.get("checks", {})
            preview_gate = checks.get("preview_smoke_gate", {})
            gate_status = preview_gate.get("gate_status")
            
            if gate_status != "pass":
                self.log_result("T9-Ready-Status", False, f"preview_smoke_gate status is '{gate_status}', expected 'pass'")
                return False
            
            self.log_result("T9-Ready-Status", True, f"Ready status PASS, preview_smoke_gate: {gate_status}")
            return True
            
        except Exception as e:
            self.log_result("T9-Ready-Status", False, f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all P0 onboarding+approval foundation tests"""
        print("=" * 80)
        print("P0 ONBOARDING+APPROVAL FOUNDATION BACKEND REGRESSION TEST")
        print(f"Target: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print("=" * 80)
        
        # Authenticate
        if not self.authenticate_admin():
            print("❌ CRITICAL: Admin authentication failed")
            return
        
        print("✅ Admin authentication successful")
        print()
        
        # Run all tests
        tests = [
            ("T1-Context-Fields", self.test_1_onboarding_context_fields),
            ("T2-Hard-Block", self.test_2_hard_block_incomplete_kyc_aml),
            ("T3-KYC-Lifecycle", self.test_3_kyc_lifecycle_upload_review),
            ("T4-Risk-Thresholds", self.test_4_risk_foundation_decision_engine_thresholds),
            ("T5-Mandatory-Fields", self.test_5_decision_reason_confirm_token_mandatory),
            ("T6-Decision-Log", self.test_6_immutable_decision_log_append_only),
            ("T7-Bulk-Disabled", self.test_7_bulk_approve_disabled),
            ("T8-Audit-Export", self.test_8_audit_export_working),
            ("T9-Ready-Status", self.test_9_ready_status_pass),
        ]
        
        for test_name, test_func in tests:
            try:
                test_func()
            except Exception as e:
                self.log_result(test_name, False, f"Test execution failed: {str(e)}")
            print()
        
        # Summary
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        passed = sum(1 for _, passed, _ in self.test_results if passed)
        total = len(self.test_results)
        
        for test_name, passed, evidence in self.test_results:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} {test_name}: {evidence}")
        
        print()
        print(f"OVERALL RESULT: {passed}/{total} PASS ({passed/total*100:.1f}% SUCCESS RATE)")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED - P0 onboarding+approval foundation is working correctly")
        else:
            print("⚠️  SOME TESTS FAILED - P0 onboarding+approval foundation needs attention")

if __name__ == "__main__":
    test_runner = P0OnboardingApprovalFoundationTest()
    test_runner.run_all_tests()