#!/usr/bin/env python3
"""
Scanner Anomaly Audit Endpoint Validation
Target: https://dry-run-shadow.preview.emergentagent.com
Tests: User login, POST /api/user/scanner/runtime/anomaly-event, validation tests, health check
"""

import requests
import json
from datetime import datetime

def test_scanner_anomaly_audit():
    """
    Backend API validation for newly added scanner anomaly audit endpoint.
    
    Tests:
    1) Login user via POST /api/auth/login/user and extract token
    2) POST /api/user/scanner/runtime/anomaly-event with valid payload
    3) Negative validation test: fail_ratio > 1 should return validation error (422)
    4) Optional sanity: /api/health still 200
    """
    
    BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
    USER_EMAIL = "canary_1774010877@example.com"
    USER_PASSWORD = "TestPass123!"
    
    print("=" * 80)
    print("SCANNER ANOMALY AUDIT ENDPOINT VALIDATION")
    print(f"Target: {BASE_URL}")
    print(f"User: {USER_EMAIL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("=" * 80)
    
    results = {
        "target_url": BASE_URL,
        "user_email": USER_EMAIL,
        "test_time": datetime.now().isoformat(),
        "tests_total": 4,
        "tests_passed": 0,
        "tests_failed": 0,
        "tests": {}
    }
    
    # Configure session with timeout
    session = requests.Session()
    session.timeout = 15
    
    # Test 1: User Login and Token Extraction
    print("\n1) Testing User Login - POST /api/auth/login/user")
    try:
        login_payload = {
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }
        
        response = session.post(f"{BASE_URL}/api/auth/login/user", json=login_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                access_token = data.get("access_token")
                
                if access_token:
                    print(f"   ✅ PASS - Login successful, token extracted")
                    print(f"   Token: {access_token[:20]}...")
                    results["tests_passed"] += 1
                    results["tests"]["user_login"] = {
                        "status": "PASS",
                        "code": 200,
                        "token_extracted": True,
                        "token_length": len(access_token)
                    }
                    
                    # Set authorization header for subsequent requests
                    session.headers.update({"Authorization": f"Bearer {access_token}"})
                    
                else:
                    print(f"   ❌ FAIL - No access_token in response")
                    print(f"   Response: {data}")
                    results["tests_failed"] += 1
                    results["tests"]["user_login"] = {
                        "status": "FAIL",
                        "code": 200,
                        "error": "No access_token in response",
                        "response": data
                    }
                    return results  # Cannot continue without token
                    
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response: {response.text[:100]}")
                results["tests_failed"] += 1
                results["tests"]["user_login"] = {
                    "status": "FAIL",
                    "code": 200,
                    "error": "Invalid JSON response"
                }
                return results
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data}")
            except:
                print(f"   Error: {response.text[:100]}")
            results["tests_failed"] += 1
            results["tests"]["user_login"] = {
                "status": "FAIL",
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}"
            }
            return results
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["tests_failed"] += 1
        results["tests"]["user_login"] = {
            "status": "FAIL",
            "error": f"Request failed: {str(e)}"
        }
        return results
    
    # Test 2: Valid Anomaly Event Submission
    print("\n2) Testing Valid Anomaly Event - POST /api/user/scanner/runtime/anomaly-event")
    try:
        valid_payload = {
            "source": "scanner_ui",
            "fail_ratio": 0.12,
            "total_requests": 50,
            "failed_requests": 6,
            "success_requests": 44,
            "trend_window_minutes": 15,
            "trend_points": [
                {
                    "label": "3m",
                    "total": 10,
                    "success": 9,
                    "fail": 1,
                    "success_ratio": 0.9
                }
            ]
        }
        
        response = session.post(f"{BASE_URL}/api/user/scanner/runtime/anomaly-event", json=valid_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response: {data}")
                
                # Check for expected response fields
                required_fields = ["status", "audit_log_id", "logged_at"]
                has_all_fields = all(field in data for field in required_fields)
                status_logged = data.get("status") == "logged"
                
                if has_all_fields and status_logged:
                    print(f"   ✅ PASS - Returns 200 with expected fields")
                    print(f"   Status: {data.get('status')}")
                    print(f"   Audit Log ID: {data.get('audit_log_id')}")
                    print(f"   Logged At: {data.get('logged_at')}")
                    results["tests_passed"] += 1
                    results["tests"]["valid_anomaly_event"] = {
                        "status": "PASS",
                        "code": 200,
                        "response": data,
                        "has_required_fields": True,
                        "status_logged": True
                    }
                else:
                    print(f"   ❌ FAIL - Missing required fields or incorrect status")
                    print(f"   Expected: status=logged, audit_log_id, logged_at")
                    print(f"   Got: {data}")
                    results["tests_failed"] += 1
                    results["tests"]["valid_anomaly_event"] = {
                        "status": "FAIL",
                        "code": 200,
                        "error": "Missing required fields or incorrect status",
                        "response": data,
                        "has_required_fields": has_all_fields,
                        "status_logged": status_logged
                    }
                    
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response: {response.text[:100]}")
                results["tests_failed"] += 1
                results["tests"]["valid_anomaly_event"] = {
                    "status": "FAIL",
                    "code": 200,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data}")
            except:
                print(f"   Error: {response.text[:100]}")
            results["tests_failed"] += 1
            results["tests"]["valid_anomaly_event"] = {
                "status": "FAIL",
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}"
            }
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["tests_failed"] += 1
        results["tests"]["valid_anomaly_event"] = {
            "status": "FAIL",
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 3: Negative Validation Test (fail_ratio > 1)
    print("\n3) Testing Negative Validation - fail_ratio > 1 should return 422")
    try:
        invalid_payload = {
            "source": "scanner_ui",
            "fail_ratio": 1.5,  # Invalid: > 1
            "total_requests": 50,
            "failed_requests": 75,  # More fails than total (also invalid)
            "success_requests": 44,
            "trend_window_minutes": 15,
            "trend_points": [
                {
                    "label": "3m",
                    "total": 10,
                    "success": 9,
                    "fail": 1,
                    "success_ratio": 0.9
                }
            ]
        }
        
        response = session.post(f"{BASE_URL}/api/user/scanner/runtime/anomaly-event", json=invalid_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 422:
            try:
                data = response.json()
                print(f"   ✅ PASS - Returns 422 validation error as expected")
                print(f"   Error: {data}")
                results["tests_passed"] += 1
                results["tests"]["negative_validation"] = {
                    "status": "PASS",
                    "code": 422,
                    "response": data,
                    "validation_working": True
                }
            except json.JSONDecodeError:
                print(f"   ✅ PASS - Returns 422 (validation error text): {response.text[:100]}")
                results["tests_passed"] += 1
                results["tests"]["negative_validation"] = {
                    "status": "PASS",
                    "code": 422,
                    "response": response.text[:200],
                    "validation_working": True
                }
        elif response.status_code == 400:
            # 400 is also acceptable for validation errors
            try:
                data = response.json()
                print(f"   ✅ PASS - Returns 400 validation error (acceptable)")
                print(f"   Error: {data}")
                results["tests_passed"] += 1
                results["tests"]["negative_validation"] = {
                    "status": "PASS",
                    "code": 400,
                    "response": data,
                    "validation_working": True
                }
            except json.JSONDecodeError:
                print(f"   ✅ PASS - Returns 400 (validation error text): {response.text[:100]}")
                results["tests_passed"] += 1
                results["tests"]["negative_validation"] = {
                    "status": "PASS",
                    "code": 400,
                    "response": response.text[:200],
                    "validation_working": True
                }
        else:
            print(f"   ❌ FAIL - Expected 422 or 400, got {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Unexpected response: {error_data}")
            except:
                print(f"   Unexpected response: {response.text[:100]}")
            results["tests_failed"] += 1
            results["tests"]["negative_validation"] = {
                "status": "FAIL",
                "code": response.status_code,
                "error": f"Expected 422 or 400, got {response.status_code}",
                "validation_working": False
            }
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["tests_failed"] += 1
        results["tests"]["negative_validation"] = {
            "status": "FAIL",
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 4: Health Check Sanity Test
    print("\n4) Testing Health Check Sanity - GET /api/health")
    try:
        # Remove auth header for health check
        health_session = requests.Session()
        health_session.timeout = 10
        
        response = health_session.get(f"{BASE_URL}/api/health")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response: {data}")
                
                if "status" in data and data["status"] == "ok":
                    print("   ✅ PASS - Health check still returns 200 with status=ok")
                    results["tests_passed"] += 1
                    results["tests"]["health_sanity"] = {
                        "status": "PASS",
                        "code": 200,
                        "response": data,
                        "health_ok": True
                    }
                else:
                    print("   ❌ FAIL - Health check missing status=ok")
                    results["tests_failed"] += 1
                    results["tests"]["health_sanity"] = {
                        "status": "FAIL",
                        "code": 200,
                        "response": data,
                        "health_ok": False,
                        "error": "Missing status=ok field"
                    }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response: {response.text[:100]}")
                results["tests_failed"] += 1
                results["tests"]["health_sanity"] = {
                    "status": "FAIL",
                    "code": 200,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            results["tests_failed"] += 1
            results["tests"]["health_sanity"] = {
                "status": "FAIL",
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}"
            }
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["tests_failed"] += 1
        results["tests"]["health_sanity"] = {
            "status": "FAIL",
            "error": f"Request failed: {str(e)}"
        }
    
    # Summary
    print("\n" + "=" * 80)
    print("SCANNER ANOMALY AUDIT VALIDATION SUMMARY")
    print("=" * 80)
    print(f"Tests Total: {results['tests_total']}")
    print(f"✅ Passed: {results['tests_passed']}")
    print(f"❌ Failed: {results['tests_failed']}")
    
    overall_status = "PASS" if results['tests_failed'] == 0 else "FAIL"
    success_rate = (results['tests_passed'] / results['tests_total']) * 100
    print(f"\n🎯 OVERALL STATUS: {overall_status} ({success_rate:.1f}% success rate)")
    
    # Detailed results
    print("\n📋 DETAILED RESULTS:")
    test_names = {
        "user_login": "1) User Login & Token Extraction",
        "valid_anomaly_event": "2) Valid Anomaly Event Submission", 
        "negative_validation": "3) Negative Validation (fail_ratio > 1)",
        "health_sanity": "4) Health Check Sanity"
    }
    
    for test_key, test_name in test_names.items():
        if test_key in results['tests']:
            test = results['tests'][test_key]
            status_icon = "✅" if test['status'] == 'PASS' else "❌"
            code = test.get('code', 'N/A')
            print(f"   {status_icon} {test_name}: {test['status']} (HTTP {code})")
            if test['status'] == 'FAIL' and 'error' in test:
                print(f"      Error: {test['error']}")
        else:
            print(f"   ⚠️  {test_name}: NOT EXECUTED")
    
    if results['tests_failed'] > 0:
        print(f"\n🚨 ISSUES FOUND:")
        for test_key, test in results['tests'].items():
            if test['status'] == 'FAIL':
                error = test.get('error', 'Unknown error')
                code = test.get('code', 'N/A')
                print(f"   - {test_names.get(test_key, test_key)}: {error} (HTTP {code})")
    else:
        print(f"\n✅ ALL TESTS PASSED - Scanner anomaly audit endpoint working correctly")
    
    print("=" * 80)
    
    return results

if __name__ == "__main__":
    results = test_scanner_anomaly_audit()