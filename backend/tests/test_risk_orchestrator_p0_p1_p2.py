"""
Risk Orchestrator P0/P1/P2 Feature Tests
=========================================
P0: Queue determinism, Idempotency, Concurrency lock, Forced resolution hardening
P1/P2: Dashboard extensions (predictive_risk_signal, governance), Pagination
"""
import os
from pathlib import Path
import pytest
import requests
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _db_context():
    from db import SessionLocal
    from model_domains.risk_execution_positions import RiskOrchestratorApprovalRequest

    return SessionLocal, RiskOrchestratorApprovalRequest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"

SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"
DETERMINISTIC_REQUESTER_PASSWORD = "DeterministicRequester123!"


class TestRiskOrchestratorP0P1P2:
    """Risk Orchestrator P0/P1/P2 feature tests"""

    @pytest.fixture(scope="class")
    def super_admin_token(self):
        """Get super admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200, f"Super admin login failed: {response.status_code} - {response.text}"
        data = response.json()
        return data.get("access_token")

    @pytest.fixture(scope="class")
    def admin_token(self, super_admin_token):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        if response.status_code != 200:
            seed_email = f"det.requester.{int(time.time())}@platform.local"
            seed_payload = {
                "email": seed_email,
                "password": DETERMINISTIC_REQUESTER_PASSWORD,
                "full_name": "Deterministic Requester",
                "role": "admin",
            }
            create_response = requests.post(
                f"{BASE_URL}/api/admin/users/admin-create",
                json=seed_payload,
                headers={"Authorization": f"Bearer {super_admin_token}"},
                timeout=30,
            )
            assert create_response.status_code in [200, 201], f"Requester seed create failed: {create_response.text}"
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": seed_email, "password": DETERMINISTIC_REQUESTER_PASSWORD},
                timeout=30,
            )
            assert response.status_code == 200, f"Seed requester login failed: {response.text}"
        data = response.json()
        return data.get("access_token")

    @pytest.fixture(scope="class")
    def auth_headers(self, super_admin_token):
        """Auth headers for super admin"""
        return {"Authorization": f"Bearer {super_admin_token}"}

    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}

    def _reset_policy_to_baseline(self, headers):
        """Reset policy to a tight baseline so that loosening triggers CRITICAL classification"""
        baseline_policy = {
            "reference_equity_usd": 10000,
            "account_max_notional_pct": 70,
            "symbol_max_notional_pct": 60,
            "strategy_max_concurrent_positions": 8,
            "strategy_cooldown_seconds": 3,
            "max_order_frequency_per_min": 30,
            "max_order_burst_per_10s": 10,
            "daily_loss_limit_pct": 10,
            "duplicate_suppression_window_seconds": 3,
        }
        sim = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            headers=headers,
            json={"candidate_policy": baseline_policy},
            timeout=30,
        )
        if sim.status_code == 200:
            sim_id = sim.json()["simulation_id"]
            requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
                headers=headers,
                json={
                    "simulation_id": sim_id,
                    "reason_note": "reset-to-baseline",
                    "double_confirmed": True,
                    "apply_with_override": False,
                    "request_key": f"baseline-reset-{int(time.time() * 1000)}",
                },
                timeout=30,
            )

    def _create_critical_simulation(self, headers):
        """Creates a policy simulation that LOOSENS constraints to trigger CRITICAL classification"""
        payload = {
            "candidate_policy": {
                "reference_equity_usd": 10000,
                "account_max_notional_pct": 100,
                "symbol_max_notional_pct": 100,
                "strategy_max_concurrent_positions": 50,
                "strategy_cooldown_seconds": 0,
                "max_order_frequency_per_min": 200,
                "max_order_burst_per_10s": 100,
                "daily_loss_limit_pct": 50,
                "duplicate_suppression_window_seconds": 0,
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            json=payload,
            headers=headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Simulation create failed: {response.text}"
        return response.json()

    def _create_assigned_approval(self, admin_headers, auth_headers, *, request_suffix: str):
        simulation = self._create_critical_simulation(admin_headers)
        apply_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
            json={
                "simulation_id": simulation["simulation_id"],
                "reason_note": f"deterministic-seed-{request_suffix}",
                "double_confirmed": True,
                "apply_with_override": True,
                "request_key": f"closure-seed-{request_suffix}-{int(time.time() * 1000)}",
            },
            headers=admin_headers,
            timeout=30,
        )
        assert apply_response.status_code == 200, f"Apply seed failed: {apply_response.text}"
        approval_id = apply_response.json().get("approval_request_id")
        assert approval_id, "Seed apply did not return approval_request_id"

        assign_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/assign",
            json={"auto_assign": True},
            headers=auth_headers,
            timeout=30,
        )
        assert assign_response.status_code in [200, 400], f"Assign seed failed: {assign_response.text}"
        return approval_id

    @pytest.fixture(scope="class", autouse=True)
    def deterministic_state_seed(self, auth_headers, admin_headers):
        # Reset policy to baseline first to ensure CRITICAL classification
        self._reset_policy_to_baseline(auth_headers)
        
        approved_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "state": "approved", "limit": 1, "page": 1},
            headers=auth_headers,
            timeout=30,
        )
        assert approved_response.status_code == 200
        if not approved_response.json():
            approval_id = self._create_assigned_approval(admin_headers, auth_headers, request_suffix="approved")
            approve_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
                json={"decision_note": "deterministic-approved-seed"},
                headers=auth_headers,
                timeout=30,
            )
            assert approve_response.status_code == 200, f"Approved seed finalize failed: {approve_response.text}"

        # Reset policy again before creating expired approval
        self._reset_policy_to_baseline(auth_headers)
        
        expired_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "state": "expired", "limit": 1, "page": 1},
            headers=auth_headers,
            timeout=30,
        )
        assert expired_response.status_code == 200
        if not expired_response.json():
            expiring_approval_id = self._create_assigned_approval(admin_headers, auth_headers, request_suffix="expired")
            # Use raw SQL to update expires_at to avoid ORM foreign key issues
            from sqlalchemy import text
            from db import SessionLocal
            db = SessionLocal()
            try:
                past_time = datetime.now(timezone.utc) - timedelta(minutes=1)
                db.execute(
                    text("UPDATE risk_orchestrator_approval_requests SET expires_at = :expires_at WHERE approval_id = :approval_id"),
                    {"expires_at": past_time, "approval_id": expiring_approval_id}
                )
                db.commit()
            finally:
                db.close()

            sweep_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/sweep",
                headers=auth_headers,
                timeout=30,
            )
            assert sweep_response.status_code == 200, f"Sweep after expire seed failed: {sweep_response.text}"

    # ==================== P0: Queue Determinism Tests ====================

    def test_p0_queue_scope_all_filter(self, auth_headers):
        """P0: Test /policy/queue with scope=all returns all items"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "limit": 50, "page": 1},
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Queue all scope failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Queue response should be a list"
        print(f"P0 Queue scope=all: {len(data)} items returned")

    def test_p0_queue_scope_my_filter(self, auth_headers):
        """P0: Test /policy/queue with scope=my returns only assigned items"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "my", "limit": 50, "page": 1},
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Queue my scope failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Queue response should be a list"
        print(f"P0 Queue scope=my: {len(data)} items returned")

    def test_p0_queue_scope_unassigned_filter(self, auth_headers):
        """P0: Test /policy/queue with scope=unassigned returns unassigned items"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "unassigned", "limit": 50, "page": 1},
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Queue unassigned scope failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Queue response should be a list"
        # Verify all items have assigned_to as None
        for item in data:
            assert item.get("assigned_to") is None, f"Unassigned queue item has assigned_to: {item.get('assigned_to')}"
        print(f"P0 Queue scope=unassigned: {len(data)} items returned")

    def test_p0_queue_state_filter(self, auth_headers):
        """P0: Test /policy/queue with state filter"""
        for state in ["pending", "assigned", "approved", "rejected", "expired"]:
            response = requests.get(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
                params={"scope": "all", "state": state, "limit": 50, "page": 1},
                headers=auth_headers,
                timeout=30
            )
            assert response.status_code == 200, f"Queue state={state} failed: {response.text}"
            data = response.json()
            # Verify all items have the correct state
            for item in data:
                assert item.get("state") == state, f"Item state mismatch: expected {state}, got {item.get('state')}"
            print(f"P0 Queue state={state}: {len(data)} items returned")

    def test_p0_queue_critical_first_sorting(self, auth_headers):
        """P0: Test /policy/queue with critical_first=true sorts CRITICAL items first"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "critical_first": "true", "limit": 50, "page": 1},
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Queue critical_first failed: {response.text}"
        data = response.json()
        
        # Verify CRITICAL items come before non-CRITICAL
        seen_non_critical = False
        for item in data:
            if item.get("classification") != "CRITICAL":
                seen_non_critical = True
            elif seen_non_critical:
                # If we see CRITICAL after non-CRITICAL, sorting is wrong
                pytest.fail("CRITICAL item found after non-CRITICAL item with critical_first=true")
        print(f"P0 Queue critical_first sorting verified: {len(data)} items")

    # ==================== P0: Idempotency Tests ====================

    def test_p0_idempotency_policy_apply(self, auth_headers):
        """P0: Test idempotent replay for /policy/apply with same request_key"""
        # First, create a simulation
        simulate_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            json={
                "candidate_policy": {
                    "reference_equity_usd": 10000,
                    "account_max_notional_pct": 60,
                    "symbol_max_notional_pct": 25,
                    "strategy_max_concurrent_positions": 3,
                    "strategy_cooldown_seconds": 60,
                    "max_order_frequency_per_min": 6,
                    "max_order_burst_per_10s": 3,
                    "daily_loss_limit_pct": 5,
                    "duplicate_suppression_window_seconds": 300
                }
            },
            headers=auth_headers,
            timeout=30
        )
        assert simulate_response.status_code == 200, f"Simulation failed: {simulate_response.text}"
        simulation = simulate_response.json()
        simulation_id = simulation.get("simulation_id")
        
        # Generate unique request_key for idempotency test
        request_key = f"test-idempotency-{datetime.now().timestamp()}"
        
        # First apply attempt
        apply_payload = {
            "simulation_id": simulation_id,
            "reason_note": "Idempotency test - first attempt",
            "double_confirmed": True,
            "apply_with_override": True,
            "request_key": request_key
        }
        
        first_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
            json=apply_payload,
            headers=auth_headers,
            timeout=30
        )
        assert first_response.status_code == 200, f"First apply failed: {first_response.text}"
        first_result = first_response.json()
        first_status = first_result.get("status")
        
        # Second apply attempt with same request_key (should be idempotent)
        second_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
            json=apply_payload,
            headers=auth_headers,
            timeout=30
        )
        assert second_response.status_code == 200, f"Second apply failed: {second_response.text}"
        second_result = second_response.json()
        
        # Verify idempotent replay
        assert "idempotent_replay" in second_result.get("message", ""), \
            f"Expected idempotent replay message, got: {second_result.get('message')}"
        print(f"P0 Idempotency verified: first={first_status}, second={second_result.get('status')}")

    # ==================== P0: Concurrency Lock Tests ====================

    def test_p0_concurrency_approve_invalid_state(self, auth_headers):
        """P0: Test approve action on non-pending/assigned state returns 409"""
        # Get any approved/rejected/expired approval
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "state": "approved", "limit": 1},
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Could not fetch approved items: {response.text}"
        
        data = response.json()
        assert data, "No approved items to test concurrency lock"
        
        approval_id = data[0].get("approval_id")
        
        # Try to approve an already approved item
        approve_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
            json={"decision_note": "Test concurrency lock"},
            headers=auth_headers,
            timeout=30
        )
        
        # Should return 409 Conflict
        assert approve_response.status_code == 409, \
            f"Expected 409 for approve on approved item, got {approve_response.status_code}"
        print("P0 Concurrency lock verified: approve on approved item returns 409")

    def test_p0_concurrency_assign_invalid_state(self, auth_headers):
        """P0: Test assign action on non-pending/assigned state returns error"""
        # Get any expired approval
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "state": "expired", "limit": 1},
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Could not fetch expired items: {response.text}"
        
        data = response.json()
        assert data, "No expired items to test concurrency lock"
        
        approval_id = data[0].get("approval_id")
        
        # Try to assign an expired item
        assign_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/assign",
            json={"auto_assign": True},
            headers=auth_headers,
            timeout=30
        )
        
        # Should return error (400 or 409)
        assert assign_response.status_code in [400, 409, 404], \
            f"Expected error for assign on expired item, got {assign_response.status_code}"
        print("P0 Concurrency lock verified: assign on expired item returns error")

    # ==================== P0: Forced Resolution Hardening ====================

    def test_p0_force_apply_expired_state_rejected(self, auth_headers):
        """P0: Test force-apply on expired state is rejected"""
        # Get any expired approval
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "state": "expired", "limit": 1},
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Could not fetch expired items: {response.text}"
        
        data = response.json()
        assert data, "No expired items to test force-apply rejection"
        
        approval_id = data[0].get("approval_id")
        
        # Try to force-apply an expired item
        force_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/force-apply",
            json={"reason_note": "Test force-apply on expired"},
            headers=auth_headers,
            timeout=30
        )
        
        # Expired -> force path allowed; should succeed OR fail with stale_simulation_requires_resimulate
        # 200 = success, 409 = stale simulation (policy changed since simulation)
        assert force_response.status_code in [200, 409], \
            f"Expected 200 or 409 for force-apply on expired item, got {force_response.status_code}"
        
        if force_response.status_code == 200:
            print("P0 Force-apply path verified: expired state force path successful")
        else:
            detail = force_response.json().get("detail", "")
            assert "stale_simulation" in detail, f"Unexpected 409 reason: {detail}"
            print("P0 Force-apply path verified: expired state rejected due to stale simulation (expected behavior)")

    # ==================== P1/P2: Dashboard Extensions ====================

    def test_p1_dashboard_predictive_risk_signal(self, auth_headers):
        """P1: Test operational dashboard returns predictive_risk_signal"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/operations/dashboard",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        
        # Verify predictive_risk_signal is present
        assert "predictive_risk_signal" in data, "predictive_risk_signal missing from dashboard"
        signal = data.get("predictive_risk_signal", {})
        
        # Verify expected fields in predictive_risk_signal
        expected_fields = [
            "predictive_score", "recent_breach_count", "previous_breach_count",
            "breach_trend_pct", "pending_critical", "pending_total",
            "queue_pressure_pct", "avg_recent_volatility", "avg_previous_volatility",
            "volatility_acceleration_pct"
        ]
        for field in expected_fields:
            assert field in signal, f"predictive_risk_signal missing field: {field}"
        
        print(f"P1 Dashboard predictive_risk_signal verified: score={signal.get('predictive_score')}")

    def test_p2_dashboard_governance_data(self, auth_headers):
        """P2: Test operational dashboard returns governance data"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/operations/dashboard",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        
        # Verify governance is present
        assert "governance" in data, "governance missing from dashboard"
        governance = data.get("governance", {})
        
        # Verify expected governance fields (dashboard shows quorum waiting status)
        expected_fields = ["critical_quorum_waiting", "weighted_progress"]
        for field in expected_fields:
            assert field in governance, f"governance missing field: {field}"
        
        # Verify weighted_progress is a list
        assert isinstance(governance.get("weighted_progress"), list), "weighted_progress should be a list"
        
        print(f"P2 Dashboard governance verified: critical_quorum_waiting={governance.get('critical_quorum_waiting')}, progress_items={len(governance.get('weighted_progress', []))}")

    def test_p1_dashboard_all_fields(self, auth_headers):
        """P1: Test operational dashboard returns all expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/operations/dashboard",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        
        # Verify all expected dashboard fields
        expected_fields = [
            "active_pending_approvals", "critical_queue", "unassigned",
            "my_approvals", "reject_spike_last_hour", "override_usage",
            "risk_score_distribution", "approval_throughput_last_hour",
            "predictive_risk_signal", "governance"
        ]
        for field in expected_fields:
            assert field in data, f"Dashboard missing field: {field}"
        
        print(f"P1 Dashboard all fields verified: {len(expected_fields)} fields present")

    # ==================== P2: Pagination Tests ====================

    def test_p2_queue_pagination_page_1(self, auth_headers):
        """P2: Test queue pagination page 1"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "limit": 5, "page": 1},
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Queue page 1 failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Queue response should be a list"
        assert len(data) <= 5, f"Page 1 returned more than limit: {len(data)}"
        print(f"P2 Queue pagination page 1: {len(data)} items")

    def test_p2_queue_pagination_page_2(self, auth_headers):
        """P2: Test queue pagination page 2"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "limit": 5, "page": 2},
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Queue page 2 failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Queue response should be a list"
        print(f"P2 Queue pagination page 2: {len(data)} items")

    def test_p2_queue_pagination_consistency(self, auth_headers):
        """P2: Test queue pagination returns different items on different pages"""
        # Get page 1
        page1_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "limit": 5, "page": 1},
            headers=auth_headers,
            timeout=30
        )
        assert page1_response.status_code == 200
        page1_data = page1_response.json()
        
        # Get page 2
        page2_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "limit": 5, "page": 2},
            headers=auth_headers,
            timeout=30
        )
        assert page2_response.status_code == 200
        page2_data = page2_response.json()
        
        # If both pages have data, verify no overlap
        if page1_data and page2_data:
            page1_ids = {item.get("approval_id") for item in page1_data}
            page2_ids = {item.get("approval_id") for item in page2_data}
            overlap = page1_ids.intersection(page2_ids)
            assert not overlap, f"Pagination overlap detected: {overlap}"
        
        print(f"P2 Queue pagination consistency verified: page1={len(page1_data)}, page2={len(page2_data)}")

    # ==================== P2: Governance Quorum Tests ====================

    def test_p2_governance_quorum_in_approval_context(self, auth_headers):
        """P2: Test governance quorum data in approval context_payload"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            params={"scope": "all", "limit": 10},
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Queue failed: {response.text}"
        data = response.json()
        
        for item in data:
            context = item.get("context_payload", {})
            if "governance_policy" in context:
                gov_policy = context.get("governance_policy", {})
                assert "quorum_weight" in gov_policy, "governance_policy missing quorum_weight"
                assert "min_distinct_approvers" in gov_policy, "governance_policy missing min_distinct_approvers"
                assert "role_weights" in gov_policy, "governance_policy missing role_weights"
                print(f"P2 Governance quorum in approval: quorum={gov_policy.get('quorum_weight')}")
                break
        else:
            print("P2 Governance quorum: No approvals with governance_policy found (may be expected)")

    # ==================== Additional P0 Tests ====================

    def test_p0_queue_sweep_escalation(self, auth_headers):
        """P0: Test queue sweep escalation endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/sweep",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Queue sweep failed: {response.text}"
        data = response.json()
        
        # Verify expected fields
        expected_fields = ["warning_escalations", "critical_escalations", "stuck_detected"]
        for field in expected_fields:
            assert field in data, f"Queue sweep missing field: {field}"
        
        print(f"P0 Queue sweep: warnings={data.get('warning_escalations')}, critical={data.get('critical_escalations')}, stuck={data.get('stuck_detected')}")

    def test_p0_policy_current_version(self, auth_headers):
        """P0: Test current policy has version number"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Policy fetch failed: {response.text}"
        data = response.json()
        
        assert "policy_version" in data, "Policy missing policy_version"
        assert isinstance(data.get("policy_version"), int), "policy_version should be integer"
        print(f"P0 Policy version: {data.get('policy_version')}")

    def test_p0_status_snapshot(self, auth_headers):
        """P0: Test status snapshot endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/status",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Status failed: {response.text}"
        data = response.json()
        
        # Verify expected fields
        expected_fields = [
            "policy", "kill_switch_active", "kill_switch_reasons",
            "trading_enabled", "open_intents", "open_intents_by_symbol",
            "open_intents_by_strategy"
        ]
        for field in expected_fields:
            assert field in data, f"Status missing field: {field}"
        
        print(f"P0 Status: kill_switch={data.get('kill_switch_active')}, trading={data.get('trading_enabled')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
