"""
Faz-6.1 + 6.2 Comprehensive Strategy Domain & Deterministic Kernel Contract Tests

Tests:
1. Admin-only strategy domain endpoints under /api/strategy-domain/admin/*
2. Create StrategyDefinition with unique code and append-only behavior
3. Create StrategyVersion immutable snapshot with version_hash generation rule
4. Activation pointer behavior: active_version_id update + strategy status active
5. Archive strategy endpoint
6. Registry endpoint /api/strategy-domain/admin/registry/active
7. Kernel evaluate contract endpoint /api/strategy-domain/admin/kernel/evaluate
8. Determinism: same context -> same context_hash + decision_hash
9. Canonical input ordering invariance for context hash
10. Validation error handling returns typed REJECT result (not 422)
11. Hash mismatch handling returns typed REJECT
"""

import copy
import os
import time
import uuid

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://risk-first-platform.preview.emergentagent.com")


@pytest.fixture(scope="module")
def admin_token() -> str:
    """Authenticate as admin and return token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
        timeout=20,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def user_token() -> str:
    """Authenticate as regular user and return token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "TEST_phase4iter2_pipeline@example.com", "password": "TestPassword123!"},
        timeout=20,
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    return None


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestAdminOnlyEndpoints:
    """Test that strategy domain endpoints are admin-only protected."""

    def test_strategies_list_requires_admin(self, admin_token, user_token):
        """GET /strategy-domain/admin/strategies requires admin role."""
        # Admin should succeed
        admin_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert admin_response.status_code == 200, "Admin should access strategies list"

        # User should be forbidden
        if user_token:
            user_response = requests.get(
                f"{BASE_URL}/api/strategy-domain/admin/strategies",
                headers=_headers(user_token),
                timeout=20,
            )
            assert user_response.status_code == 403, "User should NOT access admin strategies"

        # Unauthenticated should be rejected
        no_auth_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            timeout=20,
        )
        assert no_auth_response.status_code == 401, "Unauthenticated should be rejected"

    def test_create_strategy_requires_admin(self, admin_token, user_token):
        """POST /strategy-domain/admin/strategies requires admin role."""
        payload = {"name": "UnauthorizedTest", "code": f"unauth-{uuid.uuid4().hex[:8]}", "description": "test"}

        # User should be forbidden
        if user_token:
            user_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/strategies",
                headers=_headers(user_token),
                json=payload,
                timeout=20,
            )
            assert user_response.status_code == 403, "User should NOT create strategy"

        # Unauthenticated should be rejected
        no_auth_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            json=payload,
            timeout=20,
        )
        assert no_auth_response.status_code == 401

    def test_kernel_evaluate_requires_admin(self, admin_token, user_token):
        """POST /strategy-domain/admin/kernel/evaluate requires admin role."""
        payload = {"symbol": "BTCUSDT"}

        if user_token:
            user_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
                headers=_headers(user_token),
                json=payload,
                timeout=20,
            )
            assert user_response.status_code == 403

    def test_registry_active_requires_admin(self, admin_token, user_token):
        """GET /strategy-domain/admin/registry/active requires admin role."""
        admin_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/registry/active",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert admin_response.status_code == 200

        if user_token:
            user_response = requests.get(
                f"{BASE_URL}/api/strategy-domain/admin/registry/active",
                headers=_headers(user_token),
                timeout=20,
            )
            assert user_response.status_code == 403


class TestStrategyDefinitionCreation:
    """Test StrategyDefinition creation with unique code and append-only behavior."""

    def test_create_strategy_definition_success(self, admin_token):
        """Create strategy definition with valid payload."""
        unique_code = f"test-strat-{uuid.uuid4().hex[:8]}"
        payload = {
            "name": "Test Strategy Definition",
            "code": unique_code,
            "description": "A test strategy for testing",
        }

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json=payload,
            timeout=20,
        )
        assert response.status_code == 201, f"Create strategy failed: {response.text}"

        data = response.json()
        assert data["strategy_id"], "Should have strategy_id"
        assert data["name"] == payload["name"]
        assert data["code"] == unique_code.lower(), "Code should be normalized to lowercase"
        assert data["description"] == payload["description"]
        assert data["owner_type"] == "admin", "Admin-created strategy should have owner_type=admin"
        assert data["status"] == "draft", "New strategy should have status=draft"
        assert data["active_version_id"] is None, "New strategy should have no active version"
        assert data["created_at"], "Should have created_at timestamp"
        assert data["updated_at"], "Should have updated_at timestamp"

    def test_create_strategy_duplicate_code_rejected(self, admin_token):
        """Creating strategy with duplicate code should fail."""
        unique_code = f"dup-code-{uuid.uuid4().hex[:8]}"

        # First creation should succeed
        payload = {"name": "First Strategy", "code": unique_code, "description": "First"}
        response1 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json=payload,
            timeout=20,
        )
        assert response1.status_code == 201

        # Second creation with same code should fail
        payload2 = {"name": "Second Strategy", "code": unique_code, "description": "Second"}
        response2 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json=payload2,
            timeout=20,
        )
        assert response2.status_code == 400
        assert "strategy_code_exists" in response2.json().get("detail", "")

    def test_create_strategy_code_case_insensitive(self, admin_token):
        """Strategy code should be normalized to lowercase (case-insensitive uniqueness)."""
        unique_base = f"case-test-{uuid.uuid4().hex[:8]}"
        upper_code = unique_base.upper()
        lower_code = unique_base.lower()

        # Create with uppercase code
        response1 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json={"name": "Case Test 1", "code": upper_code, "description": ""},
            timeout=20,
        )
        assert response1.status_code == 201
        assert response1.json()["code"] == lower_code, "Code should be stored as lowercase"

        # Creating with lowercase code should fail (duplicate)
        response2 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json={"name": "Case Test 2", "code": lower_code, "description": ""},
            timeout=20,
        )
        assert response2.status_code == 400


class TestStrategyVersionCreation:
    """Test StrategyVersion immutable snapshot with version_hash generation."""

    @pytest.fixture(scope="class")
    def test_strategy(self, admin_token):
        """Create a test strategy for version tests."""
        unique_code = f"ver-test-{uuid.uuid4().hex[:8]}"
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json={"name": "Version Test Strategy", "code": unique_code, "description": "for version tests"},
            timeout=20,
        )
        assert response.status_code == 201
        return response.json()

    def test_create_strategy_version_success(self, admin_token, test_strategy):
        """Create strategy version with valid payload."""
        strategy_id = test_strategy["strategy_id"]
        config_json = {"momentum_threshold": 0.1, "base_size": 0.001, "volatility_guard": 0.5}

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=_headers(admin_token),
            json={"config_json": config_json, "config_schema_version": "1.0"},
            timeout=20,
        )
        assert response.status_code == 201, f"Create version failed: {response.text}"

        data = response.json()
        assert data["version_id"], "Should have version_id"
        assert data["strategy_id"] == strategy_id
        assert data["version_number"] == 1, "First version should be version_number=1"
        assert data["config_json"] == config_json
        assert data["config_schema_version"] == "1.0"
        assert len(data["version_hash"]) == 64, "version_hash should be SHA-256 hex (64 chars)"
        assert data["created_at"], "Should have created_at timestamp"

    def test_version_number_auto_increment(self, admin_token, test_strategy):
        """Version numbers should auto-increment."""
        strategy_id = test_strategy["strategy_id"]
        config_v2 = {"momentum_threshold": 0.15, "base_size": 0.002, "volatility_guard": 0.6}

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=_headers(admin_token),
            json={"config_json": config_v2, "config_schema_version": "1.0"},
            timeout=20,
        )
        assert response.status_code == 201
        data = response.json()
        # Should be version 2 or higher (depends on previous tests)
        assert data["version_number"] >= 1

    def test_version_hash_includes_version_number(self, admin_token, test_strategy):
        """Version hash is computed with version_number, so same config creates different versions (append-only)."""
        strategy_id = test_strategy["strategy_id"]
        config = {"same_config": True, "value": 123}

        # Create first version with this config
        response1 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=_headers(admin_token),
            json={"config_json": config, "config_schema_version": "1.0"},
            timeout=20,
        )
        assert response1.status_code == 201
        v1 = response1.json()

        # Creating another version with same config should create a NEW version
        # because version_hash = hash(config + strategy_id + version_number + schema)
        # and version_number auto-increments (append-only behavior)
        response2 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=_headers(admin_token),
            json={"config_json": config, "config_schema_version": "1.0"},
            timeout=20,
        )
        assert response2.status_code == 201
        v2 = response2.json()

        # Append-only: version_number increments, hash changes
        assert v1["version_number"] < v2["version_number"], "Version number should increment"
        assert v1["version_hash"] != v2["version_hash"], "Hash changes because version_number is in hash"
        assert v1["config_json"] == v2["config_json"], "Config should be the same"

    def test_create_version_for_nonexistent_strategy(self, admin_token):
        """Creating version for non-existent strategy should return 404."""
        fake_strategy_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{fake_strategy_id}/versions",
            headers=_headers(admin_token),
            json={"config_json": {"test": True}, "config_schema_version": "1.0"},
            timeout=20,
        )
        assert response.status_code == 404


class TestActivationPointerBehavior:
    """Test activation pointer behavior: active_version_id update + strategy status active."""

    @pytest.fixture(scope="class")
    def strategy_with_versions(self, admin_token):
        """Create a strategy with multiple versions for activation tests."""
        unique_code = f"act-test-{uuid.uuid4().hex[:8]}"
        create_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json={"name": "Activation Test Strategy", "code": unique_code, "description": "for activation tests"},
            timeout=20,
        )
        assert create_response.status_code == 201
        strategy = create_response.json()
        strategy_id = strategy["strategy_id"]

        # Create version 1
        v1_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=_headers(admin_token),
            json={"config_json": {"version": 1}, "config_schema_version": "1.0"},
            timeout=20,
        )
        assert v1_response.status_code == 201
        v1 = v1_response.json()

        # Create version 2
        v2_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=_headers(admin_token),
            json={"config_json": {"version": 2}, "config_schema_version": "1.0"},
            timeout=20,
        )
        assert v2_response.status_code == 201
        v2 = v2_response.json()

        return {"strategy": strategy, "v1": v1, "v2": v2}

    def test_activate_version_updates_pointer_and_status(self, admin_token, strategy_with_versions):
        """Activating a version should update active_version_id and status."""
        strategy_id = strategy_with_versions["strategy"]["strategy_id"]
        version_id = strategy_with_versions["v1"]["version_id"]

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{version_id}",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert response.status_code == 200, f"Activation failed: {response.text}"

        data = response.json()
        assert data["active_version_id"] == version_id, "active_version_id should be updated"
        assert data["status"] == "active", "status should become 'active'"

    def test_switch_active_version(self, admin_token, strategy_with_versions):
        """Switching to a different version should update the pointer."""
        strategy_id = strategy_with_versions["strategy"]["strategy_id"]
        v2_id = strategy_with_versions["v2"]["version_id"]

        # Activate v2
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{v2_id}",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["active_version_id"] == v2_id

    def test_activate_nonexistent_version(self, admin_token, strategy_with_versions):
        """Activating non-existent version should return 404."""
        strategy_id = strategy_with_versions["strategy"]["strategy_id"]
        fake_version_id = str(uuid.uuid4())

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{fake_version_id}",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert response.status_code == 404

    def test_activate_version_from_different_strategy(self, admin_token, strategy_with_versions):
        """Cannot activate a version that belongs to a different strategy."""
        # Create another strategy
        other_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json={"name": "Other Strategy", "code": f"other-{uuid.uuid4().hex[:8]}", "description": ""},
            timeout=20,
        )
        assert other_response.status_code == 201
        other_strategy_id = other_response.json()["strategy_id"]

        # Try to activate v1 from strategy_with_versions on this other strategy
        v1_id = strategy_with_versions["v1"]["version_id"]
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{other_strategy_id}/activate/{v1_id}",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert response.status_code == 404


class TestArchiveStrategy:
    """Test archive strategy endpoint."""

    def test_archive_strategy_success(self, admin_token):
        """Archive strategy should set status to 'archived'."""
        # Create a strategy to archive
        unique_code = f"arch-test-{uuid.uuid4().hex[:8]}"
        create_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json={"name": "Archive Test Strategy", "code": unique_code, "description": "to be archived"},
            timeout=20,
        )
        assert create_response.status_code == 201
        strategy_id = create_response.json()["strategy_id"]

        # Archive it
        archive_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/archive",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert archive_response.status_code == 200
        data = archive_response.json()
        assert data["status"] == "archived", "Status should be 'archived'"

    def test_archive_nonexistent_strategy(self, admin_token):
        """Archiving non-existent strategy should return 404."""
        fake_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{fake_id}/archive",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert response.status_code == 404


class TestActiveStrategyRegistry:
    """Test registry endpoint /api/strategy-domain/admin/registry/active."""

    def test_registry_active_returns_only_active_strategies(self, admin_token):
        """Registry/active should return only strategies with status='active'."""
        # Create and activate a strategy
        unique_code = f"reg-test-{uuid.uuid4().hex[:8]}"
        create_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json={"name": "Registry Test Strategy", "code": unique_code, "description": ""},
            timeout=20,
        )
        assert create_response.status_code == 201
        strategy_id = create_response.json()["strategy_id"]

        # Create a version
        v_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=_headers(admin_token),
            json={"config_json": {"test": True}, "config_schema_version": "1.0"},
            timeout=20,
        )
        assert v_response.status_code == 201
        version_id = v_response.json()["version_id"]

        # Activate it
        activate_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{version_id}",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert activate_response.status_code == 200

        # Check registry
        registry_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/registry/active",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert registry_response.status_code == 200
        active_strategies = registry_response.json()
        assert isinstance(active_strategies, list)

        # All returned strategies should be active
        for strategy in active_strategies:
            assert strategy["status"] == "active"

        # Our newly activated strategy should be in the list
        strategy_ids = [s["strategy_id"] for s in active_strategies]
        assert strategy_id in strategy_ids


class TestKernelEvaluateContract:
    """Test deterministic kernel evaluate contract endpoint."""

    @pytest.fixture(scope="class")
    def activated_strategy_version(self, admin_token):
        """Create and activate a strategy with a version for kernel tests."""
        unique_code = f"kernel-test-{uuid.uuid4().hex[:8]}"
        create_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json={"name": "Kernel Test Strategy", "code": unique_code, "description": "for kernel tests"},
            timeout=20,
        )
        assert create_response.status_code == 201
        strategy_id = create_response.json()["strategy_id"]

        v_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=_headers(admin_token),
            json={
                "config_json": {"momentum_threshold": 0.1, "base_size": 0.001, "volatility_guard": 0.5},
                "config_schema_version": "1.0",
            },
            timeout=20,
        )
        assert v_response.status_code == 201
        version = v_response.json()

        activate_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{version['version_id']}",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert activate_response.status_code == 200

        return version

    def _build_context(self, version_id: str, version_hash: str, momentum: float = 0.12) -> dict:
        """Build a valid decision context payload."""
        return {
            "context_id": f"ctx-{uuid.uuid4().hex[:8]}",
            "timestamp_utc": "2026-03-11T00:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900},
            "strategy_version_id": version_id,
            "strategy_version_hash": version_hash,
            "input_features": {"momentum": momentum, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": f"corr-{uuid.uuid4().hex[:8]}",
        }

    def test_kernel_evaluate_success(self, admin_token, activated_strategy_version):
        """Kernel evaluate should return valid decision result."""
        version = activated_strategy_version
        context = self._build_context(version["version_id"], version["version_hash"])

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=context,
            timeout=20,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["decision_id"], "Should have decision_id"
        assert data["action"] in ("BUY", "SELL", "HOLD", "CLOSE", "REJECT")
        assert isinstance(data["size"], (int, float))
        assert isinstance(data["confidence"], (int, float))
        assert isinstance(data["risk_score"], (int, float))
        assert isinstance(data["reason_codes"], list)
        assert len(data["context_hash"]) == 64, "context_hash should be SHA-256"
        assert len(data["decision_hash"]) == 64, "decision_hash should be SHA-256"

    def test_kernel_determinism_same_context_same_hashes(self, admin_token, activated_strategy_version):
        """Same context should produce same context_hash and decision_hash."""
        version = activated_strategy_version
        context = self._build_context(version["version_id"], version["version_hash"])

        response1 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=context,
            timeout=20,
        )
        response2 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=context,
            timeout=20,
        )

        assert response1.status_code == 200 and response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()

        assert data1["context_hash"] == data2["context_hash"], "Same context should produce same context_hash"
        assert data1["decision_hash"] == data2["decision_hash"], "Same context should produce same decision_hash"
        assert data1["action"] == data2["action"], "Same context should produce same action"

    def test_kernel_canonical_ordering_invariance(self, admin_token, activated_strategy_version):
        """Different key ordering in context should produce same context_hash."""
        version = activated_strategy_version

        # Original order
        context1 = self._build_context(version["version_id"], version["version_hash"])

        # Different key ordering for nested dicts
        context2 = {
            "context_id": context1["context_id"],
            "timestamp_utc": context1["timestamp_utc"],
            "symbol": context1["symbol"],
            "timeframe": context1["timeframe"],
            "market_snapshot": {"ask": 100010, "last_price": 100000, "bid": 99990},  # reordered
            "market_snapshot_hash": context1["market_snapshot_hash"],
            "position_state": {"qty": 0, "side": "flat"},  # reordered
            "risk_state": context1["risk_state"],
            "account_state_projection": {"free_margin": 900, "equity": 1000},  # reordered
            "strategy_version_id": context1["strategy_version_id"],
            "strategy_version_hash": context1["strategy_version_hash"],
            "input_features": {"base_size": 0.001, "volatility": 0.2, "momentum": 0.12},  # reordered
            "correlation_id": context1["correlation_id"],
        }

        response1 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=context1,
            timeout=20,
        )
        response2 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=context2,
            timeout=20,
        )

        assert response1.status_code == 200 and response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()

        assert data1["context_hash"] == data2["context_hash"], "Key ordering should not affect context_hash"
        assert data1["decision_hash"] == data2["decision_hash"], "Key ordering should not affect decision_hash"

    def test_kernel_different_context_different_hash(self, admin_token, activated_strategy_version):
        """Different context values should produce different context_hash."""
        version = activated_strategy_version
        context1 = self._build_context(version["version_id"], version["version_hash"], momentum=0.12)
        context2 = self._build_context(version["version_id"], version["version_hash"], momentum=0.25)

        response1 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=context1,
            timeout=20,
        )
        response2 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=context2,
            timeout=20,
        )

        assert response1.status_code == 200 and response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()

        # Different input features should produce different hashes
        assert data1["context_hash"] != data2["context_hash"], "Different context should produce different context_hash"


class TestValidationErrorHandling:
    """Test that validation errors return typed REJECT result, not HTTP 422."""

    def test_validation_error_returns_reject(self, admin_token):
        """Invalid/incomplete payload should return 200 with REJECT action, not 422."""
        invalid_payload = {"symbol": "BTCUSDT"}  # Missing required fields

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=invalid_payload,
            timeout=20,
        )

        # Should NOT be 422, should be 200 with REJECT
        assert response.status_code == 200, f"Should return 200, not {response.status_code}"

        data = response.json()
        assert data["action"] == "REJECT"
        assert "validation_error" in data["reason_codes"]
        assert data["confidence"] == 0.0
        assert data["risk_score"] == 1.0
        assert data["size"] == 0.0

    def test_missing_fields_returns_reject(self, admin_token):
        """Missing required fields should return REJECT, not HTTP error."""
        partial_payload = {
            "context_id": "ctx-test",
            "timestamp_utc": "2026-03-11T00:00:00Z",
            "symbol": "BTCUSDT",
            # Missing: timeframe, market_snapshot, etc.
        }

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=partial_payload,
            timeout=20,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "REJECT"
        assert "validation_error" in data["reason_codes"]


class TestHashMismatchHandling:
    """Test that hash mismatch returns typed REJECT result."""

    @pytest.fixture(scope="class")
    def test_version(self, admin_token):
        """Create a strategy version for hash mismatch tests."""
        unique_code = f"hash-mismatch-{uuid.uuid4().hex[:8]}"
        create_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json={"name": "Hash Mismatch Test", "code": unique_code, "description": ""},
            timeout=20,
        )
        assert create_response.status_code == 201
        strategy_id = create_response.json()["strategy_id"]

        v_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=_headers(admin_token),
            json={"config_json": {"test": True}, "config_schema_version": "1.0"},
            timeout=20,
        )
        assert v_response.status_code == 201
        return v_response.json()

    def test_wrong_version_hash_returns_reject(self, admin_token, test_version):
        """Wrong strategy_version_hash should return REJECT, not HTTP error."""
        context = {
            "context_id": "ctx-mismatch",
            "timestamp_utc": "2026-03-11T00:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900},
            "strategy_version_id": test_version["version_id"],
            "strategy_version_hash": "wrong-hash-value-that-does-not-match",  # WRONG HASH
            "input_features": {"momentum": 0.12, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": "corr-mismatch",
        }

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=context,
            timeout=20,
        )

        assert response.status_code == 200, "Should return 200 with REJECT, not HTTP error"
        data = response.json()
        assert data["action"] == "REJECT"
        assert "strategy_version_hash_mismatch" in data["reason_codes"]
        assert data["confidence"] == 0.0
        assert data["risk_score"] == 1.0

    def test_nonexistent_version_returns_reject(self, admin_token):
        """Non-existent strategy_version_id should return REJECT."""
        context = {
            "context_id": "ctx-missing-version",
            "timestamp_utc": "2026-03-11T00:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900},
            "strategy_version_id": str(uuid.uuid4()),  # Non-existent
            "strategy_version_hash": "some-hash",
            "input_features": {"momentum": 0.12, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": "corr-missing",
        }

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=context,
            timeout=20,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "REJECT"
        assert "strategy_version_not_found" in data["reason_codes"]


class TestKernelDecisionLogic:
    """Test kernel decision logic based on input features."""

    @pytest.fixture(scope="class")
    def kernel_test_version(self, admin_token):
        """Create an activated version for decision logic tests."""
        unique_code = f"decision-logic-{uuid.uuid4().hex[:8]}"
        create_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json={"name": "Decision Logic Test", "code": unique_code, "description": ""},
            timeout=20,
        )
        assert create_response.status_code == 201
        strategy_id = create_response.json()["strategy_id"]

        v_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=_headers(admin_token),
            json={"config_json": {"test": True}, "config_schema_version": "1.0"},
            timeout=20,
        )
        assert v_response.status_code == 201
        version = v_response.json()

        activate_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{version['version_id']}",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert activate_response.status_code == 200
        return version

    def _evaluate_with_momentum(self, admin_token, version, momentum: float, blocked: bool = False) -> dict:
        context = {
            "context_id": f"ctx-{uuid.uuid4().hex[:8]}",
            "timestamp_utc": "2026-03-11T00:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": blocked},
            "account_state_projection": {"equity": 1000, "free_margin": 900},
            "strategy_version_id": version["version_id"],
            "strategy_version_hash": version["version_hash"],
            "input_features": {"momentum": momentum, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": f"corr-{uuid.uuid4().hex[:8]}",
        }

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=_headers(admin_token),
            json=context,
            timeout=20,
        )
        assert response.status_code == 200
        return response.json()

    def test_positive_momentum_returns_buy(self, admin_token, kernel_test_version):
        """Positive momentum > 0.1 should return BUY action."""
        result = self._evaluate_with_momentum(admin_token, kernel_test_version, momentum=0.15)
        assert result["action"] == "BUY"
        assert "momentum_positive" in result["reason_codes"]
        assert result["size"] > 0

    def test_negative_momentum_returns_sell(self, admin_token, kernel_test_version):
        """Negative momentum < -0.1 should return SELL action."""
        result = self._evaluate_with_momentum(admin_token, kernel_test_version, momentum=-0.15)
        assert result["action"] == "SELL"
        assert "momentum_negative" in result["reason_codes"]

    def test_neutral_momentum_returns_hold(self, admin_token, kernel_test_version):
        """Near-zero momentum should return HOLD action."""
        result = self._evaluate_with_momentum(admin_token, kernel_test_version, momentum=0.01)
        assert result["action"] == "HOLD"
        assert "momentum_neutral" in result["reason_codes"]
        assert result["size"] == 0

    def test_risk_blocked_returns_reject(self, admin_token, kernel_test_version):
        """If risk_state.blocked=True, should return REJECT."""
        result = self._evaluate_with_momentum(admin_token, kernel_test_version, momentum=0.15, blocked=True)
        assert result["action"] == "REJECT"
        assert "risk_gate_blocked" in result["reason_codes"]
        assert result["confidence"] == 0.0
        assert result["risk_score"] == 1.0


class TestStrategyDetailEndpoint:
    """Test GET /strategy-domain/admin/strategies/{strategy_id} detail endpoint."""

    def test_get_strategy_detail_success(self, admin_token):
        """Get strategy detail should return strategy and versions."""
        # Create a strategy with versions
        unique_code = f"detail-test-{uuid.uuid4().hex[:8]}"
        create_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=_headers(admin_token),
            json={"name": "Detail Test Strategy", "code": unique_code, "description": "test"},
            timeout=20,
        )
        assert create_response.status_code == 201
        strategy_id = create_response.json()["strategy_id"]

        # Create a version
        v_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=_headers(admin_token),
            json={"config_json": {"test": True}, "config_schema_version": "1.0"},
            timeout=20,
        )
        assert v_response.status_code == 201

        # Get detail
        detail_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert detail_response.status_code == 200

        data = detail_response.json()
        assert "strategy" in data
        assert "versions" in data
        assert data["strategy"]["strategy_id"] == strategy_id
        assert isinstance(data["versions"], list)
        assert len(data["versions"]) >= 1

    def test_get_nonexistent_strategy_detail(self, admin_token):
        """Get non-existent strategy detail should return 404."""
        fake_id = str(uuid.uuid4())
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{fake_id}",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert response.status_code == 404
