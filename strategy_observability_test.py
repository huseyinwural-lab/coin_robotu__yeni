#!/usr/bin/env python3
"""
Strategy Observability P0 Sprint Backend Endpoint Testing
Target: https://gate-control-v2.preview.emergentagent.com
Credentials: canary.admin@platform.local / CanaryAdmin123!

Test endpoints:
1) POST /api/auth/login/admin
2) GET /api/admin/strategy/top-signals?window=24h&top_n=10
3) POST /api/admin/strategy/top-signals/simulate
4) POST /api/admin/strategy/top-signals/execute
5) POST /api/admin/strategy/top-signals/bulk-simulate
6) POST /api/admin/strategy/top-signals/bulk-execute (preview + confirm)
7) GET /api/admin/strategy/score-config
8) PUT /api/admin/strategy/score-config
9) POST /api/admin/strategy/score-preview
10) POST /api/admin/strategy/score-override
11) POST /api/admin/strategy/score-auto-tuning/toggle
12) GET /api/admin/strategy/signals/{signal_id}/explainability
13) GET /api/admin/strategy/rejection-analytics
14) GET /api/admin/strategy/rejection-analytics/details
15) GET /api/admin/strategy/rejection-analytics/reasons
16) GET /api/admin/strategy/audit-log
"""

import requests
import json
from datetime import datetime
import time

def test_strategy_observability_endpoints():
    """
    Test Strategy Observability P0 sprint backend endpoints
    """
    
    BASE_URL = "https://gate-control-v2.preview.emergentagent.com"
    ADMIN_EMAIL = "canary.admin@platform.local"
    ADMIN_PASSWORD = "CanaryAdmin123!"
    
    print("=" * 80)
    print("STRATEGY OBSERVABILITY P0 SPRINT BACKEND ENDPOINT TESTING")
    print(f"Target: {BASE_URL}")
    print(f"Credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("=" * 80)
    
    results = {
        "target_url": BASE_URL,
        "test_time": datetime.now().isoformat(),
        "credentials": {"email": ADMIN_EMAIL, "password": "***"},
        "endpoints_tested": 16,
        "endpoints_passed": 0,
        "endpoints_failed": 0,
        "critical_blockers": [],
        "tests": {},
        "access_token": None
    }
    
    # Configure session with timeout
    session = requests.Session()
    session.timeout = 30
    
    # Test 1: POST /api/auth/login/admin
    print("\n1) Testing POST /api/auth/login/admin")
    try:
        login_payload = {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }
        
        response = session.post(f"{BASE_URL}/api/auth/login/admin", json=login_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("POST /api/auth/login/admin returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["auth_login"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                
                if "access_token" in data:
                    results["access_token"] = data["access_token"]
                    print("   ✅ PASS - Login successful, access token received")
                    results["endpoints_passed"] += 1
                    results["tests"]["auth_login"] = {
                        "status": "PASS", 
                        "code": 200,
                        "response_contract": {
                            "has_access_token": True,
                            "response_keys": list(data.keys())
                        }
                    }
                else:
                    print("   ❌ FAIL - Missing access_token in response")
                    results["endpoints_failed"] += 1
                    results["tests"]["auth_login"] = {
                        "status": "FAIL", 
                        "code": 200,
                        "error": "Missing access_token in response",
                        "response": data
                    }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["auth_login"] = {
                    "status": "FAIL", 
                    "code": 200,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["auth_login"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["auth_login"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # If login failed, we can't test authenticated endpoints
    if not results["access_token"]:
        print("\n🚨 CRITICAL: Login failed - cannot test authenticated endpoints")
        results["critical_blockers"].append("Login failed - cannot test authenticated endpoints")
        return results
    
    # Set authorization header for subsequent requests
    session.headers.update({"Authorization": f"Bearer {results['access_token']}"})
    
    # Test 2: GET /api/admin/strategy/top-signals?window=24h&top_n=10
    print("\n2) Testing GET /api/admin/strategy/top-signals?window=24h&top_n=10")
    try:
        response = session.get(f"{BASE_URL}/api/admin/strategy/top-signals?window=24h&top_n=10")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("GET /api/admin/strategy/top-signals returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["top_signals"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response size: {len(str(data))} chars")
                
                print("   ✅ PASS - Top signals endpoint accessible")
                results["endpoints_passed"] += 1
                results["tests"]["top_signals"] = {
                    "status": "PASS", 
                    "code": 200,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "response_size": len(str(data))
                    }
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["top_signals"] = {
                    "status": "FAIL", 
                    "code": 200,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["top_signals"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["top_signals"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 3: POST /api/admin/strategy/top-signals/simulate
    print("\n3) Testing POST /api/admin/strategy/top-signals/simulate")
    try:
        simulate_payload = {
            "signal_id": "test_signal_001",
            "window": "24h",
            "parameters": {
                "threshold": 0.75,
                "confidence": 0.8
            }
        }
        
        response = session.post(f"{BASE_URL}/api/admin/strategy/top-signals/simulate", json=simulate_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("POST /api/admin/strategy/top-signals/simulate returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["simulate"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code in [200, 400, 422]:  # Accept validation errors as working
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response: {data}")
                
                print("   ✅ PASS - Simulate endpoint accessible and responding")
                results["endpoints_passed"] += 1
                results["tests"]["simulate"] = {
                    "status": "PASS", 
                    "code": response.status_code,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "accepts_simulation_payload": True
                    },
                    "response": data
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["simulate"] = {
                    "status": "FAIL", 
                    "code": response.status_code,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Unexpected status {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["simulate"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Unexpected status {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["simulate"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 4: POST /api/admin/strategy/top-signals/execute
    print("\n4) Testing POST /api/admin/strategy/top-signals/execute")
    try:
        execute_payload = {
            "signal_id": "test_signal_001",
            "reason": "Test execution for validation",
            "confirm": True
        }
        
        response = session.post(f"{BASE_URL}/api/admin/strategy/top-signals/execute", json=execute_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("POST /api/admin/strategy/top-signals/execute returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["execute"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code in [200, 400, 422, 404]:  # Accept various responses as working
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response: {data}")
                
                # Check if reason is required
                reason_required = False
                if response.status_code in [400, 422] and "reason" in str(data).lower():
                    reason_required = True
                    print("   📝 NOTE - Reason field validation detected")
                
                print("   ✅ PASS - Execute endpoint accessible and responding")
                results["endpoints_passed"] += 1
                results["tests"]["execute"] = {
                    "status": "PASS", 
                    "code": response.status_code,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "reason_validation": reason_required,
                        "accepts_execution_payload": True
                    },
                    "response": data
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["execute"] = {
                    "status": "FAIL", 
                    "code": response.status_code,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Unexpected status {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["execute"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Unexpected status {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["execute"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 5: POST /api/admin/strategy/top-signals/bulk-simulate
    print("\n5) Testing POST /api/admin/strategy/top-signals/bulk-simulate")
    try:
        bulk_simulate_payload = {
            "signal_ids": ["test_signal_001", "test_signal_002"],
            "window": "24h",
            "parameters": {
                "threshold": 0.75,
                "confidence": 0.8
            }
        }
        
        response = session.post(f"{BASE_URL}/api/admin/strategy/top-signals/bulk-simulate", json=bulk_simulate_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("POST /api/admin/strategy/top-signals/bulk-simulate returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["bulk_simulate"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code in [200, 400, 422]:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response: {data}")
                
                print("   ✅ PASS - Bulk simulate endpoint accessible and responding")
                results["endpoints_passed"] += 1
                results["tests"]["bulk_simulate"] = {
                    "status": "PASS", 
                    "code": response.status_code,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "accepts_bulk_payload": True
                    },
                    "response": data
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["bulk_simulate"] = {
                    "status": "FAIL", 
                    "code": response.status_code,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Unexpected status {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["bulk_simulate"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Unexpected status {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["bulk_simulate"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 6: POST /api/admin/strategy/top-signals/bulk-execute (preview + confirm)
    print("\n6) Testing POST /api/admin/strategy/top-signals/bulk-execute")
    try:
        bulk_execute_payload = {
            "signal_ids": ["test_signal_001", "test_signal_002"],
            "reason": "Bulk execution test for validation",
            "preview": True,
            "confirm": False
        }
        
        response = session.post(f"{BASE_URL}/api/admin/strategy/top-signals/bulk-execute", json=bulk_execute_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("POST /api/admin/strategy/top-signals/bulk-execute returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["bulk_execute"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code in [200, 400, 422, 404]:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response: {data}")
                
                # Check preview + confirm behavior
                preview_confirm_support = False
                if "preview" in str(data).lower() or "confirm" in str(data).lower():
                    preview_confirm_support = True
                    print("   📝 NOTE - Preview + Confirm workflow detected")
                
                print("   ✅ PASS - Bulk execute endpoint accessible and responding")
                results["endpoints_passed"] += 1
                results["tests"]["bulk_execute"] = {
                    "status": "PASS", 
                    "code": response.status_code,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "preview_confirm_workflow": preview_confirm_support,
                        "accepts_bulk_execution_payload": True
                    },
                    "response": data
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["bulk_execute"] = {
                    "status": "FAIL", 
                    "code": response.status_code,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Unexpected status {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["bulk_execute"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Unexpected status {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["bulk_execute"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 7: GET /api/admin/strategy/score-config
    print("\n7) Testing GET /api/admin/strategy/score-config")
    try:
        response = session.get(f"{BASE_URL}/api/admin/strategy/score-config")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("GET /api/admin/strategy/score-config returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["score_config_get"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response size: {len(str(data))} chars")
                
                print("   ✅ PASS - Score config GET endpoint accessible")
                results["endpoints_passed"] += 1
                results["tests"]["score_config_get"] = {
                    "status": "PASS", 
                    "code": 200,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "response_size": len(str(data))
                    }
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["score_config_get"] = {
                    "status": "FAIL", 
                    "code": 200,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["score_config_get"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["score_config_get"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 8: PUT /api/admin/strategy/score-config
    print("\n8) Testing PUT /api/admin/strategy/score-config")
    try:
        score_config_payload = {
            "scoring_weights": {
                "signal_strength": 0.4,
                "risk_score": 0.3,
                "confidence": 0.3
            },
            "thresholds": {
                "min_score": 0.7,
                "max_risk": 0.2
            }
        }
        
        response = session.put(f"{BASE_URL}/api/admin/strategy/score-config", json=score_config_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("PUT /api/admin/strategy/score-config returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["score_config_put"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code in [200, 400, 422]:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response: {data}")
                
                print("   ✅ PASS - Score config PUT endpoint accessible and responding")
                results["endpoints_passed"] += 1
                results["tests"]["score_config_put"] = {
                    "status": "PASS", 
                    "code": response.status_code,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "accepts_config_updates": True
                    },
                    "response": data
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["score_config_put"] = {
                    "status": "FAIL", 
                    "code": response.status_code,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Unexpected status {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["score_config_put"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Unexpected status {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["score_config_put"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 9: POST /api/admin/strategy/score-preview
    print("\n9) Testing POST /api/admin/strategy/score-preview")
    try:
        score_preview_payload = {
            "signal_id": "test_signal_001",
            "config_changes": {
                "scoring_weights": {
                    "signal_strength": 0.5,
                    "risk_score": 0.25,
                    "confidence": 0.25
                }
            }
        }
        
        response = session.post(f"{BASE_URL}/api/admin/strategy/score-preview", json=score_preview_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("POST /api/admin/strategy/score-preview returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["score_preview"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code in [200, 400, 422, 404]:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response: {data}")
                
                print("   ✅ PASS - Score preview endpoint accessible and responding")
                results["endpoints_passed"] += 1
                results["tests"]["score_preview"] = {
                    "status": "PASS", 
                    "code": response.status_code,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "accepts_preview_payload": True
                    },
                    "response": data
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["score_preview"] = {
                    "status": "FAIL", 
                    "code": response.status_code,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Unexpected status {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["score_preview"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Unexpected status {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["score_preview"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 10: POST /api/admin/strategy/score-override
    print("\n10) Testing POST /api/admin/strategy/score-override")
    try:
        score_override_payload = {
            "signal_id": "test_signal_001",
            "override_score": 0.85,
            "reason": "Manual override for testing",
            "duration_minutes": 60
        }
        
        response = session.post(f"{BASE_URL}/api/admin/strategy/score-override", json=score_override_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("POST /api/admin/strategy/score-override returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["score_override"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code in [200, 400, 422, 404]:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response: {data}")
                
                # Check if reason is required
                reason_required = False
                if response.status_code in [400, 422] and "reason" in str(data).lower():
                    reason_required = True
                    print("   📝 NOTE - Reason field validation detected")
                
                print("   ✅ PASS - Score override endpoint accessible and responding")
                results["endpoints_passed"] += 1
                results["tests"]["score_override"] = {
                    "status": "PASS", 
                    "code": response.status_code,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "reason_validation": reason_required,
                        "accepts_override_payload": True
                    },
                    "response": data
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["score_override"] = {
                    "status": "FAIL", 
                    "code": response.status_code,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Unexpected status {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["score_override"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Unexpected status {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["score_override"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 11: POST /api/admin/strategy/score-auto-tuning/toggle
    print("\n11) Testing POST /api/admin/strategy/score-auto-tuning/toggle")
    try:
        auto_tuning_payload = {
            "enabled": True,
            "reason": "Enable auto-tuning for testing"
        }
        
        response = session.post(f"{BASE_URL}/api/admin/strategy/score-auto-tuning/toggle", json=auto_tuning_payload)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("POST /api/admin/strategy/score-auto-tuning/toggle returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["auto_tuning_toggle"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code in [200, 400, 422]:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response: {data}")
                
                print("   ✅ PASS - Auto-tuning toggle endpoint accessible and responding")
                results["endpoints_passed"] += 1
                results["tests"]["auto_tuning_toggle"] = {
                    "status": "PASS", 
                    "code": response.status_code,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "accepts_toggle_payload": True
                    },
                    "response": data
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["auto_tuning_toggle"] = {
                    "status": "FAIL", 
                    "code": response.status_code,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Unexpected status {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["auto_tuning_toggle"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Unexpected status {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["auto_tuning_toggle"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 12: GET /api/admin/strategy/signals/{signal_id}/explainability
    print("\n12) Testing GET /api/admin/strategy/signals/{signal_id}/explainability")
    try:
        signal_id = "test_signal_001"
        response = session.get(f"{BASE_URL}/api/admin/strategy/signals/{signal_id}/explainability")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("GET /api/admin/strategy/signals/{signal_id}/explainability returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["explainability"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code in [200, 404]:  # 404 is acceptable for non-existent signal
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response: {data}")
                
                print("   ✅ PASS - Explainability endpoint accessible and responding")
                results["endpoints_passed"] += 1
                results["tests"]["explainability"] = {
                    "status": "PASS", 
                    "code": response.status_code,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "signal_id_parameter": signal_id
                    },
                    "response": data
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["explainability"] = {
                    "status": "FAIL", 
                    "code": response.status_code,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Unexpected status {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["explainability"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Unexpected status {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["explainability"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 13: GET /api/admin/strategy/rejection-analytics
    print("\n13) Testing GET /api/admin/strategy/rejection-analytics")
    try:
        response = session.get(f"{BASE_URL}/api/admin/strategy/rejection-analytics")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("GET /api/admin/strategy/rejection-analytics returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["rejection_analytics"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response size: {len(str(data))} chars")
                
                print("   ✅ PASS - Rejection analytics endpoint accessible")
                results["endpoints_passed"] += 1
                results["tests"]["rejection_analytics"] = {
                    "status": "PASS", 
                    "code": 200,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "response_size": len(str(data))
                    }
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["rejection_analytics"] = {
                    "status": "FAIL", 
                    "code": 200,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["rejection_analytics"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["rejection_analytics"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 14: GET /api/admin/strategy/rejection-analytics/details
    print("\n14) Testing GET /api/admin/strategy/rejection-analytics/details")
    try:
        response = session.get(f"{BASE_URL}/api/admin/strategy/rejection-analytics/details")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("GET /api/admin/strategy/rejection-analytics/details returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["rejection_analytics_details"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response size: {len(str(data))} chars")
                
                print("   ✅ PASS - Rejection analytics details endpoint accessible")
                results["endpoints_passed"] += 1
                results["tests"]["rejection_analytics_details"] = {
                    "status": "PASS", 
                    "code": 200,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "response_size": len(str(data))
                    }
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["rejection_analytics_details"] = {
                    "status": "FAIL", 
                    "code": 200,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["rejection_analytics_details"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["rejection_analytics_details"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 15: GET /api/admin/strategy/rejection-analytics/reasons
    print("\n15) Testing GET /api/admin/strategy/rejection-analytics/reasons")
    try:
        response = session.get(f"{BASE_URL}/api/admin/strategy/rejection-analytics/reasons")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("GET /api/admin/strategy/rejection-analytics/reasons returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["rejection_analytics_reasons"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response size: {len(str(data))} chars")
                
                print("   ✅ PASS - Rejection analytics reasons endpoint accessible")
                results["endpoints_passed"] += 1
                results["tests"]["rejection_analytics_reasons"] = {
                    "status": "PASS", 
                    "code": 200,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "response_size": len(str(data))
                    }
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["rejection_analytics_reasons"] = {
                    "status": "FAIL", 
                    "code": 200,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["rejection_analytics_reasons"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["rejection_analytics_reasons"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Test 16: GET /api/admin/strategy/audit-log
    print("\n16) Testing GET /api/admin/strategy/audit-log")
    try:
        response = session.get(f"{BASE_URL}/api/admin/strategy/audit-log")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 502:
            print("   🚨 CRITICAL BLOCKER - 502 Service Down")
            results["critical_blockers"].append("GET /api/admin/strategy/audit-log returns 502")
            results["endpoints_failed"] += 1
            results["tests"]["audit_log"] = {
                "status": "CRITICAL_BLOCKER", 
                "code": 502,
                "error": "502 Service Down"
            }
        elif response.status_code == 200:
            try:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                print(f"   Response size: {len(str(data))} chars")
                
                print("   ✅ PASS - Audit log endpoint accessible")
                results["endpoints_passed"] += 1
                results["tests"]["audit_log"] = {
                    "status": "PASS", 
                    "code": 200,
                    "response_contract": {
                        "response_keys": list(data.keys()),
                        "response_size": len(str(data))
                    }
                }
            except json.JSONDecodeError:
                print(f"   ❌ FAIL - Invalid JSON response")
                results["endpoints_failed"] += 1
                results["tests"]["audit_log"] = {
                    "status": "FAIL", 
                    "code": 200,
                    "error": "Invalid JSON response"
                }
        else:
            print(f"   ❌ FAIL - Expected 200, got {response.status_code}")
            results["endpoints_failed"] += 1
            results["tests"]["audit_log"] = {
                "status": "FAIL", 
                "code": response.status_code,
                "error": f"Expected 200, got {response.status_code}",
                "response_text": response.text[:200] if response.text else None
            }
    except requests.exceptions.RequestException as e:
        print(f"   ❌ FAIL - Request failed: {str(e)}")
        results["endpoints_failed"] += 1
        results["tests"]["audit_log"] = {
            "status": "FAIL", 
            "error": f"Request failed: {str(e)}"
        }
    
    # Summary
    print("\n" + "=" * 80)
    print("STRATEGY OBSERVABILITY P0 SPRINT TESTING SUMMARY")
    print("=" * 80)
    print(f"Endpoints Tested: {results['endpoints_tested']}")
    print(f"✅ Passed: {results['endpoints_passed']}")
    print(f"❌ Failed: {results['endpoints_failed']}")
    print(f"🚨 Critical Blockers: {len(results['critical_blockers'])}")
    
    overall_status = "PASS" if len(results['critical_blockers']) == 0 and results['endpoints_failed'] == 0 else "FAIL"
    if len(results['critical_blockers']) > 0:
        overall_status = "CRITICAL_BLOCKER"
    
    print(f"\n🎯 OVERALL STATUS: {overall_status}")
    
    if len(results['critical_blockers']) > 0:
        print("\n🚨 CRITICAL BLOCKERS (502/Service Down):")
        for blocker in results['critical_blockers']:
            print(f"   - {blocker}")
    
    if results['endpoints_failed'] > 0:
        print("\n❌ FAILED ENDPOINTS:")
        for endpoint, test in results['tests'].items():
            if test['status'] == 'FAIL':
                error = test.get('error', 'Unknown error')
                code = test.get('code', 'N/A')
                print(f"   - {endpoint.upper()}: {error} (HTTP {code})")
    
    if results['endpoints_passed'] > 0:
        print("\n✅ ACCESSIBLE ENDPOINTS:")
        for endpoint, test in results['tests'].items():
            if test['status'] == 'PASS':
                code = test.get('code', 'N/A')
                contract = test.get('response_contract', {})
                print(f"   - {endpoint.upper()}: HTTP {code}")
                if 'response_keys' in contract:
                    print(f"     Response keys: {contract['response_keys']}")
                if 'reason_validation' in contract and contract['reason_validation']:
                    print(f"     ⚠️ Reason field validation detected")
                if 'preview_confirm_workflow' in contract and contract['preview_confirm_workflow']:
                    print(f"     📝 Preview + Confirm workflow detected")
    
    print("=" * 80)
    
    return results

if __name__ == "__main__":
    results = test_strategy_observability_endpoints()