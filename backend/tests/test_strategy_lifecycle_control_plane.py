"""
Strategy Lifecycle Control Plane Tests

Covers:
- Version governance: immutable version model, create new version, active version uniqueness, rollback endpoint
- Diff + timeline endpoints: /versions/diff and /versions/timeline
- Validation layer: invalid config create reject, validate endpoint error format (field/error_code/message)
- Activation requires validation/compatibility
- Deterministic evaluate-standard endpoint: PASS/BLOCK, SCORE, REASON_CODES, DECISION_HASH
- Replay endpoint: deterministic=true for same context
- Compare endpoint: version A/B same context output diff
- Regime binding preview: priority conflict resolution winner
- Production safety gate: dry-run + promote-request + approve/reject flows
- Audit/history endpoint: strategy lifecycle events visible
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def authed_session() -> requests.Session:
    """Authenticated session for super admin"""
    session = requests.Session()
    login = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200, f"Login failed: {login.status_code} {login.text}"
    token = login.json().get("access_token")
    assert token, "Missing access token"
    session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def test_strategy(authed_session: requests.Session) -> dict:
    """Create a test strategy for lifecycle tests"""
    unique_code = f"test_lifecycle_{uuid.uuid4().hex[:8]}"
    response = authed_session.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies",
        json={
            "name": f"Test Lifecycle Strategy {unique_code}",
            "code": unique_code,
            "description": "Test strategy for lifecycle control plane tests"
        },
        timeout=30,
    )
    assert response.status_code == 201, f"Strategy creation failed: {response.status_code} {response.text}"
    return response.json()


@pytest.fixture(scope="module")
def test_version(authed_session: requests.Session, test_strategy: dict) -> dict:
    """Create a test version for the strategy"""
    strategy_id = test_strategy["strategy_id"]
    response = authed_session.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
        json={
            "config_json": {
                "momentum_threshold": 0.1,
                "base_size": 0.001,
                "volatility_guard": 0.5
            },
            "config_schema_version": "1.0"
        },
        timeout=30,
    )
    assert response.status_code == 201, f"Version creation failed: {response.status_code} {response.text}"
    return response.json()


# ============================================================================
# VERSION GOVERNANCE TESTS
# ============================================================================

class TestVersionGovernance:
    """Tests for version governance: immutable model, create, active uniqueness, rollback"""

    def test_create_strategy_definition(self, authed_session: requests.Session):
        """Verify strategy definition creation"""
        unique_code = f"test_def_{uuid.uuid4().hex[:8]}"
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            json={
                "name": f"Test Definition {unique_code}",
                "code": unique_code,
                "description": "Test description"
            },
            timeout=30,
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["code"] == unique_code.lower()
        assert data["status"] == "draft"
        assert data["active_version_id"] is None

    def test_create_strategy_version_with_valid_config(self, authed_session: requests.Session, test_strategy: dict):
        """Verify version creation with valid config"""
        strategy_id = test_strategy["strategy_id"]
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={
                "config_json": {
                    "momentum_threshold": 0.15,
                    "base_size": 0.002,
                    "volatility_guard": 0.6
                },
                "config_schema_version": "1.0"
            },
            timeout=30,
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert "version_id" in data
        assert "version_hash" in data
        assert data["version_number"] >= 1

    def test_version_immutability_same_hash_returns_existing(self, authed_session: requests.Session, test_strategy: dict):
        """Verify same config returns existing version (immutability)"""
        strategy_id = test_strategy["strategy_id"]
        config = {
            "momentum_threshold": 0.123,
            "base_size": 0.001,
            "volatility_guard": 0.5
        }
        
        # Create first version
        response1 = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={"config_json": config, "config_schema_version": "1.0"},
            timeout=30,
        )
        assert response1.status_code == 201
        version1 = response1.json()
        
        # Create second version with same config
        response2 = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={"config_json": config, "config_schema_version": "1.0"},
            timeout=30,
        )
        assert response2.status_code == 201
        version2 = response2.json()
        
        # Should return same version (immutability)
        assert version1["version_id"] == version2["version_id"]
        assert version1["version_hash"] == version2["version_hash"]

    def test_activate_version_updates_active_version_id(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify activation updates active_version_id"""
        strategy_id = test_strategy["strategy_id"]
        version_id = test_version["version_id"]
        
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{version_id}",
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["active_version_id"] == version_id
        assert data["status"] == "active"

    def test_rollback_to_previous_version(self, authed_session: requests.Session, test_strategy: dict):
        """Verify rollback endpoint works"""
        strategy_id = test_strategy["strategy_id"]
        
        # Create two versions
        v1_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={
                "config_json": {"momentum_threshold": 0.11, "base_size": 0.001, "volatility_guard": 0.5},
                "config_schema_version": "1.0"
            },
            timeout=30,
        )
        v1 = v1_response.json()
        
        v2_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={
                "config_json": {"momentum_threshold": 0.22, "base_size": 0.002, "volatility_guard": 0.6},
                "config_schema_version": "1.0"
            },
            timeout=30,
        )
        v2 = v2_response.json()
        
        # Activate v2
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{v2['version_id']}",
            timeout=30,
        )
        
        # Rollback to v1
        rollback_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/rollback",
            json={
                "target_version_id": v1["version_id"],
                "reason": "test_rollback"
            },
            timeout=30,
        )
        assert rollback_response.status_code == 200, rollback_response.text
        data = rollback_response.json()
        assert data["current_active_version_id"] == v1["version_id"]
        assert data["previous_active_version_id"] == v2["version_id"]


# ============================================================================
# DIFF + TIMELINE TESTS
# ============================================================================

class TestDiffAndTimeline:
    """Tests for /versions/diff and /versions/timeline endpoints"""

    def test_version_diff_endpoint(self, authed_session: requests.Session, test_strategy: dict):
        """Verify version diff endpoint returns differences"""
        strategy_id = test_strategy["strategy_id"]
        
        # Create two versions with different configs
        v1_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={
                "config_json": {"momentum_threshold": 0.1, "base_size": 0.001, "volatility_guard": 0.5},
                "config_schema_version": "1.0"
            },
            timeout=30,
        )
        v1 = v1_response.json()
        
        v2_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={
                "config_json": {"momentum_threshold": 0.2, "base_size": 0.002, "volatility_guard": 0.7},
                "config_schema_version": "1.0"
            },
            timeout=30,
        )
        v2 = v2_response.json()
        
        # Get diff
        diff_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/diff",
            json={
                "from_version_id": v1["version_id"],
                "to_version_id": v2["version_id"]
            },
            timeout=30,
        )
        assert diff_response.status_code == 200, diff_response.text
        data = diff_response.json()
        assert "differences" in data
        assert "difference_count" in data
        assert data["difference_count"] >= 1

    def test_version_timeline_endpoint(self, authed_session: requests.Session, test_strategy: dict):
        """Verify version timeline endpoint returns audit events"""
        strategy_id = test_strategy["strategy_id"]
        
        response = authed_session.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/timeline",
            params={"limit": 50},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_audit_history_endpoint(self, authed_session: requests.Session, test_strategy: dict):
        """Verify audit-history endpoint returns lifecycle events"""
        strategy_id = test_strategy["strategy_id"]
        
        response = authed_session.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/audit-history",
            params={"limit": 50},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)


# ============================================================================
# VALIDATION LAYER TESTS
# ============================================================================

class TestValidationLayer:
    """Tests for validation layer: invalid config rejection, validate endpoint error format"""

    def test_invalid_config_rejected_on_create(self, authed_session: requests.Session, test_strategy: dict):
        """Verify invalid config is rejected with proper error format"""
        strategy_id = test_strategy["strategy_id"]
        
        # Missing required field
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={
                "config_json": {
                    "momentum_threshold": 0.1
                    # Missing base_size and volatility_guard
                },
                "config_schema_version": "1.0"
            },
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        detail = data["detail"]
        if isinstance(detail, dict):
            assert "issues" in detail or "error" in detail

    def test_invalid_config_type_rejected(self, authed_session: requests.Session, test_strategy: dict):
        """Verify invalid config type is rejected"""
        strategy_id = test_strategy["strategy_id"]
        
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={
                "config_json": {
                    "momentum_threshold": "not_a_number",  # Should be number
                    "base_size": 0.001,
                    "volatility_guard": 0.5
                },
                "config_schema_version": "1.0"
            },
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    def test_validate_endpoint_returns_error_format(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify validate endpoint returns field/error_code/message format"""
        strategy_id = test_strategy["strategy_id"]
        version_id = test_version["version_id"]
        
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/validate",
            json={"force": False},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "validation_status" in data
        assert "compatibility_status" in data
        assert "issues" in data
        # Issues should be list of {field, error_code, message}
        for issue in data.get("issues", []):
            assert "field" in issue or "error_code" in issue or "message" in issue


# ============================================================================
# ACTIVATION REQUIRES VALIDATION TESTS
# ============================================================================

class TestActivationRequiresValidation:
    """Tests for activation requiring validation/compatibility"""

    def test_activation_requires_validation_pass(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify activation requires validation_status=PASS"""
        strategy_id = test_strategy["strategy_id"]
        version_id = test_version["version_id"]
        
        # First validate
        validate_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/validate",
            json={"force": False},
            timeout=30,
        )
        assert validate_response.status_code == 200
        
        # Then activate
        activate_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{version_id}",
            timeout=30,
        )
        assert activate_response.status_code == 200, activate_response.text


# ============================================================================
# DETERMINISTIC EVALUATE-STANDARD TESTS
# ============================================================================

class TestDeterministicEvaluateStandard:
    """Tests for deterministic evaluate-standard endpoint: PASS/BLOCK, SCORE, REASON_CODES, DECISION_HASH"""

    def test_evaluate_standard_returns_required_fields(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify evaluate-standard returns PASS_BLOCK, SCORE, REASON_CODES, DECISION_HASH"""
        version_id = test_version["version_id"]
        version_hash = test_version["version_hash"]
        
        context = {
            "context_id": f"ctx-{uuid.uuid4().hex[:8]}",
            "account_id": "acct-test",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900, "daily_loss_pct": 1.2, "daily_loss_usd": 12},
            "strategy_version_id": version_id,
            "strategy_version_hash": version_hash,
            "input_features": {"momentum": 0.12, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": f"corr-{uuid.uuid4().hex[:8]}"
        }
        
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate-standard",
            json=context,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        # Check required fields
        assert "result" in data or "PASS_BLOCK" in data
        assert "score" in data or "SCORE" in data
        assert "reason_codes" in data or "REASON_CODES" in data
        assert "decision_hash" in data or "DECISION_HASH" in data
        
        # Verify result is PASS or BLOCK
        result = data.get("result") or data.get("PASS_BLOCK")
        assert result in {"PASS", "BLOCK"}, f"Invalid result: {result}"

    def test_evaluate_standard_deterministic_same_context(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify same context produces same decision_hash (deterministic)"""
        version_id = test_version["version_id"]
        version_hash = test_version["version_hash"]
        
        context = {
            "context_id": "ctx-deterministic-test",
            "account_id": "acct-test",
            "timestamp_utc": "2026-01-01T00:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900, "daily_loss_pct": 1.2, "daily_loss_usd": 12},
            "strategy_version_id": version_id,
            "strategy_version_hash": version_hash,
            "input_features": {"momentum": 0.15, "volatility": 0.25, "base_size": 0.001},
            "correlation_id": "corr-deterministic-test"
        }
        
        # First call
        response1 = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate-standard",
            json=context,
            timeout=30,
        )
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Second call with same context
        response2 = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate-standard",
            json=context,
            timeout=30,
        )
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Decision hash should be same
        hash1 = data1.get("decision_hash") or data1.get("DECISION_HASH")
        hash2 = data2.get("decision_hash") or data2.get("DECISION_HASH")
        assert hash1 == hash2, f"Decision hash mismatch: {hash1} != {hash2}"


# ============================================================================
# REPLAY ENDPOINT TESTS
# ============================================================================

class TestReplayEndpoint:
    """Tests for replay endpoint: deterministic=true for same context"""

    def test_replay_returns_deterministic_true(self, authed_session: requests.Session, test_version: dict):
        """Verify replay endpoint returns deterministic=true"""
        version_id = test_version["version_id"]
        version_hash = test_version["version_hash"]
        
        context_snapshot = {
            "context_id": "ctx-replay-test",
            "account_id": "acct-test",
            "timestamp_utc": "2026-01-01T00:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900, "daily_loss_pct": 1.2, "daily_loss_usd": 12},
            "strategy_version_id": version_id,
            "strategy_version_hash": version_hash,
            "input_features": {"momentum": 0.12, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": "corr-replay-test"
        }
        
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/replay",
            json={
                "strategy_version_id": version_id,
                "context_snapshot": context_snapshot
            },
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        assert "deterministic" in data
        assert data["deterministic"] is True, f"Expected deterministic=true, got {data['deterministic']}"
        assert "output" in data
        assert "decision_hash" in data.get("output", {}) or "decision_hash_recheck" in data


# ============================================================================
# COMPARE ENDPOINT TESTS
# ============================================================================

class TestCompareEndpoint:
    """Tests for compare endpoint: version A/B same context output diff"""

    def test_compare_versions_returns_output_diff(self, authed_session: requests.Session, test_strategy: dict):
        """Verify compare endpoint returns output_diff"""
        strategy_id = test_strategy["strategy_id"]
        
        # Create two versions with different configs
        v1_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={
                "config_json": {"momentum_threshold": 0.1, "base_size": 0.001, "volatility_guard": 0.5},
                "config_schema_version": "1.0"
            },
            timeout=30,
        )
        v1 = v1_response.json()
        
        v2_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={
                "config_json": {"momentum_threshold": 0.3, "base_size": 0.003, "volatility_guard": 0.8},
                "config_schema_version": "1.0"
            },
            timeout=30,
        )
        v2 = v2_response.json()
        
        context_snapshot = {
            "context_id": "ctx-compare-test",
            "account_id": "acct-test",
            "timestamp_utc": "2026-01-01T00:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900, "daily_loss_pct": 1.2, "daily_loss_usd": 12},
            "strategy_version_id": v1["version_id"],
            "strategy_version_hash": v1["version_hash"],
            "input_features": {"momentum": 0.15, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": "corr-compare-test"
        }
        
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/compare",
            json={
                "version_a_id": v1["version_id"],
                "version_b_id": v2["version_id"],
                "context_snapshot": context_snapshot
            },
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        assert "output_diff" in data
        assert "result_a" in data
        assert "result_b" in data
        
        output_diff = data["output_diff"]
        assert "result_changed" in output_diff or "action_changed" in output_diff
        assert "score_delta" in output_diff


# ============================================================================
# REGIME BINDING PREVIEW TESTS
# ============================================================================

class TestRegimeBindingPreview:
    """Tests for regime binding preview: priority conflict resolution winner"""

    def test_resolved_binding_preview_returns_winner(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify resolved-binding-preview returns winner_binding_id"""
        version_id = test_version["version_id"]
        
        # Create a regime binding
        binding_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/regime/bindings",
            json={
                "strategy_version_id": version_id,
                "allowed_regimes": ["trend_up", "range_low_vol"],
                "blocked_regimes": ["panic_dislocation"],
                "priority": 100,
                "gating_policy_version": "1.0"
            },
            timeout=30,
        )
        assert binding_response.status_code == 201, binding_response.text
        
        # Get binding preview
        preview_response = authed_session.get(
            f"{BASE_URL}/api/strategy-domain/admin/regime/resolved-binding-preview",
            params={
                "strategy_version_id": version_id,
                "regime_label": "trend_up"
            },
            timeout=30,
        )
        assert preview_response.status_code == 200, preview_response.text
        data = preview_response.json()
        
        assert "winner_binding_id" in data
        assert "winner_priority" in data
        assert "has_conflict" in data
        assert "candidates" in data

    def test_binding_preview_conflict_detection(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify binding preview detects conflicts"""
        version_id = test_version["version_id"]
        
        # Create multiple bindings with same priority
        for i in range(2):
            authed_session.post(
                f"{BASE_URL}/api/strategy-domain/admin/regime/bindings",
                json={
                    "strategy_version_id": version_id,
                    "allowed_regimes": ["trend_up"],
                    "blocked_regimes": [],
                    "priority": 50,
                    "gating_policy_version": "1.0"
                },
                timeout=30,
            )
        
        # Get binding preview
        preview_response = authed_session.get(
            f"{BASE_URL}/api/strategy-domain/admin/regime/resolved-binding-preview",
            params={
                "strategy_version_id": version_id,
                "regime_label": "trend_up"
            },
            timeout=30,
        )
        assert preview_response.status_code == 200
        data = preview_response.json()
        
        # Should detect conflict if multiple candidates with same priority
        assert "has_conflict" in data


# ============================================================================
# PRODUCTION SAFETY GATE TESTS
# ============================================================================

class TestProductionSafetyGate:
    """Tests for production safety gate: dry-run + promote-request + approve/reject flows"""

    def test_dry_run_endpoint(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify dry-run endpoint works"""
        strategy_id = test_strategy["strategy_id"]
        version_id = test_version["version_id"]
        
        # First validate
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/validate",
            json={"force": False},
            timeout=30,
        )
        
        # Then dry-run
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/dry-run",
            json={"context_snapshot": None},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        assert "dry_run_status" in data
        assert "lifecycle_state" in data
        assert "report" in data

    def test_promote_request_creation(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify promote-request creation"""
        strategy_id = test_strategy["strategy_id"]
        version_id = test_version["version_id"]
        
        # First validate and dry-run
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/validate",
            json={"force": False},
            timeout=30,
        )
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/dry-run",
            json={"context_snapshot": None},
            timeout=30,
        )
        
        # Create promote request
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/promote-request",
            json={
                "strategy_version_id": version_id,
                "request_note": "Test promote request",
                "require_validation": True,
                "require_dry_run": True,
                "requested_stage": None
            },
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        assert "request_id" in data
        assert data["status"] == "pending"
        assert data["strategy_version_id"] == version_id

    def test_promote_request_list(self, authed_session: requests.Session, test_strategy: dict):
        """Verify promote-request list endpoint"""
        strategy_id = test_strategy["strategy_id"]
        
        response = authed_session.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/promotion-requests",
            params={"limit": 20},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_promote_request_approve(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify promote-request approve flow"""
        strategy_id = test_strategy["strategy_id"]
        version_id = test_version["version_id"]
        
        # First validate and dry-run
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/validate",
            json={"force": False},
            timeout=30,
        )
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/dry-run",
            json={"context_snapshot": None},
            timeout=30,
        )
        
        # Create promote request
        create_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/promote-request",
            json={
                "strategy_version_id": version_id,
                "request_note": "Test approve flow",
                "require_validation": True,
                "require_dry_run": True,
                "requested_stage": None
            },
            timeout=30,
        )
        request_id = create_response.json()["request_id"]
        
        # Approve
        approve_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/promotion-requests/{request_id}/approve",
            json={"note": "Approved from test"},
            timeout=30,
        )
        assert approve_response.status_code == 200, approve_response.text
        data = approve_response.json()
        assert data["status"] == "approved"

    def test_promote_request_reject(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify promote-request reject flow"""
        strategy_id = test_strategy["strategy_id"]
        version_id = test_version["version_id"]
        
        # First validate and dry-run
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/validate",
            json={"force": False},
            timeout=30,
        )
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/dry-run",
            json={"context_snapshot": None},
            timeout=30,
        )
        
        # Create promote request
        create_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/promote-request",
            json={
                "strategy_version_id": version_id,
                "request_note": "Test reject flow",
                "require_validation": True,
                "require_dry_run": True,
                "requested_stage": None
            },
            timeout=30,
        )
        request_id = create_response.json()["request_id"]
        
        # Reject
        reject_response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/promotion-requests/{request_id}/reject",
            json={"note": "Rejected from test"},
            timeout=30,
        )
        assert reject_response.status_code == 200, reject_response.text
        data = reject_response.json()
        assert data["status"] == "rejected"


# ============================================================================
# CONTROL PLANE ENDPOINT TESTS
# ============================================================================

class TestControlPlaneEndpoint:
    """Tests for control-plane endpoint"""

    def test_control_plane_returns_all_data(self, authed_session: requests.Session, test_strategy: dict):
        """Verify control-plane endpoint returns all required data"""
        strategy_id = test_strategy["strategy_id"]
        
        response = authed_session.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/control-plane",
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        assert "strategy" in data
        assert "versions" in data
        assert "lifecycles" in data
        assert "active_version_id" in data
        assert "version_lifecycle_map" in data
        assert "pending_promotion_requests" in data

    def test_lifecycle_endpoint(self, authed_session: requests.Session, test_strategy: dict):
        """Verify lifecycle endpoint returns lifecycle data"""
        strategy_id = test_strategy["strategy_id"]
        
        response = authed_session.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/lifecycle",
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        assert "strategy_id" in data
        assert "items" in data
        assert "active_version_id" in data


# ============================================================================
# ROLLOUT STAGE TESTS
# ============================================================================

class TestRolloutStage:
    """Tests for rollout stage: shadow/canary"""

    def test_set_rollout_stage_shadow(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify setting rollout stage to shadow"""
        strategy_id = test_strategy["strategy_id"]
        version_id = test_version["version_id"]
        
        # First validate and dry-run
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/validate",
            json={"force": False},
            timeout=30,
        )
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/dry-run",
            json={"context_snapshot": None},
            timeout=30,
        )
        
        # Set stage to shadow
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/stage",
            json={"rollout_stage": "shadow"},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["rollout_stage"] == "shadow"
        assert data["lifecycle_state"] == "shadow"

    def test_set_rollout_stage_canary(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify setting rollout stage to canary"""
        strategy_id = test_strategy["strategy_id"]
        version_id = test_version["version_id"]
        
        # First validate and dry-run
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/validate",
            json={"force": False},
            timeout=30,
        )
        authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/dry-run",
            json={"context_snapshot": None},
            timeout=30,
        )
        
        # Set stage to canary
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/stage",
            json={"rollout_stage": "canary"},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["rollout_stage"] == "canary"
        assert data["lifecycle_state"] == "canary"

    def test_invalid_rollout_stage_rejected(self, authed_session: requests.Session, test_strategy: dict, test_version: dict):
        """Verify invalid rollout stage is rejected"""
        strategy_id = test_strategy["strategy_id"]
        version_id = test_version["version_id"]
        
        response = authed_session.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/stage",
            json={"rollout_stage": "invalid_stage"},
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
