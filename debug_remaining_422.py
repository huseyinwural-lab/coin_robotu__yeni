#!/usr/bin/env python3
"""
Debug remaining 422 errors
"""

import requests
import json
import uuid

BASE_URL = "https://deploy-blocker-6.preview.emergentagent.com"
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
        return session, response.json().get("access_token")
    return None, None

def debug_rollback():
    """Debug rollback"""
    session, token = get_token()
    if not token:
        print("❌ Failed to get token")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create and execute a playbook first
    preview_payload = {
        "scope": {
            "correlation_id": f"rollback_test_{uuid.uuid4().hex[:8]}"
        },
        "reason": "Rollback test"
    }
    
    print("🔍 Creating playbook for rollback test...")
    response = session.post(
        f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
        headers=headers,
        json=preview_payload
    )
    
    if response.status_code != 200:
        print(f"Preview failed: {response.text}")
        return
    
    data = response.json()
    playbook_run_id = data.get("playbook_run_id")
    
    # Approve
    approve_payload = {
        "playbook_run_id": playbook_run_id,
        "reason": "Rollback test approval",
        "confirm": True
    }
    
    response = session.post(
        f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/approve",
        headers=headers,
        json=approve_payload
    )
    
    if response.status_code != 200:
        print(f"Approve failed: {response.text}")
        return
    
    # Execute
    execute_payload = {
        "playbook_run_id": playbook_run_id,
        "reason": "Rollback test execution",
        "confirm": True
    }
    
    response = session.post(
        f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/execute",
        headers=headers,
        json=execute_payload
    )
    
    if response.status_code != 200:
        print(f"Execute failed: {response.text}")
        return
    
    print("✅ Playbook executed, now testing rollback...")
    
    # Try rollback
    rollback_payload = {
        "playbook_run_id": playbook_run_id,
        "reason": "Rollback test"
    }
    
    response = session.post(
        f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/rollback",
        headers=headers,
        json=rollback_payload
    )
    
    print(f"Rollback Response: {response.status_code}")
    print(f"Rollback Response Body: {response.text}")

def debug_auto_ack_detailed():
    """Debug auto-ack with more detail"""
    session, token = get_token()
    if not token:
        print("❌ Failed to get token")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get preview
    print("🔍 Creating auto-ack preview...")
    response = session.post(
        f"{BASE_URL}/api/admin-phase3/auto-ack/preview",
        headers=headers,
        json={"reason": "Debug preview"}
    )
    
    if response.status_code != 200:
        print(f"Preview failed: {response.text}")
        return
    
    data = response.json()
    preview_token = data.get("preview_token")
    print(f"Preview Token: {preview_token}")
    print(f"Full preview response: {json.dumps(data, indent=2)}")
    
    # Try different ways to call run
    print("\n🔍 Trying auto-ack run with query params...")
    response = session.post(
        f"{BASE_URL}/api/admin-phase3/auto-ack/run",
        headers=headers,
        params={"preview_token": preview_token, "reason": "Debug run"}
    )
    
    print(f"Query params response: {response.status_code}")
    print(f"Query params response body: {response.text}")
    
    print("\n🔍 Trying auto-ack run with JSON body...")
    response = session.post(
        f"{BASE_URL}/api/admin-phase3/auto-ack/run",
        headers=headers,
        json={"preview_token": preview_token, "reason": "Debug run"}
    )
    
    print(f"JSON body response: {response.status_code}")
    print(f"JSON body response body: {response.text}")

if __name__ == "__main__":
    print("🔍 Debugging remaining 422 errors...")
    debug_rollback()
    print("\n" + "="*50)
    debug_auto_ack_detailed()