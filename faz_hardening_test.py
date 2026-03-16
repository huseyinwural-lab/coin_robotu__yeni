#!/usr/bin/env python3
import os
"""
FAZ-1 + FAZ-2 Backend Hardening Validation Test

This script validates the backend hardening changes according to the requirements:
1. Backend smoke tests (health + admin login)
2. Migration discipline regressions
3. Bootstrap behavior regression
4. Frontend smoke test

Usage: python faz_hardening_test.py
"""

import requests
import json
import sys
import time
from datetime import datetime
from typing import Dict, Any

# Configuration
BASE_URL = "https://trading-infra.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"
ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "Admin12345!")

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
        
    def pass_test(self, test_name: str):
        self.passed += 1
        print(f"✅ PASS: {test_name}")
        
    def fail_test(self, test_name: str, error: str):
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"❌ FAIL: {test_name} - {error}")
        
    def print_summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"FAZ-1 + FAZ-2 HARDENING VALIDATION RESULTS")
        print(f"{'='*60}")
        print(f"TOTAL TESTS: {total}")
        print(f"PASSED: {self.passed}")
        print(f"FAILED: {self.failed}")
        print(f"SUCCESS RATE: {(self.passed/total*100):.1f}%" if total > 0 else "0%")
        
        if self.errors:
            print(f"\nFAILED TESTS:")
            for error in self.errors:
                print(f"  ❌ {error}")
        
        return self.failed == 0

def make_request(method: str, url: str, **kwargs) -> tuple[int, dict]:
    """Make HTTP request and return status code and response data"""
    try:
        response = requests.request(method, url, timeout=30, **kwargs)
        try:
            data = response.json()
        except:
            data = {"text": response.text}
        return response.status_code, data
    except Exception as e:
        return 0, {"error": str(e)}

def test_backend_smoke(results: TestResults) -> str:
    """Test 1: Backend Smoke Tests"""
    print("\n1. BACKEND SMOKE TESTS")
    print("-" * 40)
    
    admin_token = None
    
    # Test health endpoint
    status, data = make_request("GET", f"{API_URL}/health")
    if status == 200 and data.get("status") == "ok":
        results.pass_test("Health endpoint GET /api/health")
    else:
        results.fail_test("Health endpoint GET /api/health", f"Expected 200 + {{status: ok}}, got {status}: {data}")
    
    # Test admin login
    login_payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    status, data = make_request("POST", f"{API_URL}/auth/login/admin", json=login_payload)
    
    if status == 200 and data.get("access_token"):
        admin_token = data["access_token"]
        results.pass_test("Admin login POST /api/auth/login/admin")
    else:
        results.fail_test("Admin login POST /api/auth/login/admin", f"Expected 200 + token, got {status}: {data}")
    
    return admin_token

def test_migration_regressions(results: TestResults, admin_token: str):
    """Test 2: Migration Discipline Regressions"""
    print("\n2. MIGRATION DISCIPLINE REGRESSIONS")
    print("-" * 40)
    
    # Check basic admin endpoint after startup - universe monitor
    if admin_token:
        headers = {"Authorization": f"Bearer {admin_token}"}
        status, data = make_request("GET", f"{API_URL}/admin/universe-monitor", headers=headers)
        
        if status == 200:
            results.pass_test("Admin endpoint GET /api/admin/universe-monitor")
        else:
            results.fail_test("Admin endpoint GET /api/admin/universe-monitor", f"Expected 200, got {status}: {data}")
    else:
        results.fail_test("Admin endpoint GET /api/admin/universe-monitor", "No admin token available")
    
    # Check for critical 500 errors in user endpoints (needs user token)
    # First create a test user and get user token for symbol-selection endpoint test
    register_payload = {
        "email": f"test_faz_validation_{int(time.time())}@test.com",
        "password": "TestPassword123!"
    }
    status, data = make_request("POST", f"{API_URL}/auth/register", json=register_payload)
    
    if status == 200:
        user_id = data.get("id")
        # Approve the user using admin token if we have it
        if admin_token and user_id:
            headers = {"Authorization": f"Bearer {admin_token}"}
            status, _ = make_request("POST", f"{API_URL}/auth/admin/user-approval-requests/{user_id}/approve", headers=headers)
            
            if status == 200:
                # Now login as the approved user
                login_payload = {"email": register_payload["email"], "password": register_payload["password"]}
                status, data = make_request("POST", f"{API_URL}/auth/login/user", json=login_payload)
                
                if status == 200 and data.get("access_token"):
                    user_token = data["access_token"]
                    user_headers = {"Authorization": f"Bearer {user_token}"}
                    
                    # Test user scanner symbol-selection endpoint
                    status, data = make_request("GET", f"{API_URL}/user/scanner/symbol-selection", headers=user_headers)
                    
                    if status == 200:
                        results.pass_test("User endpoint GET /api/user/scanner/symbol-selection")
                    else:
                        results.fail_test("User endpoint GET /api/user/scanner/symbol-selection", f"Expected 200, got {status}: {data}")
                else:
                    results.fail_test("User endpoint GET /api/user/scanner/symbol-selection", "User login failed after approval")
            else:
                results.fail_test("User endpoint GET /api/user/scanner/symbol-selection", "User approval failed")
        else:
            results.fail_test("User endpoint GET /api/user/scanner/symbol-selection", "Admin token not available for user approval")
    else:
        results.fail_test("User endpoint GET /api/user/scanner/symbol-selection", "User registration failed")

def test_bootstrap_behavior(results: TestResults):
    """Test 3: Bootstrap Behavior Regression"""
    print("\n3. BOOTSTRAP BEHAVIOR REGRESSION")
    print("-" * 40)
    
    # Test that admin login still works (this validates that admin account wasn't reset/duplicated)
    login_payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    status, data = make_request("POST", f"{API_URL}/auth/login/admin", json=login_payload)
    
    if status == 200 and data.get("access_token"):
        results.pass_test("Admin account bootstrap behavior (no unexpected reset)")
        
        # Check that we get expected admin user info and not duplicate accounts
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        status, user_data = make_request("GET", f"{API_URL}/auth/me", headers=headers)
        
        if status == 200 and user_data.get("email") == ADMIN_EMAIL:
            results.pass_test("Admin account consistency check")
        else:
            results.fail_test("Admin account consistency check", f"Unexpected user data: {user_data}")
    else:
        results.fail_test("Admin account bootstrap behavior (no unexpected reset)", f"Admin login failed: {status}: {data}")

def test_frontend_smoke(results: TestResults):
    """Test 4: Frontend Smoke Test"""
    print("\n4. FRONTEND SMOKE TEST")
    print("-" * 40)
    
    # Test that frontend URL is accessible (no blank page)
    status, data = make_request("GET", BASE_URL)
    
    if status == 200:
        # Check for basic HTML content (not empty/blank page)
        html_content = data.get("text", "")
        if "html" in html_content.lower() or len(html_content) > 100:
            results.pass_test("Frontend accessibility (no blank page)")
        else:
            results.fail_test("Frontend accessibility (no blank page)", f"Received empty or minimal content: {len(html_content)} chars")
    else:
        results.fail_test("Frontend accessibility (no blank page)", f"Frontend URL not accessible: {status}")

def main():
    """Main test execution"""
    print("FAZ-1 + FAZ-2 BAŞLANGIÇ HARDENING DEĞİŞİKLİKLERİ DOĞRULAMA")
    print("=" * 60)
    print(f"Test Target: {BASE_URL}")
    print(f"Started at: {datetime.now().isoformat()}")
    
    results = TestResults()
    
    try:
        # Execute all test phases
        admin_token = test_backend_smoke(results)
        test_migration_regressions(results, admin_token)
        test_bootstrap_behavior(results)
        test_frontend_smoke(results)
        
    except Exception as e:
        results.fail_test("Test Execution", f"Unexpected error: {e}")
    
    # Print final results
    success = results.print_summary()
    
    if success:
        print(f"\n🎉 FAZ-1 + FAZ-2 HARDENİNG DEĞİŞİKLİKLERİ DOĞRULANDI")
        print("ÇIKIŞ: PASS - Tüm testler başarılı")
    else:
        print(f"\n⚠️  FAZ-1 + FAZ-2 HARDENİNG VALİDASYON HATASI")
        print("ÇIKIŞ: FAIL - Bazı testler başarısız")
        
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())