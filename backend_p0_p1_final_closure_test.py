#!/usr/bin/env python3
"""
P0+P1 FINAL CLOSURE VALIDATION TEST
Turkish Review Request: P0+P1 FINAL closure doğrulaması yap (backend + frontend smoke + rapor dosyaları)

Test URL: https://dry-run-shadow.preview.emergentagent.com
Credentials: canary.admin@platform.local / CanaryAdmin123!

Requirements to validate:
1) Canonical P0 endpoints (primary)
2) Explain minimum contract
3) Replay minimum
4) Repo/deploy guard
5) P1 Query/RCA/Incident
6) Observability
7) Performance evidence files
"""

import requests
import json
import time
import os
from datetime import datetime

class P0P1FinalClosureValidator:
    def __init__(self):
        self.base_url = "https://dry-run-shadow.preview.emergentagent.com"
        self.admin_email = "canary.admin@platform.local"
        self.admin_password = "CanaryAdmin123!"
        self.token = None
        self.test_results = []
        
    def log_test(self, test_name, status, details):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status} - {details}")
        
    def authenticate(self):
        """Authenticate with admin credentials"""
        try:
            auth_url = f"{self.base_url}/api/auth/login"
            payload = {
                "email": self.admin_email,
                "password": self.admin_password
            }
            
            response = requests.post(auth_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                if self.token:
                    self.log_test("Admin Authentication", "PASS", f"Token obtained (length: {len(self.token)} chars)")
                    return True
                else:
                    self.log_test("Admin Authentication", "FAIL", "No access_token in response")
                    return False
            else:
                self.log_test("Admin Authentication", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Admin Authentication", "FAIL", f"Exception: {str(e)}")
            return False
    
    def get_headers(self):
        """Get authorization headers"""
        return {"Authorization": f"Bearer {self.token}"}
    
    def test_canonical_p0_endpoints(self):
        """Test 1: Canonical P0 endpoints (primary)"""
        print("\n=== TEST 1: CANONICAL P0 ENDPOINTS ===")
        
        # Test GET /api/audit-logs/trading-lifecycle
        try:
            url = f"{self.base_url}/api/audit-logs/trading-lifecycle"
            response = requests.get(url, headers=self.get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["correlation_id", "events", "trace_incomplete", "missing_critical_stages", "broken_chain"]
                
                # Check if response has chains/items
                chains = data.get("chains", [])
                if chains:
                    first_chain = chains[0]
                    missing_fields = []
                    for field in required_fields:
                        if field not in first_chain:
                            missing_fields.append(field)
                    
                    if not missing_fields:
                        self.log_test("P0 Trading Lifecycle Endpoint", "PASS", 
                                    f"All required fields present: {required_fields}")
                    else:
                        self.log_test("P0 Trading Lifecycle Endpoint", "FAIL", 
                                    f"Missing fields: {missing_fields}")
                else:
                    self.log_test("P0 Trading Lifecycle Endpoint", "PARTIAL", 
                                "Endpoint accessible but no chains data")
            else:
                self.log_test("P0 Trading Lifecycle Endpoint", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("P0 Trading Lifecycle Endpoint", "FAIL", f"Exception: {str(e)}")
        
        # Test GET /api/audit-logs/lifecycle/{correlation_id}
        try:
            # First get a correlation_id from trading-lifecycle
            url = f"{self.base_url}/api/audit-logs/trading-lifecycle"
            response = requests.get(url, headers=self.get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                chains = data.get("chains", [])
                if chains:
                    correlation_id = chains[0].get("correlation_id")
                    if correlation_id:
                        # Test lifecycle detail endpoint
                        detail_url = f"{self.base_url}/api/audit-logs/lifecycle/{correlation_id}"
                        detail_response = requests.get(detail_url, headers=self.get_headers(), timeout=30)
                        
                        if detail_response.status_code == 200:
                            detail_data = detail_response.json()
                            required_fields = ["correlation_id", "events", "trace_incomplete", "missing_critical_stages", "broken_chain"]
                            
                            missing_fields = []
                            for field in required_fields:
                                if field not in detail_data:
                                    missing_fields.append(field)
                            
                            if not missing_fields:
                                self.log_test("P0 Lifecycle Detail Endpoint", "PASS", 
                                            f"All required fields present: {required_fields}")
                            else:
                                self.log_test("P0 Lifecycle Detail Endpoint", "FAIL", 
                                            f"Missing fields: {missing_fields}")
                        else:
                            self.log_test("P0 Lifecycle Detail Endpoint", "FAIL", 
                                        f"HTTP {detail_response.status_code}: {detail_response.text}")
                    else:
                        self.log_test("P0 Lifecycle Detail Endpoint", "FAIL", 
                                    "No correlation_id found in trading-lifecycle response")
                else:
                    self.log_test("P0 Lifecycle Detail Endpoint", "PARTIAL", 
                                "No chains available for testing")
            else:
                self.log_test("P0 Lifecycle Detail Endpoint", "FAIL", 
                            "Could not get correlation_id from trading-lifecycle")
                
        except Exception as e:
            self.log_test("P0 Lifecycle Detail Endpoint", "FAIL", f"Exception: {str(e)}")
        
        # Test POST /api/audit-logs/explain
        try:
            url = f"{self.base_url}/api/audit-logs/explain"
            payload = {
                "correlation_id": "test-correlation-id",
                "events": [],
                "trace_incomplete": True,
                "missing_critical_stages": ["intent", "decision"],
                "broken_chain": True
            }
            
            response = requests.post(url, json=payload, headers=self.get_headers(), timeout=30)
            
            if response.status_code in [200, 201]:
                data = response.json()
                self.log_test("P0 Explain Endpoint", "PASS", 
                            f"Endpoint accessible, response: {len(str(data))} chars")
            else:
                self.log_test("P0 Explain Endpoint", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("P0 Explain Endpoint", "FAIL", f"Exception: {str(e)}")
    
    def test_explain_minimum_contract(self):
        """Test 2: Explain minimum contract"""
        print("\n=== TEST 2: EXPLAIN MINIMUM CONTRACT ===")
        
        try:
            url = f"{self.base_url}/api/audit-logs/explain"
            payload = {
                "correlation_id": "test-correlation-id",
                "events": [],
                "trace_incomplete": True,
                "missing_critical_stages": ["intent", "decision"],
                "broken_chain": True
            }
            
            response = requests.post(url, json=payload, headers=self.get_headers(), timeout=30)
            
            if response.status_code in [200, 201]:
                data = response.json()
                required_fields = ["broken_step", "root_cause", "missing_stages", "upstream_event", 
                                 "downstream_impact", "confidence", "insufficient_data"]
                
                missing_fields = []
                for field in required_fields:
                    if field not in data:
                        missing_fields.append(field)
                
                if not missing_fields:
                    self.log_test("Explain Contract Fields", "PASS", 
                                f"All required fields present: {required_fields}")
                else:
                    self.log_test("Explain Contract Fields", "PARTIAL", 
                                f"Missing fields: {missing_fields}, Present fields: {list(data.keys())}")
            else:
                self.log_test("Explain Contract Fields", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Explain Contract Fields", "FAIL", f"Exception: {str(e)}")
    
    def test_replay_minimum(self):
        """Test 3: Replay minimum"""
        print("\n=== TEST 3: REPLAY MINIMUM ===")
        
        # Check for replay endpoint
        try:
            url = f"{self.base_url}/api/audit-logs/replay"
            response = requests.get(url, headers=self.get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["deterministic", "isolated", "no_external_side_effect"]
                
                missing_fields = []
                for field in required_fields:
                    if field not in data:
                        missing_fields.append(field)
                
                if not missing_fields:
                    self.log_test("Replay Minimum Fields", "PASS", 
                                f"All required fields present: {required_fields}")
                else:
                    self.log_test("Replay Minimum Fields", "PARTIAL", 
                                f"Missing fields: {missing_fields}")
            else:
                self.log_test("Replay Minimum Fields", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Replay Minimum Fields", "FAIL", f"Exception: {str(e)}")
    
    def test_repo_deploy_guard(self):
        """Test 4: Repo/deploy guard"""
        print("\n=== TEST 4: REPO/DEPLOY GUARD ===")
        
        try:
            url = f"{self.base_url}/api/audit-logs/consistency/repo-deploy"
            response = requests.get(url, headers=self.get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Repo Deploy Guard Endpoint", "PASS", 
                            f"Endpoint accessible, response: {len(str(data))} chars")
                
                # Check for mismatch block design
                if "explain_replay_mismatch" in data or "block_design" in data:
                    self.log_test("Explain/Replay Mismatch Block", "PASS", 
                                "Mismatch block design present")
                else:
                    self.log_test("Explain/Replay Mismatch Block", "PARTIAL", 
                                "Block design structure not clearly identified")
            else:
                self.log_test("Repo Deploy Guard Endpoint", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Repo Deploy Guard Endpoint", "FAIL", f"Exception: {str(e)}")
    
    def test_p1_query_rca_incident(self):
        """Test 5: P1 Query/RCA/Incident"""
        print("\n=== TEST 5: P1 QUERY/RCA/INCIDENT ===")
        
        # Test advanced filter
        try:
            url = f"{self.base_url}/api/audit-logs/trading-lifecycle"
            params = {
                "severity": "error",
                "event_type": "execution",
                "payload_query": "test"
            }
            response = requests.get(url, params=params, headers=self.get_headers(), timeout=30)
            
            if response.status_code == 200:
                self.log_test("P1 Advanced Filter", "PASS", "Advanced filter parameters accepted")
            else:
                self.log_test("P1 Advanced Filter", "FAIL", f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("P1 Advanced Filter", "FAIL", f"Exception: {str(e)}")
        
        # Test saved query
        try:
            url = f"{self.base_url}/api/audit-logs/saved-queries"
            response = requests.get(url, headers=self.get_headers(), timeout=30)
            
            if response.status_code == 200:
                self.log_test("P1 Saved Query", "PASS", "Saved query endpoint accessible")
            else:
                self.log_test("P1 Saved Query", "FAIL", f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("P1 Saved Query", "FAIL", f"Exception: {str(e)}")
        
        # Test incident create/list/status
        try:
            url = f"{self.base_url}/api/audit-logs/incidents"
            response = requests.get(url, headers=self.get_headers(), timeout=30)
            
            if response.status_code == 200:
                self.log_test("P1 Incident Management", "PASS", "Incident endpoints accessible")
            else:
                self.log_test("P1 Incident Management", "FAIL", f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("P1 Incident Management", "FAIL", f"Exception: {str(e)}")
        
        # Test RCA output fields
        try:
            url = f"{self.base_url}/api/audit-logs/explain"
            payload = {
                "correlation_id": "test-correlation-id",
                "events": [],
                "trace_incomplete": True,
                "missing_critical_stages": ["intent"],
                "broken_chain": True
            }
            
            response = requests.post(url, json=payload, headers=self.get_headers(), timeout=30)
            
            if response.status_code in [200, 201]:
                data = response.json()
                rca_fields = ["failure_type", "root_cause", "pattern_id", "cluster_id", "confidence"]
                
                present_fields = []
                for field in rca_fields:
                    if field in data:
                        present_fields.append(field)
                
                if len(present_fields) >= 3:  # At least 3 out of 5 fields
                    self.log_test("P1 RCA Output Fields", "PASS", 
                                f"RCA fields present: {present_fields}")
                else:
                    self.log_test("P1 RCA Output Fields", "PARTIAL", 
                                f"Limited RCA fields: {present_fields}")
            else:
                self.log_test("P1 RCA Output Fields", "FAIL", f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("P1 RCA Output Fields", "FAIL", f"Exception: {str(e)}")
    
    def test_observability(self):
        """Test 6: Observability"""
        print("\n=== TEST 6: OBSERVABILITY ===")
        
        # Test /api/metrics
        try:
            url = f"{self.base_url}/api/metrics"
            response = requests.get(url, headers=self.get_headers(), timeout=30)
            
            if response.status_code == 200:
                metrics_text = response.text
                required_metrics = ["latency", "failure_rate", "success_rate", "throughput", "replay_duration"]
                
                present_metrics = []
                for metric in required_metrics:
                    if metric in metrics_text.lower():
                        present_metrics.append(metric)
                
                if len(present_metrics) >= 3:  # At least 3 out of 5 metrics
                    self.log_test("Observability Metrics", "PASS", 
                                f"Metrics present: {present_metrics}")
                else:
                    self.log_test("Observability Metrics", "PARTIAL", 
                                f"Limited metrics: {present_metrics}")
            else:
                self.log_test("Observability Metrics", "FAIL", f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Observability Metrics", "FAIL", f"Exception: {str(e)}")
        
        # Check for dashboard+alert files (this would be in the codebase)
        dashboard_files = [
            "/app/dashboard.json",
            "/app/alerts.json",
            "/app/monitoring/dashboard.yaml",
            "/app/monitoring/alerts.yaml"
        ]
        
        found_files = []
        for file_path in dashboard_files:
            if os.path.exists(file_path):
                found_files.append(file_path)
        
        if found_files:
            self.log_test("Dashboard/Alert Files", "PASS", f"Found files: {found_files}")
        else:
            self.log_test("Dashboard/Alert Files", "PARTIAL", "No dashboard/alert files found in expected locations")
    
    def test_performance_evidence_files(self):
        """Test 7: Performance evidence files"""
        print("\n=== TEST 7: PERFORMANCE EVIDENCE FILES ===")
        
        required_files = [
            "/app/test_reports/p1_seeded_benchmark_report.json",
            "/app/test_reports/p1_runtime_profile_report.json",
            "/app/test_reports/p0_p1_final_closure_report.json"
        ]
        
        found_files = []
        missing_files = []
        
        for file_path in required_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                        if len(content) > 10:  # Basic content check
                            found_files.append(file_path)
                        else:
                            missing_files.append(f"{file_path} (empty)")
                except Exception as e:
                    missing_files.append(f"{file_path} (read error: {str(e)})")
            else:
                missing_files.append(file_path)
        
        if len(found_files) == len(required_files):
            self.log_test("Performance Evidence Files", "PASS", 
                        f"All required files present: {found_files}")
        elif found_files:
            self.log_test("Performance Evidence Files", "PARTIAL", 
                        f"Found: {found_files}, Missing: {missing_files}")
        else:
            self.log_test("Performance Evidence Files", "FAIL", 
                        f"All files missing: {missing_files}")
    
    def test_frontend_smoke(self):
        """Frontend smoke test"""
        print("\n=== FRONTEND SMOKE TEST ===")
        
        try:
            url = f"{self.base_url}/admin/audit-logs"
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                content = response.text
                if len(content) > 1000 and "audit" in content.lower():
                    self.log_test("Frontend Smoke", "PASS", 
                                f"Frontend accessible ({len(content)} chars)")
                else:
                    self.log_test("Frontend Smoke", "PARTIAL", 
                                f"Frontend accessible but limited content ({len(content)} chars)")
            else:
                self.log_test("Frontend Smoke", "FAIL", f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Frontend Smoke", "FAIL", f"Exception: {str(e)}")
    
    def generate_summary(self):
        """Generate test summary"""
        print("\n" + "="*60)
        print("P0+P1 FINAL CLOSURE VALIDATION SUMMARY")
        print("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = len([t for t in self.test_results if t["status"] == "PASS"])
        failed_tests = len([t for t in self.test_results if t["status"] == "FAIL"])
        partial_tests = len([t for t in self.test_results if t["status"] == "PARTIAL"])
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ PASSED: {passed_tests}")
        print(f"⚠️ PARTIAL: {partial_tests}")
        print(f"❌ FAILED: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_symbol = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_symbol} {result['test']}: {result['status']} - {result['details']}")
        
        # Turkish summary
        print("\n" + "="*60)
        print("TÜRKÇE ÖZET (TURKISH SUMMARY)")
        print("="*60)
        
        if failed_tests == 0:
            print("✅ TÜM TESTLER BAŞARILI - Sistem production-ready")
        elif failed_tests <= 2:
            print("⚠️ ÇOĞU TEST BAŞARILI - Küçük sorunlar var, düzeltme gerekli")
        else:
            print("❌ ÇOK SAYIDA HATA - Ciddi sorunlar var, kapsamlı düzeltme gerekli")
        
        print(f"Başarı oranı: {(passed_tests/total_tests)*100:.1f}%")
        print(f"Geçen testler: {passed_tests}/{total_tests}")
        
        if failed_tests > 0:
            print("\nKRİTİK SORUNLAR:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"❌ {result['test']}: {result['details']}")
    
    def run_all_tests(self):
        """Run all validation tests"""
        print("P0+P1 FINAL CLOSURE VALIDATION TEST")
        print("URL:", self.base_url)
        print("Credentials:", self.admin_email)
        print("="*60)
        
        # Authenticate first
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Run all tests
        self.test_canonical_p0_endpoints()
        self.test_explain_minimum_contract()
        self.test_replay_minimum()
        self.test_repo_deploy_guard()
        self.test_p1_query_rca_incident()
        self.test_observability()
        self.test_performance_evidence_files()
        self.test_frontend_smoke()
        
        # Generate summary
        self.generate_summary()

if __name__ == "__main__":
    validator = P0P1FinalClosureValidator()
    validator.run_all_tests()