#!/usr/bin/env python3
"""
FAZ-3 Drift Action Center Backend Investigation
Investigate actual API structure and endpoints
"""

import requests
import json

BASE_URL = "https://audit-closure-dash.preview.emergentagent.com"
SUPER_ADMIN_CREDS = {
    "email": "canary.admin@platform.local",
    "password": "CanaryAdmin123!"
}
OPS_CREDS = {
    "email": "canary.ops@platform.local", 
    "password": "CanaryOps123!"
}

def login_super_admin():
    """Login as super admin"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json=SUPER_ADMIN_CREDS,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            print(f"✅ Super Admin Login: Success (token length: {len(token)})")
            return token
        else:
            print(f"❌ Super Admin Login: HTTP {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Super Admin Login: Exception: {str(e)}")
        return None

def login_ops():
    """Try different ops login methods"""
    # Try admin login first
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json=OPS_CREDS,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            print(f"✅ Ops Login (admin endpoint): Success (token length: {len(token)})")
            return token
        else:
            print(f"❌ Ops Login (admin endpoint): HTTP {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"❌ Ops Login (admin endpoint): Exception: {str(e)}")
        
    # Try user login
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json=OPS_CREDS,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            print(f"✅ Ops Login (user endpoint): Success (token length: {len(token)})")
            return token
        else:
            print(f"❌ Ops Login (user endpoint): HTTP {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"❌ Ops Login (user endpoint): Exception: {str(e)}")
        
    return None

def investigate_drift_endpoints(token):
    """Investigate available drift-related endpoints"""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test different possible endpoint paths
    endpoints_to_test = [
        "/api/admin/futures/strategy-control/drift-alerts",
        "/api/admin/futures/strategy-control/overview",
        "/api/admin/futures/strategy-control",
        "/api/admin/futures/drift-alerts",
        "/api/futures/strategy-control/drift-alerts",
        "/api/drift-alerts",
    ]
    
    print("\n=== INVESTIGATING DRIFT ENDPOINTS ===")
    for endpoint in endpoints_to_test:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=30)
            print(f"{endpoint}: HTTP {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"  Response keys: {list(data.keys())}")
                if "items" in data:
                    print(f"  Items count: {len(data['items'])}")
                    if data['items']:
                        print(f"  First item keys: {list(data['items'][0].keys())}")
                        
        except Exception as e:
            print(f"{endpoint}: Exception: {str(e)}")

def test_strategy_control_overview(token):
    """Test strategy control overview to understand structure"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n=== STRATEGY CONTROL OVERVIEW ===")
            print(f"Response keys: {list(data.keys())}")
            
            if "strategies" in data:
                strategies = data["strategies"]
                print(f"Strategies count: {len(strategies)}")
                if strategies:
                    print(f"First strategy keys: {list(strategies[0].keys())}")
                    strategy_id = strategies[0].get("id")
                    print(f"First strategy ID: {strategy_id}")
                    
                    # Test action endpoints with real strategy ID
                    test_action_endpoints(token, strategy_id)
                    
        else:
            print(f"Strategy control overview: HTTP {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"Strategy control overview: Exception: {str(e)}")

def test_action_endpoints(token, strategy_id):
    """Test action endpoints with real strategy ID"""
    headers = {"Authorization": f"Bearer {token}"}
    
    actions = ["ack", "mute", "ignore", "disable-strategy", "retrain"]
    
    print(f"\n=== TESTING ACTION ENDPOINTS (Strategy: {strategy_id}) ===")
    
    for action in actions:
        # Try different URL patterns
        urls_to_test = [
            f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts/{strategy_id}/{action}",
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/drift/{action}",
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/{action}",
        ]
        
        for url in urls_to_test:
            try:
                # Test with minimal payload
                payload = {"reason": "Test action"}
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                print(f"{action} ({url.split('/')[-3:]}): HTTP {response.status_code}")
                
                if response.status_code not in [404, 405]:
                    print(f"  Response: {response.text[:200]}")
                    break  # Found working endpoint
                    
            except Exception as e:
                print(f"{action}: Exception: {str(e)}")

if __name__ == "__main__":
    print("=== FAZ-3 DRIFT ACTION CENTER INVESTIGATION ===")
    
    # Login
    super_admin_token = login_super_admin()
    ops_token = login_ops()
    
    if super_admin_token:
        investigate_drift_endpoints(super_admin_token)
        test_strategy_control_overview(super_admin_token)
    else:
        print("❌ Cannot proceed without super admin token")