#!/usr/bin/env python3
"""
Diagnostic test for missing endpoints and alert structure
"""

import sys
sys.path.insert(0, '/app/backend')

from fastapi.testclient import TestClient
from server import fastapi_app

def diagnostic_test():
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
    
    # Check runtime execution endpoints
    runtime_endpoints = [
        "/api/runtime/execution/submit",
        "/api/user/execution/submit",
        "/api/admin/execution/submit",
        "/api/execution/submit"
    ]
    
    print("🔍 Checking runtime execution endpoints:")
    for endpoint in runtime_endpoints:
        try:
            resp = client.post(endpoint, headers=headers, json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 1.0,
                "confidence": 0.7,
                "strategy_name": "test",
                "mark_price": 100.0,
                "leverage": 1
            })
            print(f"   {endpoint}: {resp.status_code}")
        except Exception as e:
            print(f"   {endpoint}: Exception - {e}")
    
    # Check alert structure
    print("\n🔍 Checking alert structure:")
    try:
        overview_resp = client.get("/api/admin/commercial/overview", headers=headers)
        if overview_resp.status_code == 200:
            data = overview_resp.json()
            alert_rail = data.get("alert_rail", [])
            print(f"   Alert count: {len(alert_rail)}")
            if alert_rail:
                alert = alert_rail[0]
                print(f"   Alert keys: {list(alert.keys())}")
                print(f"   Sample alert: {alert}")
            else:
                print("   No alerts found")
        else:
            print(f"   Overview failed: {overview_resp.status_code}")
    except Exception as e:
        print(f"   Alert check exception: {e}")

if __name__ == "__main__":
    diagnostic_test()