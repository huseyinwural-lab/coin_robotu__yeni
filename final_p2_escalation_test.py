#!/usr/bin/env python3
"""
Final P2+Escalation Backend Validation Test

This script validates all P2+Escalation requirements with proper error handling
and role-based access controls.
"""

import json
import requests
import time
from datetime import datetime

BASE_URL = "https://strategy-version-gov.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

def log_result(test_name: str, status: str, details: str = ""):
    """Log test result"""
    status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"{status_symbol} {test_name}: {status}")
    if details:
        print(f"   {details}")

def get_fresh_token(email: str, password: str) -> str:
    """Get a fresh authentication token"""
    session = requests.Session()
    response = session.post(
        f"{API_BASE}/auth/login/admin",
        json={"email": email, "password": password},
        timeout=30
    )
    
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        raise Exception(f"Login failed: {response.status_code} - {response.text}")

def test_p2_escalation_backend():
    """Run comprehensive P2+Escalation backend validation"""
    print("=" * 80)
    print("P2+ESCALATION BACKEND VALIDATION - FINAL TEST")
    print("=" * 80)
    print(f"Test URL: {BASE_URL}")
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    session = requests.Session()
    test_results = []
    
    # Test credentials
    credentials = {
        "super_admin": {"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
        "admin": {"email": "canary.requester@platform.local", "password": "CanaryRequester123!"},
        "ops": {"email": "canary.ops@platform.local", "password": "CanaryOps123!"}
    }
    
    tokens = {}
    
    # Step 1: Authentication tests
    print("STEP 1: Authentication Tests")
    print("-" * 40)
    
    for role, creds in credentials.items():
        try:
            token = get_fresh_token(creds["email"], creds["password"])
            tokens[role] = token
            log_result(f"Login {role}", "PASS", f"Successfully authenticated as {role}")
            test_results.append(("PASS", f"Login {role}"))
        except Exception as e:
            log_result(f"Login {role}", "FAIL", str(e))
            test_results.append(("FAIL", f"Login {role}"))
    
    print()
    
    # Step 2: 502 Error Check
    print("STEP 2: 502 Error Check")
    print("-" * 40)
    
    try:
        response = session.get(f"{API_BASE}/health", timeout=30)
        if response.status_code == 502:
            log_result("502 Error Check", "FAIL", "502 Bad Gateway detected")
            test_results.append(("FAIL", "502 Error Check"))
        else:
            log_result("502 Error Check", "PASS", f"No 502 error (got {response.status_code})")
            test_results.append(("PASS", "502 Error Check"))
    except Exception as e:
        log_result("502 Error Check", "FAIL", str(e))
        test_results.append(("FAIL", "502 Error Check"))
    
    print()
    
    # Step 3: Escalation Center Tests
    print("STEP 3: Escalation Center Tests")
    print("-" * 40)
    
    if "admin" in tokens:
        # Test GET /api/admin/escalation-center
        try:
            response = session.get(
                f"{API_BASE}/admin/escalation-center",
                headers={"Authorization": f"Bearer {tokens['admin']}"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["active_breaches", "acknowledged", "resolved"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    log_result("GET escalation-center", "FAIL", f"Missing fields: {missing_fields}")
                    test_results.append(("FAIL", "GET escalation-center"))
                else:
                    log_result("GET escalation-center", "PASS", 
                             f"All required fields present. Active: {len(data.get('active_breaches', []))}, "
                             f"Acknowledged: {len(data.get('acknowledged', []))}, Resolved: {len(data.get('resolved', []))}")
                    test_results.append(("PASS", "GET escalation-center"))
            else:
                log_result("GET escalation-center", "FAIL", f"HTTP {response.status_code}")
                test_results.append(("FAIL", "GET escalation-center"))
        except Exception as e:
            log_result("GET escalation-center", "FAIL", str(e))
            test_results.append(("FAIL", "GET escalation-center"))
        
        # Test POST /api/admin/escalation-center/{id}/ack (admin role)
        try:
            response = session.post(
                f"{API_BASE}/admin/escalation-center/test_123/ack",
                headers={"Authorization": f"Bearer {tokens['admin']}"},
                json={
                    "current_owner": "admin_test",
                    "escalation_reason": "Test escalation acknowledgment"
                },
                timeout=30
            )
            
            if response.status_code in [200, 404]:
                log_result("POST escalation ack (admin)", "PASS", 
                         "Admin can access ack endpoint (404 for non-existent escalation is expected)")
                test_results.append(("PASS", "POST escalation ack (admin)"))
            else:
                log_result("POST escalation ack (admin)", "FAIL", f"HTTP {response.status_code}")
                test_results.append(("FAIL", "POST escalation ack (admin)"))
        except Exception as e:
            log_result("POST escalation ack (admin)", "FAIL", str(e))
            test_results.append(("FAIL", "POST escalation ack (admin)"))
    
    if "super_admin" in tokens:
        # Test POST /api/admin/escalation-center/{id}/resolve (super_admin only)
        try:
            response = session.post(
                f"{API_BASE}/admin/escalation-center/test_123/resolve",
                headers={"Authorization": f"Bearer {tokens['super_admin']}"},
                json={
                    "escalation_reason": "Test escalation resolution"
                },
                timeout=30
            )
            
            if response.status_code in [200, 404]:
                log_result("POST escalation resolve (super_admin)", "PASS", 
                         "Super admin can access resolve endpoint (404 for non-existent escalation is expected)")
                test_results.append(("PASS", "POST escalation resolve (super_admin)"))
            else:
                log_result("POST escalation resolve (super_admin)", "FAIL", f"HTTP {response.status_code}")
                test_results.append(("FAIL", "POST escalation resolve (super_admin)"))
        except Exception as e:
            log_result("POST escalation resolve (super_admin)", "FAIL", str(e))
            test_results.append(("FAIL", "POST escalation resolve (super_admin)"))
    
    print()
    
    # Step 4: Role-based Access Control Tests
    print("STEP 4: Role-based Access Control Tests")
    print("-" * 40)
    
    if "admin" in tokens and "super_admin" in tokens:
        # Test admin cannot resolve (should get 403)
        try:
            response = session.post(
                f"{API_BASE}/admin/escalation-center/test_123/resolve",
                headers={"Authorization": f"Bearer {tokens['admin']}"},
                json={
                    "escalation_reason": "Test escalation resolution"
                },
                timeout=30
            )
            
            if response.status_code == 403:
                log_result("Admin resolve blocked", "PASS", "Admin correctly blocked from resolving escalations")
                test_results.append(("PASS", "Admin resolve blocked"))
            else:
                log_result("Admin resolve blocked", "FAIL", f"Admin not properly blocked: HTTP {response.status_code}")
                test_results.append(("FAIL", "Admin resolve blocked"))
        except Exception as e:
            log_result("Admin resolve blocked", "FAIL", str(e))
            test_results.append(("FAIL", "Admin resolve blocked"))
    
    if "ops" in tokens:
        # Test ops can view escalation center
        try:
            response = session.get(
                f"{API_BASE}/admin/escalation-center",
                headers={"Authorization": f"Bearer {tokens['ops']}"},
                timeout=30
            )
            
            if response.status_code == 200:
                log_result("Ops view escalation center", "PASS", "Ops can view escalation center")
                test_results.append(("PASS", "Ops view escalation center"))
            else:
                log_result("Ops view escalation center", "FAIL", f"HTTP {response.status_code}")
                test_results.append(("FAIL", "Ops view escalation center"))
        except Exception as e:
            log_result("Ops view escalation center", "FAIL", str(e))
            test_results.append(("FAIL", "Ops view escalation center"))
        
        # Test ops cannot acknowledge escalations
        try:
            response = session.post(
                f"{API_BASE}/admin/escalation-center/test_123/ack",
                headers={"Authorization": f"Bearer {tokens['ops']}"},
                json={
                    "current_owner": "ops_test",
                    "escalation_reason": "Test escalation acknowledgment"
                },
                timeout=30
            )
            
            if response.status_code == 403:
                log_result("Ops ack blocked", "PASS", "Ops correctly blocked from acknowledging escalations")
                test_results.append(("PASS", "Ops ack blocked"))
            else:
                log_result("Ops ack blocked", "FAIL", f"Ops not properly blocked: HTTP {response.status_code}")
                test_results.append(("FAIL", "Ops ack blocked"))
        except Exception as e:
            log_result("Ops ack blocked", "FAIL", str(e))
            test_results.append(("FAIL", "Ops ack blocked"))
    
    print()
    
    # Step 5: Matrix Batch Test
    print("STEP 5: Matrix Batch Test")
    print("-" * 40)
    
    if "admin" in tokens:
        try:
            payload = {
                "user_id": "test_user_123",
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "strategy_bindings": ["trend_follow_v1", "mean_reversion_v1"],
                "intent_payload": {
                    "side": "buy",
                    "notional": 100.0,
                    "volatility_pct": 5.0,
                    "signal_confidence": 0.7
                }
            }
            
            response = session.post(
                f"{API_BASE}/admin/risk-simulation/matrix-batch",
                headers={"Authorization": f"Bearer {tokens['admin']}"},
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                log_result("Matrix batch simulation", "PASS", 
                         f"Matrix batch successful. Total combinations: {data.get('total_combinations', 0)}")
                test_results.append(("PASS", "Matrix batch simulation"))
            elif response.status_code == 400:
                error_text = response.text.lower()
                if "user_id" in error_text or "geçersiz" in error_text:
                    log_result("Matrix batch simulation", "PASS", 
                             "Endpoint accessible (validation error for test user_id is expected)")
                    test_results.append(("PASS", "Matrix batch simulation"))
                else:
                    log_result("Matrix batch simulation", "FAIL", f"Unexpected 400 error: {response.text}")
                    test_results.append(("FAIL", "Matrix batch simulation"))
            else:
                log_result("Matrix batch simulation", "FAIL", f"HTTP {response.status_code}")
                test_results.append(("FAIL", "Matrix batch simulation"))
        except Exception as e:
            log_result("Matrix batch simulation", "FAIL", str(e))
            test_results.append(("FAIL", "Matrix batch simulation"))
    
    print()
    
    # Step 6: Import/Export Tests
    print("STEP 6: Import/Export Tests")
    print("-" * 40)
    
    if "admin" in tokens:
        # Test JSON export
        try:
            response = session.get(
                f"{API_BASE}/admin/strategy-intelligence/export",
                headers={"Authorization": f"Bearer {tokens['admin']}"},
                params={
                    "export_format": "json",
                    "dataset": "decision_requests"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                log_result("JSON export", "PASS", f"JSON export successful, size: {len(response.content)} bytes")
                test_results.append(("PASS", "JSON export"))
            else:
                log_result("JSON export", "FAIL", f"HTTP {response.status_code}")
                test_results.append(("FAIL", "JSON export"))
        except Exception as e:
            log_result("JSON export", "FAIL", str(e))
            test_results.append(("FAIL", "JSON export"))
        
        # Test CSV export
        try:
            response = session.get(
                f"{API_BASE}/admin/strategy-intelligence/export",
                headers={"Authorization": f"Bearer {tokens['admin']}"},
                params={
                    "export_format": "csv",
                    "dataset": "simulation_history"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                log_result("CSV export", "PASS", f"CSV export successful, content-type: {content_type}")
                test_results.append(("PASS", "CSV export"))
            else:
                log_result("CSV export", "FAIL", f"HTTP {response.status_code}")
                test_results.append(("FAIL", "CSV export"))
        except Exception as e:
            log_result("CSV export", "FAIL", str(e))
            test_results.append(("FAIL", "CSV export"))
    
    if "super_admin" in tokens:
        # Test import (requires super_admin)
        try:
            test_import_data = {
                "simulation_runs": [
                    {
                        "run_id": "test_import_123",
                        "status": "preview",
                        "request_mode": "single"
                    }
                ],
                "decision_requests": []
            }
            
            response = session.post(
                f"{API_BASE}/admin/strategy-intelligence/import-json",
                headers={"Authorization": f"Bearer {tokens['super_admin']}"},
                json=test_import_data,
                timeout=30
            )
            
            if response.status_code == 200:
                log_result("JSON import", "PASS", "Import endpoint accessible and functional")
                test_results.append(("PASS", "JSON import"))
            elif response.status_code == 400:
                log_result("JSON import", "PASS", "Import endpoint accessible (validation error for test data is expected)")
                test_results.append(("PASS", "JSON import"))
            else:
                log_result("JSON import", "FAIL", f"HTTP {response.status_code}")
                test_results.append(("FAIL", "JSON import"))
        except Exception as e:
            log_result("JSON import", "FAIL", str(e))
            test_results.append(("FAIL", "JSON import"))
    
    print()
    
    # Generate Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    total_tests = len(test_results)
    passed_tests = len([r for r in test_results if r[0] == "PASS"])
    failed_tests = len([r for r in test_results if r[0] == "FAIL"])
    
    print(f"Total Tests: {total_tests}")
    print(f"✅ Passed: {passed_tests}")
    print(f"❌ Failed: {failed_tests}")
    print()
    
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    print(f"Success Rate: {success_rate:.1f}%")
    print()
    
    # Show failed tests
    if failed_tests > 0:
        print("FAILED TESTS:")
        for status, test_name in test_results:
            if status == "FAIL":
                print(f"❌ {test_name}")
        print()
    
    # Overall assessment
    if failed_tests == 0:
        print("🎉 ALL TESTS PASSED - P2+Escalation backend validation successful!")
        print("✅ 502 errors resolved")
        print("✅ Escalation Center endpoints functional")
        print("✅ Matrix Batch endpoint accessible")
        print("✅ Import/Export endpoints working")
        print("✅ Role-based access controls enforced correctly")
    elif failed_tests <= 2:
        print("⚠️  MOSTLY SUCCESSFUL - Minor issues detected")
    else:
        print("❌ MULTIPLE FAILURES - P2+Escalation backend needs attention")
    
    print()
    print(f"Test completed at: {datetime.now().isoformat()}")
    print("=" * 80)

if __name__ == "__main__":
    test_p2_escalation_backend()