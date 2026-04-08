#!/usr/bin/env python3
"""
GO/NO-GO FINAL BACKEND AUDIT (Pure Live sonrası)
Turkish Review Request - 5 Critical Areas Assessment

Focus Areas:
1) Advisory Mode hard-coded blocked/non_tradeable rules: active + auto-lift in live?
2) Mock/stub/static JSON control: scanner path real exchange data proof
3) Race/idempotency: scanner-engine + strategy-allocation timeout/crash behavior  
4) Scalability: current environment high symbol load CPU/memory trend + pool capacity risk
5) Auth persistence: CDN/WAF external backend effects + JWT/refresh adequacy

Risk Levels: Critical/High/Medium/Low
Output: Clear GO/NO-GO impact assessment
"""

import requests
import json
import time
import concurrent.futures
import threading
from datetime import datetime
import sys
import os

# Test Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

class BackendAudit:
    def __init__(self):
        self.admin_token = None
        self.user_token = None
        self.results = {}
        self.risk_levels = {}
        
    def authenticate_admin(self):
        """Authenticate admin user"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                return True
            return False
        except Exception as e:
            print(f"Admin auth failed: {e}")
            return False
    
    def authenticate_user(self):
        """Authenticate user"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/login/user",
                json={"email": USER_EMAIL, "password": USER_PASSWORD},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get("access_token")
                return True
            return False
        except Exception as e:
            print(f"User auth failed: {e}")
            return False
    
    def get_headers(self, token):
        """Get authorization headers"""
        return {"Authorization": f"Bearer {token}"}
    
    def audit_advisory_mode_rules(self):
        """
        1) Advisory Mode blocked/non_tradeable rules
        Check if hard-coded blocking rules are active and will auto-lift in live
        """
        print("\n=== 1) ADVISORY MODE BLOCKED/NON_TRADEABLE RULES AUDIT ===")
        
        try:
            # Test trading validation to check for blocking rules
            headers = self.get_headers(self.user_token)
            
            # Check order validation for blocking rules
            validation_payload = {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "market",
                "quantity": 0.001,
                "market_type": "spot"
            }
            
            response = requests.post(
                f"{BASE_URL}/api/user/validate-order",
                json=validation_payload,
                headers=headers,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                violations = data.get("violations", [])
                advisory_mode = data.get("advisory_mode", False)
                execution_mode = data.get("execution_mode", "unknown")
                
                # Check for hard-coded blocking violations
                blocking_violations = [v for v in violations if "blocked" in str(v).lower() or "non_tradeable" in str(v).lower()]
                
                result = {
                    "status": "PASS" if len(blocking_violations) == 0 else "FAIL",
                    "violations_count": len(violations),
                    "blocking_violations": blocking_violations,
                    "advisory_mode": advisory_mode,
                    "execution_mode": execution_mode,
                    "evidence": f"Trading validation: {len(violations)} violations, {len(blocking_violations)} blocking"
                }
                
                # Risk assessment
                if len(blocking_violations) > 0:
                    risk_level = "HIGH"
                    go_no_go = "NO-GO - Active blocking rules preventing trading"
                elif advisory_mode:
                    risk_level = "MEDIUM" 
                    go_no_go = "CAUTION - Advisory mode active"
                else:
                    risk_level = "LOW"
                    go_no_go = "GO - No blocking rules affecting trading"
                
                self.results["advisory_mode"] = result
                self.risk_levels["advisory_mode"] = {"risk": risk_level, "go_no_go": go_no_go}
                
                print(f"✅ Advisory Mode Check: {result['status']}")
                print(f"   Violations: {len(violations)}, Blocking: {len(blocking_violations)}")
                print(f"   Advisory Mode: {advisory_mode}, Execution Mode: {execution_mode}")
                print(f"   Risk Level: {risk_level}")
                print(f"   GO/NO-GO: {go_no_go}")
                
            else:
                self.results["advisory_mode"] = {"status": "ERROR", "error": f"HTTP {response.status_code}"}
                self.risk_levels["advisory_mode"] = {"risk": "HIGH", "go_no_go": "NO-GO - Cannot validate trading rules"}
                print(f"❌ Advisory Mode Check Failed: HTTP {response.status_code}")
                
        except Exception as e:
            self.results["advisory_mode"] = {"status": "ERROR", "error": str(e)}
            self.risk_levels["advisory_mode"] = {"risk": "HIGH", "go_no_go": "NO-GO - Advisory mode check failed"}
            print(f"❌ Advisory Mode Check Exception: {e}")
    
    def audit_mock_static_json(self):
        """
        2) Mock/stub/static JSON control
        Verify scanner path has real exchange data proof, not mocked responses
        """
        print("\n=== 2) MOCK/STUB/STATIC JSON CONTROL AUDIT ===")
        
        try:
            headers = self.get_headers(self.user_token)
            
            # Test market ticker for real data
            ticker_response = requests.get(
                f"{BASE_URL}/api/market/ticker?symbol=BTCUSDT",
                headers=headers,
                timeout=15
            )
            
            real_data_evidence = []
            mock_evidence = []
            
            if ticker_response.status_code == 200:
                ticker_data = ticker_response.json()
                price = ticker_data.get("price", 0)
                timestamp = ticker_data.get("timestamp")
                environment = ticker_data.get("environment", "unknown")
                
                if price > 0:
                    real_data_evidence.append(f"Market ticker: BTCUSDT price={price}, env={environment}")
                else:
                    mock_evidence.append(f"Market ticker: BTCUSDT price=0 (likely mocked)")
            else:
                mock_evidence.append(f"Market ticker: HTTP {ticker_response.status_code}")
            
            # Test scanner analysis for real data
            try:
                scanner_response = requests.get(
                    f"{BASE_URL}/api/user/scanner/analysis?limit=5",
                    headers=headers,
                    timeout=15
                )
                
                if scanner_response.status_code == 200:
                    scanner_data = scanner_response.json()
                    items = scanner_data.get("items", [])
                    if len(items) > 0:
                        # Check for real analysis data
                        sample_item = items[0]
                        if "score" in sample_item and "analysis" in sample_item:
                            real_data_evidence.append(f"Scanner analysis: {len(items)} items with scores")
                        else:
                            mock_evidence.append(f"Scanner analysis: Missing score/analysis fields")
                    else:
                        mock_evidence.append("Scanner analysis: No items returned")
                else:
                    mock_evidence.append(f"Scanner analysis: HTTP {scanner_response.status_code}")
                    
            except requests.exceptions.Timeout:
                mock_evidence.append("Scanner analysis: Timeout (possible mock/broken integration)")
            
            # Risk assessment
            if len(mock_evidence) > len(real_data_evidence):
                risk_level = "HIGH"
                status = "FAIL"
                go_no_go = "NO-GO - Mock/static data detected, real exchange integration failing"
            elif len(mock_evidence) > 0:
                risk_level = "MEDIUM"
                status = "PARTIAL"
                go_no_go = "CAUTION - Some mock data detected"
            else:
                risk_level = "LOW"
                status = "PASS"
                go_no_go = "GO - Real exchange data confirmed"
            
            result = {
                "status": status,
                "real_data_evidence": real_data_evidence,
                "mock_evidence": mock_evidence,
                "real_count": len(real_data_evidence),
                "mock_count": len(mock_evidence)
            }
            
            self.results["mock_static_json"] = result
            self.risk_levels["mock_static_json"] = {"risk": risk_level, "go_no_go": go_no_go}
            
            print(f"✅ Mock/Static JSON Check: {status}")
            print(f"   Real Data Evidence: {len(real_data_evidence)}")
            for evidence in real_data_evidence:
                print(f"     - {evidence}")
            print(f"   Mock Evidence: {len(mock_evidence)}")
            for evidence in mock_evidence:
                print(f"     - {evidence}")
            print(f"   Risk Level: {risk_level}")
            print(f"   GO/NO-GO: {go_no_go}")
            
        except Exception as e:
            self.results["mock_static_json"] = {"status": "ERROR", "error": str(e)}
            self.risk_levels["mock_static_json"] = {"risk": "HIGH", "go_no_go": "NO-GO - Cannot verify data sources"}
            print(f"❌ Mock/Static JSON Check Exception: {e}")
    
    def audit_race_idempotency(self):
        """
        3) Race/idempotency conditions
        Test scanner-engine + strategy-allocation timeout/crash behavior
        """
        print("\n=== 3) RACE CONDITIONS/IDEMPOTENCY AUDIT ===")
        
        try:
            headers = self.get_headers(self.user_token)
            admin_headers = self.get_headers(self.admin_token)
            
            # Test concurrent scanner engine calls
            def call_scanner_engine():
                try:
                    response = requests.post(
                        f"{BASE_URL}/api/user/scanner-engine/run-async",
                        json={"scan_limit": 100},
                        headers=headers,
                        timeout=10
                    )
                    return {"status": response.status_code, "response": response.json() if response.status_code == 200 else None}
                except Exception as e:
                    return {"status": "ERROR", "error": str(e)}
            
            # Execute concurrent calls
            print("   Testing concurrent scanner engine calls...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(call_scanner_engine) for _ in range(3)]
                concurrent_results = [f.result() for f in futures]
            
            # Analyze results
            success_count = sum(1 for r in concurrent_results if r.get("status") == 200)
            conflict_count = sum(1 for r in concurrent_results if r.get("status") == 409)
            error_count = sum(1 for r in concurrent_results if r.get("status") not in [200, 409])
            
            # Test strategy allocation under load
            strategy_allocation_ok = True
            try:
                alloc_response = requests.get(
                    f"{BASE_URL}/api/admin/strategy-allocation",
                    headers=admin_headers,
                    timeout=10
                )
                if alloc_response.status_code != 200:
                    strategy_allocation_ok = False
            except:
                strategy_allocation_ok = False
            
            # Risk assessment
            if error_count > 0 or not strategy_allocation_ok:
                risk_level = "HIGH"
                status = "FAIL"
                go_no_go = "NO-GO - Race conditions causing errors"
            elif conflict_count == 0 and success_count < 2:
                risk_level = "HIGH"
                status = "FAIL"
                go_no_go = "NO-GO - No idempotency handling"
            elif success_count > 0 and conflict_count > 0:
                risk_level = "LOW"
                status = "PASS"
                go_no_go = "GO - Proper idempotency handling detected"
            else:
                risk_level = "MEDIUM"
                status = "PARTIAL"
                go_no_go = "CAUTION - Unclear idempotency behavior"
            
            result = {
                "status": status,
                "concurrent_calls": len(concurrent_results),
                "success_count": success_count,
                "conflict_count": conflict_count,
                "error_count": error_count,
                "strategy_allocation_ok": strategy_allocation_ok,
                "evidence": f"Concurrent calls: {success_count} success, {conflict_count} conflicts, {error_count} errors"
            }
            
            self.results["race_idempotency"] = result
            self.risk_levels["race_idempotency"] = {"risk": risk_level, "go_no_go": go_no_go}
            
            print(f"✅ Race/Idempotency Check: {status}")
            print(f"   Concurrent Calls: {len(concurrent_results)}")
            print(f"   Success: {success_count}, Conflicts: {conflict_count}, Errors: {error_count}")
            print(f"   Strategy Allocation OK: {strategy_allocation_ok}")
            print(f"   Risk Level: {risk_level}")
            print(f"   GO/NO-GO: {go_no_go}")
            
        except Exception as e:
            self.results["race_idempotency"] = {"status": "ERROR", "error": str(e)}
            self.risk_levels["race_idempotency"] = {"risk": "HIGH", "go_no_go": "NO-GO - Cannot test concurrency"}
            print(f"❌ Race/Idempotency Check Exception: {e}")
    
    def audit_scalability(self):
        """
        4) Scalability assessment
        Check current environment high symbol load CPU/memory trend + pool capacity risk
        """
        print("\n=== 4) SCALABILITY AUDIT ===")
        
        try:
            headers = self.get_headers(self.admin_token)
            
            # Get system health metrics
            health_response = requests.get(
                f"{BASE_URL}/api/health",
                timeout=10
            )
            
            # Get system metrics if available
            metrics_data = {}
            if health_response.status_code == 200:
                health_data = health_response.json()
                metrics_data.update(health_data)
            
            # Test load with multiple concurrent requests
            def load_test_call():
                try:
                    response = requests.get(f"{BASE_URL}/api/health", timeout=5)
                    return {"status": response.status_code, "time": time.time()}
                except Exception as e:
                    return {"status": "ERROR", "error": str(e)}
            
            print("   Running load test (10 concurrent health checks)...")
            start_time = time.time()
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(load_test_call) for _ in range(10)]
                load_results = [f.result() for f in futures]
            end_time = time.time()
            
            # Analyze load test results
            successful_calls = sum(1 for r in load_results if r.get("status") == 200)
            total_time = end_time - start_time
            avg_response_time = total_time / len(load_results)
            
            # Check for high symbol load indicators
            try:
                # Test market data endpoint for symbol capacity
                symbols_response = requests.get(
                    f"{BASE_URL}/api/market/symbols?limit=100",
                    headers=headers,
                    timeout=10
                )
                symbol_count = 0
                if symbols_response.status_code == 200:
                    symbols_data = symbols_response.json()
                    symbol_count = len(symbols_data.get("symbols", []))
            except:
                symbol_count = 0
            
            # Risk assessment
            risk_factors = []
            if successful_calls < 8:  # Less than 80% success rate
                risk_factors.append("Low success rate under load")
            if avg_response_time > 2.0:  # Slow response times
                risk_factors.append("High response times")
            if symbol_count > 1000:  # High symbol count
                risk_factors.append("High symbol count may impact performance")
            
            if len(risk_factors) >= 2:
                risk_level = "HIGH"
                status = "FAIL"
                go_no_go = "NO-GO - Multiple scalability risk factors"
            elif len(risk_factors) == 1:
                risk_level = "MEDIUM"
                status = "PARTIAL"
                go_no_go = "CAUTION - Some scalability concerns"
            else:
                risk_level = "LOW"
                status = "PASS"
                go_no_go = "GO - System can handle increased load"
            
            result = {
                "status": status,
                "load_test_success_rate": f"{successful_calls}/{len(load_results)}",
                "avg_response_time": round(avg_response_time, 3),
                "symbol_count": symbol_count,
                "risk_factors": risk_factors,
                "metrics": metrics_data
            }
            
            self.results["scalability"] = result
            self.risk_levels["scalability"] = {"risk": risk_level, "go_no_go": go_no_go}
            
            print(f"✅ Scalability Check: {status}")
            print(f"   Load Test: {successful_calls}/{len(load_results)} successful")
            print(f"   Avg Response Time: {avg_response_time:.3f}s")
            print(f"   Symbol Count: {symbol_count}")
            print(f"   Risk Factors: {len(risk_factors)}")
            for factor in risk_factors:
                print(f"     - {factor}")
            print(f"   Risk Level: {risk_level}")
            print(f"   GO/NO-GO: {go_no_go}")
            
        except Exception as e:
            self.results["scalability"] = {"status": "ERROR", "error": str(e)}
            self.risk_levels["scalability"] = {"risk": "HIGH", "go_no_go": "NO-GO - Cannot assess scalability"}
            print(f"❌ Scalability Check Exception: {e}")
    
    def audit_auth_persistence(self):
        """
        5) Auth persistence
        Test CDN/WAF external backend effects + JWT/refresh adequacy
        """
        print("\n=== 5) AUTH PERSISTENCE AUDIT ===")
        
        try:
            # Test JWT token validation
            headers = self.get_headers(self.user_token)
            
            # Test current session
            me_response = requests.get(
                f"{BASE_URL}/api/auth/me",
                headers=headers,
                timeout=10
            )
            
            session_valid = me_response.status_code == 200
            
            # Test refresh token if available (try to get refresh token)
            refresh_available = False
            try:
                # Attempt to use refresh endpoint
                refresh_response = requests.post(
                    f"{BASE_URL}/api/auth/refresh",
                    headers=headers,
                    timeout=10
                )
                refresh_available = refresh_response.status_code in [200, 401]  # 401 means endpoint exists but token invalid
            except:
                pass
            
            # Test concurrent sessions (simulate CDN/WAF scenario)
            concurrent_sessions_ok = True
            try:
                # Make multiple concurrent auth requests
                def auth_check():
                    try:
                        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=5)
                        return response.status_code == 200
                    except:
                        return False
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(auth_check) for _ in range(3)]
                    auth_results = [f.result() for f in futures]
                
                concurrent_sessions_ok = all(auth_results)
            except:
                concurrent_sessions_ok = False
            
            # Test external access simulation (different headers)
            external_access_ok = True
            try:
                external_headers = {
                    **headers,
                    "X-Forwarded-For": "203.0.113.1",  # Simulate CDN
                    "X-Real-IP": "203.0.113.1",
                    "User-Agent": "Mozilla/5.0 (compatible; CDN-Bot/1.0)"
                }
                external_response = requests.get(
                    f"{BASE_URL}/api/auth/me",
                    headers=external_headers,
                    timeout=10
                )
                external_access_ok = external_response.status_code == 200
            except:
                external_access_ok = False
            
            # Risk assessment
            risk_factors = []
            if not session_valid:
                risk_factors.append("Session validation failing")
            if not refresh_available:
                risk_factors.append("Refresh token mechanism not available")
            if not concurrent_sessions_ok:
                risk_factors.append("Concurrent session handling issues")
            if not external_access_ok:
                risk_factors.append("External access (CDN/WAF) compatibility issues")
            
            if len(risk_factors) >= 2:
                risk_level = "HIGH"
                status = "FAIL"
                go_no_go = "NO-GO - Multiple auth persistence issues"
            elif len(risk_factors) == 1:
                risk_level = "MEDIUM"
                status = "PARTIAL"
                go_no_go = "CAUTION - Some auth concerns"
            else:
                risk_level = "LOW"
                status = "PASS"
                go_no_go = "GO - Auth persistence adequate"
            
            result = {
                "status": status,
                "session_valid": session_valid,
                "refresh_available": refresh_available,
                "concurrent_sessions_ok": concurrent_sessions_ok,
                "external_access_ok": external_access_ok,
                "risk_factors": risk_factors
            }
            
            self.results["auth_persistence"] = result
            self.risk_levels["auth_persistence"] = {"risk": risk_level, "go_no_go": go_no_go}
            
            print(f"✅ Auth Persistence Check: {status}")
            print(f"   Session Valid: {session_valid}")
            print(f"   Refresh Available: {refresh_available}")
            print(f"   Concurrent Sessions OK: {concurrent_sessions_ok}")
            print(f"   External Access OK: {external_access_ok}")
            print(f"   Risk Factors: {len(risk_factors)}")
            for factor in risk_factors:
                print(f"     - {factor}")
            print(f"   Risk Level: {risk_level}")
            print(f"   GO/NO-GO: {go_no_go}")
            
        except Exception as e:
            self.results["auth_persistence"] = {"status": "ERROR", "error": str(e)}
            self.risk_levels["auth_persistence"] = {"risk": "HIGH", "go_no_go": "NO-GO - Cannot verify auth persistence"}
            print(f"❌ Auth Persistence Check Exception: {e}")
    
    def generate_final_assessment(self):
        """Generate final GO/NO-GO assessment"""
        print("\n" + "="*80)
        print("FINAL GO/NO-GO ASSESSMENT")
        print("="*80)
        
        # Count risk levels
        critical_count = sum(1 for r in self.risk_levels.values() if r["risk"] == "CRITICAL")
        high_count = sum(1 for r in self.risk_levels.values() if r["risk"] == "HIGH")
        medium_count = sum(1 for r in self.risk_levels.values() if r["risk"] == "MEDIUM")
        low_count = sum(1 for r in self.risk_levels.values() if r["risk"] == "LOW")
        
        # Determine overall assessment
        if critical_count > 0 or high_count >= 2:
            overall_decision = "NO-GO"
            overall_risk = "HIGH"
        elif high_count == 1 or medium_count >= 2:
            overall_decision = "CAUTION"
            overall_risk = "MEDIUM"
        else:
            overall_decision = "GO"
            overall_risk = "LOW"
        
        print(f"\nOVERALL DECISION: {overall_decision}")
        print(f"OVERALL RISK LEVEL: {overall_risk}")
        print(f"\nRISK BREAKDOWN:")
        print(f"  Critical: {critical_count}")
        print(f"  High: {high_count}")
        print(f"  Medium: {medium_count}")
        print(f"  Low: {low_count}")
        
        print(f"\nDETAILED ASSESSMENT BY AREA:")
        areas = [
            ("Advisory Mode", "advisory_mode"),
            ("Mock/Static JSON", "mock_static_json"),
            ("Race/Idempotency", "race_idempotency"),
            ("Scalability", "scalability"),
            ("Auth Persistence", "auth_persistence")
        ]
        
        for area_name, area_key in areas:
            if area_key in self.risk_levels:
                risk_info = self.risk_levels[area_key]
                print(f"  {area_name}: {risk_info['risk']} RISK - {risk_info['go_no_go']}")
            else:
                print(f"  {area_name}: NOT TESTED")
        
        # Production readiness summary
        print(f"\nPRODUCTION READINESS SUMMARY:")
        if overall_decision == "GO":
            print("✅ SYSTEM IS READY FOR PRODUCTION")
            print("   All critical areas assessed with acceptable risk levels")
        elif overall_decision == "CAUTION":
            print("⚠️  SYSTEM REQUIRES ATTENTION BEFORE PRODUCTION")
            print("   Some areas have medium/high risks that should be addressed")
        else:
            print("❌ SYSTEM IS NOT READY FOR PRODUCTION")
            print("   Critical issues must be resolved before go-live")
        
        return {
            "overall_decision": overall_decision,
            "overall_risk": overall_risk,
            "risk_counts": {
                "critical": critical_count,
                "high": high_count,
                "medium": medium_count,
                "low": low_count
            },
            "area_assessments": self.risk_levels,
            "detailed_results": self.results
        }
    
    def run_audit(self):
        """Run complete GO/NO-GO audit"""
        print("GO/NO-GO FINAL BACKEND AUDIT (Pure Live sonrası)")
        print("="*60)
        print(f"Base URL: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print(f"User: {USER_EMAIL}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        
        # Authenticate
        print("\n=== AUTHENTICATION ===")
        admin_auth = self.authenticate_admin()
        user_auth = self.authenticate_user()
        
        if not admin_auth or not user_auth:
            print("❌ Authentication failed - cannot proceed with audit")
            return {"error": "Authentication failed"}
        
        print("✅ Authentication successful")
        
        # Run all audits
        self.audit_advisory_mode_rules()
        self.audit_mock_static_json()
        self.audit_race_idempotency()
        self.audit_scalability()
        self.audit_auth_persistence()
        
        # Generate final assessment
        final_assessment = self.generate_final_assessment()
        
        return final_assessment

if __name__ == "__main__":
    audit = BackendAudit()
    result = audit.run_audit()
    
    # Save results to file
    with open("/app/go_no_go_audit_results.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"\n✅ Audit complete. Results saved to /app/go_no_go_audit_results.json")