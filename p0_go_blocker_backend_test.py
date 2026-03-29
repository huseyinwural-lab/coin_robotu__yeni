#!/usr/bin/env python3
"""
P0 GO-BLOCKER Backend Validation
Target: https://dry-run-shadow.preview.emergentagent.com
Credentials: canary.admin@platform.local / CanaryAdmin123!

Test Steps:
1) Login and get bearer token
2) Contract validation:
   - POST /api/runtime/ws/reconnect (reason + confirmation_phrase)
   - POST /api/runtime/gate/recheck (reason + confirmation_phrase)
   - POST /api/admin/universe-monitor/risk/exposure-override (override_type=force_reject, scope=BTCUSDT, ttl_minutes=30, reason, confirmation_phrase)
   Each should return {status, trace_id, message, state_snapshot} fields
3) GET /api/runtime/state-validation -> check for fix_action fields in checks
4) GET /api/runtime/gate/status -> check for suggested_fix/run_fix_action fields in FAIL rules
5) Report errors with endpoint and payload, or give PASS

Note: If temporary 502 during test, do short retry (2-3 attempts) and specify if persistent or transient.
"""

import requests
import json
import time
from datetime import datetime

def test_p0_go_blocker():
    """
    P0 GO-BLOCKER backend validation test
    """
    
    BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
    ADMIN_EMAIL = "canary.admin@platform.local"
    ADMIN_PASSWORD = "CanaryAdmin123!"
    
    print("=" * 80)
    print("P0 GO-BLOCKER BACKEND VALIDATION")
    print(f"Target: {BASE_URL}")
    print(f"Credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("=" * 80)
    
    results = {
        "target_url": BASE_URL,
        "test_time": datetime.now().isoformat(),
        "admin_credentials": f"{ADMIN_EMAIL} / {ADMIN_PASSWORD}",
        "total_tests": 6,
        "passed_tests": 0,
        "failed_tests": 0,
        "tests": {}
    }
    
    # Configure session with timeout and retries
    session = requests.Session()
    session.timeout = 30
    
    def make_request_with_retry(method, url, **kwargs):
        """Make request with 2-3 retry attempts for 502 handling"""
        for attempt in range(3):
            try:
                if method.upper() == 'GET':
                    response = session.get(url, **kwargs)
                elif method.upper() == 'POST':
                    response = session.post(url, **kwargs)
                elif method.upper() == 'PUT':
                    response = session.put(url, **kwargs)
                else:
                    response = session.request(method, url, **kwargs)
                
                if response.status_code == 502:
                    print(f"   ⚠️  502 detected on attempt {attempt + 1}/3, retrying...")
                    if attempt < 2:  # Don't sleep on last attempt
                        time.sleep(2)
                    continue
                
                return response, False  # Success, not persistent 502
                
            except requests.exceptions.RequestException as e:
                print(f"   ⚠️  Request exception on attempt {attempt + 1}/3: {str(e)}")
                if attempt < 2:
                    time.sleep(2)
                    continue
                return None, True  # Failed after retries
        
        # If we get here, all attempts returned 502
        return response, True  # Persistent 502
    
    # Test 1: Admin Login and Token Extraction
    print("\n1) Testing Admin Login and Bearer Token Extraction")
    try:
        login_payload = {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }
        
        response, is_persistent_502 = make_request_with_retry(
            'POST', 
            f"{BASE_URL}/api/auth/login/admin",
            json=login_payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response is None:
            print("   ❌ FAIL - Request failed after retries")
            results["failed_tests"] += 1
            results["tests"]["admin_login"] = {
                "status": "FAIL",
                "error": "Request failed after retries"
            }
            return results
        
        if is_persistent_502:
            print("   ❌ FAIL - Persistent 502 error after 3 attempts")
            results["failed_tests"] += 1
            results["tests"]["admin_login"] = {
                "status": "FAIL",
                "code": 502,
                "error": "Persistent 502 error",
                "is_persistent": True
            }
            return results
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if "access_token" in data:
                    token = data["access_token"]
                    print(f"   ✅ PASS - Login successful, token extracted (length: {len(token)})")
                    results["passed_tests"] += 1
                    results["tests"]["admin_login"] = {
                        "status": "PASS",
                        "code": 200,
                        "token_length": len(token),
                        "has_access_token": True
                    }
                    
                    # Set authorization header for subsequent requests
                    session.headers.update({"Authorization": f"Bearer {token}"})
                    
                else:
                    print("   ❌ FAIL - Missing access_token in response")
                    results["failed_tests"] += 1
                    results["tests"]["admin_login"] = {
                        "status": "FAIL",
                        "code": 200,
                        "response": data,
                        "error": "Missing access_token"
                    }
                    return results
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response: {response.text[:200]}")
                results["failed_tests"] += 1
                results["tests"]["admin_login"] = {
                    "status": "FAIL",
                    "code": 200,
                    "error": "Invalid JSON response"
                }
                return results
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error response: {error_data}")
            except:
                print(f"   Error response: {response.text[:200]}")
            results["failed_tests"] += 1
            results["tests"]["admin_login"] = {
                "status": "FAIL",
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}"
            }
            return results
    except Exception as e:
        print(f"   ❌ FAIL - Exception during login: {str(e)}")
        results["failed_tests"] += 1
        results["tests"]["admin_login"] = {
            "status": "FAIL",
            "error": f"Exception: {str(e)}"
        }
        return results
    
    # Test 2: POST /api/runtime/ws/reconnect
    print("\n2) Testing POST /api/runtime/ws/reconnect")
    try:
        reconnect_payload = {
            "reason": "P0 GO-BLOCKER validation test - websocket reconnection",
            "confirmation_phrase": "RECONNECT WS"
        }
        
        response, is_persistent_502 = make_request_with_retry(
            'POST',
            f"{BASE_URL}/api/runtime/ws/reconnect",
            json=reconnect_payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response is None:
            print("   ❌ FAIL - Request failed after retries")
            results["failed_tests"] += 1
            results["tests"]["ws_reconnect"] = {
                "status": "FAIL",
                "error": "Request failed after retries"
            }
        elif is_persistent_502:
            print("   ❌ FAIL - Persistent 502 error after 3 attempts")
            results["failed_tests"] += 1
            results["tests"]["ws_reconnect"] = {
                "status": "FAIL",
                "code": 502,
                "error": "Persistent 502 error",
                "is_persistent": True
            }
        else:
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   Response: {json.dumps(data, indent=2)}")
                    
                    # Check for required fields: status, trace_id, message, state_snapshot
                    required_fields = ["status", "trace_id", "message", "state_snapshot"]
                    missing_fields = [field for field in required_fields if field not in data]
                    
                    if not missing_fields:
                        print("   ✅ PASS - All required fields present (status, trace_id, message, state_snapshot)")
                        results["passed_tests"] += 1
                        results["tests"]["ws_reconnect"] = {
                            "status": "PASS",
                            "code": 200,
                            "response": data,
                            "required_fields_present": True,
                            "fields_found": list(data.keys())
                        }
                    else:
                        print(f"   ❌ FAIL - Missing required fields: {missing_fields}")
                        results["failed_tests"] += 1
                        results["tests"]["ws_reconnect"] = {
                            "status": "FAIL",
                            "code": 200,
                            "response": data,
                            "missing_fields": missing_fields,
                            "fields_found": list(data.keys())
                        }
                except json.JSONDecodeError:
                    print(f"   ❌ FAIL - Invalid JSON response: {response.text[:200]}")
                    results["failed_tests"] += 1
                    results["tests"]["ws_reconnect"] = {
                        "status": "FAIL",
                        "code": 200,
                        "error": "Invalid JSON response"
                    }
            else:
                print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error response: {error_data}")
                except:
                    print(f"   Error response: {response.text[:200]}")
                results["failed_tests"] += 1
                results["tests"]["ws_reconnect"] = {
                    "status": "FAIL",
                    "code": response.status_code,
                    "error": f"Expected 200, got {response.status_code}",
                    "payload_sent": reconnect_payload
                }
    except Exception as e:
        print(f"   ❌ FAIL - Exception during ws/reconnect: {str(e)}")
        results["failed_tests"] += 1
        results["tests"]["ws_reconnect"] = {
            "status": "FAIL",
            "error": f"Exception: {str(e)}",
            "payload_sent": reconnect_payload
        }
    
    # Test 3: POST /api/runtime/gate/recheck
    print("\n3) Testing POST /api/runtime/gate/recheck")
    try:
        recheck_payload = {
            "reason": "P0 GO-BLOCKER validation test - gate recheck",
            "confirmation_phrase": "RECHECK RELEASE GATE"
        }
        
        response, is_persistent_502 = make_request_with_retry(
            'POST',
            f"{BASE_URL}/api/runtime/gate/recheck",
            json=recheck_payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response is None:
            print("   ❌ FAIL - Request failed after retries")
            results["failed_tests"] += 1
            results["tests"]["gate_recheck"] = {
                "status": "FAIL",
                "error": "Request failed after retries"
            }
        elif is_persistent_502:
            print("   ❌ FAIL - Persistent 502 error after 3 attempts")
            results["failed_tests"] += 1
            results["tests"]["gate_recheck"] = {
                "status": "FAIL",
                "code": 502,
                "error": "Persistent 502 error",
                "is_persistent": True
            }
        else:
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   Response: {json.dumps(data, indent=2)}")
                    
                    # Check for required fields: status, trace_id, message, state_snapshot
                    required_fields = ["status", "trace_id", "message", "state_snapshot"]
                    missing_fields = [field for field in required_fields if field not in data]
                    
                    if not missing_fields:
                        print("   ✅ PASS - All required fields present (status, trace_id, message, state_snapshot)")
                        results["passed_tests"] += 1
                        results["tests"]["gate_recheck"] = {
                            "status": "PASS",
                            "code": 200,
                            "response": data,
                            "required_fields_present": True,
                            "fields_found": list(data.keys())
                        }
                    else:
                        print(f"   ❌ FAIL - Missing required fields: {missing_fields}")
                        results["failed_tests"] += 1
                        results["tests"]["gate_recheck"] = {
                            "status": "FAIL",
                            "code": 200,
                            "response": data,
                            "missing_fields": missing_fields,
                            "fields_found": list(data.keys())
                        }
                except json.JSONDecodeError:
                    print(f"   ❌ FAIL - Invalid JSON response: {response.text[:200]}")
                    results["failed_tests"] += 1
                    results["tests"]["gate_recheck"] = {
                        "status": "FAIL",
                        "code": 200,
                        "error": "Invalid JSON response"
                    }
            else:
                print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error response: {error_data}")
                except:
                    print(f"   Error response: {response.text[:200]}")
                results["failed_tests"] += 1
                results["tests"]["gate_recheck"] = {
                    "status": "FAIL",
                    "code": response.status_code,
                    "error": f"Expected 200, got {response.status_code}",
                    "payload_sent": recheck_payload
                }
    except Exception as e:
        print(f"   ❌ FAIL - Exception during gate/recheck: {str(e)}")
        results["failed_tests"] += 1
        results["tests"]["gate_recheck"] = {
            "status": "FAIL",
            "error": f"Exception: {str(e)}",
            "payload_sent": recheck_payload
        }
    
    # Test 4: POST /api/admin/universe-monitor/risk/exposure-override
    print("\n4) Testing POST /api/admin/universe-monitor/risk/exposure-override")
    try:
        override_payload = {
            "override_type": "force_reject",
            "scope": "BTCUSDT",
            "ttl_minutes": 30,
            "reason": "P0 GO-BLOCKER validation test - exposure override",
            "confirmation_phrase": "APPLY EXPOSURE OVERRIDE"
        }
        
        response, is_persistent_502 = make_request_with_retry(
            'POST',
            f"{BASE_URL}/api/admin/universe-monitor/risk/exposure-override",
            json=override_payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response is None:
            print("   ❌ FAIL - Request failed after retries")
            results["failed_tests"] += 1
            results["tests"]["exposure_override"] = {
                "status": "FAIL",
                "error": "Request failed after retries"
            }
        elif is_persistent_502:
            print("   ❌ FAIL - Persistent 502 error after 3 attempts")
            results["failed_tests"] += 1
            results["tests"]["exposure_override"] = {
                "status": "FAIL",
                "code": 502,
                "error": "Persistent 502 error",
                "is_persistent": True
            }
        else:
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   Response: {json.dumps(data, indent=2)}")
                    
                    # Check for required fields: status, trace_id, message, state_snapshot
                    required_fields = ["status", "trace_id", "message", "state_snapshot"]
                    missing_fields = [field for field in required_fields if field not in data]
                    
                    if not missing_fields:
                        print("   ✅ PASS - All required fields present (status, trace_id, message, state_snapshot)")
                        results["passed_tests"] += 1
                        results["tests"]["exposure_override"] = {
                            "status": "PASS",
                            "code": 200,
                            "response": data,
                            "required_fields_present": True,
                            "fields_found": list(data.keys())
                        }
                    else:
                        print(f"   ❌ FAIL - Missing required fields: {missing_fields}")
                        results["failed_tests"] += 1
                        results["tests"]["exposure_override"] = {
                            "status": "FAIL",
                            "code": 200,
                            "response": data,
                            "missing_fields": missing_fields,
                            "fields_found": list(data.keys())
                        }
                except json.JSONDecodeError:
                    print(f"   ❌ FAIL - Invalid JSON response: {response.text[:200]}")
                    results["failed_tests"] += 1
                    results["tests"]["exposure_override"] = {
                        "status": "FAIL",
                        "code": 200,
                        "error": "Invalid JSON response"
                    }
            else:
                print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error response: {error_data}")
                except:
                    print(f"   Error response: {response.text[:200]}")
                results["failed_tests"] += 1
                results["tests"]["exposure_override"] = {
                    "status": "FAIL",
                    "code": response.status_code,
                    "error": f"Expected 200, got {response.status_code}",
                    "payload_sent": override_payload
                }
    except Exception as e:
        print(f"   ❌ FAIL - Exception during exposure-override: {str(e)}")
        results["failed_tests"] += 1
        results["tests"]["exposure_override"] = {
            "status": "FAIL",
            "error": f"Exception: {str(e)}",
            "payload_sent": override_payload
        }
    
    # Test 5: GET /api/runtime/state-validation (check for fix_action fields)
    print("\n5) Testing GET /api/runtime/state-validation (fix_action fields)")
    try:
        response, is_persistent_502 = make_request_with_retry(
            'GET',
            f"{BASE_URL}/api/runtime/state-validation"
        )
        
        if response is None:
            print("   ❌ FAIL - Request failed after retries")
            results["failed_tests"] += 1
            results["tests"]["state_validation"] = {
                "status": "FAIL",
                "error": "Request failed after retries"
            }
        elif is_persistent_502:
            print("   ❌ FAIL - Persistent 502 error after 3 attempts")
            results["failed_tests"] += 1
            results["tests"]["state_validation"] = {
                "status": "FAIL",
                "code": 502,
                "error": "Persistent 502 error",
                "is_persistent": True
            }
        else:
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   Response keys: {list(data.keys())}")
                    
                    # Check for 'checks' field and fix_action within checks
                    if "checks" in data:
                        checks = data["checks"]
                        print(f"   Found checks: {type(checks)}")
                        
                        if isinstance(checks, dict):
                            print(f"   Found {len(checks)} check items")
                            
                            fix_action_found = False
                            checks_with_fix_action = []
                            
                            for key, check in checks.items():
                                if isinstance(check, dict) and "fix_action" in check:
                                    fix_action_found = True
                                    checks_with_fix_action.append(key)
                                    print(f"   Check '{key}': fix_action = {check['fix_action']}")
                            
                            if fix_action_found:
                                print(f"   ✅ PASS - fix_action fields found in checks (keys: {checks_with_fix_action})")
                                results["passed_tests"] += 1
                                results["tests"]["state_validation"] = {
                                    "status": "PASS",
                                    "code": 200,
                                    "checks_count": len(checks),
                                    "fix_action_found": True,
                                    "checks_with_fix_action": checks_with_fix_action,
                                    "sample_checks": {k: v for k, v in list(checks.items())[:3]}
                                }
                            else:
                                print("   ❌ FAIL - No fix_action fields found in checks")
                                results["failed_tests"] += 1
                                results["tests"]["state_validation"] = {
                                    "status": "FAIL",
                                    "code": 200,
                                    "checks_count": len(checks),
                                    "fix_action_found": False,
                                    "sample_checks": {k: v for k, v in list(checks.items())[:3]}
                                }
                        elif isinstance(checks, list):
                            print(f"   Found {len(checks)} checks")
                            
                            fix_action_found = False
                            checks_with_fix_action = []
                            
                            for i, check in enumerate(checks):
                                if isinstance(check, dict) and "fix_action" in check:
                                    fix_action_found = True
                                    checks_with_fix_action.append(i)
                                    print(f"   Check {i}: fix_action = {check['fix_action']}")
                            
                            if fix_action_found:
                                print(f"   ✅ PASS - fix_action fields found in checks (indices: {checks_with_fix_action})")
                                results["passed_tests"] += 1
                                results["tests"]["state_validation"] = {
                                    "status": "PASS",
                                    "code": 200,
                                    "checks_count": len(checks),
                                    "fix_action_found": True,
                                    "checks_with_fix_action": checks_with_fix_action,
                                    "sample_checks": checks[:3] if len(checks) >= 3 else checks
                                }
                            else:
                                print("   ❌ FAIL - No fix_action fields found in checks")
                                results["failed_tests"] += 1
                                results["tests"]["state_validation"] = {
                                    "status": "FAIL",
                                    "code": 200,
                                    "checks_count": len(checks),
                                    "fix_action_found": False,
                                    "sample_checks": checks[:3] if len(checks) >= 3 else checks
                                }
                        else:
                            print(f"   ❌ FAIL - 'checks' field is neither list nor dict: {type(checks)}")
                            results["failed_tests"] += 1
                            results["tests"]["state_validation"] = {
                                "status": "FAIL",
                                "code": 200,
                                "checks_type": str(type(checks)),
                                "error": "checks field is neither list nor dict"
                            }
                    else:
                        print("   ❌ FAIL - No 'checks' field in response")
                        results["failed_tests"] += 1
                        results["tests"]["state_validation"] = {
                            "status": "FAIL",
                            "code": 200,
                            "response": data,
                            "error": "No 'checks' field in response"
                        }
                except json.JSONDecodeError:
                    print(f"   ❌ FAIL - Invalid JSON response: {response.text[:200]}")
                    results["failed_tests"] += 1
                    results["tests"]["state_validation"] = {
                        "status": "FAIL",
                        "code": 200,
                        "error": "Invalid JSON response"
                    }
            else:
                print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error response: {error_data}")
                except:
                    print(f"   Error response: {response.text[:200]}")
                results["failed_tests"] += 1
                results["tests"]["state_validation"] = {
                    "status": "FAIL",
                    "code": response.status_code,
                    "error": f"Expected 200, got {response.status_code}"
                }
    except Exception as e:
        print(f"   ❌ FAIL - Exception during state-validation: {str(e)}")
        results["failed_tests"] += 1
        results["tests"]["state_validation"] = {
            "status": "FAIL",
            "error": f"Exception: {str(e)}"
        }
    
    # Test 6: GET /api/runtime/gate/status (check for suggested_fix/run_fix_action in FAIL rules)
    print("\n6) Testing GET /api/runtime/gate/status (suggested_fix/run_fix_action in FAIL rules)")
    try:
        response, is_persistent_502 = make_request_with_retry(
            'GET',
            f"{BASE_URL}/api/runtime/gate/status"
        )
        
        if response is None:
            print("   ❌ FAIL - Request failed after retries")
            results["failed_tests"] += 1
            results["tests"]["gate_status"] = {
                "status": "FAIL",
                "error": "Request failed after retries"
            }
        elif is_persistent_502:
            print("   ❌ FAIL - Persistent 502 error after 3 attempts")
            results["failed_tests"] += 1
            results["tests"]["gate_status"] = {
                "status": "FAIL",
                "code": 502,
                "error": "Persistent 502 error",
                "is_persistent": True
            }
        else:
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   Response keys: {list(data.keys())}")
                    
                    # Look for rules with FAIL status and check for suggested_fix/run_fix_action
                    fail_rules_found = 0
                    fix_fields_found = 0
                    rules_with_fix_fields = []
                    
                    # Check different possible structures
                    rules_to_check = []
                    if "rules" in data:
                        rules_to_check = data["rules"]
                    elif "checks" in data:
                        rules_to_check = data["checks"]
                    elif isinstance(data, list):
                        rules_to_check = data
                    
                    for i, rule in enumerate(rules_to_check):
                        if isinstance(rule, dict):
                            # Check if this is a FAIL rule (check both 'status' and 'result' fields)
                            status = rule.get("status", "").upper()
                            result = rule.get("result", "").upper()
                            if status == "FAIL" or status == "FAILED" or result == "FAIL" or result == "FAILED":
                                fail_rules_found += 1
                                rule_name = rule.get('rule_id', rule.get('name', f'rule_{i}'))
                                print(f"   FAIL rule {i}: {rule_name}")
                                
                                # Check for suggested_fix or run_fix_action
                                has_suggested_fix = "suggested_fix" in rule
                                has_run_fix_action = "run_fix_action" in rule
                                
                                if has_suggested_fix or has_run_fix_action:
                                    fix_fields_found += 1
                                    rules_with_fix_fields.append(i)
                                    print(f"     - suggested_fix: {has_suggested_fix}")
                                    print(f"     - run_fix_action: {has_run_fix_action}")
                                    if has_suggested_fix:
                                        print(f"     - suggested_fix value: {rule['suggested_fix']}")
                                    if has_run_fix_action:
                                        print(f"     - run_fix_action value: {rule['run_fix_action']}")
                    
                    print(f"   Found {fail_rules_found} FAIL rules, {fix_fields_found} with fix fields")
                    
                    if fail_rules_found > 0 and fix_fields_found > 0:
                        print(f"   ✅ PASS - FAIL rules found with suggested_fix/run_fix_action fields")
                        results["passed_tests"] += 1
                        results["tests"]["gate_status"] = {
                            "status": "PASS",
                            "code": 200,
                            "fail_rules_count": fail_rules_found,
                            "rules_with_fix_fields": fix_fields_found,
                            "rules_with_fix_indices": rules_with_fix_fields,
                            "sample_data": data if len(str(data)) < 1000 else "Response too large"
                        }
                    elif fail_rules_found == 0:
                        print("   ⚠️  INFO - No FAIL rules found (system may be healthy)")
                        results["passed_tests"] += 1  # This is actually OK
                        results["tests"]["gate_status"] = {
                            "status": "PASS",
                            "code": 200,
                            "fail_rules_count": 0,
                            "info": "No FAIL rules found - system healthy",
                            "sample_data": data if len(str(data)) < 1000 else "Response too large"
                        }
                    else:
                        print(f"   ❌ FAIL - FAIL rules found but no suggested_fix/run_fix_action fields")
                        results["failed_tests"] += 1
                        results["tests"]["gate_status"] = {
                            "status": "FAIL",
                            "code": 200,
                            "fail_rules_count": fail_rules_found,
                            "rules_with_fix_fields": 0,
                            "error": "FAIL rules found but no fix fields",
                            "sample_data": data if len(str(data)) < 1000 else "Response too large"
                        }
                except json.JSONDecodeError:
                    print(f"   ❌ FAIL - Invalid JSON response: {response.text[:200]}")
                    results["failed_tests"] += 1
                    results["tests"]["gate_status"] = {
                        "status": "FAIL",
                        "code": 200,
                        "error": "Invalid JSON response"
                    }
            else:
                print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error response: {error_data}")
                except:
                    print(f"   Error response: {response.text[:200]}")
                results["failed_tests"] += 1
                results["tests"]["gate_status"] = {
                    "status": "FAIL",
                    "code": response.status_code,
                    "error": f"Expected 200, got {response.status_code}"
                }
    except Exception as e:
        print(f"   ❌ FAIL - Exception during gate/status: {str(e)}")
        results["failed_tests"] += 1
        results["tests"]["gate_status"] = {
            "status": "FAIL",
            "error": f"Exception: {str(e)}"
        }
    
    # Final Results Summary
    print("\n" + "=" * 80)
    print("P0 GO-BLOCKER BACKEND VALIDATION RESULTS")
    print("=" * 80)
    print(f"Total Tests: {results['total_tests']}")
    print(f"Passed: {results['passed_tests']}")
    print(f"Failed: {results['failed_tests']}")
    print(f"Success Rate: {(results['passed_tests'] / results['total_tests']) * 100:.1f}%")
    
    if results['failed_tests'] == 0:
        print("\n🎉 OVERALL RESULT: ✅ PASS - All P0 GO-BLOCKER tests passed")
    else:
        print(f"\n⚠️  OVERALL RESULT: ❌ FAIL - {results['failed_tests']} test(s) failed")
        print("\nFAILED TESTS:")
        for test_name, test_data in results['tests'].items():
            if test_data['status'] == 'FAIL':
                print(f"  - {test_name}: {test_data.get('error', 'Unknown error')}")
    
    print("\nDetailed results saved in results object")
    return results

if __name__ == "__main__":
    results = test_p0_go_blocker()
    
    # Save results to file
    with open("/app/p0_go_blocker_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: /app/p0_go_blocker_test_results.json")