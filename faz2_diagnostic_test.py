#!/usr/bin/env python3
"""
FAZ-2 Backend Diagnostic Test
Detailed investigation of API responses for debugging
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://hard-guard-layer.preview.emergentagent.com"
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

def investigate_strategy_overview(token):
    """Investigate strategy control overview response"""
    print("\n🔍 INVESTIGATING STRATEGY CONTROL OVERVIEW")
    print("=" * 60)
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=headers,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response Keys: {list(data.keys())}")
            print(f"Full Response:")
            print(json.dumps(data, indent=2))
            
            # Check specific fields
            if "rollout_policy" in data:
                print(f"\nRollout Policy: {data['rollout_policy']}")
                if "thresholds" in data["rollout_policy"]:
                    print(f"Thresholds: {data['rollout_policy']['thresholds']}")
                else:
                    print("❌ No 'thresholds' in rollout_policy")
            else:
                print("❌ No 'rollout_policy' in response")
                
        else:
            print(f"❌ Error Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")

def investigate_rollout_precheck(token):
    """Investigate rollout precheck response"""
    print("\n🔍 INVESTIGATING ROLLOUT PRECHECK")
    print("=" * 60)
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # First get a strategy ID
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
        
        strategy_id = strategies[0].get("id") or strategies[0].get("strategy_id")
        print(f"Testing with strategy ID: {strategy_id}")
        
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollout-precheck",
            headers=headers,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response Keys: {list(data.keys())}")
            print(f"Full Response:")
            print(json.dumps(data, indent=2))
        else:
            print(f"❌ Error Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")

def investigate_bulk_action(token):
    """Investigate bulk action response"""
    print("\n🔍 INVESTIGATING BULK ACTION")
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
        
        strategy_ids = [s.get("id") or s.get("strategy_id") for s in strategies[:1]]  # Test with 1 strategy
        print(f"Testing with strategy IDs: {strategy_ids}")
        
        # Test pause action
        payload = {
            "strategy_ids": strategy_ids,
            "action": "pause",
            "reason": "Test pause for Faz-2 diagnostic"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"Pause Action - Status Code: {response.status_code}")
        print(f"Pause Action - Response: {response.text}")
        
        if response.status_code == 422:
            try:
                error_data = response.json()
                print(f"Validation Error Details: {json.dumps(error_data, indent=2)}")
            except:
                pass
            
    except Exception as e:
        print(f"❌ Exception: {e}")

def main():
    print("FAZ-2 BACKEND DIAGNOSTIC TEST")
    print("=" * 80)
    
    token = login_and_get_token()
    if not token:
        print("❌ Cannot proceed without token")
        return
    
    investigate_strategy_overview(token)
    investigate_rollout_precheck(token)
    investigate_bulk_action(token)
    
    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()