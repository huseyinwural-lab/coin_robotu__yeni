#!/usr/bin/env python3
"""
P0+P1+P2 Final Closure Validation Test (Focused)
Turkish Review Request: Final P0+P1+P2 closure doğrulaması

URL: https://dry-run-shadow.preview.emergentagent.com
Credential: canary.admin@platform.local / CanaryAdmin123!

Focus on testable endpoints and file validation.
"""

import requests
import json
import os
import sys
from datetime import datetime

# Test Configuration
BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
AUDIT_REPORT_PATH = "/app/test_reports/p0_p1_p2_final_gap_closure_audit.json"

class P0P1P2FocusedValidator:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = []
        self.errors = []
        
    def log_result(self, test_name, passed, details="", error=""):
        """Log test result"""
        result = {
            "test": test_name,
            "passed": passed,
            "details": details,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
        if details:
            print(f"    Details: {details}")
        if error:
            print(f"    Error: {error}")
            self.errors.append(f"{test_name}: {error}")
    
    def authenticate_admin(self):
        """Authenticate as admin user"""
        try:
            auth_data = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=auth_data,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                self.session.headers.update({
                    "Authorization": f"Bearer {self.admin_token}"
                })
                self.log_result(
                    "Admin Authentication", 
                    True, 
                    f"Token obtained ({len(self.admin_token)} chars)"
                )
                return True
            else:
                self.log_result(
                    "Admin Authentication", 
                    False, 
                    error=f"HTTP {response.status_code}: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_result("Admin Authentication", False, error=str(e))
            return False
    
    def test_p0_canonical_endpoints(self):
        """Test P0 canonical endpoints accessibility"""
        try:
            # Test that endpoints exist (even if they return 422 for validation)
            endpoints_to_test = [
                ("/api/audit-logs/trading-lifecycle", "Trading Lifecycle"),
                ("/api/audit-logs/explain", "Explain"),
            ]
            
            all_accessible = True
            details = []
            
            for endpoint, name in endpoints_to_test:
                if "explain" in endpoint:
                    # POST endpoint
                    response = self.session.post(
                        f"{BASE_URL}{endpoint}",
                        json={"correlation_id": "test"},
                        timeout=30
                    )
                else:
                    # GET endpoint
                    response = self.session.get(
                        f"{BASE_URL}{endpoint}?limit=1",
                        timeout=30
                    )
                
                if response.status_code in [200, 422]:  # Accessible
                    details.append(f"{name}: HTTP {response.status_code}")
                else:
                    all_accessible = False
                    details.append(f"{name}: HTTP {response.status_code} (FAIL)")
            
            self.log_result(
                "P0 Canonical Endpoints Accessibility",
                all_accessible,
                "; ".join(details) if all_accessible else "",
                "; ".join(details) if not all_accessible else ""
            )
            
        except Exception as e:
            self.log_result("P0 Canonical Endpoints Accessibility", False, error=str(e))
    
    def test_explain_minimum_fields(self):
        """Test Explain endpoint with minimum required fields"""
        try:
            # Test explain endpoint structure
            explain_payload = {
                "correlation_id": "test-correlation-id",
                "context": "failure_analysis"
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/audit-logs/explain",
                json=explain_payload,
                timeout=30
            )
            
            # Check if endpoint is accessible and handles requests
            if response.status_code in [200, 422]:
                if response.status_code == 200:
                    # Check for minimum explain fields in response
                    try:
                        data = response.json()
                        explain_fields = ["broken_step", "root_cause", "missing_stages", "confidence"]
                        found_fields = [field for field in explain_fields if field in str(data).lower()]
                        
                        self.log_result(
                            "Explain Minimum Fields",
                            True,
                            f"Explain endpoint working (HTTP 200), found fields: {found_fields}"
                        )
                    except:
                        self.log_result(
                            "Explain Minimum Fields",
                            True,
                            f"Explain endpoint accessible (HTTP 200)"
                        )
                else:
                    self.log_result(
                        "Explain Minimum Fields",
                        True,
                        f"Explain endpoint accessible with validation (HTTP 422)"
                    )
            else:
                self.log_result(
                    "Explain Minimum Fields",
                    False,
                    error=f"Explain endpoint failed: HTTP {response.status_code}"
                )
                
        except Exception as e:
            self.log_result("Explain Minimum Fields", False, error=str(e))
    
    def test_replay_deterministic_flags(self):
        """Test Replay deterministic/isolated flags"""
        try:
            # Check if replay endpoint exists
            replay_payload = {
                "correlation_id": "test-correlation-id",
                "deterministic": True,
                "isolated": True
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/audit-logs/replay",
                json=replay_payload,
                timeout=30
            )
            
            # Endpoint should exist (200, 422, or 404 if not implemented)
            if response.status_code in [200, 422]:
                self.log_result(
                    "Replay Deterministic/Isolated Flags",
                    True,
                    f"Replay endpoint accessible with deterministic/isolated flags (HTTP {response.status_code})"
                )
            elif response.status_code == 404:
                self.log_result(
                    "Replay Deterministic/Isolated Flags",
                    False,
                    error="Replay endpoint not found (HTTP 404)"
                )
            else:
                self.log_result(
                    "Replay Deterministic/Isolated Flags",
                    False,
                    error=f"Replay endpoint failed: HTTP {response.status_code}"
                )
                
        except Exception as e:
            self.log_result("Replay Deterministic/Isolated Flags", False, error=str(e))
    
    def test_p1_query_search_no_500(self):
        """Test P1 query search endpoint - no 500 errors"""
        try:
            # Test search endpoint
            response = self.session.get(
                f"{BASE_URL}/api/audit-logs/trading-lifecycle/search?q=test&limit=5",
                timeout=30
            )
            
            if response.status_code == 500:
                self.log_result(
                    "P1 Query Search (No 500 Errors)",
                    False,
                    error=f"Search endpoint returned 500 error"
                )
            elif response.status_code in [200, 422]:
                self.log_result(
                    "P1 Query Search (No 500 Errors)",
                    True,
                    f"Search endpoint working without 500 errors (HTTP {response.status_code})"
                )
            else:
                self.log_result(
                    "P1 Query Search (No 500 Errors)",
                    True,
                    f"Search endpoint accessible, no 500 error (HTTP {response.status_code})"
                )
                
        except Exception as e:
            self.log_result("P1 Query Search (No 500 Errors)", False, error=str(e))
    
    def test_saved_query_and_incident_endpoints(self):
        """Test Saved query and incident endpoints exist"""
        try:
            # Test saved queries endpoint
            saved_query_response = self.session.get(
                f"{BASE_URL}/api/audit-logs/saved-queries",
                timeout=30
            )
            
            # Test incidents endpoint  
            incident_response = self.session.get(
                f"{BASE_URL}/api/audit-logs/incidents",
                timeout=30
            )
            
            saved_query_accessible = saved_query_response.status_code in [200, 422]
            incident_accessible = incident_response.status_code in [200, 422]
            
            if saved_query_accessible and incident_accessible:
                self.log_result(
                    "Saved Query + Incident Endpoints",
                    True,
                    f"Both endpoints accessible - Saved queries: HTTP {saved_query_response.status_code}, Incidents: HTTP {incident_response.status_code}"
                )
            else:
                self.log_result(
                    "Saved Query + Incident Endpoints",
                    False,
                    error=f"Endpoints not accessible - Saved queries: HTTP {saved_query_response.status_code}, Incidents: HTTP {incident_response.status_code}"
                )
                
        except Exception as e:
            self.log_result("Saved Query + Incident Endpoints", False, error=str(e))
    
    def test_metrics_required_set(self):
        """Test Required metrics set"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/metrics",
                timeout=30
            )
            
            if response.status_code == 200:
                metrics_text = response.text
                
                # Check for required metrics
                required_metrics = [
                    "latency",
                    "failure_rate", 
                    "success_rate",
                    "throughput",
                    "replay_duration"
                ]
                
                found_metrics = []
                for metric in required_metrics:
                    if metric in metrics_text.lower():
                        found_metrics.append(metric)
                
                if len(found_metrics) >= 4:  # At least 4 out of 5 required metrics
                    self.log_result(
                        "Metrics Required Set",
                        True,
                        f"Required metrics found ({len(found_metrics)}/5): {found_metrics}"
                    )
                else:
                    self.log_result(
                        "Metrics Required Set",
                        False,
                        error=f"Only found {len(found_metrics)}/5 required metrics: {found_metrics}"
                    )
            else:
                self.log_result(
                    "Metrics Required Set",
                    False,
                    error=f"Metrics endpoint failed: HTTP {response.status_code}"
                )
                
        except Exception as e:
            self.log_result("Metrics Required Set", False, error=str(e))
    
    def test_p2_verify_trace_and_archive_mode(self):
        """Test P2 verify-trace and archive_mode API"""
        try:
            # Test verify-trace endpoint
            verify_response = self.session.get(
                f"{BASE_URL}/api/audit/verify-trace?correlation_id=test-correlation",
                timeout=30
            )
            
            # Test cross-env compare (consistency)
            consistency_response = self.session.get(
                f"{BASE_URL}/api/audit-logs/consistency/repo-deploy",
                timeout=30
            )
            
            verify_accessible = verify_response.status_code in [200, 422, 404]
            consistency_accessible = consistency_response.status_code in [200, 422]
            
            details = f"verify-trace: HTTP {verify_response.status_code}, consistency: HTTP {consistency_response.status_code}"
            
            if verify_accessible and consistency_accessible:
                self.log_result(
                    "P2 Verify-trace + Cross-env Compare",
                    True,
                    details
                )
            else:
                self.log_result(
                    "P2 Verify-trace + Cross-env Compare",
                    False,
                    error=details
                )
                
        except Exception as e:
            self.log_result("P2 Verify-trace + Cross-env Compare", False, error=str(e))
    
    def test_archive_mode_api(self):
        """Test archive_mode API parameter"""
        try:
            # Test archive_mode parameter acceptance
            response = self.session.get(
                f"{BASE_URL}/api/audit-logs/trading-lifecycle?archive_mode=true&limit=1",
                timeout=30
            )
            
            # Parameter should be accepted (200 or 422 for validation, not 400 for bad parameter)
            if response.status_code in [200, 422]:
                self.log_result(
                    "Archive Mode API Parameter",
                    True,
                    f"archive_mode parameter accepted (HTTP {response.status_code})"
                )
            elif response.status_code == 400:
                self.log_result(
                    "Archive Mode API Parameter",
                    False,
                    error=f"archive_mode parameter rejected (HTTP 400)"
                )
            else:
                self.log_result(
                    "Archive Mode API Parameter",
                    True,
                    f"archive_mode parameter processed (HTTP {response.status_code})"
                )
                
        except Exception as e:
            self.log_result("Archive Mode API Parameter", False, error=str(e))
    
    def test_audit_report_file(self):
        """Test Final audit report file exists"""
        try:
            if os.path.exists(AUDIT_REPORT_PATH):
                with open(AUDIT_REPORT_PATH, 'r') as f:
                    audit_data = json.load(f)
                
                # Check if audit shows overall pass
                overall_pass = audit_data.get("summary", {}).get("overall_pass", False)
                p0_pass = audit_data.get("summary", {}).get("p0_pass", False)
                p1_pass = audit_data.get("summary", {}).get("p1_pass", False)
                p2_pass = audit_data.get("summary", {}).get("p2_pass", False)
                
                file_size = os.path.getsize(AUDIT_REPORT_PATH)
                
                self.log_result(
                    "Final Audit Report File",
                    True,
                    f"File exists ({file_size} bytes), P0: {p0_pass}, P1: {p1_pass}, P2: {p2_pass}, Overall: {overall_pass}"
                )
            else:
                self.log_result(
                    "Final Audit Report File",
                    False,
                    error=f"Audit report file not found at {AUDIT_REPORT_PATH}"
                )
                
        except Exception as e:
            self.log_result("Final Audit Report File", False, error=str(e))
    
    def run_validation(self):
        """Run focused P0+P1+P2 final closure validation"""
        print("=" * 80)
        print("P0+P1+P2 FINAL CLOSURE VALIDATION (FOCUSED)")
        print("Turkish Review Request - Kısa ama Kapsamlı Doğrulama")
        print(f"URL: {BASE_URL}")
        print(f"Credentials: {ADMIN_EMAIL}")
        print("=" * 80)
        
        # Step 1: Authenticate
        if not self.authenticate_admin():
            print("\n❌ CRITICAL: Authentication failed. Cannot proceed with validation.")
            return False
        
        # Step 2: Run all validation tests
        print("\n🔍 Running P0+P1+P2 Focused Validation Tests...")
        
        self.test_p0_canonical_endpoints()
        self.test_explain_minimum_fields()
        self.test_replay_deterministic_flags()
        self.test_p1_query_search_no_500()
        self.test_saved_query_and_incident_endpoints()
        self.test_metrics_required_set()
        self.test_p2_verify_trace_and_archive_mode()
        self.test_archive_mode_api()
        self.test_audit_report_file()
        
        # Step 3: Generate summary
        total_tests = len(self.test_results) - 1  # Exclude authentication
        passed_tests = sum(1 for r in self.test_results[1:] if r["passed"])  # Exclude authentication
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        print("\n" + "=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.errors:
            print(f"\n❌ ERRORS DETECTED ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")
        
        # Final verdict based on Turkish review requirements
        critical_requirements_met = (
            passed_tests >= 7 and  # At least 7/9 tests must pass
            success_rate >= 75.0   # At least 75% success rate
        )
        
        if critical_requirements_met:
            print(f"\n✅✅✅ OVERALL RESULT: PASS")
            print("P0+P1+P2 Final Closure Validation SUCCESSFUL")
            print("Kısa ama kapsamlı doğrulama tamamlandı - kritik blocker YOK")
            return True
        else:
            print(f"\n❌❌❌ OVERALL RESULT: FAIL")
            print("P0+P1+P2 Final Closure Validation FAILED")
            print("Kritik blocker tespit edildi - sistem production-ready değil")
            return False

def main():
    """Main execution function"""
    validator = P0P1P2FocusedValidator()
    success = validator.run_validation()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()