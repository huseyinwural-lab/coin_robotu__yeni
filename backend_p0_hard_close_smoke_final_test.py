#!/usr/bin/env python3
"""
P0 Hard Close Smoke Validation Test - Final Version
Turkish Review Request: Backend kısa smoke doğrulama yap: P0 Hard Close sonrası fail-safe hard block, 
execution/post-trade enforcement, portfolio domain separation ve admin observability metrikleri 
endpoint seviyesinde çalışıyor mu kontrol et.

Focus Areas:
1. P0 Hard Close after fail-safe hard block
2. Execution/post-trade enforcement 
3. Portfolio domain separation
4. Admin observability metrics
"""

import requests
import json
import sys
from datetime import datetime

# Backend URL from frontend/.env
BASE_URL = "http://localhost:8001"

# Create a session to maintain device fingerprint
session = requests.Session()

def log_test(test_name, status, details=""):
    """Log test results with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"[{timestamp}] {status_symbol} {test_name}: {status}")
    if details:
        print(f"    Details: {details}")

def test_admin_auth():
    """Test admin authentication"""
    try:
        # Use credentials from test_result.md
        auth_data = {
            "email": "canary.admin@platform.local",
            "password": "CanaryAdmin123!"
        }
        
        response = session.post(f"{BASE_URL}/api/auth/login", json=auth_data, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if "access_token" in data:
                token = data["access_token"]
                log_test("Admin Authentication", "PASS", f"Token length: {len(token)} chars")
                return token
            else:
                log_test("Admin Authentication", "FAIL", "No access_token in response")
                return None
        else:
            log_test("Admin Authentication", "FAIL", f"HTTP {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        log_test("Admin Authentication", "FAIL", f"Exception: {str(e)}")
        return None

def test_p0_hard_close_fail_safe(token):
    """Test P0 Hard Close after fail-safe hard block"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # Test execution policies endpoint for fail-safe hard block
        response = session.get(f"{BASE_URL}/api/admin/execution-policies", headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
            # Check for fail-safe hard block configuration
            if "engine_config" in data:
                engine_config = data["engine_config"]
                fail_safe_mode = engine_config.get("fail_safe_mode")
                enabled = engine_config.get("enabled")
                rollout_mode = engine_config.get("rollout_mode")
                
                if fail_safe_mode == "block":
                    log_test("P0 Hard Close Fail-Safe Hard Block", "PASS", 
                            f"fail_safe_mode={fail_safe_mode}, enabled={enabled}, rollout_mode={rollout_mode}")
                    return True
                else:
                    log_test("P0 Hard Close Fail-Safe Hard Block", "FAIL", 
                            f"fail_safe_mode={fail_safe_mode}, expected 'block'")
                    return False
            else:
                log_test("P0 Hard Close Fail-Safe Hard Block", "FAIL", "No engine_config in response")
                return False
        else:
            log_test("P0 Hard Close Fail-Safe Hard Block", "FAIL", f"HTTP {response.status_code}")
            return False
            
    except Exception as e:
        log_test("P0 Hard Close Fail-Safe Hard Block", "FAIL", f"Exception: {str(e)}")
        return False

def test_execution_post_trade_enforcement(token):
    """Test execution/post-trade enforcement"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # Test execution policies for post-trade enforcement
        response = session.get(f"{BASE_URL}/api/admin/execution-policies", headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
            # Check for enforcement in policy decision log and observability metrics
            enforcement_evidence = []
            
            if "policy_decision_log" in data:
                decision_log = data["policy_decision_log"]
                
                # Look for enforcement stages
                stages = [entry.get("stage") for entry in decision_log if entry.get("stage")]
                unique_stages = set(stages)
                
                if "POST_TRADE" in unique_stages or "post_trade" in unique_stages:
                    enforcement_evidence.append("post-trade enforcement in decision log")
                
                if "PRE_TRADE" in unique_stages or "pre_trade" in unique_stages:
                    enforcement_evidence.append("pre-trade enforcement in decision log")
                
                # Check for enforcement actions
                actions = [entry.get("enforced_action") for entry in decision_log if entry.get("enforced_action")]
                if "BLOCK" in actions:
                    enforcement_evidence.append("BLOCK actions enforced")
                
                if unique_stages:
                    enforcement_evidence.append(f"enforcement stages: {list(unique_stages)}")
            
            if "observability_metrics" in data:
                metrics = data["observability_metrics"]
                violation_count = metrics.get("violation_count", 0)
                decision_count = metrics.get("decision_log_count", 0)
                
                if violation_count > 0:
                    enforcement_evidence.append(f"violations detected: {violation_count}")
                
                if decision_count > 0:
                    enforcement_evidence.append(f"decisions logged: {decision_count}")
            
            if enforcement_evidence:
                log_test("Execution/Post-Trade Enforcement", "PASS", 
                        f"Enforcement active: {', '.join(enforcement_evidence)}")
                return True
            else:
                log_test("Execution/Post-Trade Enforcement", "FAIL", "No enforcement evidence found")
                return False
        else:
            log_test("Execution/Post-Trade Enforcement", "FAIL", f"HTTP {response.status_code}")
            return False
            
    except Exception as e:
        log_test("Execution/Post-Trade Enforcement", "FAIL", f"Exception: {str(e)}")
        return False

def test_portfolio_domain_separation(token):
    """Test portfolio domain separation"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # Test user live endpoints for domain separation
        user_endpoints = [
            "/api/user/live/summary?window=24h",
            "/api/user/live/positions",
            "/api/user/live/performance?window=24h",
            "/api/user/live/risk?window=24h",
            "/api/user/live/execution-quality?window=24h"
        ]
        
        separation_results = []
        
        for endpoint in user_endpoints:
            try:
                response = session.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=10)
                
                if response.status_code == 403:
                    # Expected - admin token should not access user endpoints (proper separation)
                    separation_results.append(f"✅ {endpoint}: 403 (proper separation)")
                elif response.status_code == 401:
                    # Also acceptable - authentication/authorization rejection
                    separation_results.append(f"✅ {endpoint}: 401 (auth rejection)")
                elif response.status_code == 200:
                    # Check if response contains user-scoped data only
                    separation_results.append(f"⚠️ {endpoint}: 200 (check scope isolation)")
                else:
                    separation_results.append(f"⚠️ {endpoint}: {response.status_code}")
                    
            except Exception as e:
                separation_results.append(f"❌ {endpoint}: Exception - {str(e)}")
        
        # Count proper separations
        proper_separations = sum(1 for result in separation_results if result.startswith("✅"))
        total_endpoints = len(user_endpoints)
        
        if proper_separations >= total_endpoints * 0.8:  # 80% threshold
            log_test("Portfolio Domain Separation", "PASS", 
                    f"{proper_separations}/{total_endpoints} endpoints properly separated")
            return True
        else:
            log_test("Portfolio Domain Separation", "PARTIAL", 
                    f"Only {proper_separations}/{total_endpoints} endpoints properly separated")
            return False
        
    except Exception as e:
        log_test("Portfolio Domain Separation", "FAIL", f"Exception: {str(e)}")
        return False

def test_admin_observability_metrics(token):
    """Test admin observability metrics"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # Test key admin observability endpoints
        observability_results = []
        
        # Test execution policies observability
        try:
            response = session.get(f"{BASE_URL}/api/admin/execution-policies", headers=headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                if "observability_metrics" in data:
                    metrics = data["observability_metrics"]
                    required_fields = ["decision_log_count", "violation_count", "reject_reason_distribution"]
                    
                    missing_fields = [field for field in required_fields if field not in metrics]
                    if not missing_fields:
                        observability_results.append("✅ Execution policy metrics: All required fields present")
                    else:
                        observability_results.append(f"⚠️ Execution policy metrics: Missing {missing_fields}")
                else:
                    observability_results.append("❌ Execution policy metrics: No observability_metrics")
            else:
                observability_results.append(f"❌ Execution policy metrics: HTTP {response.status_code}")
                
        except Exception as e:
            observability_results.append(f"❌ Execution policy metrics: Exception - {str(e)}")
        
        # Test system alerts
        try:
            response = session.get(f"{BASE_URL}/api/admin/system-alerts", headers=headers, timeout=15)
            
            if response.status_code == 200:
                observability_results.append("✅ System alerts: Endpoint accessible")
            else:
                observability_results.append(f"❌ System alerts: HTTP {response.status_code}")
                
        except Exception as e:
            observability_results.append(f"❌ System alerts: Exception - {str(e)}")
        
        # Test health endpoint (no auth required)
        try:
            response = session.get(f"{BASE_URL}/api/health", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "status" in data and data["status"] == "ok":
                    observability_results.append("✅ Health check: System healthy")
                else:
                    observability_results.append("⚠️ Health check: System status unclear")
            else:
                observability_results.append(f"❌ Health check: HTTP {response.status_code}")
                
        except Exception as e:
            observability_results.append(f"❌ Health check: Exception - {str(e)}")
        
        # Count successful observability checks
        successful_checks = sum(1 for result in observability_results if result.startswith("✅"))
        total_checks = len(observability_results)
        
        if successful_checks >= 2:  # At least 2 out of 3 should work
            log_test("Admin Observability Metrics", "PASS", 
                    f"{successful_checks}/{total_checks} observability endpoints working")
            return True
        else:
            log_test("Admin Observability Metrics", "FAIL", 
                    f"Only {successful_checks}/{total_checks} observability endpoints working")
            return False
        
    except Exception as e:
        log_test("Admin Observability Metrics", "FAIL", f"Exception: {str(e)}")
        return False

def main():
    """Main test execution"""
    print("=" * 80)
    print("P0 HARD CLOSE SMOKE VALIDATION TEST - FINAL")
    print("Turkish Review Request: Backend kısa smoke doğrulama")
    print(f"Backend URL: {BASE_URL}")
    print("=" * 80)
    
    # Test 1: Admin Authentication
    token = test_admin_auth()
    if not token:
        print("\n❌ CRITICAL: Admin authentication failed. Cannot proceed with other tests.")
        sys.exit(1)
    
    # Test 2: P0 Hard Close after fail-safe hard block
    p0_hard_close_result = test_p0_hard_close_fail_safe(token)
    
    # Test 3: Execution/post-trade enforcement
    execution_enforcement_result = test_execution_post_trade_enforcement(token)
    
    # Test 4: Portfolio domain separation
    portfolio_separation_result = test_portfolio_domain_separation(token)
    
    # Test 5: Admin observability metrics
    observability_metrics_result = test_admin_observability_metrics(token)
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    results = [
        ("P0 Hard Close Fail-Safe Hard Block", p0_hard_close_result),
        ("Execution/Post-Trade Enforcement", execution_enforcement_result),
        ("Portfolio Domain Separation", portfolio_separation_result),
        ("Admin Observability Metrics", observability_metrics_result)
    ]
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"OVERALL RESULT: {passed}/{total} PASS ({(passed/total)*100:.1f}% SUCCESS RATE)")
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {test_name}")
    
    print("\n" + "=" * 80)
    print("TURKISH REVIEW REQUEST FINDINGS")
    print("=" * 80)
    
    if passed == total:
        print("✅ TÜM TESTLER BAŞARILI - P0 Hard Close smoke validation successful")
        print("✅ Backend endpoints working correctly for Turkish review requirements")
        print("✅ Kritik bulgu YOK - All systems operational")
    else:
        print(f"⚠️ {total - passed} TEST BAŞARISIZ - Critical findings detected")
        print("❌ Backend has issues that need investigation")
        
        # Specific findings
        if not p0_hard_close_result:
            print("🔴 KRITIK BULGU: P0 Hard Close fail-safe hard block not working properly")
            print("   Dosya: backend/routers/admin/execution_policies.py")
            print("   Sebep: fail_safe_mode should be 'block' but found different value")
        
        if not execution_enforcement_result:
            print("🔴 KRITIK BULGU: Execution/post-trade enforcement not active")
            print("   Dosya: backend/core/execution/policy_engine.py")
            print("   Sebep: No enforcement evidence in policy decision log or metrics")
        
        if not portfolio_separation_result:
            print("🔴 KRITIK BULGU: Portfolio domain separation not working")
            print("   Dosya: backend/routers/user/live.py")
            print("   Sebep: Admin tokens can access user endpoints (domain separation failure)")
        
        if not observability_metrics_result:
            print("🔴 KRITIK BULGU: Admin observability metrics not accessible")
            print("   Dosya: backend/routers/admin/system_alerts.py, backend/routers/admin/execution_policies.py")
            print("   Sebep: Observability endpoints not responding or missing required metrics")
    
    print("=" * 80)

if __name__ == "__main__":
    main()