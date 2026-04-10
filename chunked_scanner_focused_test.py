#!/usr/bin/env python3
"""
Focused test for Turkish review request: Yeni chunked scanner akışını backend seviyede doğrula.

Exact requirements:
1) POST /api/user/scanner/run-async market_type=all -> job tamamlanmalı, status completed dönmeli.
2) GET /api/user/scanner/run-async/{job_id} final payload içinde şu alanlar olmalı:
   - job_type=dual_market
   - chunk_strategy=market+symbol
   - chunk_base_size=150
   - timeout_policy=adaptive
   - result.runs içinde spot ve futures leg status
3) POST /api/user/scanner/run-async market_type=spot -> job stuck olmadan tamamlanmalı (reasonable sürede completed veya failed ama running'de sonsuz kalmamalı).
4) Spot job result.scanner_perf içinde chunk alanları dönmeli:
   - chunk_mode_active
   - chunk_size
   - processed_chunk_symbols
   - total_ranked_symbols
   - chunk_timeout_budget_seconds

Çıktı: PASS/FAIL + kısa bulgu.
"""

import json
import time
import requests
from typing import Dict, Any, Optional

# Test configuration
BASE_URL = "http://127.0.0.1:8001"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

def authenticate() -> Optional[str]:
    """Authenticate and return token"""
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login/user", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        
        if response.status_code == 200:
            token = response.json().get("access_token")
            print(f"✅ Authentication successful")
            return token
        else:
            print(f"❌ Authentication failed: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Authentication error: {str(e)}")
        return None

def wait_for_job(token: str, job_id: str, max_wait: int = 120) -> Optional[Dict[str, Any]]:
    """Wait for job completion"""
    headers = {"Authorization": f"Bearer {token}"}
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(f"{BASE_URL}/api/user/scanner/run-async/{job_id}", headers=headers)
            if response.status_code == 200:
                payload = response.json()
                status = payload.get("status")
                
                if status == "completed":
                    return payload
                elif status == "failed":
                    return payload
                elif status in ["queued", "running"]:
                    time.sleep(2)
                    continue
                else:
                    return payload
            else:
                print(f"❌ Status check failed: HTTP {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Status check error: {str(e)}")
            time.sleep(2)
    
    return None

def test_requirement_1(token: str) -> tuple[bool, str]:
    """Test 1: POST /api/user/scanner/run-async market_type=all -> job tamamlanmalı, status completed dönmeli"""
    print("\n1) POST /api/user/scanner/run-async market_type=all")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "market_type": "all",
            "mode": "AUTO",
            "max_results": 50,
            "symbol_source": "crypto",
            "selected_symbols": [],
            "symbol_selection_mode": "all_market_symbols"
        }
        
        response = requests.post(f"{BASE_URL}/api/user/scanner/run-async", json=payload, headers=headers)
        
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}"
        
        data = response.json()
        job_id = data.get("job_id")
        
        if not job_id:
            return False, "No job_id returned"
        
        print(f"   Job created: {job_id}")
        
        # Wait for completion
        final_payload = wait_for_job(token, job_id)
        
        if not final_payload:
            return False, "Job timed out"
        
        status = final_payload.get("status")
        if status == "completed":
            return True, f"Job completed successfully"
        else:
            return False, f"Job status: {status}"
            
    except Exception as e:
        return False, f"Exception: {str(e)}"

def test_requirement_2(token: str) -> tuple[bool, str]:
    """Test 2: Final payload fields validation"""
    print("\n2) GET /api/user/scanner/run-async/{job_id} final payload field validation")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "market_type": "all",
            "mode": "AUTO",
            "max_results": 50,
            "symbol_source": "crypto",
            "selected_symbols": [],
            "symbol_selection_mode": "all_market_symbols"
        }
        
        response = requests.post(f"{BASE_URL}/api/user/scanner/run-async", json=payload, headers=headers)
        
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}"
        
        job_id = response.json().get("job_id")
        final_payload = wait_for_job(token, job_id)
        
        if not final_payload or final_payload.get("status") != "completed":
            return False, "Job did not complete"
        
        # Check required fields
        required_fields = {
            "job_type": "dual_market",
            "chunk_strategy": "market+symbol", 
            "chunk_base_size": 150,
            "timeout_policy": "adaptive"
        }
        
        missing_or_wrong = []
        for field, expected_value in required_fields.items():
            actual_value = final_payload.get(field)
            if actual_value != expected_value:
                missing_or_wrong.append(f"{field}={actual_value} (expected {expected_value})")
        
        if missing_or_wrong:
            return False, f"Field issues: {', '.join(missing_or_wrong)}"
        
        # Check result.runs for spot and futures
        result = final_payload.get("result", {})
        runs = result.get("runs", [])
        
        spot_found = any(run.get("market_type") == "spot" for run in runs)
        futures_found = any(run.get("market_type") == "futures" for run in runs)
        
        if not spot_found:
            return False, "No spot leg in result.runs"
        if not futures_found:
            return False, "No futures leg in result.runs"
        
        return True, "All required fields present and correct"
        
    except Exception as e:
        return False, f"Exception: {str(e)}"

def test_requirement_3(token: str) -> tuple[bool, str]:
    """Test 3: Spot job should not get stuck"""
    print("\n3) POST /api/user/scanner/run-async market_type=spot -> job stuck olmadan tamamlanmalı")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "market_type": "spot",
            "mode": "AUTO",
            "max_results": 30,
            "symbol_source": "crypto",
            "selected_symbols": [],
            "symbol_selection_mode": "all_market_symbols"
        }
        
        response = requests.post(f"{BASE_URL}/api/user/scanner/run-async", json=payload, headers=headers)
        
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}"
        
        job_id = response.json().get("job_id")
        print(f"   Spot job created: {job_id}")
        
        # Wait with reasonable timeout (90 seconds)
        final_payload = wait_for_job(token, job_id, max_wait=90)
        
        if not final_payload:
            return False, "Job stuck - did not complete in reasonable time (90s)"
        
        status = final_payload.get("status")
        if status in ["completed", "failed"]:
            return True, f"Job finished with status: {status} (not stuck)"
        else:
            return False, f"Job stuck in status: {status}"
            
    except Exception as e:
        return False, f"Exception: {str(e)}"

def test_requirement_4(token: str) -> tuple[bool, str]:
    """Test 4: Spot job scanner_perf chunk fields"""
    print("\n4) Spot job result.scanner_perf chunk fields validation")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "market_type": "spot",
            "mode": "AUTO",
            "max_results": 30,
            "symbol_source": "crypto",
            "selected_symbols": [],
            "symbol_selection_mode": "all_market_symbols"
        }
        
        response = requests.post(f"{BASE_URL}/api/user/scanner/run-async", json=payload, headers=headers)
        
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}"
        
        job_id = response.json().get("job_id")
        final_payload = wait_for_job(token, job_id)
        
        if not final_payload or final_payload.get("status") != "completed":
            return False, "Job did not complete successfully"
        
        # Check scanner_perf chunk fields
        result = final_payload.get("result", {})
        scanner_perf = result.get("scanner_perf", {})
        
        if not scanner_perf:
            return False, "No scanner_perf in result"
        
        required_chunk_fields = [
            "chunk_mode_active",
            "chunk_size",
            "processed_chunk_symbols", 
            "total_ranked_symbols",
            "chunk_timeout_budget_seconds"
        ]
        
        missing_fields = []
        for field in required_chunk_fields:
            if field not in scanner_perf:
                missing_fields.append(field)
        
        if missing_fields:
            return False, f"Missing chunk fields: {missing_fields}"
        
        # Show values for verification
        chunk_info = {field: scanner_perf[field] for field in required_chunk_fields}
        return True, f"All chunk fields present: {chunk_info}"
        
    except Exception as e:
        return False, f"Exception: {str(e)}"

def main():
    """Main test execution"""
    print("🧪 Chunked Scanner Backend Validation")
    print(f"Base URL: {BASE_URL}")
    print(f"User: {USER_EMAIL}")
    
    # Authenticate
    token = authenticate()
    if not token:
        print("\n❌ OVERALL RESULT: FAIL - Authentication failed")
        return
    
    # Run tests
    tests = [
        ("Test 1: market_type=all job completion", test_requirement_1),
        ("Test 2: Final payload field validation", test_requirement_2),
        ("Test 3: Spot job not stuck", test_requirement_3),
        ("Test 4: Spot scanner_perf chunk fields", test_requirement_4)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        success, message = test_func(token)
        results.append((test_name, success, message))
        
        if success:
            print(f"   ✅ PASS: {message}")
        else:
            print(f"   ❌ FAIL: {message}")
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 FINAL RESULTS")
    print(f"{'='*60}")
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for i, (test_name, success, message) in enumerate(results, 1):
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{i}) {status} - {message}")
    
    print(f"\n📈 OVERALL: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 PASS - All chunked scanner requirements validated successfully")
    else:
        print("⚠️ FAIL - Some chunked scanner requirements not met")
    
    # Turkish output as requested
    print(f"\n🇹🇷 Çıktı: {'PASS' if passed == total else 'FAIL'} + kısa bulgu:")
    for i, (_, success, message) in enumerate(results, 1):
        status = "PASS" if success else "FAIL"
        short_msg = message[:80] + "..." if len(message) > 80 else message
        print(f"   {i}) {status} - {short_msg}")

if __name__ == "__main__":
    main()