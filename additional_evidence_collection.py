#!/usr/bin/env python3
"""
Additional Evidence Collection for GO/NO-GO Assessment
Focus on the HIGH RISK areas identified
"""

import requests
import json
import time

BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

def get_auth_tokens():
    """Get both admin and user tokens"""
    # Admin token
    admin_response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30
    )
    admin_token = admin_response.json().get("access_token") if admin_response.status_code == 200 else None
    
    # User token
    user_response = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=30
    )
    user_token = user_response.json().get("access_token") if user_response.status_code == 200 else None
    
    return admin_token, user_token

def detailed_market_data_test(user_token):
    """Test market data endpoints for real vs mock evidence"""
    print("\n=== DETAILED MARKET DATA EVIDENCE ===")
    headers = {"Authorization": f"Bearer {user_token}"}
    
    # Test multiple symbols
    symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
    evidence = []
    
    for symbol in symbols:
        try:
            response = requests.get(
                f"{BASE_URL}/api/market/ticker?symbol={symbol}",
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                price = data.get("price", 0)
                timestamp = data.get("timestamp")
                environment = data.get("environment", "unknown")
                
                print(f"   {symbol}: price={price}, env={environment}, timestamp={timestamp}")
                
                if price == 0:
                    evidence.append(f"MOCK: {symbol} price=0")
                elif price > 0:
                    evidence.append(f"REAL: {symbol} price={price}")
                else:
                    evidence.append(f"UNKNOWN: {symbol} price={price}")
            else:
                evidence.append(f"ERROR: {symbol} HTTP {response.status_code}")
                print(f"   {symbol}: HTTP {response.status_code}")
        except Exception as e:
            evidence.append(f"ERROR: {symbol} {str(e)}")
            print(f"   {symbol}: Exception {e}")
    
    return evidence

def detailed_scanner_test(user_token):
    """Test scanner endpoints for functionality"""
    print("\n=== DETAILED SCANNER EVIDENCE ===")
    headers = {"Authorization": f"Bearer {user_token}"}
    
    evidence = []
    
    # Test scanner config
    try:
        config_response = requests.get(
            f"{BASE_URL}/api/user/scanner-engine/config",
            headers=headers,
            timeout=10
        )
        if config_response.status_code == 200:
            evidence.append("WORKING: Scanner config endpoint accessible")
            print("   ✅ Scanner config: HTTP 200")
        else:
            evidence.append(f"BROKEN: Scanner config HTTP {config_response.status_code}")
            print(f"   ❌ Scanner config: HTTP {config_response.status_code}")
    except Exception as e:
        evidence.append(f"BROKEN: Scanner config {str(e)}")
        print(f"   ❌ Scanner config: {e}")
    
    # Test scanner run with timeout
    try:
        print("   Testing scanner run (15s timeout)...")
        run_response = requests.post(
            f"{BASE_URL}/api/user/scanner-engine/run-async",
            json={"scan_limit": 50},
            headers=headers,
            timeout=15
        )
        if run_response.status_code == 200:
            evidence.append("WORKING: Scanner run successful")
            print("   ✅ Scanner run: HTTP 200")
        else:
            evidence.append(f"BROKEN: Scanner run HTTP {run_response.status_code}")
            print(f"   ❌ Scanner run: HTTP {run_response.status_code}")
    except requests.exceptions.Timeout:
        evidence.append("BROKEN: Scanner run timeout (15s)")
        print("   ❌ Scanner run: TIMEOUT")
    except Exception as e:
        evidence.append(f"BROKEN: Scanner run {str(e)}")
        print(f"   ❌ Scanner run: {e}")
    
    return evidence

def detailed_strategy_allocation_test(admin_token):
    """Test strategy allocation endpoint"""
    print("\n=== DETAILED STRATEGY ALLOCATION EVIDENCE ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    evidence = []
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            evidence.append("WORKING: Strategy allocation accessible")
            print("   ✅ Strategy allocation: HTTP 200")
        else:
            evidence.append(f"BROKEN: Strategy allocation HTTP {response.status_code}")
            print(f"   ❌ Strategy allocation: HTTP {response.status_code}")
            
            # Get response body for more details
            try:
                error_body = response.text[:200]
                print(f"   Error body: {error_body}")
                evidence.append(f"Error details: {error_body}")
            except:
                pass
                
    except Exception as e:
        evidence.append(f"BROKEN: Strategy allocation {str(e)}")
        print(f"   ❌ Strategy allocation: {e}")
    
    return evidence

def test_concurrent_scanner_detailed(user_token):
    """Detailed concurrent scanner test"""
    print("\n=== DETAILED CONCURRENT SCANNER TEST ===")
    headers = {"Authorization": f"Bearer {user_token}"}
    
    import concurrent.futures
    
    def single_scanner_call(call_id):
        try:
            start_time = time.time()
            response = requests.post(
                f"{BASE_URL}/api/user/scanner-engine/run-async",
                json={"scan_limit": 10},
                headers=headers,
                timeout=10
            )
            end_time = time.time()
            
            return {
                "call_id": call_id,
                "status": response.status_code,
                "duration": round(end_time - start_time, 2),
                "response": response.json() if response.status_code == 200 else response.text[:100]
            }
        except Exception as e:
            return {
                "call_id": call_id,
                "status": "ERROR",
                "error": str(e)
            }
    
    # Execute 5 concurrent calls
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(single_scanner_call, i) for i in range(5)]
        results = [f.result() for f in futures]
    
    # Analyze results
    success_count = sum(1 for r in results if r.get("status") == 200)
    conflict_count = sum(1 for r in results if r.get("status") == 409)
    error_count = sum(1 for r in results if r.get("status") not in [200, 409])
    
    print(f"   Results: {success_count} success, {conflict_count} conflicts, {error_count} errors")
    
    for result in results:
        status = result.get("status")
        duration = result.get("duration", "N/A")
        call_id = result.get("call_id")
        print(f"   Call {call_id}: {status} ({duration}s)")
    
    evidence = [
        f"Concurrent scanner calls: {success_count} success, {conflict_count} conflicts, {error_count} errors",
        f"Total calls: {len(results)}"
    ]
    
    return evidence, results

def main():
    print("ADDITIONAL EVIDENCE COLLECTION FOR GO/NO-GO ASSESSMENT")
    print("="*60)
    
    # Get tokens
    admin_token, user_token = get_auth_tokens()
    
    if not admin_token or not user_token:
        print("❌ Authentication failed")
        return
    
    print("✅ Authentication successful")
    
    # Collect detailed evidence
    market_evidence = detailed_market_data_test(user_token)
    scanner_evidence = detailed_scanner_test(user_token)
    strategy_evidence = detailed_strategy_allocation_test(admin_token)
    concurrent_evidence, concurrent_results = test_concurrent_scanner_detailed(user_token)
    
    # Summary
    print("\n" + "="*60)
    print("EVIDENCE SUMMARY")
    print("="*60)
    
    print("\n1) MARKET DATA EVIDENCE:")
    for evidence in market_evidence:
        print(f"   - {evidence}")
    
    print("\n2) SCANNER EVIDENCE:")
    for evidence in scanner_evidence:
        print(f"   - {evidence}")
    
    print("\n3) STRATEGY ALLOCATION EVIDENCE:")
    for evidence in strategy_evidence:
        print(f"   - {evidence}")
    
    print("\n4) CONCURRENT SCANNER EVIDENCE:")
    for evidence in concurrent_evidence:
        print(f"   - {evidence}")
    
    # Save detailed results
    detailed_results = {
        "timestamp": time.time(),
        "market_evidence": market_evidence,
        "scanner_evidence": scanner_evidence,
        "strategy_evidence": strategy_evidence,
        "concurrent_evidence": concurrent_evidence,
        "concurrent_results": concurrent_results
    }
    
    with open("/app/additional_evidence.json", "w") as f:
        json.dump(detailed_results, f, indent=2)
    
    print(f"\n✅ Additional evidence saved to /app/additional_evidence.json")

if __name__ == "__main__":
    main()