#!/usr/bin/env python3
"""
FAZ-2 Bulk Action Investigation
Detailed investigation of bulk action responses for forbidden actions
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://exec-tuning.preview.emergentagent.com"
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"

def login_and_get_token():
    """Login and get super admin token"""
    try:
        login_data = {
            "email": SUPER_ADMIN_EMAIL,
            "password": SUPER_ADMIN_PASSWORD
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json=login_data,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            print(f"✅ Login successful, token length: {len(token)}")
            return token
        else:
            print(f"❌ Login failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Login error: {e}")
        return None

def investigate_forbidden_actions(token):
    """Investigate forbidden bulk actions in detail"""
    print("\n🔍 INVESTIGATING FORBIDDEN BULK ACTIONS")
    print("=" * 60)
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get strategy IDs
        overview_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=headers,
            timeout=30
        )
        
        if overview_response.status_code != 200:
            print("❌ Could not get strategy list")
            return
        
        strategies = overview_response.json().get("strategies", [])
        if not strategies:
            print("❌ No strategies available")
            return
        
        strategy_ids = [s.get("strategy_id") for s in strategies[:1]]  # Test with 1 strategy
        print(f"Testing with strategy IDs: {strategy_ids}")
        
        # Test forbidden actions
        forbidden_actions = ["disable", "decommission"]
        
        for action in forbidden_actions:
            print(f"\n--- Testing {action.upper()} action ---")
            
            payload = {
                "strategy_ids": strategy_ids,
                "action": action,
                "reason": f"Test bulk {action} for Faz-2 investigation",
                "confirm_phrase": f"CONFIRM BULK {action.upper()}"
            }
            
            print(f"Payload: {json.dumps(payload, indent=2)}")
            
            response = requests.post(
                f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}")
            print(f"Response Body: {response.text}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"Response JSON: {json.dumps(data, indent=2)}")
                except:
                    pass
            
            print("-" * 40)
            
    except Exception as e:
        print(f"❌ Exception: {e}")

def main():
    print("FAZ-2 BULK ACTION INVESTIGATION")
    print("=" * 80)
    
    token = login_and_get_token()
    if not token:
        print("❌ Cannot proceed without token")
        return
    
    investigate_forbidden_actions(token)
    
    print("\n" + "=" * 80)
    print("INVESTIGATION COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()