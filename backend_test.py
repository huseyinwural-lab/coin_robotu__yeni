#!/usr/bin/env python3
"""
Focused Backend Regression Check for 502 Outage
Target: https://deploy-blocker-6.preview.emergentagent.com
Tests: GET /api/health, GET /api/ready, GET /api/
"""

import requests
import json
from datetime import datetime

def test_502_regression():
    """
    Focused regression check for recent 502 outage.
    Tests the 3 specific endpoints requested.
    """
    
    BASE_URL = "https://deploy-blocker-6.preview.emergentagent.com"
    
    print("=" * 60)
    print("FOCUSED BACKEND REGRESSION CHECK - 502 OUTAGE")
    print(f"Target: {BASE_URL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    results = {
        "target_url": BASE_URL,
        "test_time": datetime.now().isoformat(),
        "endpoints_tested": 3,
        "endpoints_passed": 0,
        "endpoints_failed": 0,
        "tests": {}
    }
    
    # Configure session with timeout
    session = requests.Session()
    session.timeout = 10
    
    # Test 1: GET /api/health
    print("\n1) Testing GET /api/health")
    try:
        response = session.get(f"{BASE_URL}/api/health")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response: {data}")
                
                if "status" in data and data["status"] == "ok":
                    print("   ✅ PASS - Returns 200 with status=ok")
                    results["endpoints_passed"] += 1
                    results["tests"]["health"] = {
                        "status": "PASS", 
                        "code": 200, 
                        "response": data,
                        "has_status_ok": True
                    }
                else:
                    print("   ❌ FAIL - Missing status=ok field")
                    results["endpoints_failed"] += 1
                    results["tests"]["health"] = {
                        "status": "FAIL", 
                        "code": 200, 
                        "response": data,
                        "has_status_ok": False,
                        "error": "Missing status=ok field"
                    }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response: {response.text[:100]}")
                results["endpoints_failed"] += 1
                results["tests"]["health"] = {
                    "status": "FAIL", 
                    "code": 200, 
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            results["endpoints_failed"] += 1  
            results["tests"]["health"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}"
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["health"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 2: GET /api/ready  
    print("\n2) Testing GET /api/ready")
    try:
        response = session.get(f"{BASE_URL}/api/ready")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response: {data}")
                
                # Check for database ready indicators
                db_ready = False
                if "database" in data:
                    if isinstance(data["database"], dict) and data["database"].get("status") == "ready":
                        db_ready = True
                    elif isinstance(data["database"], str) and "ready" in data["database"].lower():
                        db_ready = True
                elif "ready" in data or data.get("status") == "ready":
                    db_ready = True
                elif "checks" in data and isinstance(data["checks"], dict):
                    if "database" in data["checks"] and isinstance(data["checks"]["database"], dict):
                        if data["checks"]["database"].get("status") == "ready":
                            db_ready = True
                
                if db_ready:
                    print("   ✅ PASS - Returns 200 with database ready")
                    results["endpoints_passed"] += 1
                    results["tests"]["ready"] = {
                        "status": "PASS", 
                        "code": 200, 
                        "response": data,
                        "database_ready": True
                    }
                else:
                    print("   ❌ FAIL - Database not ready")
                    results["endpoints_failed"] += 1
                    results["tests"]["ready"] = {
                        "status": "FAIL", 
                        "code": 200, 
                        "response": data,
                        "database_ready": False,
                        "error": "Database not ready"
                    }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response: {response.text[:100]}")
                results["endpoints_failed"] += 1
                results["tests"]["ready"] = {
                    "status": "FAIL", 
                    "code": 200, 
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["ready"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}"
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["ready"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 3: GET /api/
    print("\n3) Testing GET /api/")
    try:
        response = session.get(f"{BASE_URL}/api/")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response: {data}")
                
                # Check for root payload (any valid JSON with content)
                if data and len(str(data)) > 10:  # Basic check for meaningful content
                    print("   ✅ PASS - Returns 200 with root payload")
                    results["endpoints_passed"] += 1
                    results["tests"]["root"] = {
                        "status": "PASS", 
                        "code": 200, 
                        "response": data,
                        "has_payload": True
                    }
                else:
                    print("   ❌ FAIL - Empty or minimal payload")
                    results["endpoints_failed"] += 1
                    results["tests"]["root"] = {
                        "status": "FAIL", 
                        "code": 200, 
                        "response": data,
                        "has_payload": False,
                        "error": "Empty or minimal payload"
                    }
            except json.JSONDecodeError:
                # Maybe it's text or HTML
                if len(response.text) > 10:
                    print(f"   ✅ PASS - Returns 200 with root payload (non-JSON): {response.text[:50]}...")
                    results["endpoints_passed"] += 1
                    results["tests"]["root"] = {
                        "status": "PASS", 
                        "code": 200, 
                        "response": response.text[:200],
                        "has_payload": True,
                        "content_type": "non-JSON"
                    }
                else:
                    print(f"   ❌ FAIL - Empty response: {response.text}")
                    results["endpoints_failed"] += 1
                    results["tests"]["root"] = {
                        "status": "FAIL", 
                        "code": 200, 
                        "error": "Empty response"
                    }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["root"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}"
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["root"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Summary
    print("\n" + "=" * 60)
    print("REGRESSION CHECK SUMMARY")
    print("=" * 60)
    print(f"Endpoints Tested: {results['endpoints_tested']}")
    print(f"✅ Passed: {results['endpoints_passed']}")
    print(f"❌ Failed: {results['endpoints_failed']}")
    
    overall_status = "PASS" if results['endpoints_failed'] == 0 else "FAIL"
    print(f"\n🎯 OVERALL STATUS: {overall_status}")
    
    if results['endpoints_failed'] > 0:
        print("\n🚨 REMAINING BLOCKERS:")
        for endpoint, test in results['tests'].items():
            if test['status'] == 'FAIL':
                error = test.get('error', 'Unknown error')
                code = test.get('code', 'N/A')
                print(f"   - {endpoint.upper()}: {error} (HTTP {code})")
    else:
        print("\n✅ NO BLOCKERS - All endpoints operational")
    
    print("=" * 60)
    
    return results

if __name__ == "__main__":
    results = test_502_regression()