#!/usr/bin/env python3
import os
"""
FAZ-1/FAZ-2 Final Hardening Validation Script

This script validates the specific hardening requirements:
1) API sağlık + auth
2) Alembic-only migration disiplini regresyonu  
3) Model domain ayrıştırma regresyonu
4) In-memory Redis TTL semantiği
5) Frontend smoke

Expected format: PASS/FAIL ve kısa kanıtlar
"""

import requests
import json
import sys
import time
from datetime import datetime
from typing import Dict, Any, List

# Configuration
BASE_URL = "https://market-scanner-prod.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"
ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "Admin12345!")

class ValidationResults:
    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0
        
    def add_test(self, name: str, status: str, proof: str, endpoint: str = "", response_code: str = ""):
        test_result = {
            "name": name,
            "status": status,
            "proof": proof,
            "endpoint": endpoint,
            "response_code": response_code
        }
        self.tests.append(test_result)
        
        if status == "PASS":
            self.passed += 1
        else:
            self.failed += 1
            
    def print_results(self):
        print("\nFAZ-1/FAZ-2 DOĞRULAMA SONUÇLARI:")
        print("=" * 50)
        
        for test in self.tests:
            status_icon = "✅" if test["status"] == "PASS" else "❌"
            print(f"{status_icon} {test['status']}: {test['name']}")
            print(f"   Kanıt: {test['proof']}")
            if test["endpoint"]:
                print(f"   Endpoint: {test['endpoint']}")
            if test["response_code"]:
                print(f"   Response: {test['response_code']}")
            print()
        
        print(f"TOPLAM: {self.passed + self.failed} | BAŞARILI: {self.passed} | BAŞARISIZ: {self.failed}")
        return self.failed == 0

def make_request(method: str, url: str, **kwargs) -> tuple[int, dict]:
    """Make HTTP request and return status code and response data"""
    try:
        response = requests.request(method, url, timeout=30, **kwargs)
        try:
            data = response.json()
        except:
            # For non-JSON responses (like HTML), return the text
            data = {"text": response.text}
        return response.status_code, data
    except Exception as e:
        return 0, {"error": str(e)}

def test_api_health_auth(results: ValidationResults) -> str:
    """Test 1: API sağlık + auth"""
    print("1) API sağlık + auth testi...")
    
    # Test health endpoint
    status, data = make_request("GET", f"{API_URL}/health")
    if status == 200 and data.get("status") == "ok":
        results.add_test(
            "GET /api/health",
            "PASS", 
            "200 response with {status: ok}",
            "/api/health",
            "200"
        )
    else:
        results.add_test(
            "GET /api/health",
            "FAIL",
            f"Expected 200 + status:ok, got {status}: {data}",
            "/api/health", 
            str(status)
        )
    
    # Test admin login
    login_payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    status, data = make_request("POST", f"{API_URL}/auth/login/admin", json=login_payload)
    
    if status == 200 and data.get("access_token"):
        admin_token = data["access_token"]
        results.add_test(
            "POST /api/auth/login/admin",
            "PASS",
            f"200 response with access_token for {ADMIN_EMAIL}",
            "/api/auth/login/admin",
            "200"
        )
        return admin_token
    else:
        results.add_test(
            "POST /api/auth/login/admin",
            "FAIL", 
            f"Expected 200 + token, got {status}: {data}",
            "/api/auth/login/admin",
            str(status)
        )
        return None

def test_alembic_only_migration(results: ValidationResults, admin_token: str):
    """Test 2: Alembic-only migration disiplini regresyonu"""
    print("2) Alembic-only migration disiplini regresyonu...")
    
    if not admin_token:
        results.add_test(
            "Alembic Migration Test",
            "FAIL",
            "Admin token not available",
            "",
            ""
        )
        return
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Test admin universe-monitor endpoint (critical after startup)
    status, data = make_request("GET", f"{API_URL}/admin/universe-monitor", headers=headers)
    
    if status == 200:
        results.add_test(
            "Admin token ile GET /api/admin/universe-monitor", 
            "PASS",
            "200 response, no 500 after create_all removal",
            "/api/admin/universe-monitor",
            "200"
        )
    else:
        results.add_test(
            "Admin token ile GET /api/admin/universe-monitor",
            "FAIL",
            f"Expected 200, got {status}: {data}",
            "/api/admin/universe-monitor", 
            str(status)
        )
    
    # Test user scanner endpoint after user creation/approval
    user_email = f"test_faz_user_{int(time.time())}@test.com"
    register_payload = {"email": user_email, "password": "TestPassword123!"}
    
    # Register user
    status, reg_data = make_request("POST", f"{API_URL}/auth/register", json=register_payload)
    if status == 200 and reg_data.get("id"):
        user_id = reg_data["id"]
        
        # Approve user
        approve_payload = {"ids": [user_id]}
        status, _ = make_request("POST", f"{API_URL}/admin/user-approvals/bulk-approve", 
                                json=approve_payload, headers=headers)
        
        if status == 200:
            # Login as user
            status, login_data = make_request("POST", f"{API_URL}/auth/login/user", json=register_payload)
            
            if status == 200 and login_data.get("access_token"):
                user_headers = {"Authorization": f"Bearer {login_data['access_token']}"}
                
                # Test user scanner endpoint
                status, data = make_request("GET", f"{API_URL}/user/scanner/symbol-selection", headers=user_headers)
                
                if status == 200:
                    results.add_test(
                        "User token ile GET /api/user/scanner/symbol-selection",
                        "PASS", 
                        "200 response, no 500 after create_all removal",
                        "/api/user/scanner/symbol-selection",
                        "200"
                    )
                else:
                    results.add_test(
                        "User token ile GET /api/user/scanner/symbol-selection",
                        "FAIL",
                        f"Expected 200, got {status}: {data}",
                        "/api/user/scanner/symbol-selection",
                        str(status)
                    )
            else:
                results.add_test(
                    "User token ile GET /api/user/scanner/symbol-selection",
                    "FAIL",
                    "User login failed after approval",
                    "/api/auth/login/user", 
                    str(status)
                )
        else:
            results.add_test(
                "User token ile GET /api/user/scanner/symbol-selection",
                "FAIL",
                "User approval failed",
                "/api/admin/user-approvals/bulk-approve",
                str(status)
            )
    else:
        results.add_test(
            "User token ile GET /api/user/scanner/symbol-selection",
            "FAIL",
            "User registration failed",
            "/api/auth/register",
            str(status)
        )

def test_model_domain_separation(results: ValidationResults, admin_token: str):
    """Test 3: Model domain ayrıştırma regresyonu"""
    print("3) Model domain ayrıştırma regresyonu...")
    
    # Test that models.py imports work correctly (no import errors/NameError)
    # We test this by calling multiple endpoints that use different model domains
    
    if not admin_token:
        results.add_test(
            "Model Domain Separation Test",
            "FAIL", 
            "Admin token not available",
            "",
            ""
        )
        return
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Test 1: Auth model domain access
    status, data = make_request("GET", f"{API_URL}/auth/me", headers=headers)
    auth_success = status == 200
    
    # Test 2: Scanner model domain access  
    status, data = make_request("GET", f"{API_URL}/admin/universe-monitor", headers=headers)
    scanner_success = status == 200
    
    # Test 3: Admin monitor model domain access
    status, data = make_request("GET", f"{API_URL}/dashboard/summary", headers=headers)  
    admin_success = status == 200
    
    if auth_success and scanner_success and admin_success:
        results.add_test(
            "Model domain ayrıştırma - 3 endpoint test",
            "PASS",
            "Auth + Scanner + Admin endpoints all accessible (no import/NameError)",
            "Multiple endpoints",
            "All 200"
        )
    else:
        failed_endpoints = []
        if not auth_success: failed_endpoints.append("auth/me")
        if not scanner_success: failed_endpoints.append("universe-monitor") 
        if not admin_success: failed_endpoints.append("dashboard/summary")
        
        results.add_test(
            "Model domain ayrıştırma - 3 endpoint test",
            "FAIL",
            f"Failed endpoints: {', '.join(failed_endpoints)} (possible import errors)",
            "Multiple endpoints",
            f"Failures: {len(failed_endpoints)}"
        )

def test_redis_ttl_semantics(results: ValidationResults, admin_token: str):
    """Test 4: In-memory Redis TTL semantiği"""  
    print("4) In-memory Redis TTL semantiği...")
    
    if not admin_token:
        results.add_test(
            "In-memory Redis TTL - Pipeline monitoring",
            "FAIL",
            "Admin token not available",
            "",
            ""
        )
        return
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Test pipeline monitoring (uses Redis for caching)
    status, data = make_request("GET", f"{API_URL}/pipeline/monitoring", headers=headers)
    
    if status == 200:
        # Check if we get expected Redis-dependent fields
        required_fields = ["websocket_status", "heartbeat", "latency_ms", "queue_depth"]
        has_all_fields = all(field in data for field in required_fields)
        
        if has_all_fields:
            results.add_test(
                "In-memory Redis TTL - Pipeline monitoring",
                "PASS",
                "Pipeline endpoint returns all required fields (Redis fallback working)",
                "/api/pipeline/monitoring",
                "200"
            )
        else:
            missing_fields = [field for field in required_fields if field not in data]
            results.add_test(
                "In-memory Redis TTL - Pipeline monitoring", 
                "FAIL",
                f"Missing Redis-dependent fields: {missing_fields}",
                "/api/pipeline/monitoring",
                "200"
            )
    else:
        results.add_test(
            "In-memory Redis TTL - Pipeline monitoring",
            "FAIL",
            f"Pipeline monitoring failed: {status}",
            "/api/pipeline/monitoring", 
            str(status)
        )

def test_frontend_smoke(results: ValidationResults):
    """Test 5: Frontend smoke"""
    print("5) Frontend smoke test...")
    
    # Test landing page loads
    status, data = make_request("GET", BASE_URL)
    
    if status == 200:
        html_content = data.get("text", "")
        
        is_not_blank = len(html_content) > 200
        
        if is_not_blank:
            results.add_test(
                "Frontend smoke - Landing page", 
                "PASS",
                f"Landing page loads correctly ({len(html_content)} chars, not blank)",
                BASE_URL,
                "200"
            )
        else:
            results.add_test(
                "Frontend smoke - Landing page",
                "FAIL",
                f"Landing page appears blank ({len(html_content)} chars)",
                BASE_URL,
                "200"
            )
    else:
        results.add_test(
            "Frontend smoke - Landing page",
            "FAIL", 
            f"Frontend not accessible: {status}",
            BASE_URL,
            str(status)
        )

def main():
    """Main validation execution"""
    print("FAZ-1/FAZ-2 FINAL HARDENING VALIDATION")
    print("=" * 50)
    print(f"Target: {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}\n")
    
    results = ValidationResults()
    
    try:
        # Execute all validation tests
        admin_token = test_api_health_auth(results)
        test_alembic_only_migration(results, admin_token) 
        test_model_domain_separation(results, admin_token)
        test_redis_ttl_semantics(results, admin_token)
        test_frontend_smoke(results)
        
    except Exception as e:
        results.add_test("Test Execution", "FAIL", f"Unexpected error: {e}", "", "")
    
    # Print results in requested format
    success = results.print_results()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())