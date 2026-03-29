#!/usr/bin/env python3
"""
Focused test for the POST quarantine action endpoint
"""

import requests
import json
import uuid

BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def test_post_endpoint():
    session = requests.Session()
    
    # Login
    login_data = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    login_response = session.post(f"{BASE_URL}/api/auth/login/admin", json=login_data)
    
    if login_response.status_code != 200:
        print(f"Login failed: {login_response.status_code}")
        return
    
    token = login_response.json()["access_token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    
    # Test invalid action
    test_event_id = str(uuid.uuid4())
    invalid_response = session.post(
        f"{BASE_URL}/api/execution-readiness/quarantine/{test_event_id}/invalid_action"
    )
    
    print(f"Invalid action response: {invalid_response.status_code}")
    if invalid_response.status_code != 200:
        print(f"Response body: {invalid_response.text}")
    
    # Test valid action with non-existent event
    valid_response = session.post(
        f"{BASE_URL}/api/execution-readiness/quarantine/{test_event_id}/replay"
    )
    
    print(f"Valid action (non-existent event) response: {valid_response.status_code}")
    if valid_response.status_code != 200:
        print(f"Response body: {valid_response.text}")

if __name__ == "__main__":
    test_post_endpoint()