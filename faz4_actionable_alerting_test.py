#!/usr/bin/env python3
"""
FAZ-4 Actionable Alerting Backend Validation
Target: https://ops-trace-control.preview.emergentagent.com
Tests: Anomaly alerts policy, mute flow, validation guards
"""

import requests
import json
import time
from datetime import datetime

def test_faz4_actionable_alerting():
    """
    Comprehensive backend validation for FAZ-4 actionable alerting.
    Tests all required endpoints and flows.
    """
    
    BASE_URL = "https://ops-trace-control.preview.emergentagent.com"
    
    print("=" * 80)
    print("FAZ-4 ACTIONABLE ALERTING BACKEND VALIDATION")
    print(f"Target: {BASE_URL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("=" * 80)
    
    results = {
        "target_url": BASE_URL,
        "test_time": datetime.now().isoformat(),
        "tests_total": 7,
        "tests_passed": 0,
        "tests_failed": 0,
        "tests": {}
    }
    
    # Configure session with timeout
    session = requests.Session()
    session.timeout = 15
    
    # Get admin token
    print("\n🔐 Getting admin authentication token...")
    try:
        admin_login_response = session.post(f"{BASE_URL}/api/auth/login/admin", json={
            "email": "canary.admin@platform.local",
            "password": "CanaryAdmin123!"
        })
        
        if admin_login_response.status_code == 200:
            admin_token = admin_login_response.json()["access_token"]
            admin_headers = {"Authorization": f"Bearer {admin_token}"}
            print(f"   ✅ Admin login successful")
        else:
            print(f"   ❌ Admin login failed: {admin_login_response.status_code}")
            return results
    except Exception as e:
        print(f"   ❌ Admin login error: {e}")
        return results
    
    # Get user token
    print("\n🔐 Getting user authentication token...")
    try:
        user_login_response = session.post(f"{BASE_URL}/api/auth/login/user", json={
            "email": "canary_1774010877@example.com",
            "password": "TestPass123!"
        })
        
        if user_login_response.status_code == 200:
            user_token = user_login_response.json()["access_token"]
            user_headers = {"Authorization": f"Bearer {user_token}"}
            print(f"   ✅ User login successful")
        else:
            print(f"   ❌ User login failed: {user_login_response.status_code}")
            return results
    except Exception as e:
        print(f"   ❌ User login error: {e}")
        return results
    
    # Test 1: GET /api/admin/anomaly-alerts/policy returns policy payload
    print("\n1️⃣ Testing GET /api/admin/anomaly-alerts/policy")
    try:
        response = session.get(f"{BASE_URL}/api/admin/anomaly-alerts/policy", headers=admin_headers)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            policy_data = response.json()
            print(f"   ✅ Policy retrieved successfully")
            print(f"   Policy keys: {list(policy_data.keys())}")
            
            results["tests"]["policy_get"] = {
                "status": "PASS",
                "status_code": response.status_code,
                "response_keys": list(policy_data.keys())
            }
            results["tests_passed"] += 1
        else:
            print(f"   ❌ Policy retrieval failed")
            results["tests"]["policy_get"] = {
                "status": "FAIL",
                "status_code": response.status_code,
                "error": response.text
            }
            results["tests_failed"] += 1
    except Exception as e:
        print(f"   ❌ Policy retrieval error: {e}")
        results["tests"]["policy_get"] = {"status": "ERROR", "error": str(e)}
        results["tests_failed"] += 1
    
    # Test 2: PUT /api/admin/anomaly-alerts/policy with custom thresholds
    print("\n2️⃣ Testing PUT /api/admin/anomaly-alerts/policy")
    try:
        policy_update = {
            "critical_threshold": 0.15,
            "warning_threshold": 0.10,
            "notifications_enabled": False,
            "webhook_urls": []
        }
        
        response = session.put(f"{BASE_URL}/api/admin/anomaly-alerts/policy", 
                              headers=admin_headers, json=policy_update)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            updated_policy = response.json()
            print(f"   ✅ Policy updated successfully")
            print(f"   Updated policy: {updated_policy}")
            
            results["tests"]["policy_put"] = {
                "status": "PASS",
                "status_code": response.status_code,
                "updated_policy": updated_policy
            }
            results["tests_passed"] += 1
        else:
            print(f"   ❌ Policy update failed")
            results["tests"]["policy_put"] = {
                "status": "FAIL",
                "status_code": response.status_code,
                "error": response.text
            }
            results["tests_failed"] += 1
    except Exception as e:
        print(f"   ❌ Policy update error: {e}")
        results["tests"]["policy_put"] = {"status": "ERROR", "error": str(e)}
        results["tests_failed"] += 1
    
    # Test 3: User anomaly event with fail_ratio above critical
    print("\n3️⃣ Testing POST /api/user/scanner/runtime/anomaly-event (critical level)")
    try:
        anomaly_payload = {
            "source": "scanner_ui",
            "fail_ratio": 0.20,  # Above critical threshold (0.15)
            "total_requests": 100,
            "failed_requests": 20,
            "success_requests": 80,
            "trend_window_minutes": 15,
            "trend_points": [
                {"minute_offset": 0, "success_count": 16, "fail_count": 4},
                {"minute_offset": 5, "success_count": 16, "fail_count": 4},
                {"minute_offset": 10, "success_count": 16, "fail_count": 4},
                {"minute_offset": 15, "success_count": 16, "fail_count": 4}
            ]
        }
        
        response = session.post(f"{BASE_URL}/api/user/scanner/runtime/anomaly-event", 
                               headers=user_headers, json=anomaly_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            anomaly_response = response.json()
            print(f"   ✅ Anomaly event logged successfully")
            print(f"   Response: {anomaly_response}")
            
            # Check for expected fields
            expected_status = "logged"
            expected_severity = "critical"
            
            if (anomaly_response.get("status") == expected_status and 
                anomaly_response.get("alert_severity") == expected_severity):
                print(f"   ✅ Expected status={expected_status} and alert_severity={expected_severity}")
                results["tests"]["anomaly_critical"] = {
                    "status": "PASS",
                    "status_code": response.status_code,
                    "response": anomaly_response,
                    "payload_hash": anomaly_response.get("payload_hash")
                }
                results["tests_passed"] += 1
                
                # Store payload hash for mute test
                payload_hash = anomaly_response.get("payload_hash")
            else:
                print(f"   ❌ Unexpected response fields")
                results["tests"]["anomaly_critical"] = {
                    "status": "FAIL",
                    "status_code": response.status_code,
                    "response": anomaly_response,
                    "expected": {"status": expected_status, "alert_severity": expected_severity}
                }
                results["tests_failed"] += 1
                payload_hash = None
        else:
            print(f"   ❌ Anomaly event failed")
            results["tests"]["anomaly_critical"] = {
                "status": "FAIL",
                "status_code": response.status_code,
                "error": response.text
            }
            results["tests_failed"] += 1
            payload_hash = None
    except Exception as e:
        print(f"   ❌ Anomaly event error: {e}")
        results["tests"]["anomaly_critical"] = {"status": "ERROR", "error": str(e)}
        results["tests_failed"] += 1
        payload_hash = None
    
    # Test 4: Manual mute flow
    print("\n4️⃣ Testing POST /api/admin/anomaly-alerts/mutes (manual mute)")
    if payload_hash:
        try:
            mute_payload = {
                "payload_hash": payload_hash,
                "duration_seconds": 600,
                "reason": "Testing mute functionality"
            }
            
            response = session.post(f"{BASE_URL}/api/admin/anomaly-alerts/mutes", 
                                   headers=admin_headers, json=mute_payload)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                mute_response = response.json()
                print(f"   ✅ Mute created successfully")
                print(f"   Mute response: {mute_response}")
                
                results["tests"]["mute_create"] = {
                    "status": "PASS",
                    "status_code": response.status_code,
                    "response": mute_response
                }
                results["tests_passed"] += 1
            else:
                print(f"   ❌ Mute creation failed")
                results["tests"]["mute_create"] = {
                    "status": "FAIL",
                    "status_code": response.status_code,
                    "error": response.text
                }
                results["tests_failed"] += 1
        except Exception as e:
            print(f"   ❌ Mute creation error: {e}")
            results["tests"]["mute_create"] = {"status": "ERROR", "error": str(e)}
            results["tests_failed"] += 1
    else:
        print("   ⏭️ Skipping mute test - no payload_hash from previous test")
        results["tests"]["mute_create"] = {"status": "SKIP", "reason": "No payload_hash"}
        results["tests_failed"] += 1
    
    # Test 5: Test suppressed anomaly after mute
    print("\n5️⃣ Testing suppressed anomaly after mute")
    if payload_hash:
        try:
            # Wait a moment for mute to be active
            time.sleep(2)
            
            # Send same anomaly payload again
            response = session.post(f"{BASE_URL}/api/user/scanner/runtime/anomaly-event", 
                                   headers=user_headers, json=anomaly_payload)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                suppressed_response = response.json()
                print(f"   ✅ Anomaly event processed")
                print(f"   Response: {suppressed_response}")
                
                # Check for suppressed status
                expected_status = "suppressed"
                expected_reason = "muted_pattern"
                
                if (suppressed_response.get("status") == expected_status and 
                    suppressed_response.get("suppress_reason") == expected_reason):
                    print(f"   ✅ Expected status={expected_status} and suppress_reason={expected_reason}")
                    results["tests"]["anomaly_suppressed"] = {
                        "status": "PASS",
                        "status_code": response.status_code,
                        "response": suppressed_response
                    }
                    results["tests_passed"] += 1
                else:
                    print(f"   ❌ Unexpected suppression response")
                    results["tests"]["anomaly_suppressed"] = {
                        "status": "FAIL",
                        "status_code": response.status_code,
                        "response": suppressed_response,
                        "expected": {"status": expected_status, "suppress_reason": expected_reason}
                    }
                    results["tests_failed"] += 1
            else:
                print(f"   ❌ Suppressed anomaly test failed")
                results["tests"]["anomaly_suppressed"] = {
                    "status": "FAIL",
                    "status_code": response.status_code,
                    "error": response.text
                }
                results["tests_failed"] += 1
        except Exception as e:
            print(f"   ❌ Suppressed anomaly error: {e}")
            results["tests"]["anomaly_suppressed"] = {"status": "ERROR", "error": str(e)}
            results["tests_failed"] += 1
    else:
        print("   ⏭️ Skipping suppressed test - no payload_hash from previous test")
        results["tests"]["anomaly_suppressed"] = {"status": "SKIP", "reason": "No payload_hash"}
        results["tests_failed"] += 1
    
    # Test 6: GET /api/admin/anomaly-alerts/mutes
    print("\n6️⃣ Testing GET /api/admin/anomaly-alerts/mutes")
    try:
        response = session.get(f"{BASE_URL}/api/admin/anomaly-alerts/mutes", headers=admin_headers)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            mutes_data = response.json()
            print(f"   ✅ Mutes retrieved successfully")
            print(f"   Mutes count: {len(mutes_data) if isinstance(mutes_data, list) else 'N/A'}")
            
            # Check for at least one active mute
            if isinstance(mutes_data, list) and len(mutes_data) > 0:
                print(f"   ✅ At least one mute row found")
                results["tests"]["mutes_get"] = {
                    "status": "PASS",
                    "status_code": response.status_code,
                    "mutes_count": len(mutes_data),
                    "sample_mute": mutes_data[0] if mutes_data else None
                }
                results["tests_passed"] += 1
            else:
                print(f"   ❌ No active mutes found")
                results["tests"]["mutes_get"] = {
                    "status": "FAIL",
                    "status_code": response.status_code,
                    "mutes_count": 0,
                    "response": mutes_data
                }
                results["tests_failed"] += 1
        else:
            print(f"   ❌ Mutes retrieval failed")
            results["tests"]["mutes_get"] = {
                "status": "FAIL",
                "status_code": response.status_code,
                "error": response.text
            }
            results["tests_failed"] += 1
    except Exception as e:
        print(f"   ❌ Mutes retrieval error: {e}")
        results["tests"]["mutes_get"] = {"status": "ERROR", "error": str(e)}
        results["tests_failed"] += 1
    
    # Test 7: Validation guard - invalid consistency
    print("\n7️⃣ Testing validation guard (failed+success > total)")
    try:
        invalid_payload = {
            "source": "scanner_ui",
            "fail_ratio": 0.20,
            "total_requests": 50,
            "failed_requests": 30,  # 30 + 40 = 70 > 50 (invalid)
            "success_requests": 40,
            "trend_window_minutes": 15,
            "trend_points": []
        }
        
        response = session.post(f"{BASE_URL}/api/user/scanner/runtime/anomaly-event", 
                               headers=user_headers, json=invalid_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 422:
            error_response = response.json()
            print(f"   ✅ Validation guard working - 422 returned")
            print(f"   Error response: {error_response}")
            
            results["tests"]["validation_guard"] = {
                "status": "PASS",
                "status_code": response.status_code,
                "error_response": error_response
            }
            results["tests_passed"] += 1
        else:
            print(f"   ❌ Validation guard failed - expected 422")
            results["tests"]["validation_guard"] = {
                "status": "FAIL",
                "status_code": response.status_code,
                "expected_status": 422,
                "response": response.text
            }
            results["tests_failed"] += 1
    except Exception as e:
        print(f"   ❌ Validation guard error: {e}")
        results["tests"]["validation_guard"] = {"status": "ERROR", "error": str(e)}
        results["tests_failed"] += 1
    
    # Test 8: Health endpoint sanity check
    print("\n8️⃣ Testing GET /api/health (sanity check)")
    try:
        response = session.get(f"{BASE_URL}/api/health")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            health_data = response.json()
            print(f"   ✅ Health endpoint working")
            print(f"   Health status: {health_data.get('status', 'N/A')}")
            
            results["tests"]["health_check"] = {
                "status": "PASS",
                "status_code": response.status_code,
                "health_status": health_data.get('status')
            }
            results["tests_passed"] += 1
        else:
            print(f"   ❌ Health endpoint failed")
            results["tests"]["health_check"] = {
                "status": "FAIL",
                "status_code": response.status_code,
                "error": response.text
            }
            results["tests_failed"] += 1
    except Exception as e:
        print(f"   ❌ Health endpoint error: {e}")
        results["tests"]["health_check"] = {"status": "ERROR", "error": str(e)}
        results["tests_failed"] += 1
    
    # Final summary
    print("\n" + "=" * 80)
    print("FAZ-4 ACTIONABLE ALERTING VALIDATION SUMMARY")
    print("=" * 80)
    print(f"Tests Total: {results['tests_total']}")
    print(f"Tests Passed: {results['tests_passed']}")
    print(f"Tests Failed: {results['tests_failed']}")
    print(f"Success Rate: {(results['tests_passed']/results['tests_total']*100):.1f}%")
    
    # Test results breakdown
    print("\nDETAILED RESULTS:")
    for test_name, test_result in results["tests"].items():
        status_emoji = "✅" if test_result["status"] == "PASS" else "❌" if test_result["status"] == "FAIL" else "⏭️"
        print(f"  {status_emoji} {test_name}: {test_result['status']}")
    
    # Evidence snippets
    print("\nKEY EVIDENCE:")
    if "policy_get" in results["tests"] and results["tests"]["policy_get"]["status"] == "PASS":
        print(f"  • Policy GET: {results['tests']['policy_get']['response_keys']}")
    
    if "anomaly_critical" in results["tests"] and results["tests"]["anomaly_critical"]["status"] == "PASS":
        response = results["tests"]["anomaly_critical"]["response"]
        print(f"  • Critical anomaly: status={response.get('status')}, alert_severity={response.get('alert_severity')}")
    
    if "anomaly_suppressed" in results["tests"] and results["tests"]["anomaly_suppressed"]["status"] == "PASS":
        response = results["tests"]["anomaly_suppressed"]["response"]
        print(f"  • Suppressed anomaly: status={response.get('status')}, suppress_reason={response.get('suppress_reason')}")
    
    if "mutes_get" in results["tests"] and results["tests"]["mutes_get"]["status"] == "PASS":
        print(f"  • Active mutes: {results['tests']['mutes_get']['mutes_count']} found")
    
    if "validation_guard" in results["tests"] and results["tests"]["validation_guard"]["status"] == "PASS":
        print(f"  • Validation guard: 422 returned for invalid consistency")
    
    print("\n" + "=" * 80)
    
    return results

if __name__ == "__main__":
    test_results = test_faz4_actionable_alerting()
    
    # Save results to file
    with open("/app/faz4_test_results.json", "w") as f:
        json.dump(test_results, f, indent=2)
    
    print(f"\nTest results saved to: /app/faz4_test_results.json")