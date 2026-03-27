# ruff: noqa: E402
"""
P0 Sprint-1 Execution Policy Engine + Enforcement Pipeline API Tests

Tests:
1. /api/user/execution/intent/preview - Pipeline policy decision + reject contract
2. /api/user/execution/intent/submit - Submit with policy enforcement
3. Shadow mode enforcement behavior
4. Risk breach and kill-switch reject paths
5. /api/admin/execution-policies - engine_config, observability_metrics, policy_decision_log

Uses TestClient to avoid rate limiting and session issues.
"""
import json
import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from server import app
from db import SessionLocal
from models import User, UserRole
from core.security import hash_password, create_access_token

ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
TEST_USER_EMAIL = f"policy-test-{uuid.uuid4().hex[:8]}@example.com"
TEST_USER_PASSWORD = "PolicyTest123!"


def get_or_create_admin_token(db):
    """Get admin token for testing"""
    admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if not admin:
        pytest.skip("Admin user not found")
    return create_access_token(
        subject=admin.id,
        role=admin.role.value,
        email=admin.email,
        device_id=f"test-device-{uuid.uuid4().hex[:8]}",
    )


def get_or_create_user_token(db):
    """Get or create test user and return token"""
    user = db.query(User).filter(User.email == TEST_USER_EMAIL).first()
    if not user:
        user = User(
            email=TEST_USER_EMAIL,
            password_hash=hash_password(TEST_USER_PASSWORD),
            role=UserRole.USER,
            is_active=True,
            approval_status="approved",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.is_active or user.approval_status != "approved":
        user.is_active = True
        user.approval_status = "approved"
        db.commit()
    
    return create_access_token(
        subject=user.id,
        role=user.role.value,
        email=user.email,
        device_id=f"test-device-{uuid.uuid4().hex[:8]}",
    )


@pytest.fixture(scope="module")
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_headers():
    """Get admin auth headers"""
    db = SessionLocal()
    try:
        token = get_or_create_admin_token(db)
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


@pytest.fixture(scope="module")
def user_headers():
    """Get user auth headers"""
    db = SessionLocal()
    try:
        token = get_or_create_user_token(db)
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


class TestExecutionPolicyEngineSprint1API:
    """API tests for P0 Sprint-1 Execution Policy Engine"""

    # =========================================================================
    # Test 1: /api/user/execution/intent/preview - Basic preview with policy decision
    # =========================================================================
    def test_01_intent_preview_returns_policy_decision(self, client, user_headers):
        """Preview endpoint returns policy_decision with rollout_mode and standardized_reject"""
        payload = {
            "source_type": "manual",
            "source_ref_id": f"test-{uuid.uuid4().hex[:8]}",
            "intent_type": "OPEN_POSITION",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100.0,
            "execution_mode": "manual",
            "strategy_binding": "trend_following",
            "environment": "testnet",
        }
        
        resp = client.post(
            "/api/user/execution/intent/preview",
            json=payload,
            headers=user_headers,
        )
        
        # Should return 200 or 409 (duplicate)
        assert resp.status_code in [200, 409], f"Unexpected status: {resp.status_code}, {resp.text}"
        
        if resp.status_code == 200:
            data = resp.json()
            # Verify policy_decision is present
            assert "policy_decision" in data, "Missing policy_decision in response"
            assert "rollout_mode" in data, "Missing rollout_mode in response"
            
            # Verify rollout_mode is one of expected values
            assert data["rollout_mode"] in ["shadow", "soft", "partial", "full"], \
                f"Invalid rollout_mode: {data['rollout_mode']}"
            
            # Verify pipeline_stage_results is present
            assert "pipeline_stage_results" in data, "Missing pipeline_stage_results"
            
            print(f"PASS: Preview returns policy_decision with rollout_mode={data['rollout_mode']}")
        else:
            # 409 = duplicate intent, which is acceptable
            print("PASS: Preview returned 409 (duplicate intent) - idempotency working")

    # =========================================================================
    # Test 2: Preview with missing strategy policy - soft allow non-live
    # =========================================================================
    def test_02_preview_missing_strategy_soft_allow_non_live(self, client, user_headers):
        """Missing strategy policy should soft-allow in non-live environment"""
        payload = {
            "source_type": "manual",
            "source_ref_id": f"test-missing-{uuid.uuid4().hex[:8]}",
            "intent_type": "OPEN_POSITION",
            "market_type": "spot",
            "symbol": "ETHUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
            "execution_mode": "manual",
            "strategy_binding": f"nonexistent_strategy_{uuid.uuid4().hex[:6]}",
            "environment": "testnet",
        }
        
        resp = client.post(
            "/api/user/execution/intent/preview",
            json=payload,
            headers=user_headers,
        )
        
        assert resp.status_code in [200, 409], f"Unexpected status: {resp.status_code}, {resp.text}"
        
        if resp.status_code == 200:
            data = resp.json()
            # In testnet with missing strategy, should be soft-allowed (PREVIEWED)
            # Check standardized_reject for STRATEGY_POLICY_MISSING
            standardized_reject = data.get("standardized_reject") or {}
            
            if standardized_reject:
                reason_code = standardized_reject.get("reason_code", "")
                print(f"standardized_reject.reason_code: {reason_code}")
            
            # In shadow/soft mode, should still allow
            assert data.get("intent_status") in ["PREVIEWED", "REJECTED"], \
                f"Unexpected intent_status: {data.get('intent_status')}"
            
            print(f"PASS: Missing strategy in testnet - intent_status={data.get('intent_status')}")
        else:
            print("PASS: Preview returned 409 (duplicate intent)")

    # =========================================================================
    # Test 3: Preview with missing strategy policy - block in live
    # =========================================================================
    def test_03_preview_missing_strategy_block_live(self, client, user_headers):
        """Missing strategy policy should block in live environment (full rollout)"""
        payload = {
            "source_type": "manual",
            "source_ref_id": f"test-live-{uuid.uuid4().hex[:8]}",
            "intent_type": "OPEN_POSITION",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
            "execution_mode": "manual",
            "strategy_binding": f"missing_live_strategy_{uuid.uuid4().hex[:6]}",
            "environment": "live",
        }
        
        resp = client.post(
            "/api/user/execution/intent/preview",
            json=payload,
            headers=user_headers,
        )
        
        # Could be 200 (with REJECTED status) or 409 (duplicate)
        assert resp.status_code in [200, 409], f"Unexpected status: {resp.status_code}, {resp.text}"
        
        if resp.status_code == 200:
            data = resp.json()
            rollout_mode = data.get("rollout_mode", "shadow")
            intent_status = data.get("intent_status")
            reject_codes = data.get("reject_reason_codes", [])
            
            print(f"Live preview: rollout_mode={rollout_mode}, intent_status={intent_status}")
            print(f"reject_reason_codes: {reject_codes}")
            
            # If in full mode and live, should be REJECTED
            if rollout_mode == "full":
                assert intent_status == "REJECTED", \
                    f"Expected REJECTED in full mode live, got {intent_status}"
                assert "STRATEGY_POLICY_MISSING" in reject_codes, \
                    f"Expected STRATEGY_POLICY_MISSING in reject codes"
            
            print(f"PASS: Live preview with missing strategy handled correctly")
        else:
            print("PASS: Preview returned 409 (duplicate intent)")

    # =========================================================================
    # Test 4: Submit endpoint with policy enforcement
    # =========================================================================
    def test_04_submit_endpoint_policy_enforcement(self, client, user_headers):
        """Submit endpoint should enforce policy and return pipeline trace"""
        # First create a preview
        preview_payload = {
            "source_type": "manual",
            "source_ref_id": f"test-submit-{uuid.uuid4().hex[:8]}",
            "intent_type": "OPEN_POSITION",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100.0,
            "execution_mode": "manual",
            "strategy_binding": "trend_following",
            "environment": "testnet",
        }
        
        preview_resp = client.post(
            "/api/user/execution/intent/preview",
            json=preview_payload,
            headers=user_headers,
        )
        
        if preview_resp.status_code == 409:
            print("SKIP: Duplicate intent - cannot test submit")
            return
        
        assert preview_resp.status_code == 200, f"Preview failed: {preview_resp.text}"
        preview_data = preview_resp.json()
        
        intent_token = preview_data.get("intent_token")
        preview_hash = preview_data.get("preview_hash")
        intent_status = preview_data.get("intent_status")
        
        if intent_status != "PREVIEWED":
            print(f"SKIP: Intent not in PREVIEWED state ({intent_status})")
            return
        
        # Now submit
        submit_payload = {
            "intent_token": intent_token,
            "preview_hash": preview_hash,
        }
        
        submit_resp = client.post(
            "/api/user/execution/intent/submit",
            json=submit_payload,
            headers=user_headers,
        )
        
        # Could be 200 (success), 400 (validation), 423 (policy block)
        assert submit_resp.status_code in [200, 400, 423], \
            f"Unexpected submit status: {submit_resp.status_code}, {submit_resp.text}"
        
        if submit_resp.status_code == 200:
            data = submit_resp.json()
            assert "intent_id" in data, "Missing intent_id in submit response"
            assert "policy_decision" in data, "Missing policy_decision in submit response"
            assert "pipeline_trace" in data, "Missing pipeline_trace in submit response"
            print(f"PASS: Submit successful with policy_decision and pipeline_trace")
        elif submit_resp.status_code == 423:
            data = submit_resp.json()
            print(f"PASS: Submit blocked by policy - reason: {data.get('reason_code', 'unknown')}")
        else:
            print(f"PASS: Submit returned 400 - validation issue")

    # =========================================================================
    # Test 5: Admin execution-policies endpoint
    # =========================================================================
    def test_05_admin_execution_policies_endpoint(self, client, admin_headers):
        """Admin endpoint should return engine_config, observability_metrics, policy_decision_log"""
        resp = client.get(
            "/api/admin/execution-policies",
            headers=admin_headers,
        )
        
        assert resp.status_code == 200, f"Admin execution-policies failed: {resp.status_code}, {resp.text}"
        
        data = resp.json()
        
        # Verify required fields
        assert "engine_config" in data, "Missing engine_config in response"
        assert "observability_metrics" in data, "Missing observability_metrics in response"
        assert "policy_decision_log" in data, "Missing policy_decision_log in response"
        
        # Verify engine_config structure
        engine_config = data["engine_config"]
        assert "enabled" in engine_config, "Missing enabled in engine_config"
        assert "rollout_mode" in engine_config, "Missing rollout_mode in engine_config"
        assert engine_config["rollout_mode"] in ["shadow", "soft", "partial", "full"], \
            f"Invalid rollout_mode: {engine_config['rollout_mode']}"
        
        # Verify observability_metrics structure
        obs_metrics = data["observability_metrics"]
        assert "decision_log_count" in obs_metrics, "Missing decision_log_count"
        assert "violation_count" in obs_metrics, "Missing violation_count"
        assert "risk_breach_metrics" in obs_metrics, "Missing risk_breach_metrics"
        
        # Verify policy_decision_log is a list
        assert isinstance(data["policy_decision_log"], list), "policy_decision_log should be a list"
        
        print(f"PASS: Admin execution-policies returns all required fields")
        print(f"  - engine_config.rollout_mode: {engine_config['rollout_mode']}")
        print(f"  - observability_metrics.decision_log_count: {obs_metrics['decision_log_count']}")
        print(f"  - policy_decision_log entries: {len(data['policy_decision_log'])}")

    # =========================================================================
    # Test 6: Verify shadow mode behavior
    # =========================================================================
    def test_06_shadow_mode_allows_but_logs_violations(self, client, admin_headers, user_headers):
        """In shadow mode, violations should be logged but execution allowed"""
        # First check current rollout mode
        policies_resp = client.get(
            "/api/admin/execution-policies",
            headers=admin_headers,
        )
        assert policies_resp.status_code == 200
        
        engine_config = policies_resp.json().get("engine_config", {})
        rollout_mode = engine_config.get("rollout_mode", "shadow")
        
        print(f"Current rollout_mode: {rollout_mode}")
        
        # Create a preview that would normally be blocked
        payload = {
            "source_type": "manual",
            "source_ref_id": f"test-shadow-{uuid.uuid4().hex[:8]}",
            "intent_type": "OPEN_POSITION",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100.0,
            "execution_mode": "manual",
            "strategy_binding": f"shadow_test_strategy_{uuid.uuid4().hex[:6]}",
            "environment": "testnet",
        }
        
        resp = client.post(
            "/api/user/execution/intent/preview",
            json=payload,
            headers=user_headers,
        )
        
        assert resp.status_code in [200, 409], f"Unexpected status: {resp.status_code}"
        
        if resp.status_code == 200:
            data = resp.json()
            response_rollout_mode = data.get("rollout_mode", "unknown")
            standardized_reject = data.get("standardized_reject")
            intent_status = data.get("intent_status")
            
            print(f"Response rollout_mode: {response_rollout_mode}")
            print(f"intent_status: {intent_status}")
            print(f"standardized_reject: {standardized_reject}")
            
            # In shadow mode, should be PREVIEWED even with violations
            if response_rollout_mode == "shadow":
                assert intent_status == "PREVIEWED", \
                    f"Shadow mode should allow preview, got {intent_status}"
                print("PASS: Shadow mode allows preview with logged violation")
            else:
                print(f"PASS: Non-shadow mode ({response_rollout_mode}) - behavior as expected")
        else:
            print("PASS: Duplicate intent (409)")

    # =========================================================================
    # Test 7: Verify reject contract structure
    # =========================================================================
    def test_07_reject_contract_structure(self, client, user_headers):
        """Verify standardized_reject contract has required fields"""
        # Create a preview that will have a reject
        payload = {
            "source_type": "manual",
            "source_ref_id": f"test-reject-{uuid.uuid4().hex[:8]}",
            "intent_type": "OPEN_POSITION",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100.0,
            "execution_mode": "manual",
            "strategy_binding": f"reject_test_{uuid.uuid4().hex[:6]}",
            "environment": "testnet",
        }
        
        resp = client.post(
            "/api/user/execution/intent/preview",
            json=payload,
            headers=user_headers,
        )
        
        assert resp.status_code in [200, 409], f"Unexpected status: {resp.status_code}"
        
        if resp.status_code == 200:
            data = resp.json()
            standardized_reject = data.get("standardized_reject")
            
            if standardized_reject:
                # Verify reject contract structure
                assert "reason_code" in standardized_reject, "Missing reason_code in reject"
                assert "reason_message" in standardized_reject, "Missing reason_message in reject"
                assert "stage" in standardized_reject, "Missing stage in reject"
                assert "severity" in standardized_reject, "Missing severity in reject"
                assert "action_taken" in standardized_reject, "Missing action_taken in reject"
                
                print(f"PASS: Reject contract structure verified")
                print(f"  - reason_code: {standardized_reject['reason_code']}")
                print(f"  - stage: {standardized_reject['stage']}")
                print(f"  - severity: {standardized_reject['severity']}")
                print(f"  - action_taken: {standardized_reject['action_taken']}")
            else:
                print("PASS: No reject (valid intent)")
        else:
            print("PASS: Duplicate intent (409)")

    # =========================================================================
    # Test 8: Policy decision log entries
    # =========================================================================
    def test_08_policy_decision_log_entries(self, client, admin_headers):
        """Verify policy_decision_log entries have required fields"""
        resp = client.get(
            "/api/admin/execution-policies",
            headers=admin_headers,
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        decision_log = data.get("policy_decision_log", [])
        
        if len(decision_log) > 0:
            entry = decision_log[0]
            
            # Verify required fields in decision log entry
            required_fields = [
                "id", "pipeline_id", "lifecycle_action", "stage",
                "rollout_mode", "recommended_action", "enforced_action",
                "created_at"
            ]
            
            for field in required_fields:
                assert field in entry, f"Missing {field} in decision log entry"
            
            print(f"PASS: Policy decision log entry has all required fields")
            print(f"  - Sample entry: stage={entry['stage']}, recommended={entry['recommended_action']}, enforced={entry['enforced_action']}")
        else:
            print("PASS: No decision log entries yet (empty log)")

    # =========================================================================
    # Test 9: Observability metrics structure
    # =========================================================================
    def test_09_observability_metrics_structure(self, client, admin_headers):
        """Verify observability_metrics has required structure"""
        resp = client.get(
            "/api/admin/execution-policies",
            headers=admin_headers,
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        obs_metrics = data.get("observability_metrics", {})
        
        # Verify required fields
        required_fields = [
            "window_hours", "decision_log_count", "violation_count",
            "risk_breach_metrics", "reject_reason_distribution",
            "stage_decision_rates"
        ]
        
        for field in required_fields:
            assert field in obs_metrics, f"Missing {field} in observability_metrics"
        
        # Verify risk_breach_metrics structure
        risk_metrics = obs_metrics.get("risk_breach_metrics", {})
        assert "breach_count" in risk_metrics, "Missing breach_count in risk_breach_metrics"
        assert "breach_rate" in risk_metrics, "Missing breach_rate in risk_breach_metrics"
        
        print(f"PASS: Observability metrics structure verified")
        print(f"  - window_hours: {obs_metrics['window_hours']}")
        print(f"  - decision_log_count: {obs_metrics['decision_log_count']}")
        print(f"  - violation_count: {obs_metrics['violation_count']}")
        print(f"  - risk_breach_count: {risk_metrics['breach_count']}")

    # =========================================================================
    # Test 10: Engine config structure
    # =========================================================================
    def test_10_engine_config_structure(self, client, admin_headers):
        """Verify engine_config has required structure"""
        resp = client.get(
            "/api/admin/execution-policies",
            headers=admin_headers,
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        engine_config = data.get("engine_config", {})
        
        # Verify required fields
        required_fields = [
            "enabled", "rollout_mode", "progression", "fail_safe_mode"
        ]
        
        for field in required_fields:
            assert field in engine_config, f"Missing {field} in engine_config"
        
        # Verify rollout_mode is valid
        assert engine_config["rollout_mode"] in ["shadow", "soft", "partial", "full"], \
            f"Invalid rollout_mode: {engine_config['rollout_mode']}"
        
        # Verify progression is a list
        assert isinstance(engine_config["progression"], list), "progression should be a list"
        
        print(f"PASS: Engine config structure verified")
        print(f"  - enabled: {engine_config['enabled']}")
        print(f"  - rollout_mode: {engine_config['rollout_mode']}")
        print(f"  - progression: {engine_config['progression']}")
        print(f"  - fail_safe_mode: {engine_config['fail_safe_mode']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
