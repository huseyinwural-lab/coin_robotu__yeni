#!/usr/bin/env python3
"""
FAZ-4 Backend API Response Investigation
"""

import requests
import json

BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"

def get_admin_token():
    """Get admin token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get('access_token')
    return None

def investigate_apis():
    """Investigate actual API responses"""
    token = get_admin_token()
    if not token:
        print("Failed to get admin token")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    strategy_id = "trend_follow_v1"
    
    print("=" * 80)
    print("FAZ-4 API RESPONSE INVESTIGATION")
    print("=" * 80)
    
    # Test feedback-label
    print("\n1. POST feedback-label response:")
    payload = {
        "drift_alert_id": "test_drift_alert_123",
        "taxonomy": "performance_degradation",
        "label": "confirmed_drift",
        "corrected_label": "performance_issue",
        "reason_taxonomy": "market_volatility",
        "context": {"strategy_context": "trend_following"},
        "reason": "Test reason"
    }
    response = requests.post(
        f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback-label",
        headers=headers,
        json=payload
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response keys: {list(data.keys())}")
        print(f"Full response: {json.dumps(data, indent=2)}")
    else:
        print(f"Error: {response.text}")
    
    # Test trigger-model-update
    print("\n2. POST trigger-model-update response:")
    payload = {
        "update_type": "retrain",
        "priority": "high",
        "reason": "Performance degradation detected",
        "confirm_phrase": "TRIGGER MODEL UPDATE"
    }
    response = requests.post(
        f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/trigger-model-update",
        headers=headers,
        json=payload
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response keys: {list(data.keys())}")
        print(f"Full response: {json.dumps(data, indent=2)}")
    else:
        print(f"Error: {response.text}")
    
    # Test model-update-status
    print("\n3. GET model-update-status response:")
    response = requests.get(
        f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/model-update-status",
        headers=headers
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response keys: {list(data.keys())}")
        print(f"Full response: {json.dumps(data, indent=2)}")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    investigate_apis()