#!/usr/bin/env python3
"""
Test scope application separately
"""

import requests
import json
import time

# Test configuration
BASE_URL = "http://127.0.0.1:8001"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

def test_scope_application():
    """Test scope application with shorter timeout"""
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
    
    # Test with include_futures=false and manual scope
    config_data = {
        "include_futures": False,
        "market_scope": {
            "spot_mode": "manual"
        },
        "manual_symbols": ["BTCUSDT", "ETHUSDT"],
        "scan_limit": 100
    }
    
    print(f"📤 Saving config: {json.dumps(config_data, indent=2)}")
    
    # Save config first
    config_response = session.post(
        f"{BASE_URL}/api/user/scanner-engine/config/save",
        json=config_data,
        timeout=30
    )
    
    if config_response.status_code == 200:
        print("✅ Config saved successfully")
        
        # Try synchronous scanner run first (shorter timeout)
        print("📤 Running synchronous scanner...")
        run_response = session.post(
            f"{BASE_URL}/api/user/scanner/run",
            json={
                "market_type": "spot",
                "manual_symbols": config_data["manual_symbols"]
            },
            timeout=15  # Shorter timeout
        )
        
        if run_response.status_code == 200:
            run_data = run_response.json()
            print(f"✅ Scanner run successful")
            print(f"📥 Response: {json.dumps(run_data, indent=2)}")
            
            # Check if candidate_count is narrowed
            candidate_count = run_data.get('candidate_count', 0)
            result_count = run_data.get('result_count', 0)
            
            print(f"🔍 Analysis:")
            print(f"  - candidate_count: {candidate_count}")
            print(f"  - result_count: {result_count}")
            print(f"  - manual_symbols: {len(config_data['manual_symbols'])}")
            print(f"  - scan_limit: {config_data['scan_limit']}")
            
            if candidate_count <= 10:  # Reasonable limit for manual symbols
                print("✅ Scope application: candidate_count properly narrowed")
            else:
                print("❌ Scope application: candidate_count not properly narrowed")
                
        else:
            print(f"❌ Scanner run failed: HTTP {run_response.status_code}")
            print(f"Response: {run_response.text}")
    else:
        print(f"❌ Config save failed: HTTP {config_response.status_code}")
        print(f"Response: {config_response.text}")

if __name__ == "__main__":
    test_scope_application()