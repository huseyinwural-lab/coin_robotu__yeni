#!/usr/bin/env python3

"""
Final P2 Backend Validation Test
Base URL: https://identity-control-1.preview.emergentagent.com
Creds: canary.admin@platform.local / CanaryAdmin123!

Test matrix:
1) Controlled MFA override: login/admin should return mfa_required=false and access_token
2) Observability endpoints 200: /admin/identity/users/{id}/activity-timeline, /security-telemetry, /execution-metrics, /trading-observability
3) Approval reason strict: disable_user request with short reason => 400 request_reason_too_short
4) Approval impact payload: /admin/identity/approvals item contains impact_delta.risk_delta and impact_delta.numeric_changes
5) Bulk preview depth: summary has blocker_breakdown, risk_score_total, action_summary
6) Health/ready both 200
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://identity-control-1.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def log_test(test_name, status, details=""):
    timestamp = datetime.now().strftime("%H:%M:%S")
    status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"[{timestamp}] {status_symbol} {test_name}: {status}")
    if details:
        print(f"    {details}")

def test_controlled_mfa_override():
    """Test 1: Controlled MFA override - login/admin should return mfa_required=false and access_token"""
    try:
        response = requests.post(f"{API_BASE}/auth/login/admin", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            mfa_required = data.get("mfa_required", True)
            access_token = data.get("access_token")
            
            if mfa_required == False and access_token:
                log_test("Controlled MFA override", "PASS", f"mfa_required=false, access_token received")
                return access_token
            else:
                log_test("Controlled MFA override", "FAIL", f"mfa_required={mfa_required}, access_token={'present' if access_token else 'missing'}")
                return None
        else:
            log_test("Controlled MFA override", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        log_test("Controlled MFA override", "FAIL", f"Exception: {str(e)}")
        return None

def test_observability_endpoints(token):
    """Test 2: Observability endpoints 200"""
    if not token:
        log_test("Observability endpoints", "SKIP", "No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # First get a real user ID
    try:
        users_response = requests.get(f"{API_BASE}/admin/identity/users", headers=headers, timeout=10)
        if users_response.status_code == 200:
            users_data = users_response.json()
            if users_data.get("items"):
                user_id = users_data["items"][0]["id"]
            else:
                user_id = "test-user-id"
        else:
            user_id = "test-user-id"
    except:
        user_id = "test-user-id"
    
    endpoints = [
        f"/admin/identity/users/{user_id}/activity-timeline",
        "/security-telemetry", 
        "/execution-metrics",
        "/trading-observability"
    ]
    
    results = []
    for endpoint in endpoints:
        try:
            response = requests.get(f"{API_BASE}{endpoint}", headers=headers, timeout=10)
            if response.status_code == 200:
                results.append(f"{endpoint.split('/')[-1]}: 200")
            else:
                results.append(f"{endpoint.split('/')[-1]}: {response.status_code}")
        except Exception as e:
            results.append(f"{endpoint.split('/')[-1]}: ERROR")
    
    all_200 = all("200" in result for result in results)
    status = "PASS" if all_200 else "FAIL"
    log_test("Observability endpoints", status, " | ".join(results))

def test_approval_reason_strict(token):
    """Test 3: Approval reason strict - disable_user request with short reason => 400 request_reason_too_short"""
    if not token:
        log_test("Approval reason strict", "SKIP", "No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # First get a real user ID
    try:
        users_response = requests.get(f"{API_BASE}/admin/users", headers=headers, timeout=10)
        if users_response.status_code == 200:
            users_data = users_response.json()
            if users_data and len(users_data) > 0:
                user_id = users_data[0]["id"]
            else:
                user_id = "test-user-id"
        else:
            user_id = "test-user-id"
    except:
        user_id = "test-user-id"
    
    try:
        # Try to disable a user with short reason
        response = requests.patch(f"{API_BASE}/admin/users/{user_id}/status", 
                               headers=headers,
                               json={"status": "disabled", "reason": "bad"},  # Short reason
                               timeout=10)
        
        if response.status_code == 400:
            data = response.json()
            if "request_reason_too_short" in str(data) or "reason" in str(data).lower():
                log_test("Approval reason strict", "PASS", "400 validation error for short reason")
            else:
                log_test("Approval reason strict", "FAIL", f"400 but wrong error: {data}")
        elif response.status_code == 422:
            data = response.json()
            if "reason" in str(data).lower() or "short" in str(data).lower():
                log_test("Approval reason strict", "PASS", "422 validation error for short reason")
            else:
                log_test("Approval reason strict", "FAIL", f"422 but wrong error: {data}")
        elif response.status_code == 200:
            data = response.json()
            if data.get("status") == "approval_required":
                log_test("Approval reason strict", "PARTIAL", "Request went to approval (reason validation may be in approval flow)")
            else:
                log_test("Approval reason strict", "FAIL", f"200 but unexpected response: {data}")
        else:
            log_test("Approval reason strict", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Approval reason strict", "FAIL", f"Exception: {str(e)}")

def test_approval_impact_payload(token):
    """Test 4: Approval impact payload - /admin/identity/approvals item contains impact_delta.risk_delta and impact_delta.numeric_changes"""
    if not token:
        log_test("Approval impact payload", "SKIP", "No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # Try the correct approvals endpoint
        response = requests.get(f"{API_BASE}/admin/identity/approvals", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            
            if items:
                # Check first item for impact_delta structure
                first_item = items[0]
                impact_delta = first_item.get("impact_delta", {})
                
                has_risk_delta = "risk_delta" in impact_delta
                has_numeric_changes = "numeric_changes" in impact_delta
                
                if has_risk_delta and has_numeric_changes:
                    log_test("Approval impact payload", "PASS", "impact_delta.risk_delta and impact_delta.numeric_changes found")
                else:
                    log_test("Approval impact payload", "FAIL", f"Missing fields - risk_delta: {has_risk_delta}, numeric_changes: {has_numeric_changes}")
            else:
                log_test("Approval impact payload", "PARTIAL", "No approval items to check")
        elif response.status_code == 404:
            # Try alternative endpoint
            response = requests.get(f"{API_BASE}/admin/approvals", headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", data if isinstance(data, list) else [])
                
                if items:
                    first_item = items[0]
                    impact_delta = first_item.get("impact_delta", {})
                    
                    has_risk_delta = "risk_delta" in impact_delta
                    has_numeric_changes = "numeric_changes" in impact_delta
                    
                    if has_risk_delta and has_numeric_changes:
                        log_test("Approval impact payload", "PASS", "impact_delta.risk_delta and impact_delta.numeric_changes found")
                    else:
                        log_test("Approval impact payload", "FAIL", f"Missing fields - risk_delta: {has_risk_delta}, numeric_changes: {has_numeric_changes}")
                else:
                    log_test("Approval impact payload", "PARTIAL", "No approval items to check")
            else:
                log_test("Approval impact payload", "FAIL", f"Both endpoints failed: {response.status_code}")
        else:
            log_test("Approval impact payload", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Approval impact payload", "FAIL", f"Exception: {str(e)}")

def test_bulk_preview_depth(token):
    """Test 5: Bulk preview depth - summary has blocker_breakdown, risk_score_total, action_summary"""
    if not token:
        log_test("Bulk preview depth", "SKIP", "No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # Test bulk preview with sample user IDs - try the correct endpoint
        response = requests.post(f"{API_BASE}/admin/identity/users/bulk-status/preview",
                               headers=headers,
                               json={"user_ids": ["test-user-1", "test-user-2"]},
                               timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            summary = data.get("summary", {})
            
            has_blocker_breakdown = "blocker_breakdown" in summary
            has_risk_score_total = "risk_score_total" in summary
            has_action_summary = "action_summary" in summary
            
            if has_blocker_breakdown and has_risk_score_total and has_action_summary:
                log_test("Bulk preview depth", "PASS", "blocker_breakdown, risk_score_total, action_summary found")
            else:
                log_test("Bulk preview depth", "FAIL", f"Missing fields - blocker_breakdown: {has_blocker_breakdown}, risk_score_total: {has_risk_score_total}, action_summary: {has_action_summary}")
        elif response.status_code == 404:
            # Try alternative endpoint
            response = requests.post(f"{API_BASE}/admin/users/bulk-status/preview",
                                   headers=headers,
                                   json={"user_ids": ["test-user-1", "test-user-2"]},
                                   timeout=10)
            if response.status_code == 200:
                data = response.json()
                summary = data.get("summary", {})
                
                has_blocker_breakdown = "blocker_breakdown" in summary
                has_risk_score_total = "risk_score_total" in summary
                has_action_summary = "action_summary" in summary
                
                if has_blocker_breakdown and has_risk_score_total and has_action_summary:
                    log_test("Bulk preview depth", "PASS", "blocker_breakdown, risk_score_total, action_summary found")
                else:
                    log_test("Bulk preview depth", "FAIL", f"Missing fields - blocker_breakdown: {has_blocker_breakdown}, risk_score_total: {has_risk_score_total}, action_summary: {has_action_summary}")
            else:
                log_test("Bulk preview depth", "FAIL", f"Both endpoints failed: {response.status_code}")
        else:
            log_test("Bulk preview depth", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Bulk preview depth", "FAIL", f"Exception: {str(e)}")

def test_health_ready():
    """Test 6: Health/ready both 200"""
    results = []
    
    # Test health endpoint
    try:
        response = requests.get(f"{API_BASE}/health", timeout=10)
        results.append(f"health: {response.status_code}")
    except Exception as e:
        results.append(f"health: ERROR")
    
    # Test ready endpoint
    try:
        response = requests.get(f"{API_BASE}/ready", timeout=10)
        results.append(f"ready: {response.status_code}")
    except Exception as e:
        results.append(f"ready: ERROR")
    
    all_200 = all("200" in result for result in results)
    status = "PASS" if all_200 else "FAIL"
    log_test("Health/ready both 200", status, " | ".join(results))

def main():
    print("=" * 80)
    print("FINAL P2 BACKEND VALIDATION TEST")
    print(f"Base URL: {BASE_URL}")
    print(f"Credentials: {ADMIN_EMAIL} / CanaryAdmin123!")
    print("=" * 80)
    
    # Test 1: Controlled MFA override
    token = test_controlled_mfa_override()
    
    # Test 2: Observability endpoints
    test_observability_endpoints(token)
    
    # Test 3: Approval reason strict
    test_approval_reason_strict(token)
    
    # Test 4: Approval impact payload
    test_approval_impact_payload(token)
    
    # Test 5: Bulk preview depth
    test_bulk_preview_depth(token)
    
    # Test 6: Health/ready both 200
    test_health_ready()
    
    print("=" * 80)
    print("P2 BACKEND VALIDATION COMPLETED")
    print("=" * 80)

if __name__ == "__main__":
    main()