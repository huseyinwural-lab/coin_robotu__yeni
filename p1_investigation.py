#!/usr/bin/env python3
"""
P1 Backend Investigation - Deep dive into failing endpoints
"""

import requests
import json

BASE_URL = "https://risk-orchestrator-p0.preview.emergentagent.com"
SUPER_ADMIN_CREDS = {
    "email": "canary.admin@platform.local",
    "password": "CanaryAdmin123!"
}

def login_user(credentials):
    """Login and get access token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json=credentials,
        timeout=30
    )
    
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token", "")
    return None

def investigate_broken_chain(token):
    """Investigate broken chain response"""
    print("🔍 INVESTIGATING BROKEN CHAIN RESPONSE")
    
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/api/admin/strategy/timeline/p1-broken-chain-001?window=7d&strategy_id=seed_strategy"
    
    response = requests.get(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        print(f"Status: {response.status_code}")
        print(f"Response keys: {list(data.keys())}")
        print(f"Summary: {data.get('summary', {})}")
        print(f"Broken links count: {data.get('broken_links_count', 'NOT_FOUND')}")
        print(f"Invalid reasons: {data.get('invalid_reasons', 'NOT_FOUND')}")
        
        # Check if broken_links_count is in summary
        summary = data.get('summary', {})
        print(f"Summary broken_links_count: {summary.get('broken_links_count', 'NOT_FOUND')}")
        print(f"Summary invalid_reasons: {summary.get('invalid_reasons', 'NOT_FOUND')}")
        
        return data
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None

def investigate_action_impact_timeline(token):
    """Investigate action-impact-timeline response"""
    print("\n🔍 INVESTIGATING ACTION-IMPACT-TIMELINE RESPONSE")
    
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/api/admin/strategy/action-impact-timeline"
    
    response = requests.get(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        print(f"Status: {response.status_code}")
        print(f"Response type: {type(data)}")
        
        if isinstance(data, list):
            print(f"List length: {len(data)}")
            if data:
                print(f"First item keys: {list(data[0].keys()) if data[0] else 'Empty'}")
                print(f"First item: {data[0]}")
        elif isinstance(data, dict):
            print(f"Dict keys: {list(data.keys())}")
            print(f"Full response: {json.dumps(data, indent=2)}")
        
        return data
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None

def investigate_preflight_endpoint(token):
    """Investigate preflight endpoint response"""
    print("\n🔍 INVESTIGATING PREFLIGHT ENDPOINT RESPONSE")
    
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight"
    
    response = requests.get(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        print(f"Status: {response.status_code}")
        print(f"Response keys: {list(data.keys())}")
        print(f"Checks: {data.get('checks', {})}")
        print(f"Migration: {data.get('migration', {})}")
        
        # Print full response for analysis
        print(f"Full response: {json.dumps(data, indent=2)}")
        
        return data
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None

def main():
    print("🔍 P1 Backend Investigation Starting...")
    
    # Login
    token = login_user(SUPER_ADMIN_CREDS)
    if not token:
        print("❌ Login failed")
        return
    
    print("✅ Authenticated successfully")
    
    # Investigate each failing endpoint
    broken_chain_data = investigate_broken_chain(token)
    action_impact_data = investigate_action_impact_timeline(token)
    preflight_data = investigate_preflight_endpoint(token)
    
    # Save investigation results
    investigation_results = {
        "broken_chain": broken_chain_data,
        "action_impact_timeline": action_impact_data,
        "preflight": preflight_data
    }
    
    with open("/app/p1_investigation_results.json", "w") as f:
        json.dump(investigation_results, f, indent=2)
    
    print(f"\n📄 Investigation results saved to: /app/p1_investigation_results.json")

if __name__ == "__main__":
    main()