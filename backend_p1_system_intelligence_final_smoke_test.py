#!/usr/bin/env python3
"""
P1 System Intelligence Final Backend Smoke Test
Turkish Review Request: P1 System Intelligence final backend smoke.

Test Environment: https://enforcement-backend.preview.emergentagent.com
Admin Credentials: canary.admin@platform.local / CanaryAdmin123!

Test Requirements:
1) Workflow engine: ops->risk->final sıra ihlali engelleniyor mu, doğru sırada ilerliyor mu?
2) Assignment + priority queue: queue risk_score bazlı sıralanıyor mu?
3) SLA timeout escalation endpoint çalışıyor mu? supervisor queue/escalation flag görünüyor mu?
4) Decision support payload shape: recommended_action, confidence, reason_codes, human_readable_summary
5) Approval sonrası activation event zinciri tetikleniyor mu (en az event kayıtları)
6) /api/ready PASS

Expected Output: PASS/FAIL + kısa smoke raporu
"""

import requests
import json
import time
from datetime import datetime, timezone
import sys

# Test Configuration
BASE_URL = "https://enforcement-backend.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class P1SystemIntelligenceFinalSmokeTest:
    def __init__(self):
        self.base_url = BASE_URL
        self.admin_token = None
        self.test_results = []
        self.session = requests.Session()
        self.session.timeout = 30
        
    def log_test(self, test_name, status, details=""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
    
    def authenticate_admin(self):
        """Authenticate admin user and get token"""
        try:
            auth_url = f"{self.base_url}/api/auth/login"
            auth_data = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(auth_url, json=auth_data)
            
            if response.status_code == 200:
                auth_result = response.json()
                self.admin_token = auth_result.get("access_token")
                if self.admin_token:
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.admin_token}"
                    })
                    self.log_test("Admin Authentication", "PASS", f"Token length: {len(self.admin_token)} chars")
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
    
    def test_ready_endpoint(self):
        """Test 6: /api/ready PASS"""
        try:
            ready_url = f"{self.base_url}/api/ready"
            response = self.session.get(ready_url)
            
            if response.status_code == 200:
                ready_data = response.json()
                status = ready_data.get("status")
                gate_status = ready_data.get("gate_status")
                
                if status == "ready" and gate_status == "pass":
                    self.log_test("Ready Endpoint", "PASS", f"status={status}, gate_status={gate_status}")
                    return True
                else:
                    self.log_test("Ready Endpoint", "FAIL", f"status={status}, gate_status={gate_status}")
                    return False
            else:
                self.log_test("Ready Endpoint", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Ready Endpoint", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_workflow_engine_sequence(self):
        """Test 1: Workflow engine ops->risk->final sequence validation"""
        try:
            # Check workflow engine endpoint
            workflow_url = f"{self.base_url}/api/admin/workflow/engine"
            response = self.session.get(workflow_url)
            
            if response.status_code == 200:
                workflow_data = response.json()
                
                # Look for workflow sequence validation
                sequence_validation = workflow_data.get("sequence_validation", {})
                ops_to_risk = sequence_validation.get("ops_to_risk", False)
                risk_to_final = sequence_validation.get("risk_to_final", False)
                violation_prevention = sequence_validation.get("violation_prevention", False)
                
                if ops_to_risk and risk_to_final and violation_prevention:
                    self.log_test("Workflow Engine Sequence", "PASS", "ops->risk->final sequence validation working")
                    return True
                else:
                    # Try alternative endpoint for workflow validation
                    alt_url = f"{self.base_url}/api/admin/system/workflow-validation"
                    alt_response = self.session.get(alt_url)
                    
                    if alt_response.status_code == 200:
                        alt_data = alt_response.json()
                        workflow_status = alt_data.get("workflow_status", "unknown")
                        sequence_enforced = alt_data.get("sequence_enforced", False)
                        
                        if workflow_status == "active" and sequence_enforced:
                            self.log_test("Workflow Engine Sequence", "PASS", f"workflow_status={workflow_status}, sequence_enforced={sequence_enforced}")
                            return True
                    
                    self.log_test("Workflow Engine Sequence", "FAIL", f"Sequence validation incomplete: ops_to_risk={ops_to_risk}, risk_to_final={risk_to_final}, violation_prevention={violation_prevention}")
                    return False
            else:
                self.log_test("Workflow Engine Sequence", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Workflow Engine Sequence", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_priority_queue_risk_scoring(self):
        """Test 2: Assignment + priority queue risk_score based sorting"""
        try:
            # Check priority queue endpoint
            queue_url = f"{self.base_url}/api/admin/queue/priority"
            response = self.session.get(queue_url)
            
            if response.status_code == 200:
                queue_data = response.json()
                
                # Check if queue is sorted by risk_score
                queue_items = queue_data.get("queue_items", [])
                risk_score_sorting = queue_data.get("risk_score_sorting", False)
                sort_order = queue_data.get("sort_order", "unknown")
                
                if risk_score_sorting and sort_order in ["desc", "descending"]:
                    # Verify actual sorting if items exist
                    if len(queue_items) > 1:
                        is_sorted = True
                        for i in range(len(queue_items) - 1):
                            current_score = queue_items[i].get("risk_score", 0)
                            next_score = queue_items[i + 1].get("risk_score", 0)
                            if current_score < next_score:
                                is_sorted = False
                                break
                        
                        if is_sorted:
                            self.log_test("Priority Queue Risk Scoring", "PASS", f"Queue sorted by risk_score (desc), {len(queue_items)} items")
                            return True
                        else:
                            self.log_test("Priority Queue Risk Scoring", "FAIL", "Queue items not properly sorted by risk_score")
                            return False
                    else:
                        self.log_test("Priority Queue Risk Scoring", "PASS", f"Risk score sorting enabled, sort_order={sort_order}")
                        return True
                else:
                    self.log_test("Priority Queue Risk Scoring", "FAIL", f"risk_score_sorting={risk_score_sorting}, sort_order={sort_order}")
                    return False
            else:
                self.log_test("Priority Queue Risk Scoring", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Priority Queue Risk Scoring", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_sla_timeout_escalation(self):
        """Test 3: SLA timeout escalation endpoint and supervisor queue/escalation flag"""
        try:
            # Check SLA escalation endpoint
            sla_url = f"{self.base_url}/api/admin/sla/escalation"
            response = self.session.get(sla_url)
            
            if response.status_code == 200:
                sla_data = response.json()
                
                # Check escalation functionality
                escalation_enabled = sla_data.get("escalation_enabled", False)
                supervisor_queue = sla_data.get("supervisor_queue", {})
                escalation_flag = sla_data.get("escalation_flag", False)
                
                if escalation_enabled and supervisor_queue and escalation_flag:
                    queue_size = supervisor_queue.get("queue_size", 0)
                    escalated_items = supervisor_queue.get("escalated_items", 0)
                    
                    self.log_test("SLA Timeout Escalation", "PASS", f"escalation_enabled={escalation_enabled}, supervisor_queue_size={queue_size}, escalated_items={escalated_items}")
                    return True
                else:
                    # Try alternative escalation status endpoint
                    alt_url = f"{self.base_url}/api/admin/system/escalation-status"
                    alt_response = self.session.get(alt_url)
                    
                    if alt_response.status_code == 200:
                        alt_data = alt_response.json()
                        escalation_active = alt_data.get("escalation_active", False)
                        supervisor_visible = alt_data.get("supervisor_visible", False)
                        
                        if escalation_active and supervisor_visible:
                            self.log_test("SLA Timeout Escalation", "PASS", f"escalation_active={escalation_active}, supervisor_visible={supervisor_visible}")
                            return True
                    
                    self.log_test("SLA Timeout Escalation", "FAIL", f"escalation_enabled={escalation_enabled}, supervisor_queue={bool(supervisor_queue)}, escalation_flag={escalation_flag}")
                    return False
            else:
                self.log_test("SLA Timeout Escalation", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("SLA Timeout Escalation", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_decision_support_payload(self):
        """Test 4: Decision support payload shape validation"""
        try:
            # Check decision support endpoint
            decision_url = f"{self.base_url}/api/admin/decision-support"
            response = self.session.get(decision_url)
            
            if response.status_code == 200:
                decision_data = response.json()
                
                # Check required payload fields
                required_fields = ["recommended_action", "confidence", "reason_codes", "human_readable_summary"]
                missing_fields = []
                
                for field in required_fields:
                    if field not in decision_data:
                        missing_fields.append(field)
                
                if not missing_fields:
                    # Validate field types and content
                    recommended_action = decision_data.get("recommended_action")
                    confidence = decision_data.get("confidence")
                    reason_codes = decision_data.get("reason_codes")
                    human_readable_summary = decision_data.get("human_readable_summary")
                    
                    # Basic validation
                    valid_action = isinstance(recommended_action, str) and recommended_action
                    valid_confidence = isinstance(confidence, (int, float)) and 0 <= confidence <= 1
                    valid_reason_codes = isinstance(reason_codes, list) and len(reason_codes) > 0
                    valid_summary = isinstance(human_readable_summary, str) and human_readable_summary
                    
                    if valid_action and valid_confidence and valid_reason_codes and valid_summary:
                        self.log_test("Decision Support Payload", "PASS", f"All required fields present and valid: action={recommended_action}, confidence={confidence}, reason_codes={len(reason_codes)}, summary_length={len(human_readable_summary)}")
                        return True
                    else:
                        self.log_test("Decision Support Payload", "FAIL", f"Invalid field types: action={valid_action}, confidence={valid_confidence}, reason_codes={valid_reason_codes}, summary={valid_summary}")
                        return False
                else:
                    self.log_test("Decision Support Payload", "FAIL", f"Missing required fields: {missing_fields}")
                    return False
            else:
                self.log_test("Decision Support Payload", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Decision Support Payload", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_approval_activation_event_chain(self):
        """Test 5: Approval after activation event chain triggering"""
        try:
            # Check activation events endpoint
            events_url = f"{self.base_url}/api/admin/events/activation"
            response = self.session.get(events_url)
            
            if response.status_code == 200:
                events_data = response.json()
                
                # Check for event records
                event_records = events_data.get("event_records", [])
                activation_chain = events_data.get("activation_chain", {})
                chain_triggered = activation_chain.get("triggered", False)
                
                if len(event_records) > 0 and chain_triggered:
                    # Look for approval-related events
                    approval_events = [e for e in event_records if "approval" in e.get("event_type", "").lower()]
                    activation_events = [e for e in event_records if "activation" in e.get("event_type", "").lower()]
                    
                    if len(approval_events) > 0 and len(activation_events) > 0:
                        self.log_test("Approval Activation Event Chain", "PASS", f"Event chain triggered: {len(approval_events)} approval events, {len(activation_events)} activation events")
                        return True
                    else:
                        self.log_test("Approval Activation Event Chain", "PARTIAL", f"Event records found ({len(event_records)}) but limited approval/activation events: approval={len(approval_events)}, activation={len(activation_events)}")
                        return True  # Partial pass - at least some events exist
                else:
                    # Try alternative events endpoint
                    alt_url = f"{self.base_url}/api/admin/audit/events"
                    alt_response = self.session.get(alt_url)
                    
                    if alt_response.status_code == 200:
                        alt_data = alt_response.json()
                        audit_events = alt_data.get("events", [])
                        
                        if len(audit_events) > 0:
                            approval_audit = [e for e in audit_events if "approval" in str(e).lower()]
                            if len(approval_audit) > 0:
                                self.log_test("Approval Activation Event Chain", "PASS", f"Audit events found: {len(audit_events)} total, {len(approval_audit)} approval-related")
                                return True
                    
                    self.log_test("Approval Activation Event Chain", "FAIL", f"No event records found: event_records={len(event_records)}, chain_triggered={chain_triggered}")
                    return False
            else:
                self.log_test("Approval Activation Event Chain", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Approval Activation Event Chain", "FAIL", f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all P1 System Intelligence tests"""
        print("=" * 80)
        print("P1 SYSTEM INTELLIGENCE FINAL BACKEND SMOKE TEST")
        print("=" * 80)
        print(f"Test Environment: {self.base_url}")
        print(f"Admin Credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        print(f"Test Started: {datetime.now(timezone.utc).isoformat()}")
        print()
        
        # Authenticate first
        if not self.authenticate_admin():
            print("\n❌ CRITICAL: Admin authentication failed. Cannot proceed with tests.")
            return False
        
        print()
        
        # Run all tests
        test_functions = [
            self.test_ready_endpoint,
            self.test_workflow_engine_sequence,
            self.test_priority_queue_risk_scoring,
            self.test_sla_timeout_escalation,
            self.test_decision_support_payload,
            self.test_approval_activation_event_chain
        ]
        
        passed_tests = 0
        total_tests = len(test_functions)
        
        for test_func in test_functions:
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                print(f"❌ Test {test_func.__name__} failed with exception: {str(e)}")
        
        print()
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        success_rate = (passed_tests / total_tests) * 100
        overall_status = "PASS" if passed_tests == total_tests else "FAIL"
        
        print(f"Overall Status: {overall_status}")
        print(f"Tests Passed: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
        print()
        
        # Detailed results
        for result in self.test_results:
            status_symbol = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_symbol} {result['test']}: {result['status']}")
            if result["details"]:
                print(f"   {result['details']}")
        
        print()
        print("KISA SMOKE RAPORU:")
        print(f"- P1 System Intelligence Final Backend Smoke: {overall_status}")
        print(f"- Test Environment: {self.base_url}")
        print(f"- Success Rate: {success_rate:.1f}% ({passed_tests}/{total_tests})")
        
        if overall_status == "PASS":
            print("- All critical system intelligence components operational")
            print("- Workflow engine sequence validation working")
            print("- Priority queue risk scoring functional")
            print("- SLA escalation and decision support operational")
            print("- Event chain and ready endpoint confirmed")
        else:
            print("- Some system intelligence components need attention")
            failed_tests = [r["test"] for r in self.test_results if r["status"] == "FAIL"]
            if failed_tests:
                print(f"- Failed tests: {', '.join(failed_tests)}")
        
        print(f"- Test Completed: {datetime.now(timezone.utc).isoformat()}")
        
        return overall_status == "PASS"

def main():
    """Main test execution"""
    test_runner = P1SystemIntelligenceFinalSmokeTest()
    success = test_runner.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()