#!/usr/bin/env python3
"""
Debug the 422 errors from the final lock test
"""

import requests
import json
import uuid

BASE_URL = "https://unified-orchestrator.preview.emergentagent.com"
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"

def get_token():
    """Get super admin token"""
    session = requests.Session()
    response = session.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={
            "email": SUPER_ADMIN_EMAIL,
            "password": SUPER_ADMIN_PASSWORD
        }
    )
    
    if response.status_code == 200:
        return session.post, response.json().get("access_token")
    return None, None

def debug_playbook_flow():
    """Debug playbook flow"""
    post_func, token = get_token()
    if not token:
        print("❌ Failed to get token")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create preview
    preview_payload = {
        "scope": {
            "correlation_id": f"debug_test_{uuid.uuid4().hex[:8]}"
        },
        "reason": "Debug test"
    }
    
    print("🔍 Creating playbook preview...")
    response = post_func(
        f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
        headers=headers,
        json=preview_payload
    )
    
    print(f"Preview Response: {response.status_code}")
    if response.status_code != 200:
        print(f"Preview Error: {response.text}")
        return
    
    data = response.json()
    playbook_run_id = data.get("playbook_run_id")
    print(f"Playbook Run ID: {playbook_run_id}")
    
    # Try to approve
    approve_payload = {
        "playbook_run_id": playbook_run_id,
        "reason": "Debug approval"
    }
    
    print("\n🔍 Attempting playbook approval...")
    response = post_func(
        f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/approve",
        headers=headers,
        json=approve_payload
    )
    
    print(f"Approve Response: {response.status_code}")
    print(f"Approve Response Body: {response.text}")

def debug_auto_ack():
    """Debug auto-ack flow"""
    post_func, token = get_token()
    if not token:
        print("❌ Failed to get token")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get preview
    print("🔍 Creating auto-ack preview...")
    response = post_func(
        f"{BASE_URL}/api/admin-phase3/auto-ack/preview",
        headers=headers,
        json={"reason": "Debug preview"}
    )
    
    print(f"Preview Response: {response.status_code}")
    if response.status_code != 200:
        print(f"Preview Error: {response.text}")
        return
    
    data = response.json()
    preview_token = data.get("preview_token")
    print(f"Preview Token: {preview_token}")
    
    # Try to run
    run_payload = {
        "preview_token": preview_token,
        "reason": "Debug run"
    }
    
    print("\n🔍 Attempting auto-ack run...")
    response = post_func(
        f"{BASE_URL}/api/admin-phase3/auto-ack/run",
        headers=headers,
        json=run_payload
    )
    
    print(f"Run Response: {response.status_code}")
    print(f"Run Response Body: {response.text}")

if __name__ == "__main__":
    print("🔍 Debugging 422 errors...")
    debug_playbook_flow()
    print("\n" + "="*50)
    debug_auto_ack()