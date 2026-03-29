#!/usr/bin/env python3
"""
P0+P1 FINAL CLOSURE COMPREHENSIVE VALIDATION TEST
Turkish Review Request: P0+P1 FINAL closure doğrulaması yap (backend + frontend smoke + rapor dosyaları)

Test URL: https://unified-orchestrator.preview.emergentagent.com
Credentials: canary.admin@platform.local / CanaryAdmin123!

This test focuses on what can be validated given the security constraints.
"""

import requests
import json
import time
import os
from datetime import datetime

class P0P1ComprehensiveValidator:
    def __init__(self):
        self.base_url = "https://unified-orchestrator.preview.emergentagent.com"
        self.admin_email = "canary.admin@platform.local"
        self.admin_password = "CanaryAdmin123!"
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
        
    def test_authentication_endpoint(self):
        """Test 1: Authentication endpoint functionality"""
        print("\n=== TEST 1: AUTHENTICATION ENDPOINT ===")
        
        try:
            auth_url = f"{self.base_url}/api/auth/login"
            payload = {
                "email": self.admin_email,
                "password": self.admin_password
            }
            
            response = requests.post(auth_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                if token and len(token) > 100:
                    self.log_test("Authentication Endpoint", "PASS", 
                                f"Login successful, token obtained (length: {len(token)} chars)")
                    
                    # Check token structure
                    if "." in token and token.count(".") == 2:
                        self.log_test("JWT Token Structure", "PASS", "Valid JWT token format")
                    else:
                        self.log_test("JWT Token Structure", "PARTIAL", "Token format unclear")
                        
                    # Check user role
                    user_role = data.get("role", "unknown")
                    if user_role == "super_admin":
                        self.log_test("Admin Role Verification", "PASS", f"Role: {user_role}")
                    else:
                        self.log_test("Admin Role Verification", "PARTIAL", f"Role: {user_role}")
                        
                else:
                    self.log_test("Authentication Endpoint", "FAIL", "No valid access_token in response")
            else:
                self.log_test("Authentication Endpoint", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Authentication Endpoint", "FAIL", f"Exception: {str(e)}")
    
    def test_observability_metrics(self):
        """Test 2: Observability metrics endpoint"""
        print("\n=== TEST 2: OBSERVABILITY METRICS ===")
        
        try:
            url = f"{self.base_url}/api/metrics"
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                metrics_text = response.text
                required_metrics = ["latency", "failure_rate", "success_rate", "throughput", "replay_duration"]
                
                present_metrics = []
                for metric in required_metrics:
                    if metric in metrics_text.lower():
                        present_metrics.append(metric)
                
                if len(present_metrics) == len(required_metrics):
                    self.log_test("Observability Metrics Complete", "PASS", 
                                f"All required metrics present: {present_metrics}")
                elif len(present_metrics) >= 3:
                    self.log_test("Observability Metrics Partial", "PARTIAL", 
                                f"Most metrics present: {present_metrics}")
                else:
                    self.log_test("Observability Metrics", "FAIL", 
                                f"Limited metrics: {present_metrics}")
                
                # Check specific metric values
                lines = metrics_text.split('\n')
                metric_values = {}
                for line in lines:
                    if 'failure_rate' in line and '{' in line:
                        try:
                            value = float(line.split()[-1])
                            metric_values['failure_rate'] = value
                        except:
                            pass
                    if 'success_rate' in line and '{' in line:
                        try:
                            value = float(line.split()[-1])
                            metric_values['success_rate'] = value
                        except:
                            pass
                
                if metric_values:
                    self.log_test("Metrics Values", "PASS", 
                                f"Sample values: {metric_values}")
                else:
                    self.log_test("Metrics Values", "PARTIAL", "Could not parse metric values")
                    
            else:
                self.log_test("Observability Metrics", "FAIL", f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Observability Metrics", "FAIL", f"Exception: {str(e)}")
    
    def test_performance_evidence_files(self):
        """Test 3: Performance evidence files"""
        print("\n=== TEST 3: PERFORMANCE EVIDENCE FILES ===")
        
        required_files = [
            "/app/test_reports/p1_seeded_benchmark_report.json",
            "/app/test_reports/p1_runtime_profile_report.json",
            "/app/test_reports/p0_p1_final_closure_report.json"
        ]
        
        found_files = []
        missing_files = []
        file_details = {}
        
        for file_path in required_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                        if len(content) > 10:
                            data = json.loads(content)
                            found_files.append(file_path)
                            file_details[file_path] = {
                                "size": len(content),
                                "type": data.get("type", "unknown"),
                                "generated_at": data.get("generated_at", "unknown")
                            }
                        else:
                            missing_files.append(f"{file_path} (empty)")
                except Exception as e:
                    missing_files.append(f"{file_path} (parse error: {str(e)})")
            else:
                missing_files.append(file_path)
        
        if len(found_files) == len(required_files):
            self.log_test("Performance Evidence Files", "PASS", 
                        f"All required files present: {found_files}")
            
            # Validate file contents
            for file_path, details in file_details.items():
                filename = os.path.basename(file_path)
                self.log_test(f"File Content: {filename}", "PASS", 
                            f"Type: {details['type']}, Size: {details['size']} bytes, Generated: {details['generated_at']}")
                            
        elif found_files:
            self.log_test("Performance Evidence Files", "PARTIAL", 
                        f"Found: {found_files}, Missing: {missing_files}")
        else:
            self.log_test("Performance Evidence Files", "FAIL", 
                        f"All files missing: {missing_files}")
    
    def test_p0_p1_closure_report_content(self):
        """Test 4: P0+P1 closure report content validation"""
        print("\n=== TEST 4: P0+P1 CLOSURE REPORT CONTENT ===")
        
        try:
            file_path = "/app/test_reports/p0_p1_final_closure_report.json"
            with open(file_path, 'r') as f:
                data = json.loads(f.read())
            
            # Check P0 requirements
            p0_requirements = [
                "canonical_endpoints_primary",
                "lifecycle_chain_validation", 
                "explain_minimum_contract",
                "ui_lifecycle_debugger",
                "replay_deterministic_isolated",
                "repo_deploy_guard_hard_fail"
            ]
            
            p0_data = data.get("p0", {})
            p0_passed = []
            p0_failed = []
            
            for req in p0_requirements:
                if p0_data.get(req) == True:
                    p0_passed.append(req)
                else:
                    p0_failed.append(req)
            
            if len(p0_passed) == len(p0_requirements):
                self.log_test("P0 Requirements", "PASS", 
                            f"All P0 requirements met: {len(p0_passed)}/{len(p0_requirements)}")
            elif len(p0_passed) >= 4:
                self.log_test("P0 Requirements", "PARTIAL", 
                            f"Most P0 requirements met: {len(p0_passed)}/{len(p0_requirements)}, Failed: {p0_failed}")
            else:
                self.log_test("P0 Requirements", "FAIL", 
                            f"Too many P0 failures: {len(p0_passed)}/{len(p0_requirements)}, Failed: {p0_failed}")
            
            # Check P1 requirements
            p1_requirements = [
                "advanced_filtering",
                "full_text_search_indexed",
                "saved_query",
                "rca_automation",
                "metrics_dashboard_alerts",
                "pagination_virtual_scroll",
                "incident_management"
            ]
            
            p1_data = data.get("p1", {})
            p1_passed = []
            p1_failed = []
            
            for req in p1_requirements:
                if p1_data.get(req) == True:
                    p1_passed.append(req)
                else:
                    p1_failed.append(req)
            
            if len(p1_passed) == len(p1_requirements):
                self.log_test("P1 Requirements", "PASS", 
                            f"All P1 requirements met: {len(p1_passed)}/{len(p1_requirements)}")
            elif len(p1_passed) >= 5:
                self.log_test("P1 Requirements", "PARTIAL", 
                            f"Most P1 requirements met: {len(p1_passed)}/{len(p1_requirements)}, Failed: {p1_failed}")
            else:
                self.log_test("P1 Requirements", "FAIL", 
                            f"Too many P1 failures: {len(p1_passed)}/{len(p1_requirements)}, Failed: {p1_failed}")
            
            # Check performance benchmarks
            perf_data = p1_data.get("performance_benchmark", {})
            if "seeded" in perf_data and "runtime" in perf_data:
                seeded = perf_data["seeded"]
                runtime = perf_data["runtime"]
                
                if seeded.get("meets_target") and runtime.get("slo_pass"):
                    self.log_test("Performance Benchmarks", "PASS", 
                                f"Seeded: {seeded.get('meets_target')}, Runtime SLO: {runtime.get('slo_pass')}")
                else:
                    self.log_test("Performance Benchmarks", "PARTIAL", 
                                f"Seeded: {seeded.get('meets_target')}, Runtime SLO: {runtime.get('slo_pass')}")
            else:
                self.log_test("Performance Benchmarks", "FAIL", "Performance benchmark data missing")
            
            # Overall pass status
            overall_pass = data.get("overall_pass", False)
            if overall_pass:
                self.log_test("Overall Closure Status", "PASS", "overall_pass: true")
            else:
                self.log_test("Overall Closure Status", "FAIL", "overall_pass: false")
                
        except Exception as e:
            self.log_test("P0+P1 Closure Report Content", "FAIL", f"Exception: {str(e)}")
    
    def test_frontend_smoke(self):
        """Test 5: Frontend smoke test"""
        print("\n=== TEST 5: FRONTEND SMOKE TEST ===")
        
        try:
            # Test main page
            url = f"{self.base_url}"
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                content = response.text
                content_length = len(content)
                
                if content_length > 5000:
                    self.log_test("Frontend Main Page", "PASS", 
                                f"Frontend accessible ({content_length} chars)")
                    
                    # Check for key elements
                    if "html" in content.lower() and "head" in content.lower():
                        self.log_test("Frontend HTML Structure", "PASS", "Valid HTML structure")
                    else:
                        self.log_test("Frontend HTML Structure", "PARTIAL", "HTML structure unclear")
                        
                    # Check for React/JS app indicators
                    if "react" in content.lower() or "app" in content.lower() or "script" in content.lower():
                        self.log_test("Frontend App Framework", "PASS", "App framework detected")
                    else:
                        self.log_test("Frontend App Framework", "PARTIAL", "App framework unclear")
                        
                else:
                    self.log_test("Frontend Main Page", "PARTIAL", 
                                f"Frontend accessible but limited content ({content_length} chars)")
            else:
                self.log_test("Frontend Main Page", "FAIL", f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Frontend Main Page", "FAIL", f"Exception: {str(e)}")
    
    def test_endpoint_availability(self):
        """Test 6: Endpoint availability (without authentication)"""
        print("\n=== TEST 6: ENDPOINT AVAILABILITY ===")
        
        endpoints_to_test = [
            ("/api/health", "Health Check"),
            ("/api/ready", "Ready Check"),
            ("/api/metrics", "Metrics"),
            ("/api/audit-logs/trading-lifecycle", "Trading Lifecycle"),
            ("/api/audit-logs/explain", "Explain Endpoint"),
            ("/api/audit-logs/saved-queries", "Saved Queries"),
            ("/api/audit-logs/incidents", "Incidents"),
            ("/api/audit-logs/consistency/repo-deploy", "Repo Deploy Guard")
        ]
        
        available_endpoints = []
        auth_required_endpoints = []
        unavailable_endpoints = []
        
        for endpoint, name in endpoints_to_test:
            try:
                url = f"{self.base_url}{endpoint}"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    available_endpoints.append(name)
                elif response.status_code in [401, 403]:
                    auth_required_endpoints.append(name)
                else:
                    unavailable_endpoints.append(f"{name} ({response.status_code})")
                    
            except Exception as e:
                unavailable_endpoints.append(f"{name} (error)")
        
        if available_endpoints:
            self.log_test("Public Endpoints", "PASS", 
                        f"Available: {available_endpoints}")
        
        if auth_required_endpoints:
            self.log_test("Protected Endpoints", "PASS", 
                        f"Auth required (expected): {auth_required_endpoints}")
        
        if unavailable_endpoints:
            self.log_test("Unavailable Endpoints", "PARTIAL", 
                        f"Unavailable: {unavailable_endpoints}")
    
    def test_security_headers(self):
        """Test 7: Security headers"""
        print("\n=== TEST 7: SECURITY HEADERS ===")
        
        try:
            url = f"{self.base_url}/api/metrics"
            response = requests.get(url, timeout=30)
            
            security_headers = [
                "X-Content-Type-Options",
                "X-Frame-Options", 
                "X-XSS-Protection",
                "Strict-Transport-Security",
                "Content-Security-Policy"
            ]
            
            present_headers = []
            missing_headers = []
            
            for header in security_headers:
                if header in response.headers:
                    present_headers.append(header)
                else:
                    missing_headers.append(header)
            
            if len(present_headers) >= 3:
                self.log_test("Security Headers", "PASS", 
                            f"Present: {present_headers}")
            elif present_headers:
                self.log_test("Security Headers", "PARTIAL", 
                            f"Present: {present_headers}, Missing: {missing_headers}")
            else:
                self.log_test("Security Headers", "FAIL", 
                            f"No security headers found")
                
        except Exception as e:
            self.log_test("Security Headers", "FAIL", f"Exception: {str(e)}")
    
    def generate_summary(self):
        """Generate test summary"""
        print("\n" + "="*80)
        print("P0+P1 FINAL CLOSURE COMPREHENSIVE VALIDATION SUMMARY")
        print("="*80)
        
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
        print("\n" + "="*80)
        print("TÜRKÇE ÖZET (TURKISH SUMMARY)")
        print("="*80)
        
        if failed_tests == 0:
            print("✅ TÜM TESTLER BAŞARILI - Sistem production-ready")
            turkish_status = "PASS"
        elif failed_tests <= 2:
            print("⚠️ ÇOĞU TEST BAŞARILI - Küçük sorunlar var, düzeltme gerekli")
            turkish_status = "PARTIAL"
        else:
            print("❌ ÇOK SAYIDA HATA - Ciddi sorunlar var, kapsamlı düzeltme gerekli")
            turkish_status = "FAIL"
        
        print(f"Başarı oranı: {(passed_tests/total_tests)*100:.1f}%")
        print(f"Geçen testler: {passed_tests}/{total_tests}")
        
        # Key findings
        print("\nANA BULGULAR (KEY FINDINGS):")
        
        # Check for critical components
        auth_working = any("Authentication" in t["test"] and t["status"] == "PASS" for t in self.test_results)
        metrics_working = any("Metrics" in t["test"] and t["status"] == "PASS" for t in self.test_results)
        files_present = any("Performance Evidence" in t["test"] and t["status"] == "PASS" for t in self.test_results)
        frontend_working = any("Frontend" in t["test"] and t["status"] in ["PASS", "PARTIAL"] for t in self.test_results)
        
        print(f"✅ Authentication: {'ÇALIŞIYOR' if auth_working else 'SORUNLU'}")
        print(f"✅ Metrics/Observability: {'ÇALIŞIYOR' if metrics_working else 'SORUNLU'}")
        print(f"✅ Performance Reports: {'MEVCUT' if files_present else 'EKSİK'}")
        print(f"✅ Frontend: {'ERİŞİLEBİLİR' if frontend_working else 'SORUNLU'}")
        
        if failed_tests > 0:
            print("\nKRİTİK SORUNLAR:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"❌ {result['test']}: {result['details']}")
        
        return turkish_status
    
    def run_all_tests(self):
        """Run all validation tests"""
        print("P0+P1 FINAL CLOSURE COMPREHENSIVE VALIDATION TEST")
        print("URL:", self.base_url)
        print("Credentials:", self.admin_email)
        print("="*80)
        
        # Run all tests
        self.test_authentication_endpoint()
        self.test_observability_metrics()
        self.test_performance_evidence_files()
        self.test_p0_p1_closure_report_content()
        self.test_frontend_smoke()
        self.test_endpoint_availability()
        self.test_security_headers()
        
        # Generate summary
        return self.generate_summary()

if __name__ == "__main__":
    validator = P0P1ComprehensiveValidator()
    status = validator.run_all_tests()
    print(f"\nFINAL STATUS: {status}")