#!/usr/bin/env python3
"""
Focused P2+Escalation Backend Test - Using working credentials
"""

import json
import requests
import time
from datetime import datetime

BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

def test_escalation_endpoints():
    """Test escalation endpoints with working credentials"""
    session = requests.Session()
    
    print("=== P2+ESCALATION FOCUSED BACKEND TEST ===")
    print(f"Test URL: {BASE_URL}")
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    # Login as super admin
    print("1. Logging in as super admin...")
    response = session.post(
        f"{API_BASE}/auth/login/admin",
        json={
            "email": "canary.admin@platform.local",
            "password": "CanaryAdmin123!"
        },
        timeout=30
    )
    
    if response.status_code != 200:
        print(f"❌ Super admin login failed: {response.status_code}")
        return
        
    super_admin_token = response.json().get("access_token")
    print("✅ Super admin login successful")
    
    # Login as admin
    print("\n2. Logging in as admin...")
    time.sleep(1)  # Add delay to avoid rate limiting
    response = session.post(
        f"{API_BASE}/auth/login/admin",
        json={
            "email": "canary.requester@platform.local",
            "password": "CanaryRequester123!"
        },
        timeout=30
    )
    
    if response.status_code != 200:
        print(f"❌ Admin login failed: {response.status_code} - {response.text}")
        return
        
    admin_token = response.json().get("access_token")
    print("✅ Admin login successful")
    
    # Login as ops
    print("\n3. Logging in as ops...")
    time.sleep(1)  # Add delay to avoid rate limiting
    response = session.post(
        f"{API_BASE}/auth/login/admin",
        json={
            "email": "canary.ops@platform.local",
            "password": "CanaryOps123!"
        },
        timeout=30
    )
    
    if response.status_code != 200:
        print(f"❌ Ops login failed: {response.status_code} - {response.text}")
        return
        
    ops_token = response.json().get("access_token")
    print("✅ Ops login successful")
    
    # Test escalation center endpoints
    print("\n4. Testing Escalation Center endpoints...")
    
    # Test GET /api/admin/escalation-center
    print("\n4.1. Testing GET /api/admin/escalation-center...")
    response = session.get(
        f"{API_BASE}/admin/escalation-center",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30
    )
    
    if response.status_code == 200:
        data = response.json()
        required_fields = ["active_breaches", "acknowledged", "resolved"]
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            print(f"❌ Missing required fields: {missing_fields}")
        else:
            print(f"✅ GET /api/admin/escalation-center - Response structure correct")
            print(f"   Active: {len(data.get('active_breaches', []))}, Acknowledged: {len(data.get('acknowledged', []))}, Resolved: {len(data.get('resolved', []))}")
            
            # Check if any escalation items have required fields
            sample_item = None
            for items_list in [data.get("active_breaches", []), data.get("acknowledged", []), data.get("resolved", [])]:
                if items_list:
                    sample_item = items_list[0]
                    break
            
            if sample_item:
                escalation_required_fields = [
                    "breach_age_seconds", "ack_by", "ack_at", "escalation_level", 
                    "escalation_reason", "linked_request_id", "current_owner"
                ]
                missing_escalation_fields = [field for field in escalation_required_fields if field not in sample_item]
                
                if missing_escalation_fields:
                    print(f"❌ Escalation item missing fields: {missing_escalation_fields}")
                else:
                    print("✅ Escalation items have all required fields")
    else:
        print(f"❌ GET /api/admin/escalation-center failed: {response.status_code} - {response.text}")
    
    # Test POST /api/admin/escalation-center/{id}/ack (admin role)
    print("\n4.2. Testing POST /api/admin/escalation-center/{id}/ack (admin role)...")
    test_id = "test_escalation_123"
    response = session.post(
        f"{API_BASE}/admin/escalation-center/{test_id}/ack",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "current_owner": "admin_test",
            "escalation_reason": "Test acknowledgment"
        },
        timeout=30
    )
    
    if response.status_code == 404:
        print("✅ Admin can access ack endpoint (404 for non-existent escalation is expected)")
    elif response.status_code == 200:
        print("✅ Admin successfully acknowledged escalation")
    else:
        print(f"❌ Admin ack failed: {response.status_code} - {response.text}")
    
    # Test POST /api/admin/escalation-center/{id}/resolve (super_admin only)
    print("\n4.3. Testing POST /api/admin/escalation-center/{id}/resolve (super_admin only)...")
    response = session.post(
        f"{API_BASE}/admin/escalation-center/{test_id}/resolve",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        json={
            "escalation_reason": "Test resolution"
        },
        timeout=30
    )
    
    if response.status_code == 404:
        print("✅ Super admin can access resolve endpoint (404 for non-existent escalation is expected)")
    elif response.status_code == 200:
        print("✅ Super admin successfully resolved escalation")
    else:
        print(f"❌ Super admin resolve failed: {response.status_code} - {response.text}")
    
    # Test admin cannot resolve (should get 403)
    print("\n4.4. Testing admin cannot resolve (should get 403)...")
    response = session.post(
        f"{API_BASE}/admin/escalation-center/{test_id}/resolve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "escalation_reason": "Test resolution"
        },
        timeout=30
    )
    
    if response.status_code == 403:
        print("✅ Admin correctly blocked from resolving escalations")
    else:
        print(f"❌ Admin not properly blocked: {response.status_code} - {response.text}")
    
    # Test matrix batch endpoint
    print("\n5. Testing Matrix Batch endpoint...")
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
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
        timeout=30
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Matrix batch simulation successful. Total combinations: {data.get('total_combinations', 0)}")
    elif response.status_code == 400:
        error_text = response.text.lower()
        if "user_id" in error_text or "geçersiz" in error_text:
            print("✅ Matrix batch endpoint accessible (validation error for test user_id is expected)")
        else:
            print(f"❌ Matrix batch unexpected error: {response.text}")
    else:
        print(f"❌ Matrix batch failed: {response.status_code} - {response.text}")
    
    # Test export endpoints
    print("\n6. Testing Export endpoints...")
    
    # Test JSON export
    response = session.get(
        f"{API_BASE}/admin/strategy-intelligence/export",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={
            "export_format": "json",
            "dataset": "decision_requests"
        },
        timeout=30
    )
    
    if response.status_code == 200:
        print(f"✅ JSON export successful, response size: {len(response.content)} bytes")
    else:
        print(f"❌ JSON export failed: {response.status_code} - {response.text}")
    
    # Test CSV export
    response = session.get(
        f"{API_BASE}/admin/strategy-intelligence/export",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={
            "export_format": "csv",
            "dataset": "simulation_history"
        },
        timeout=30
    )
    
    if response.status_code == 200:
        content_type = response.headers.get("content-type", "")
        print(f"✅ CSV export successful, content-type: {content_type}")
    else:
        print(f"❌ CSV export failed: {response.status_code} - {response.text}")
    
    # Test import endpoint
    print("\n7. Testing Import endpoint...")
    test_import_data = {
        "import_type": "decision_requests",
        "data": [
            {
                "request_type": "test_import",
                "status": "pending",
                "reason_note": "Test import data"
            }
        ]
    }
    
    response = session.post(
        f"{API_BASE}/admin/strategy-intelligence/import-json",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=test_import_data,
        timeout=30
    )
    
    if response.status_code == 200:
        print("✅ Import endpoint accessible and functional")
    elif response.status_code == 400:
        print("✅ Import endpoint accessible (validation error for test data is expected)")
    elif response.status_code == 403:
        print("❌ Import endpoint blocked (403 Forbidden)")
    else:
        print(f"❌ Import failed: {response.status_code} - {response.text}")
    
    # Test role-based access control
    print("\n8. Testing Role-based Access Control...")
    
    # Test ops can view escalation center
    response = session.get(
        f"{API_BASE}/admin/escalation-center",
        headers={"Authorization": f"Bearer {ops_token}"},
        timeout=30
    )
    
    if response.status_code == 200:
        print("✅ Ops can view escalation center")
    elif response.status_code == 403:
        print("❌ Ops blocked from viewing escalation center")
    else:
        print(f"❌ Ops escalation center access: {response.status_code}")
    
    # Test ops cannot acknowledge escalations
    response = session.post(
        f"{API_BASE}/admin/escalation-center/test_123/ack",
        headers={"Authorization": f"Bearer {ops_token}"},
        json={"current_owner": "ops_test", "escalation_reason": "Test"},
        timeout=30
    )
    
    if response.status_code == 403:
        print("✅ Ops correctly blocked from acknowledging escalations")
    else:
        print(f"❌ Ops not properly blocked from ack: {response.status_code}")
    
    print("\n=== TEST COMPLETED ===")

if __name__ == "__main__":
    test_escalation_endpoints()