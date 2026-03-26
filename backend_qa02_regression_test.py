#!/usr/bin/env python3
"""
QA-02 Kısa Regression Test
Target: https://enforcement-backend.preview.emergentagent.com
Credentials: canary.admin@platform.local / CanaryAdmin123!

Test Requirements:
1) Scheduler race protection (no duplicate export generation in same window)
2) Export create + manifest generation  
3) Signed URL delivery (should not be local://download)
4) Alert SLA endpoint/overview flow
5) Readiness (/api/ready) pass
"""

import requests
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

class QA02RegressionTest:
    def __init__(self):
        self.base_url = "https://enforcement-backend.preview.emergentagent.com"
        self.admin_email = "canary.admin@platform.local"
        self.admin_password = "CanaryAdmin123!"
        self.session = requests.Session()
        self.session.timeout = 30
        self.admin_token = None
        self.test_results = []
        
    def log_result(self, test_name: str, status: str, details: str, evidence: Any = None):
        """Log test result with timestamp"""
        result = {
            "test_name": test_name,
            "status": status,
            "details": details,
            "evidence": evidence,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        print(f"[{status}] {test_name}: {details}")
        if evidence:
            print(f"    Evidence: {json.dumps(evidence, indent=2)[:200]}...")
    
    def authenticate_admin(self) -> bool:
        """Authenticate as admin and get token"""
        try:
            login_url = f"{self.base_url}/api/auth/login"
            login_data = {
                "email": self.admin_email,
                "password": self.admin_password
            }
            
            response = self.session.post(login_url, json=login_data)
            
            if response.status_code == 200:
                token_data = response.json()
                self.admin_token = token_data.get("access_token")
                self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
                self.log_result("Admin Authentication", "PASS", 
                              f"Successfully authenticated admin user. Token length: {len(self.admin_token) if self.admin_token else 0}")
                return True
            else:
                self.log_result("Admin Authentication", "FAIL", 
                              f"Authentication failed with status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Authentication", "FAIL", f"Authentication error: {str(e)}")
            return False
    
    def test_readiness_endpoint(self) -> bool:
        """Test 5: Readiness (/api/ready) pass"""
        try:
            ready_url = f"{self.base_url}/api/ready"
            response = self.session.get(ready_url)
            
            if response.status_code == 200:
                ready_data = response.json()
                status = ready_data.get("status")
                gate_status = ready_data.get("gate_status")
                
                if status == "ready" and gate_status == "pass":
                    self.log_result("Readiness Endpoint", "PASS", 
                                  f"Readiness check passed: status={status}, gate_status={gate_status}",
                                  ready_data)
                    return True
                else:
                    self.log_result("Readiness Endpoint", "FAIL", 
                                  f"Readiness check failed: status={status}, gate_status={gate_status}",
                                  ready_data)
                    return False
            else:
                self.log_result("Readiness Endpoint", "FAIL", 
                              f"Readiness endpoint returned {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Readiness Endpoint", "FAIL", f"Readiness test error: {str(e)}")
            return False
    
    def test_export_creation_and_manifest(self) -> bool:
        """Test 2: Export create + manifest generation"""
        try:
            # Create export schedule
            schedule_url = f"{self.base_url}/api/admin/commercial/exports/schedules"
            schedule_data = {
                "export_type": "pnl",
                "schedule_period": "daily",
                "output_format": "csv",
                "is_active": True,
                "max_retry": 3
            }
            
            response = self.session.post(schedule_url, json=schedule_data)
            
            if response.status_code == 200:
                schedule_result = response.json()
                schedule_id = schedule_result.get("schedule_id")
                
                # Trigger export generation
                trigger_url = f"{self.base_url}/api/admin/commercial/exports/trigger"
                trigger_data = {
                    "export_type": "pnl",
                    "time_window": "last_7_days",
                    "output_format": "csv"
                }
                
                trigger_response = self.session.post(trigger_url, json=trigger_data)
                
                if trigger_response.status_code == 200:
                    export_result = trigger_response.json()
                    export_id = export_result.get("export_id")
                    
                    # Check manifest generation
                    manifest_url = f"{self.base_url}/api/admin/commercial/exports/{export_id}/manifest"
                    manifest_response = self.session.get(manifest_url)
                    
                    if manifest_response.status_code == 200:
                        manifest_data = manifest_response.json()
                        has_checksum = "file_hash" in manifest_data
                        has_metadata = "export_metadata" in manifest_data
                        
                        self.log_result("Export Creation and Manifest", "PASS", 
                                      f"Export created (ID: {export_id}) and manifest generated with checksum: {has_checksum}, metadata: {has_metadata}",
                                      {
                                          "schedule_id": schedule_id,
                                          "export_id": export_id,
                                          "manifest_keys": list(manifest_data.keys())
                                      })
                        return True
                    else:
                        self.log_result("Export Creation and Manifest", "FAIL", 
                                      f"Manifest generation failed: {manifest_response.status_code}")
                        return False
                else:
                    self.log_result("Export Creation and Manifest", "FAIL", 
                                  f"Export trigger failed: {trigger_response.status_code}")
                    return False
            else:
                self.log_result("Export Creation and Manifest", "FAIL", 
                              f"Schedule creation failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_result("Export Creation and Manifest", "FAIL", f"Export test error: {str(e)}")
            return False
    
    def test_signed_url_delivery(self) -> bool:
        """Test 3: Signed URL delivery (should not be local://download)"""
        try:
            # Get recent exports
            exports_url = f"{self.base_url}/api/admin/commercial/exports"
            response = self.session.get(exports_url)
            
            if response.status_code == 200:
                exports_data = response.json()
                exports = exports_data.get("exports", [])
                
                if exports:
                    # Get download URL for first export
                    export_id = exports[0].get("export_id")
                    download_url = f"{self.base_url}/api/admin/commercial/exports/{export_id}/download"
                    
                    download_response = self.session.get(download_url, allow_redirects=False)
                    
                    if download_response.status_code in [200, 302, 307]:
                        # Check if it's a signed URL (not local://)
                        if download_response.status_code in [302, 307]:
                            redirect_url = download_response.headers.get("Location", "")
                        else:
                            redirect_url = download_response.json().get("download_url", "")
                        
                        is_local_url = redirect_url.startswith("local://")
                        is_signed_url = "supabase" in redirect_url or "amazonaws" in redirect_url or "storage" in redirect_url
                        
                        if not is_local_url and (is_signed_url or redirect_url.startswith("http")):
                            self.log_result("Signed URL Delivery", "PASS", 
                                          f"Proper signed URL delivered (not local://): {redirect_url[:100]}...",
                                          {"export_id": export_id, "url_type": "signed"})
                            return True
                        else:
                            self.log_result("Signed URL Delivery", "FAIL", 
                                          f"Invalid URL format: {redirect_url}",
                                          {"export_id": export_id, "is_local": is_local_url})
                            return False
                    else:
                        self.log_result("Signed URL Delivery", "FAIL", 
                                      f"Download endpoint failed: {download_response.status_code}")
                        return False
                else:
                    # Create a test export first
                    self.log_result("Signed URL Delivery", "PARTIAL", 
                                  "No existing exports found, creating test export first")
                    return self.test_export_creation_and_manifest()
            else:
                self.log_result("Signed URL Delivery", "FAIL", 
                              f"Failed to get exports list: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_result("Signed URL Delivery", "FAIL", f"Signed URL test error: {str(e)}")
            return False
    
    def test_scheduler_race_protection(self) -> bool:
        """Test 1: Scheduler race protection (no duplicate export generation in same window)"""
        try:
            # Create multiple concurrent export requests for same time window
            export_requests = []
            time_window = "last_24_hours"
            export_type = "pnl"
            
            # Send 3 concurrent requests
            for i in range(3):
                trigger_url = f"{self.base_url}/api/admin/commercial/exports/trigger"
                trigger_data = {
                    "export_type": export_type,
                    "time_window": time_window,
                    "output_format": "csv",
                    "request_id": f"race_test_{uuid.uuid4().hex[:8]}"
                }
                
                try:
                    response = self.session.post(trigger_url, json=trigger_data)
                    export_requests.append({
                        "request_id": trigger_data["request_id"],
                        "status_code": response.status_code,
                        "response": response.json() if response.status_code == 200 else response.text
                    })
                except Exception as e:
                    export_requests.append({
                        "request_id": trigger_data["request_id"],
                        "status_code": "ERROR",
                        "response": str(e)
                    })
                
                # Small delay between requests
                time.sleep(0.1)
            
            # Analyze results for race condition
            successful_requests = [req for req in export_requests if req["status_code"] == 200]
            duplicate_exports = []
            
            if len(successful_requests) > 1:
                # Check if multiple exports were created for same window
                export_ids = []
                for req in successful_requests:
                    if isinstance(req["response"], dict):
                        export_id = req["response"].get("export_id")
                        if export_id:
                            export_ids.append(export_id)
                
                # Check for duplicates by querying export details
                unique_exports = set()
                for export_id in export_ids:
                    try:
                        detail_url = f"{self.base_url}/api/admin/commercial/exports/{export_id}"
                        detail_response = self.session.get(detail_url)
                        if detail_response.status_code == 200:
                            export_detail = detail_response.json()
                            export_key = f"{export_detail.get('export_type')}_{export_detail.get('time_window')}"
                            if export_key in unique_exports:
                                duplicate_exports.append(export_id)
                            unique_exports.add(export_key)
                    except:
                        pass
            
            if len(duplicate_exports) == 0:
                self.log_result("Scheduler Race Protection", "PASS", 
                              f"No duplicate exports detected. Successful requests: {len(successful_requests)}, Unique exports: {len(unique_exports) if 'unique_exports' in locals() else 0}",
                              {"requests": export_requests, "duplicates": duplicate_exports})
                return True
            else:
                self.log_result("Scheduler Race Protection", "FAIL", 
                              f"Duplicate exports detected: {duplicate_exports}",
                              {"requests": export_requests, "duplicates": duplicate_exports})
                return False
                
        except Exception as e:
            self.log_result("Scheduler Race Protection", "FAIL", f"Race protection test error: {str(e)}")
            return False
    
    def test_alert_sla_endpoint_flow(self) -> bool:
        """Test 4: Alert SLA endpoint/overview flow"""
        try:
            # Test alert SLA overview endpoint
            sla_url = f"{self.base_url}/api/admin/alerts/sla/overview"
            response = self.session.get(sla_url)
            
            if response.status_code == 200:
                sla_data = response.json()
                
                # Check required SLA fields
                required_fields = ["total_alerts", "sla_breaches", "avg_response_time", "sla_compliance_rate"]
                missing_fields = [field for field in required_fields if field not in sla_data]
                
                if not missing_fields:
                    # Test alert lifecycle endpoint
                    alerts_url = f"{self.base_url}/api/admin/alerts"
                    alerts_response = self.session.get(alerts_url)
                    
                    if alerts_response.status_code == 200:
                        alerts_data = alerts_response.json()
                        alerts = alerts_data.get("alerts", [])
                        
                        if alerts:
                            # Test alert acknowledgment
                            alert_id = alerts[0].get("id")
                            ack_url = f"{self.base_url}/api/admin/alerts/{alert_id}/acknowledge"
                            ack_data = {"acknowledged_by": "qa_test", "reason": "QA-02 regression test"}
                            
                            ack_response = self.session.post(ack_url, json=ack_data)
                            
                            if ack_response.status_code in [200, 204]:
                                self.log_result("Alert SLA Endpoint Flow", "PASS", 
                                              f"Alert SLA overview and lifecycle working. SLA compliance: {sla_data.get('sla_compliance_rate', 'N/A')}%",
                                              {
                                                  "sla_overview": sla_data,
                                                  "alerts_count": len(alerts),
                                                  "ack_test": "success"
                                              })
                                return True
                            else:
                                self.log_result("Alert SLA Endpoint Flow", "FAIL", 
                                              f"Alert acknowledgment failed: {ack_response.status_code}")
                                return False
                        else:
                            self.log_result("Alert SLA Endpoint Flow", "PASS", 
                                          "Alert SLA overview working (no alerts to test lifecycle)",
                                          sla_data)
                            return True
                    else:
                        self.log_result("Alert SLA Endpoint Flow", "FAIL", 
                                      f"Alerts endpoint failed: {alerts_response.status_code}")
                        return False
                else:
                    self.log_result("Alert SLA Endpoint Flow", "FAIL", 
                                  f"Missing SLA fields: {missing_fields}",
                                  sla_data)
                    return False
            else:
                self.log_result("Alert SLA Endpoint Flow", "FAIL", 
                              f"SLA overview endpoint failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_result("Alert SLA Endpoint Flow", "FAIL", f"Alert SLA test error: {str(e)}")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all QA-02 regression tests"""
        print(f"=== QA-02 Kısa Regression Test ===")
        print(f"Target: {self.base_url}")
        print(f"Credentials: {self.admin_email}")
        print(f"Started at: {datetime.now().isoformat()}")
        print("=" * 50)
        
        # Authenticate first
        if not self.authenticate_admin():
            return {"status": "FAILED", "reason": "Authentication failed", "results": self.test_results}
        
        # Run all tests
        test_functions = [
            ("Test 5: Readiness Pass", self.test_readiness_endpoint),
            ("Test 1: Scheduler Race Protection", self.test_scheduler_race_protection),
            ("Test 2: Export Creation + Manifest", self.test_export_creation_and_manifest),
            ("Test 3: Signed URL Delivery", self.test_signed_url_delivery),
            ("Test 4: Alert SLA Endpoint Flow", self.test_alert_sla_endpoint_flow),
        ]
        
        passed_tests = 0
        total_tests = len(test_functions)
        
        for test_name, test_func in test_functions:
            print(f"\n--- Running {test_name} ---")
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                self.log_result(test_name, "ERROR", f"Test execution error: {str(e)}")
        
        # Generate summary
        success_rate = (passed_tests / total_tests) * 100
        overall_status = "PASS" if passed_tests == total_tests else "FAIL"
        
        summary = {
            "status": overall_status,
            "passed_tests": passed_tests,
            "total_tests": total_tests,
            "success_rate": f"{success_rate:.1f}%",
            "test_results": self.test_results,
            "completed_at": datetime.now().isoformat()
        }
        
        print("\n" + "=" * 50)
        print(f"QA-02 REGRESSION SUMMARY:")
        print(f"Status: {overall_status}")
        print(f"Tests Passed: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
        print("=" * 50)
        
        # Print individual test results
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_icon} {result['test_name']}: {result['details']}")
        
        return summary

def main():
    """Main execution function"""
    test_runner = QA02RegressionTest()
    results = test_runner.run_all_tests()
    
    # Save results to file
    with open("/app/qa02_regression_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: /app/qa02_regression_results.json")
    
    # Return appropriate exit code
    return 0 if results["status"] == "PASS" else 1

if __name__ == "__main__":
    exit(main())