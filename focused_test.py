#!/usr/bin/env python3
"""
Focused Turkish Patch Validation Test
Testing specific issues found in the initial test
"""

import requests
import json
import time

# Test configuration
BASE_URL = "http://127.0.0.1:8001"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

def test_config_save_issue():
    """Test the config save issue specifically"""
    session = requests.Session()
    
    # Login
    login_response = session.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=30
    )
    
    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.status_code}")
        return
    
    token = login_response.json().get('access_token')
    session.headers.update({'Authorization': f'Bearer {token}'})
    
    print("✅ Login successful")
    
    # Test config save
    config_data = {
        "signal_mode": "manual",
        "manual_symbols": ["BTCUSDT", "ETHUSDT", "ADAUSDT"],
        "scan_limit": 1500,
        "market_scope": {
            "spot_mode": "manual",
            "futures_mode": "all"
        },
        "include_futures": False
    }
    
    print(f"📤 Sending config: {json.dumps(config_data, indent=2)}")
    
    config_response = session.post(
        f"{BASE_URL}/api/user/scanner-engine/config/save",
        json=config_data,
        timeout=30
    )
    
    print(f"📥 Response status: {config_response.status_code}")
    
    if config_response.status_code == 200:
        response_data = config_response.json()
        print(f"📥 Response data: {json.dumps(response_data, indent=2)}")
        
        # Check what we got back
        print("\n🔍 VALIDATION RESULTS:")
        print(f"signal_mode: sent='{config_data['signal_mode']}', received='{response_data.get('signal_mode')}'")
        print(f"manual_symbols: sent={config_data['manual_symbols']}, received={response_data.get('manual_symbols')}")
        print(f"scan_limit: sent={config_data['scan_limit']}, received={response_data.get('scan_limit')}")
        print(f"market_scope: sent={config_data['market_scope']}, received={response_data.get('market_scope')}")
        print(f"include_futures: sent={config_data['include_futures']}, received={response_data.get('include_futures')}")
    else:
        print(f"❌ Config save failed: {config_response.text}")
    
    # Also check what the GET endpoint returns
    print("\n🔍 CHECKING GET CONFIG:")
    get_response = session.get(f"{BASE_URL}/api/user/scanner-engine/config", timeout=30)
    if get_response.status_code == 200:
        get_data = get_response.json()
        print(f"📥 GET config data: {json.dumps(get_data, indent=2)}")
    else:
        print(f"❌ GET config failed: {get_response.text}")

def test_scanner_run_async_progress():
    """Test the scanner run async progress fields issue"""
    session = requests.Session()
    
    # Login
    login_response = session.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=30
    )
    
    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.status_code}")
        return
    
    token = login_response.json().get('access_token')
    session.headers.update({'Authorization': f'Bearer {token}'})
    
    print("✅ Login successful")
    
    # Start scanner run
    run_response = session.post(
        f"{BASE_URL}/api/user/scanner/run-async",
        json={
            "market_type": "spot",
            "manual_symbols": ["BTCUSDT", "ETHUSDT"]
        },
        timeout=10
    )
    
    print(f"📥 Run response status: {run_response.status_code}")
    
    if run_response.status_code == 200:
        run_data = run_response.json()
        print(f"📥 Run response: {json.dumps(run_data, indent=2)}")
        
        job_id = run_data.get('job_id')
        if job_id:
            print(f"\n🔍 CHECKING STATUS FOR JOB: {job_id}")
            
            # Check status multiple times
            for i in range(3):
                time.sleep(2)
                status_response = session.get(
                    f"{BASE_URL}/api/user/scanner/run-async/{job_id}",
                    timeout=30
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    print(f"📥 Status check {i+1}: {json.dumps(status_data, indent=2)}")
                    
                    # Check for progress fields
                    progress_fields = ['progress', 'processed_count', 'total_count', 'current_batch', 'total_batches']
                    found_progress = [field for field in progress_fields if field in status_data]
                    print(f"🔍 Progress fields found: {found_progress}")
                else:
                    print(f"❌ Status check {i+1} failed: {status_response.text}")
        else:
            print("❌ No job_id in response")
    else:
        print(f"❌ Scanner run failed: {run_response.text}")

if __name__ == "__main__":
    print("🔍 FOCUSED TURKISH PATCH VALIDATION")
    print("=" * 50)
    
    print("\n1️⃣ TESTING CONFIG SAVE ISSUE:")
    test_config_save_issue()
    
    print("\n2️⃣ TESTING SCANNER RUN ASYNC PROGRESS:")
    test_scanner_run_async_progress()