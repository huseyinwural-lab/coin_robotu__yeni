#!/usr/bin/env python3
"""
Detailed payload inspection for chunked scanner validation
"""

import json
import time
import requests

BASE_URL = "http://127.0.0.1:8001"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

def authenticate():
    response = requests.post(f"{BASE_URL}/api/auth/login/user", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    return response.json().get("access_token") if response.status_code == 200 else None

def wait_and_inspect_payload(token, job_id):
    headers = {"Authorization": f"Bearer {token}"}
    
    while True:
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
        time.sleep(2)

def main():
    print("🔍 Detailed Payload Inspection for Chunked Scanner")
    
    token = authenticate()
    if not token:
        print("❌ Authentication failed")
        return
    
    print("✅ Authenticated successfully")
    
    # Test dual market scanner
    print("\n📋 Testing dual market scanner (market_type=all)...")
    
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
    
    if response.status_code == 200:
        job_data = response.json()
        job_id = job_data.get("job_id")
        print(f"✅ Job created: {job_id}")
        
        print("⏳ Waiting for completion...")
        final_payload = wait_and_inspect_payload(token, job_id)
        
        if final_payload:
            print("\n📊 FINAL PAYLOAD STRUCTURE:")
            print("="*60)
            
            # Show key fields
            key_fields = ["status", "job_type", "chunk_strategy", "chunk_base_size", "timeout_policy"]
            for field in key_fields:
                value = final_payload.get(field)
                print(f"{field}: {value}")
            
            # Show result structure
            result = final_payload.get("result", {})
            if result:
                print(f"\nresult.runs count: {len(result.get('runs', []))}")
                for i, run in enumerate(result.get("runs", [])):
                    market_type = run.get("market_type")
                    status = run.get("status")
                    print(f"  run[{i}]: market_type={market_type}, status={status}")
            
            print("\n📋 FULL PAYLOAD (first 2000 chars):")
            print("-"*60)
            full_json = json.dumps(final_payload, indent=2)
            print(full_json[:2000])
            if len(full_json) > 2000:
                print("... (truncated)")
        else:
            print("❌ Failed to get final payload")
    else:
        print(f"❌ Failed to create job: HTTP {response.status_code}")
    
    # Test spot scanner for chunk fields
    print(f"\n{'='*60}")
    print("📋 Testing spot scanner for chunk fields...")
    
    payload = {
        "market_type": "spot",
        "mode": "AUTO",
        "max_results": 30,
        "symbol_source": "crypto",
        "selected_symbols": [],
        "symbol_selection_mode": "all_market_symbols"
    }
    
    response = requests.post(f"{BASE_URL}/api/user/scanner/run-async", json=payload, headers=headers)
    
    if response.status_code == 200:
        job_data = response.json()
        job_id = job_data.get("job_id")
        print(f"✅ Spot job created: {job_id}")
        
        print("⏳ Waiting for completion...")
        final_payload = wait_and_inspect_payload(token, job_id)
        
        if final_payload:
            result = final_payload.get("result", {})
            scanner_perf = result.get("scanner_perf", {})
            
            print("\n📊 SCANNER_PERF CHUNK FIELDS:")
            print("="*60)
            
            chunk_fields = [
                "chunk_mode_active",
                "chunk_size", 
                "processed_chunk_symbols",
                "total_ranked_symbols",
                "chunk_timeout_budget_seconds"
            ]
            
            for field in chunk_fields:
                value = scanner_perf.get(field, "NOT_FOUND")
                print(f"{field}: {value}")
            
            print(f"\n📋 FULL SCANNER_PERF:")
            print("-"*60)
            print(json.dumps(scanner_perf, indent=2))
        else:
            print("❌ Failed to get spot job final payload")
    else:
        print(f"❌ Failed to create spot job: HTTP {response.status_code}")

if __name__ == "__main__":
    main()