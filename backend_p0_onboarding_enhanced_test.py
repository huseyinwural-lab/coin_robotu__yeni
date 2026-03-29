#!/usr/bin/env python3
"""
P0 Onboarding+Approval Foundation Backend Regression Test - Enhanced Version

This version properly sets up all required conditions for testing the decision engine thresholds.
"""

import requests
import json
import io
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

# Configuration
BASE_URL = "https://unified-orchestrator.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class P0OnboardingApprovalFoundationTestEnhanced:
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
    
    def setup_complete_user_profile(self, user_id: str, risk_score: float) -> bool:
        """Set up a complete user profile with KYC, AML, and risk foundation"""
        try:
            # 1. Upload and approve KYC document
            pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000074 00000 n \n0000000120 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n179\n%%EOF"
            files = {"file": ("test_kyc.pdf", io.BytesIO(pdf_content), "application/pdf")}
            upload_response = self.session.post(f"{BASE_URL}/api/admin/onboarding/{user_id}/kyc-documents", files=files, timeout=30)
            
            if upload_response.status_code == 200:
                upload_data = upload_response.json()
                document_id = upload_data.get("document_id")
                if document_id:
                    review_response = self.session.post(
                        f"{BASE_URL}/api/admin/onboarding/{user_id}/kyc-documents/{document_id}/review",
                        json={"review_status": "approved", "review_note": "Test document approved"},
                        timeout=30
                    )
                    if review_response.status_code != 200:
                        return False
            else:
                return False
            
            # 2. Update risk foundation with all required fields
            risk_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/risk-foundation",
                json={
                    "risk_score": risk_score,
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
            
            return risk_response.status_code == 200
            
        except Exception as e:
            print(f"Failed to setup complete user profile: {e}")
            return False
    
    def test_4_risk_foundation_decision_engine_thresholds_enhanced(self) -> bool:
        """Test 4 Enhanced: Risk foundation update -> decision engine thresholds working (<35 auto_approve, >=35 manual review)?"""
        try:
            # Test case 1: Risk score < 35 should trigger auto_approve
            user_id_low = self.create_test_user()
            if not user_id_low:
                self.log_result("T4-Risk-Thresholds-Enhanced", False, "Failed to create test user for low risk")
                return False
            
            if not self.setup_complete_user_profile(user_id_low, 25.0):
                self.log_result("T4-Risk-Thresholds-Enhanced", False, "Failed to setup complete profile for low risk user")
                return False
            
            # Get context to check decision engine
            low_risk_context_response = self.session.get(f"{BASE_URL}/api/admin/onboarding/{user_id_low}/context", timeout=30)
            if low_risk_context_response.status_code != 200:
                self.log_result("T4-Risk-Thresholds-Enhanced", False, f"Failed to get context for low risk user: HTTP {low_risk_context_response.status_code}")
                return False
            
            low_risk_data = low_risk_context_response.json()
            low_risk_engine = low_risk_data.get("decision_engine", {})
            
            print(f"Low risk user context: approval_disabled={low_risk_data.get('approval_disabled')}, reasons={low_risk_data.get('approval_disable_reasons')}")
            print(f"Low risk decision engine: {low_risk_engine}")
            
            # Test case 2: Risk score >= 35 should trigger manual review
            user_id_high = self.create_test_user()
            if not user_id_high:
                self.log_result("T4-Risk-Thresholds-Enhanced", False, "Failed to create test user for high risk")
                return False
            
            if not self.setup_complete_user_profile(user_id_high, 45.0):
                self.log_result("T4-Risk-Thresholds-Enhanced", False, "Failed to setup complete profile for high risk user")
                return False
            
            # Get context to check decision engine
            high_risk_context_response = self.session.get(f"{BASE_URL}/api/admin/onboarding/{user_id_high}/context", timeout=30)
            if high_risk_context_response.status_code != 200:
                self.log_result("T4-Risk-Thresholds-Enhanced", False, f"Failed to get context for high risk user: HTTP {high_risk_context_response.status_code}")
                return False
            
            high_risk_data = high_risk_context_response.json()
            high_risk_engine = high_risk_data.get("decision_engine", {})
            
            print(f"High risk user context: approval_disabled={high_risk_data.get('approval_disabled')}, reasons={high_risk_data.get('approval_disable_reasons')}")
            print(f"High risk decision engine: {high_risk_engine}")
            
            # Check if low risk user can auto-approve
            low_risk_auto_approve = low_risk_engine.get("auto_approve", False)
            low_risk_action = low_risk_engine.get("recommended_action", "")
            
            # Check if high risk user requires manual review
            high_risk_auto_approve = high_risk_engine.get("auto_approve", False)
            high_risk_action = high_risk_engine.get("recommended_action", "")
            
            # Validate thresholds
            if not low_risk_data.get("approval_disabled") and low_risk_auto_approve and low_risk_action == "auto_approve":
                if high_risk_data.get("approval_disabled") or not high_risk_auto_approve or high_risk_action == "force_manual_review":
                    self.log_result("T4-Risk-Thresholds-Enhanced", True, f"Thresholds working: risk_score=25 -> auto_approve={low_risk_auto_approve}, risk_score=45 -> auto_approve={high_risk_auto_approve}")
                    return True
                else:
                    self.log_result("T4-Risk-Thresholds-Enhanced", False, f"High risk (45) should require manual review but got auto_approve={high_risk_auto_approve}, action={high_risk_action}")
                    return False
            else:
                self.log_result("T4-Risk-Thresholds-Enhanced", False, f"Low risk (25) should auto_approve but got auto_approve={low_risk_auto_approve}, action={low_risk_action}, disabled={low_risk_data.get('approval_disabled')}")
                return False
            
        except Exception as e:
            self.log_result("T4-Risk-Thresholds-Enhanced", False, f"Exception: {str(e)}")
            return False
    
    def test_5_decision_reason_confirm_token_mandatory_enhanced(self) -> bool:
        """Test 5 Enhanced: Decision reason mandatory? confirm token mandatory?"""
        try:
            user_id = self.create_test_user()
            if not user_id:
                self.log_result("T5-Mandatory-Fields-Enhanced", False, "Failed to create test user")
                return False
            
            # Test 1: Missing reason should fail
            no_reason_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/decision",
                json={
                    "decision": "approve",
                    "reason": "abc",  # Too short reason (< 5 chars)
                    "confirm_token": "CONFIRM"
                },
                timeout=30
            )
            
            print(f"Short reason test: HTTP {no_reason_response.status_code}, response: {no_reason_response.text}")
            
            if no_reason_response.status_code not in [400, 422]:
                self.log_result("T5-Mandatory-Fields-Enhanced", False, f"Short reason should fail but got HTTP {no_reason_response.status_code}")
                return False
            
            # Test 2: Missing confirm token should fail
            no_token_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/decision",
                json={
                    "decision": "approve",
                    "reason": "Valid reason for testing with sufficient length",
                    "confirm_token": ""  # Empty token
                },
                timeout=30
            )
            
            print(f"Empty token test: HTTP {no_token_response.status_code}, response: {no_token_response.text}")
            
            if no_token_response.status_code not in [400, 422]:
                self.log_result("T5-Mandatory-Fields-Enhanced", False, f"Empty confirm_token should fail but got HTTP {no_token_response.status_code}")
                return False
            
            # Test 3: Wrong confirm token should fail
            wrong_token_response = self.session.post(
                f"{BASE_URL}/api/admin/onboarding/{user_id}/decision",
                json={
                    "decision": "approve",
                    "reason": "Valid reason for testing with sufficient length",
                    "confirm_token": "WRONG"  # Wrong token
                },
                timeout=30
            )
            
            print(f"Wrong token test: HTTP {wrong_token_response.status_code}, response: {wrong_token_response.text}")
            
            if wrong_token_response.status_code not in [400, 422]:
                self.log_result("T5-Mandatory-Fields-Enhanced", False, f"Wrong confirm_token should fail but got HTTP {wrong_token_response.status_code}")
                return False
            
            self.log_result("T5-Mandatory-Fields-Enhanced", True, "Reason and confirm_token validation working correctly (all validation cases returned 400/422)")
            return True
            
        except Exception as e:
            self.log_result("T5-Mandatory-Fields-Enhanced", False, f"Exception: {str(e)}")
            return False
    
    def run_enhanced_tests(self):
        """Run enhanced tests for the failing cases"""
        print("=" * 80)
        print("P0 ONBOARDING+APPROVAL FOUNDATION - ENHANCED TESTS")
        print(f"Target: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print("=" * 80)
        
        # Authenticate
        if not self.authenticate_admin():
            print("❌ CRITICAL: Admin authentication failed")
            return
        
        print("✅ Admin authentication successful")
        print()
        
        # Run enhanced tests for failing cases
        enhanced_tests = [
            ("T4-Risk-Thresholds-Enhanced", self.test_4_risk_foundation_decision_engine_thresholds_enhanced),
            ("T5-Mandatory-Fields-Enhanced", self.test_5_decision_reason_confirm_token_mandatory_enhanced),
        ]
        
        for test_name, test_func in enhanced_tests:
            try:
                test_func()
            except Exception as e:
                self.log_result(test_name, False, f"Test execution failed: {str(e)}")
            print()
        
        # Summary
        print("=" * 80)
        print("ENHANCED TEST SUMMARY")
        print("=" * 80)
        
        passed = sum(1 for _, passed, _ in self.test_results if passed)
        total = len(self.test_results)
        
        for test_name, passed, evidence in self.test_results:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} {test_name}: {evidence}")
        
        print()
        print(f"ENHANCED RESULT: {passed}/{total} PASS ({passed/total*100:.1f}% SUCCESS RATE)")

if __name__ == "__main__":
    test_runner = P0OnboardingApprovalFoundationTestEnhanced()
    test_runner.run_enhanced_tests()