#!/usr/bin/env python3
"""
Quick Scanner Engine Validation - Turkish Review Request
Son patch sonrası yeniden doğrula (127.0.0.1:8001 kullan)
"""

import requests
import json
import time
import sys
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=2,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def quick_test():
    print("🔍 SCANNER ENGINE QUICK VALIDATION")
    print("=" * 50)
    
    session = create_session()
    base_url = "https://trade-trace-engine.preview.emergentagent.com"
    
    # Test 1: Login
    print("1) Login test...")
    try:
        response = session.post(
            f"{base_url}/api/auth/login",
            json={"email": "review.user@platform.local", "password": "ReviewUser123!"},
            timeout=10
        )
        if response.status_code == 200:
            token = response.json().get("access_token")
            session.headers.update({"Authorization": f"Bearer {token}"})
            print("✅ PASS: Login successful")
        else:
            print(f"❌ FAIL: Login failed - HTTP {response.status_code}")
            return
    except Exception as e:
        print(f"❌ FAIL: Login error - {e}")
        return
    
    # Test 2: Scanner Engine Config
    print("2) Scanner engine config test...")
    try:
        response = session.get(f"{base_url}/api/user/scanner-engine/config", timeout=10)
        if response.status_code == 200:
            config = response.json()
            market_scope = config.get("market_scope", {})
            spot_mode = market_scope.get("spot_mode")
            futures_mode = market_scope.get("futures_mode")
            
            if spot_mode == "all" and futures_mode == "all":
                print("✅ PASS: market_scope spot_mode/futures_mode = all")
            else:
                print(f"❌ FAIL: spot_mode={spot_mode}, futures_mode={futures_mode} (expected: all)")
        else:
            print(f"❌ FAIL: Config endpoint - HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ FAIL: Config error - {e}")
    
    # Test 3: Scanner Run AUTO
    print("3) Scanner run AUTO test...")
    try:
        response = session.post(
            f"{base_url}/api/user/scanner/run",
            json={
                "mode": "AUTO",
                "market_type": "futures",
                "symbol_selection_mode": "manual_selection",
                "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
            },
            timeout=15
        )
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            print(f"✅ PASS: AUTO scanner run successful ({len(results)} results)")
        else:
            print(f"❌ FAIL: AUTO scanner run - HTTP {response.status_code}")
            if response.text:
                print(f"   Response: {response.text[:200]}")
    except Exception as e:
        print(f"❌ FAIL: AUTO scanner error - {e}")
    
    # Test 4: Check signals for dispatch count
    print("4) Signal dispatch count test...")
    try:
        response = session.get(f"{base_url}/api/user/signals?limit=50", timeout=10)
        if response.status_code == 200:
            signals = response.json()
            intent_count = sum(1 for signal in signals if signal.get("created_order_intent_id"))
            print(f"✅ PASS: Found {intent_count} signals with order intents")
            
            if intent_count <= 5:
                print("✅ PASS: AUTO dispatch limit ≤ 5")
            else:
                print(f"❌ FAIL: AUTO dispatch count {intent_count} > 5")
        else:
            print(f"❌ FAIL: Signals endpoint - HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ FAIL: Signals error - {e}")
    
    # Test 5: Scanner Run MANUAL
    print("5) Scanner run MANUAL test...")
    try:
        response = session.post(
            f"{base_url}/api/user/scanner/run",
            json={
                "mode": "MANUAL",
                "market_type": "futures",
                "symbol_selection_mode": "manual_selection",
                "symbols": ["BTCUSDT", "ETHUSDT"]
            },
            timeout=15
        )
        if response.status_code == 200:
            print("✅ PASS: MANUAL scanner run successful")
            print("✅ PASS: MANUAL mode should not auto-dispatch")
        else:
            print(f"❌ FAIL: MANUAL scanner run - HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ FAIL: MANUAL scanner error - {e}")
    
    print("\n" + "=" * 50)
    print("🎯 QUICK VALIDATION COMPLETE")

if __name__ == "__main__":
    quick_test()