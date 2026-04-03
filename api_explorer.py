#!/usr/bin/env python3
"""
Quick API exploration for Strategy Domain endpoints
"""

import requests
import json

def explore_api():
    base_url = "https://trade-trace-engine.preview.emergentagent.com"
    session = requests.Session()
    
    # Login
    login_url = f"{base_url}/api/auth/login"
    payload = {
        "email": "canary.admin@platform.local",
        "password": "CanaryAdmin123!",
        "panel": "admin"
    }
    
    response = session.post(login_url, json=payload, timeout=30)
    if response.status_code == 200:
        data = response.json()
        token = data.get('access_token')
        session.headers.update({'Authorization': f'Bearer {token}'})
        print("✅ Login successful")
    else:
        print("❌ Login failed")
        return
    
    # Test various endpoints
    endpoints_to_test = [
        "/api/strategy-domain/admin/strategies",
        "/api/strategy-domain/admin/strategies/ops",
        "/api/strategy-domain/admin/strategies/0a72d022-e93c-4231-9927-69b9abcac622/versions",
        "/api/strategy-domain/admin/strategies/0a72d022-e93c-4231-9927-69b9abcac622/audit-history/export?format_type=csv",
        "/api/strategy-domain/admin/strategies/0a72d022-e93c-4231-9927-69b9abcac622/regime-binding",
        "/api/strategy-domain/admin/regime-bindings",
        "/api/strategy-domain/admin/promotions",
        "/api/strategy-domain/admin/versions",
    ]
    
    for endpoint in endpoints_to_test:
        url = f"{base_url}{endpoint}"
        try:
            response = session.get(url, timeout=10)
            print(f"{endpoint}: HTTP {response.status_code}")
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, list):
                        print(f"  -> List with {len(data)} items")
                        if data and isinstance(data[0], dict):
                            print(f"  -> First item keys: {list(data[0].keys())}")
                    elif isinstance(data, dict):
                        print(f"  -> Dict with keys: {list(data.keys())}")
                except:
                    print(f"  -> Content length: {len(response.text)}")
        except Exception as e:
            print(f"{endpoint}: ERROR - {str(e)}")

if __name__ == "__main__":
    explore_api()