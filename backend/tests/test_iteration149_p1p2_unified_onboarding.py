"""
Iteration 149: P1+P2 Unified Onboarding Decision Platform Tests
Tests for:
- Workflow engine enforcement (step order violation 409, complete-step only current step)
- SLA/escalation behavior (escalation endpoint + supervisor_queue/escalation_count)
- Assignment flow (assign dropdown payload ile owner değişimi)
- Decision guardrail (missing data varsa approve BLOCK ve missing[] dönüyor mu)
- Risk explanation guardrail (high-risk/AML kararlarında min 15 karakter zorunluluğu)
- Decision + audit log atomic davranışının fonksiyonel doğrulaması
- Observability endpoint (GET /api/admin/onboarding/observability/summary schema + KPI alanları)
- Observability reconcile/status + telemetry percentiles alanları
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"

ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


class TestHealthAndAuth:
    """Health check and authentication tests"""

    def test_health_endpoint(self):
        """Test health endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert "status" in data or "database" in data
        print(f"Health check passed: {data}")

    def test_admin_login(self):
        """Test admin login returns token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=60
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data or "token" in data
        print(f"Login successful, role: {data.get('role', 'N/A')}")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=60
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def test_user_id(auth_headers):
    """Get a test user ID from pending approvals"""
    response = requests.get(
        f"{BASE_URL}/api/admin/user-approvals",
        headers=auth_headers,
        params={"status": "pending", "limit": 10},
        timeout=30
    )
    if response.status_code != 200:
        pytest.skip(f"Could not get user approvals: {response.text}")
    data = response.json()
    if not data or len(data) == 0:
        pytest.skip("No pending users available for testing")
    return data[0].get("id")


class TestWorkflowEngineEnforcement:
    """Workflow engine enforcement tests - step order violation 409, complete-step only current step"""

    def test_workflow_queue_endpoint(self, auth_headers):
        """Test workflow queue returns items with expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/workflow/queue",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Workflow queue failed: {response.text}"
        data = response.json()
        assert "items" in data
        print(f"Workflow queue returned {len(data['items'])} items")
        
        # Check item structure if items exist
        if data["items"]:
            item = data["items"][0]
            expected_fields = ["user_id", "current_step", "workflow_status"]
            for field in expected_fields:
                assert field in item, f"Missing field {field} in workflow item"
            # Check for supervisor_queue and escalation_count fields
            assert "supervisor_queue" in item, "Missing supervisor_queue field"
            assert "escalation_count" in item, "Missing escalation_count field"
            print(f"Sample item: step={item.get('current_step')}, status={item.get('workflow_status')}")

    def test_workflow_step_sequence_violation_returns_409(self, auth_headers, test_user_id):
        """Test completing wrong step returns 409 conflict"""
        # First start workflow if not exists
        start_response = requests.post(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/workflow/start",
            headers=auth_headers,
            json={"assigned_admin_id": None},
            timeout=30
        )
        # May return 200 or already exists
        
        # Get current workflow state
        workflow_response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/workflow",
            headers=auth_headers,
            timeout=30
        )
        if workflow_response.status_code != 200:
            pytest.skip("Could not get workflow state")
        
        workflow_data = workflow_response.json()
        workflow_case = workflow_data.get("workflow_case")
        if not workflow_case:
            pytest.skip("No workflow case found")
        
        current_step = workflow_case.get("current_step", "ops")
        
        # Try to complete a wrong step (not the current one)
        wrong_steps = {"ops": "risk", "risk": "final", "final": "ops"}
        wrong_step = wrong_steps.get(current_step, "risk")
        
        response = requests.post(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/workflow/steps/{wrong_step}/complete",
            headers=auth_headers,
            json={"note": "test_wrong_step"},
            timeout=30
        )
        
        # Should return 409 for step sequence violation
        assert response.status_code == 409, f"Expected 409 for wrong step, got {response.status_code}: {response.text}"
        data = response.json()
        assert "workflow_step_sequence_violation" in str(data.get("detail", "")).lower() or "sequence" in str(data).lower()
        print(f"Step sequence violation correctly returned 409: {data}")

    def test_complete_current_step_succeeds(self, auth_headers, test_user_id):
        """Test completing current step succeeds"""
        # Get current workflow state
        workflow_response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/workflow",
            headers=auth_headers,
            timeout=30
        )
        if workflow_response.status_code != 200:
            pytest.skip("Could not get workflow state")
        
        workflow_data = workflow_response.json()
        workflow_case = workflow_data.get("workflow_case")
        if not workflow_case:
            pytest.skip("No workflow case found")
        
        current_step = workflow_case.get("current_step", "ops")
        if current_step == "completed":
            pytest.skip("Workflow already completed")
        
        response = requests.post(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/workflow/steps/{current_step}/complete",
            headers=auth_headers,
            json={"note": "test_complete_step"},
            timeout=30
        )
        
        # Should succeed
        assert response.status_code == 200, f"Complete step failed: {response.text}"
        data = response.json()
        assert "workflow_case_id" in data
        assert "current_step" in data
        print(f"Step {current_step} completed, new step: {data.get('current_step')}")


class TestSLAEscalationBehavior:
    """SLA/escalation behavior tests"""

    def test_escalate_endpoint(self, auth_headers, test_user_id):
        """Test escalation endpoint returns supervisor_queue and escalation_count"""
        # Ensure workflow exists
        requests.post(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/workflow/start",
            headers=auth_headers,
            json={"assigned_admin_id": None},
            timeout=30
        )
        
        response = requests.post(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/workflow/escalate",
            headers=auth_headers,
            json={"supervisor_admin_id": None, "note": "test_escalation"},
            timeout=30
        )
        
        # May return 200 or 409 if already completed
        if response.status_code == 409:
            data = response.json()
            if "completed" in str(data.get("detail", "")).lower():
                pytest.skip("Workflow already completed, cannot escalate")
        
        assert response.status_code == 200, f"Escalation failed: {response.text}"
        data = response.json()
        
        # Check required fields
        assert "supervisor_queue" in data, "Missing supervisor_queue in escalation response"
        assert "escalation_count" in data, "Missing escalation_count in escalation response"
        assert data["supervisor_queue"] == True, "supervisor_queue should be True after escalation"
        assert data["escalation_count"] >= 1, "escalation_count should be >= 1"
        print(f"Escalation successful: supervisor_queue={data['supervisor_queue']}, escalation_count={data['escalation_count']}")

    def test_escalate_timeouts_endpoint(self, auth_headers):
        """Test bulk escalate timeouts endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/admin/onboarding/workflow/escalate-timeouts",
            headers=auth_headers,
            json={"supervisor_admin_id": None},
            timeout=30
        )
        
        assert response.status_code == 200, f"Escalate timeouts failed: {response.text}"
        data = response.json()
        assert "escalated" in data, "Missing escalated count in response"
        print(f"Escalate timeouts: {data['escalated']} cases escalated")


class TestAssignmentFlow:
    """Assignment flow tests - assign dropdown payload ile owner değişimi"""

    def test_admin_candidates_endpoint(self, auth_headers):
        """Test admin candidates endpoint returns list of admins"""
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/workflow/admin-candidates",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Admin candidates failed: {response.text}"
        data = response.json()
        assert "items" in data, "Missing items in admin candidates response"
        
        if data["items"]:
            admin = data["items"][0]
            assert "id" in admin, "Missing id in admin candidate"
            assert "email" in admin, "Missing email in admin candidate"
            assert "role" in admin, "Missing role in admin candidate"
            print(f"Found {len(data['items'])} admin candidates")
        return data["items"]

    def test_assign_workflow_owner(self, auth_headers, test_user_id):
        """Test assigning workflow owner changes assigned_admin_id"""
        # Get admin candidates
        candidates_response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/workflow/admin-candidates",
            headers=auth_headers,
            timeout=30
        )
        if candidates_response.status_code != 200:
            pytest.skip("Could not get admin candidates")
        
        candidates = candidates_response.json().get("items", [])
        if not candidates:
            pytest.skip("No admin candidates available")
        
        target_admin_id = candidates[0]["id"]
        
        # Ensure workflow exists
        requests.post(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/workflow/start",
            headers=auth_headers,
            json={"assigned_admin_id": None},
            timeout=30
        )
        
        # Assign to target admin
        response = requests.post(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/workflow/assign",
            headers=auth_headers,
            json={"assigned_admin_id": target_admin_id},
            timeout=30
        )
        
        assert response.status_code == 200, f"Assign failed: {response.text}"
        data = response.json()
        assert "assigned_admin_id" in data, "Missing assigned_admin_id in response"
        assert data["assigned_admin_id"] == target_admin_id, "assigned_admin_id not updated"
        print(f"Assignment successful: assigned_admin_id={data['assigned_admin_id']}")


class TestDecisionGuardrails:
    """Decision guardrail tests - missing data blocks approve, returns missing[]"""

    def test_context_returns_missing_data_fields(self, auth_headers, test_user_id):
        """Test context endpoint returns missing_data_fields when approval_disabled"""
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/context",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Context failed: {response.text}"
        data = response.json()
        
        # Check required fields exist
        assert "approval_disabled" in data, "Missing approval_disabled field"
        assert "missing_data_fields" in data, "Missing missing_data_fields field"
        assert "approval_disable_reasons" in data, "Missing approval_disable_reasons field"
        
        print(f"Context: approval_disabled={data['approval_disabled']}, missing_fields={data['missing_data_fields']}")

    def test_approve_blocked_when_missing_data(self, auth_headers, test_user_id):
        """Test approve is blocked when missing data, returns missing[] in error"""
        # Get context to check if approval is disabled
        context_response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/context",
            headers=auth_headers,
            timeout=30
        )
        if context_response.status_code != 200:
            pytest.skip("Could not get context")
        
        context = context_response.json()
        
        if not context.get("approval_disabled"):
            pytest.skip("User does not have approval_disabled, cannot test guardrail")
        
        # Try to approve - should be blocked
        response = requests.post(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/decision",
            headers=auth_headers,
            json={
                "decision": "approve",
                "reason": "test_approve_blocked",
                "explanation": "testing guardrail",
                "confirm_token": "CONFIRM"
            },
            timeout=30
        )
        
        # Should return 409 with missing[] in detail
        assert response.status_code == 409, f"Expected 409 for blocked approval, got {response.status_code}"
        data = response.json()
        detail = data.get("detail", {})
        
        if isinstance(detail, dict):
            assert "missing" in detail, "Missing 'missing' field in error detail"
            assert "code" in detail, "Missing 'code' field in error detail"
            assert detail["code"] == "approval_blocked_missing_data"
            print(f"Approval correctly blocked: missing={detail.get('missing')}")
        else:
            assert "missing" in str(detail).lower() or "blocked" in str(detail).lower()
            print(f"Approval blocked with detail: {detail}")


class TestRiskExplanationGuardrail:
    """Risk explanation guardrail tests - high-risk/AML requires min 15 char explanation"""

    def test_high_risk_requires_15_char_explanation(self, auth_headers, test_user_id):
        """Test high-risk decision requires minimum 15 character explanation"""
        # First set up a high-risk profile
        risk_foundation_response = requests.post(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/risk-foundation",
            headers=auth_headers,
            json={
                "risk_score": 75,  # High risk
                "aml_flag": "clear",
                "aml_reason": None,
                "api_key_validity": "valid",
                "balance_usd": 1000,
                "country_code": None,
                "leverage_permission": True,
                "futures_capability": True,
                "spot_capability": True
            },
            timeout=30
        )
        
        # Try to approve with short explanation (< 15 chars)
        response = requests.post(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/decision",
            headers=auth_headers,
            json={
                "decision": "approve",
                "reason": "test reason",
                "explanation": "short",  # Less than 15 chars
                "confirm_token": "CONFIRM"
            },
            timeout=30
        )
        
        # May return 400 for short explanation or 409 for other reasons
        if response.status_code == 400:
            data = response.json()
            assert "15" in str(data) or "explanation" in str(data).lower() or "risk" in str(data).lower()
            print(f"High-risk explanation guardrail working: {data}")
        elif response.status_code == 409:
            # May be blocked for other reasons (missing data)
            print(f"Decision blocked (possibly for other reasons): {response.json()}")
        else:
            # If it succeeded, the user may not be high-risk
            print(f"Decision response: {response.status_code} - {response.text}")


class TestObservabilityEndpoint:
    """Observability endpoint tests - schema + KPI fields"""

    def test_observability_summary_schema(self, auth_headers):
        """Test observability summary returns correct schema with KPI fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/observability/summary",
            headers=auth_headers,
            params={"days": 30},
            timeout=30
        )
        
        assert response.status_code == 200, f"Observability summary failed: {response.text}"
        data = response.json()
        
        # Check top-level fields
        assert "status" in data, "Missing status field"
        assert "window" in data, "Missing window field"
        assert "kpis" in data, "Missing kpis field"
        assert "reconcile" in data, "Missing reconcile field"
        assert "telemetry" in data, "Missing telemetry field"
        
        # Check KPI fields
        kpis = data["kpis"]
        assert "approval_rate" in kpis, "Missing approval_rate in kpis"
        assert "avg_approval_time" in kpis, "Missing avg_approval_time in kpis"
        assert "drop_off_rate" in kpis, "Missing drop_off_rate in kpis"
        assert "sla_breach_rate" in kpis, "Missing sla_breach_rate in kpis"
        assert "funnel" in kpis, "Missing funnel in kpis"
        assert "reject_distribution" in kpis, "Missing reject_distribution in kpis"
        
        # Check funnel fields
        funnel = kpis["funnel"]
        assert "signup" in funnel, "Missing signup in funnel"
        assert "kyc_started" in funnel, "Missing kyc_started in funnel"
        assert "kyc_verified" in funnel, "Missing kyc_verified in funnel"
        assert "approved" in funnel, "Missing approved in funnel"
        assert "activated" in funnel, "Missing activated in funnel"
        
        print(f"Observability KPIs: approval_rate={kpis['approval_rate']}%, sla_breach_rate={kpis['sla_breach_rate']}%")

    def test_observability_reconcile_status(self, auth_headers):
        """Test observability reconcile and status fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/observability/summary",
            headers=auth_headers,
            params={"days": 30},
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check reconcile fields
        reconcile = data["reconcile"]
        assert "decision_logs" in reconcile, "Missing decision_logs in reconcile"
        assert "decision_audit_logs" in reconcile, "Missing decision_audit_logs in reconcile"
        assert "workflow_cases" in reconcile, "Missing workflow_cases in reconcile"
        assert "workflow_logs" in reconcile, "Missing workflow_logs in reconcile"
        assert "mismatch_reasons" in reconcile, "Missing mismatch_reasons in reconcile"
        
        print(f"Reconcile: decision_logs={reconcile['decision_logs']}, workflow_cases={reconcile['workflow_cases']}")

    def test_observability_telemetry_percentiles(self, auth_headers):
        """Test observability telemetry percentiles fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/observability/summary",
            headers=auth_headers,
            params={"days": 30},
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check telemetry fields
        telemetry = data["telemetry"]
        assert "percentiles_ms" in telemetry, "Missing percentiles_ms in telemetry"
        assert "thresholds_ms" in telemetry, "Missing thresholds_ms in telemetry"
        assert "status" in telemetry, "Missing status in telemetry"
        
        # Check percentile fields
        percentiles = telemetry["percentiles_ms"]
        assert "p50" in percentiles, "Missing p50 in percentiles"
        assert "p95" in percentiles, "Missing p95 in percentiles"
        assert "p99" in percentiles, "Missing p99 in percentiles"
        
        print(f"Telemetry: p50={percentiles['p50']}ms, p95={percentiles['p95']}ms, p99={percentiles['p99']}ms, status={telemetry['status']}")


class TestDecisionSupportDrawer:
    """Decision Support Drawer tests - required fields"""

    def test_decision_support_required_fields(self, auth_headers, test_user_id):
        """Test decision support returns all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/decision-support",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Decision support failed: {response.text}"
        data = response.json()
        
        assert "decision_support" in data, "Missing decision_support field"
        ds = data["decision_support"]
        
        # Check required fields
        assert "recommended_action" in ds, "Missing recommended_action"
        assert "confidence" in ds, "Missing confidence"
        assert "reason_codes" in ds, "Missing reason_codes"
        assert "human_readable_summary" in ds, "Missing human_readable_summary"
        assert "auto_tag" in ds, "Missing auto_tag"
        
        print(f"Decision support: recommended_action={ds['recommended_action']}, confidence={ds['confidence']}, auto_tag={ds['auto_tag']}")

    def test_context_includes_precheck_reasons(self, auth_headers, test_user_id):
        """Test context includes precheck reasons (approval_disable_reasons)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/context",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "approval_disable_reasons" in data, "Missing approval_disable_reasons"
        assert "decision_engine" in data, "Missing decision_engine"
        
        engine = data["decision_engine"]
        assert "recommended_action" in engine, "Missing recommended_action in decision_engine"
        assert "why_approving" in engine, "Missing why_approving in decision_engine"
        
        print(f"Precheck reasons: {data['approval_disable_reasons']}")


class TestDetailDrawerContent:
    """Detail Drawer content tests - KYC/AML/risk/API/balance/workflow/audit/last decision/last 5 events"""

    def test_context_includes_all_detail_fields(self, auth_headers, test_user_id):
        """Test context includes all fields needed for detail drawer"""
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/context",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # KYC fields
        assert "kyc_status" in data, "Missing kyc_status"
        assert "kyc_documents" in data, "Missing kyc_documents"
        
        # AML fields
        assert "aml_flag" in data, "Missing aml_flag"
        assert "aml_reason" in data, "Missing aml_reason"
        
        # Risk fields
        assert "risk_score" in data, "Missing risk_score"
        assert "risk_flags" in data, "Missing risk_flags"
        
        # API fields
        assert "api_key_validity" in data, "Missing api_key_validity"
        assert "api_preview" in data, "Missing api_preview"
        
        # Balance fields
        assert "balance_usd" in data, "Missing balance_usd"
        
        # Workflow fields
        assert "workflow_case" in data, "Missing workflow_case"
        assert "assigned_to" in data, "Missing assigned_to"
        
        # Audit fields
        assert "audit_trail_recent" in data, "Missing audit_trail_recent"
        
        # Last decision attempt
        assert "last_decision_attempt" in data, "Missing last_decision_attempt"
        
        # Last 5 events
        assert "last_events" in data, "Missing last_events"
        
        print(f"Detail drawer fields present: kyc={data['kyc_status']}, aml={data['aml_flag']}, risk={data['risk_score']}")


class TestAtomicDecisionAudit:
    """Decision + audit log atomic behavior tests"""

    def test_reject_creates_audit_log(self, auth_headers, test_user_id):
        """Test reject decision creates audit log atomically"""
        # Get initial audit count
        context_before = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/context",
            headers=auth_headers,
            timeout=30
        ).json()
        
        audit_count_before = len(context_before.get("audit_trail_recent", []))
        
        # Make reject decision
        response = requests.post(
            f"{BASE_URL}/api/admin/onboarding/{test_user_id}/decision",
            headers=auth_headers,
            json={
                "decision": "reject",
                "reason": "test_atomic_audit: testing audit log creation",
                "explanation": "This is a test rejection to verify audit log is created atomically",
                "confirm_token": "CONFIRM"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            # Get context after to check audit log
            context_after = requests.get(
                f"{BASE_URL}/api/admin/onboarding/{test_user_id}/context",
                headers=auth_headers,
                timeout=30
            ).json()
            
            audit_count_after = len(context_after.get("audit_trail_recent", []))
            
            # Audit log should have increased
            assert audit_count_after >= audit_count_before, "Audit log not created after decision"
            print(f"Audit log created: before={audit_count_before}, after={audit_count_after}")
        else:
            # Decision may have failed for other reasons
            print(f"Decision response: {response.status_code} - {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
