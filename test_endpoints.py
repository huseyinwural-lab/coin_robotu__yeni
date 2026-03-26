#!/usr/bin/env python3
"""
Simple endpoint discovery test
"""

import sys
sys.path.insert(0, '/app/backend')

from fastapi.testclient import TestClient
from server import fastapi_app

def test_endpoints():
    client = TestClient(fastapi_app)
    
    # Login first
    login_resp = client.post("/api/auth/login", json={
        "email": "canary.admin@platform.local",
        "password": "CanaryAdmin123!"
    })
    
    if login_resp.status_code != 200:
        print(f"❌ Login failed: {login_resp.status_code}")
        return
    
    token = login_resp.json().get("access_token") or login_resp.json().get("token")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test various endpoints
    endpoints_to_test = [
        "/api/admin/commercial/overview",
        "/api/admin/commercial/monthly-pnl/export",
        "/api/admin/commercial/exports/schedules",
        "/api/admin/commercial/usage-logs",
        "/api/admin/commercial/total-pnl"
    ]
    
    for endpoint in endpoints_to_test:
        try:
            resp = client.get(endpoint, headers=headers)
            print(f"✅ {endpoint}: {resp.status_code}")
            if resp.status_code >= 400:
                print(f"   Error: {resp.text[:200]}")
        except Exception as e:
            print(f"❌ {endpoint}: Exception - {e}")
    
    # Test POST endpoint
    try:
        user_id = login_resp.json().get("user", {}).get("id")
        if user_id:
            control_payload = {
                "trading_enabled": True,
                "capital_frozen": False,
                "withdraw_locked": False,
                "emergency_stop": False,
                "reason_note": "test"
            }
            resp = client.post(f"/api/admin/commercial/controls/{user_id}", headers=headers, json=control_payload)
            print(f"✅ POST /api/admin/commercial/controls/{user_id}: {resp.status_code}")
            if resp.status_code >= 400:
                print(f"   Error: {resp.text[:200]}")
    except Exception as e:
        print(f"❌ POST controls: Exception - {e}")

if __name__ == "__main__":
    test_endpoints()