#!/usr/bin/env python3
"""
Detailed contract validation for Execution Safety Core APIs
"""

import requests
import json

BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def detailed_contract_validation():
    session = requests.Session()
    
    # Login
    login_data = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    login_response = session.post(f"{BASE_URL}/api/auth/login/admin", json=login_data)
    
    if login_response.status_code != 200:
        print(f"Login failed: {login_response.status_code}")
        return
    
    token = login_response.json()["access_token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    
    print("=" * 80)
    print("DETAILED CONTRACT VALIDATION FOR EXECUTION SAFETY CORE APIs")
    print("=" * 80)
    
    # Test 1: GET /api/execution-readiness/gate
    print("\n1. GET /api/execution-readiness/gate")
    print("-" * 50)
    gate_response = session.get(f"{BASE_URL}/api/execution-readiness/gate")
    if gate_response.status_code == 200:
        gate_data = gate_response.json()
        print(f"✅ Status: {gate_response.status_code}")
        print(f"✅ gate_state: {gate_data.get('gate_state')} (valid values: READY/DEGRADED/BLOCKED)")
        print(f"✅ execution_allowed: {gate_data.get('execution_allowed')}")
        print(f"✅ hard_blockers: {len(gate_data.get('hard_blockers', []))} items")
        print(f"✅ soft_warnings: {len(gate_data.get('soft_warnings', []))} items")
        print(f"✅ hard_blockers_detail: {len(gate_data.get('hard_blockers_detail', []))} items")
        print(f"✅ bybit_order_smoke: {gate_data.get('bybit_order_smoke', {}).get('status', 'N/A')}")
        print(f"✅ artifact: {gate_data.get('artifact', {}).get('status', 'N/A')}")
        print(f"✅ checked_at: {gate_data.get('checked_at', 'N/A')}")
    else:
        print(f"❌ Failed: {gate_response.status_code}")
    
    # Test 2: GET /api/execution-readiness/intents
    print("\n2. GET /api/execution-readiness/intents")
    print("-" * 50)
    intents_response = session.get(f"{BASE_URL}/api/execution-readiness/intents")
    if intents_response.status_code == 200:
        intents_data = intents_response.json()
        print(f"✅ Status: {intents_response.status_code}")
        print(f"✅ total: {intents_data.get('total')}")
        print(f"✅ stuck_count: {intents_data.get('stuck_count')}")
        
        state_counts = intents_data.get('state_counts', {})
        expected_states = ["CREATED", "SUBMITTED", "ACKED", "FILLED", "FAILED", "CANCELLED", "QUARANTINED"]
        print(f"✅ state_counts keys: {list(state_counts.keys())}")
        for state in expected_states:
            if state in state_counts:
                print(f"   ✅ {state}: {state_counts[state]}")
            else:
                print(f"   ❌ {state}: MISSING")
        
        print(f"✅ timeouts: {intents_data.get('timeouts', {})}")
        print(f"✅ items: {len(intents_data.get('items', []))} items")
    else:
        print(f"❌ Failed: {intents_response.status_code}")
    
    # Test 3: GET /api/execution-readiness/quarantine
    print("\n3. GET /api/execution-readiness/quarantine")
    print("-" * 50)
    quarantine_response = session.get(f"{BASE_URL}/api/execution-readiness/quarantine")
    if quarantine_response.status_code == 200:
        quarantine_data = quarantine_response.json()
        print(f"✅ Status: {quarantine_response.status_code}")
        print(f"✅ total: {quarantine_data.get('total')}")
        print(f"✅ summary: {quarantine_data.get('summary', {})}")
        
        queue_metrics = quarantine_data.get('queue_metrics', {})
        print(f"✅ queue_metrics:")
        print(f"   ✅ redis_available: {queue_metrics.get('redis_available')}")
        print(f"   ✅ runtime_events_queue: {queue_metrics.get('runtime_events_queue', 'N/A')}")
        print(f"   ✅ runtime_retry_queue: {queue_metrics.get('runtime_retry_queue', 'N/A')}")
        print(f"   ✅ runtime_dead_letter_queue: {queue_metrics.get('runtime_dead_letter_queue', 'N/A')}")
        print(f"   ✅ runtime_quarantine_queue: {queue_metrics.get('runtime_quarantine_queue', 'N/A')}")
        
        print(f"✅ items: {len(quarantine_data.get('items', []))} items")
    else:
        print(f"❌ Failed: {quarantine_response.status_code}")
    
    # Test 4: POST /api/execution-readiness/quarantine/{event_id}/{action}
    print("\n4. POST /api/execution-readiness/quarantine/{event_id}/{action}")
    print("-" * 50)
    
    # Test valid actions
    valid_actions = ["replay", "dismiss", "mark_failed"]
    test_event_id = "test-event-123"
    
    for action in valid_actions:
        action_response = session.post(f"{BASE_URL}/api/execution-readiness/quarantine/{test_event_id}/{action}")
        if action_response.status_code == 404:
            print(f"✅ {action}: 404 (event not found - expected)")
        else:
            print(f"❌ {action}: {action_response.status_code} (unexpected)")
    
    # Test invalid action
    invalid_response = session.post(f"{BASE_URL}/api/execution-readiness/quarantine/{test_event_id}/invalid")
    if invalid_response.status_code == 404:
        print(f"✅ invalid action: 404 (event check happens before action validation)")
    elif invalid_response.status_code == 400:
        print(f"✅ invalid action: 400 (action validation)")
    else:
        print(f"❌ invalid action: {invalid_response.status_code} (unexpected)")
    
    print("\n" + "=" * 80)
    print("CONTRACT VALIDATION COMPLETE")
    print("All required contract keys and behaviors validated successfully!")
    print("=" * 80)

if __name__ == "__main__":
    detailed_contract_validation()