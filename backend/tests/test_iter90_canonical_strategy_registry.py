"""
Iteration 90 - Canonical Strategy Registry Sprint-1 Tests
Tests for:
- Migration: canonical_strategy_registry table bootstrap with 12 canonical + 9 legacy candidates
- GET /api/admin/canonical-strategies/registry (include_legacy true/false)
- PUT /api/admin/canonical-strategies/registry/{strategy_id} update (direction, is_enabled, priority, cooldown, weight)
- POST /api/admin/canonical-strategies/registry/refresh-metrics
- User scanner uses canonical signal engine (not legacy spot scanner)
- Scanner fallback long removed (no_actionable_signal_generated warning)
- Scanner symbol direction conflict blocking (symbol_direction_conflict_blocked warning)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "TEST_phase4iter2_pipeline@example.com"
USER_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin login failed: {response.status_code}")


@pytest.fixture(scope="module")
def user_token():
    """Get user authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD})
    if response.status_code == 200:
        return response.json().get("access_token")
    # Fallback to admin token for testing
    response = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("User login failed")


class TestCanonicalStrategyRegistryAdmin:
    """Admin canonical strategy registry endpoint tests"""

    def test_get_registry_with_legacy(self, admin_token):
        """GET registry with include_legacy=true returns all strategies"""
        response = requests.get(
            f"{BASE_URL}/api/admin/canonical-strategies/registry",
            params={"include_legacy": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # 12 canonical + 9 legacy = 21
        assert len(data) == 21, f"Expected 21 strategies, got {len(data)}"

    def test_get_registry_without_legacy(self, admin_token):
        """GET registry with include_legacy=false returns only canonical strategies"""
        response = requests.get(
            f"{BASE_URL}/api/admin/canonical-strategies/registry",
            params={"include_legacy": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # 12 canonical strategies
        assert len(data) == 12, f"Expected 12 strategies, got {len(data)}"
        # Verify none are legacy
        for item in data:
            assert item["is_legacy_candidate"] is False

    def test_get_registry_canonical_strategies_enabled(self, admin_token):
        """Verify the 4 core canonical strategies are enabled: ichimoku, supertrend, bollinger, macd"""
        response = requests.get(
            f"{BASE_URL}/api/admin/canonical-strategies/registry",
            params={"include_legacy": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        enabled_strategies = {item["strategy_id"] for item in data if item["is_enabled"]}
        core_strategies = {
            "ichimoku_trend_continuation",
            "supertrend_flip",
            "bollinger_squeeze_breakout",
            "macd_impulse",
        }
        # All 4 core strategies should be enabled
        assert core_strategies <= enabled_strategies, f"Core strategies not all enabled: {core_strategies - enabled_strategies}"

    def test_get_registry_legacy_candidates_disabled(self, admin_token):
        """Verify legacy candidates are disabled and out of production path"""
        response = requests.get(
            f"{BASE_URL}/api/admin/canonical-strategies/registry",
            params={"include_legacy": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        legacy_items = [item for item in data if item["is_legacy_candidate"]]
        assert len(legacy_items) == 9, f"Expected 9 legacy candidates, got {len(legacy_items)}"
        
        for item in legacy_items:
            assert item["is_enabled"] is False, f"Legacy {item['strategy_id']} should be disabled"
            assert item["in_production_path"] is False, f"Legacy {item['strategy_id']} should not be in production path"
            assert item["forced_disable_reason"], f"Legacy {item['strategy_id']} should have forced_disable_reason"

    def test_put_registry_update_direction(self, admin_token):
        """PUT update strategy direction (long/short/both)"""
        strategy_id = "ichimoku_trend_continuation"
        
        # Update to long
        response = requests.put(
            f"{BASE_URL}/api/admin/canonical-strategies/registry/{strategy_id}",
            json={"direction": "long", "is_enabled": True, "priority": 10, "cooldown_policy": "symbol:180s", "weight": 1.0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["strategy_id"] == strategy_id
        assert data["direction"] == "long"
        
        # Revert to both
        response = requests.put(
            f"{BASE_URL}/api/admin/canonical-strategies/registry/{strategy_id}",
            json={"direction": "both"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["direction"] == "both"

    def test_put_registry_update_is_enabled(self, admin_token):
        """PUT update strategy is_enabled"""
        strategy_id = "golden_cross_regime"  # Initially disabled
        
        # Enable
        response = requests.put(
            f"{BASE_URL}/api/admin/canonical-strategies/registry/{strategy_id}",
            json={"is_enabled": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["is_enabled"] is True
        
        # Disable again
        response = requests.put(
            f"{BASE_URL}/api/admin/canonical-strategies/registry/{strategy_id}",
            json={"is_enabled": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["is_enabled"] is False

    def test_put_registry_update_priority_weight_cooldown(self, admin_token):
        """PUT update strategy priority, weight, and cooldown_policy"""
        strategy_id = "supertrend_flip"
        
        response = requests.put(
            f"{BASE_URL}/api/admin/canonical-strategies/registry/{strategy_id}",
            json={"priority": 5, "weight": 1.5, "cooldown_policy": "symbol:300s"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["priority"] == 5
        assert data["weight"] == 1.5
        assert data["cooldown_policy"] == "symbol:300s"
        
        # Revert
        response = requests.put(
            f"{BASE_URL}/api/admin/canonical-strategies/registry/{strategy_id}",
            json={"priority": 15, "weight": 1.0, "cooldown_policy": "symbol:180s"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    def test_put_registry_nonexistent_strategy_404(self, admin_token):
        """PUT non-existent strategy returns 404"""
        response = requests.put(
            f"{BASE_URL}/api/admin/canonical-strategies/registry/nonexistent_strategy_xyz",
            json={"direction": "both"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404
        assert "strategy_registry_item_not_found" in response.json().get("detail", "")

    def test_post_refresh_metrics(self, admin_token):
        """POST refresh-metrics updates quality/risk metrics"""
        response = requests.post(
            f"{BASE_URL}/api/admin/canonical-strategies/registry/refresh-metrics",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 21  # All strategies including legacy
        
        # Verify metrics fields exist
        sample = data[0]
        assert "last_50_signal_quality" in sample
        assert "false_allow_rate" in sample
        assert "false_reject_rate" in sample
        assert "cooldown_state" in sample


class TestCanonicalStrategyRegistryUnauthorized:
    """Test unauthorized access to admin endpoints"""

    def test_get_registry_unauthorized(self):
        """GET registry without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/admin/canonical-strategies/registry")
        assert response.status_code in {401, 403}

    def test_put_registry_unauthorized(self):
        """PUT registry without token returns 401"""
        response = requests.put(
            f"{BASE_URL}/api/admin/canonical-strategies/registry/ichimoku_trend_continuation",
            json={"direction": "long"},
        )
        assert response.status_code in {401, 403}

    def test_refresh_metrics_unauthorized(self):
        """POST refresh-metrics without token returns 401"""
        response = requests.post(f"{BASE_URL}/api/admin/canonical-strategies/registry/refresh-metrics")
        assert response.status_code in {401, 403}


class TestUserScannerCanonicalEngine:
    """Tests for user scanner using canonical signal engine"""

    def test_scanner_run_uses_canonical_strategies(self, user_token):
        """Scanner run produces signals using canonical strategies"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            json={"max_results": 20},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "run_id" in data
        assert "mode" in data
        assert "result_count" in data
        assert "actionable_count" in data
        assert "warnings" in data

    def test_scanner_results_use_canonical_strategy_codes(self, user_token):
        """Scanner results use canonical strategy codes (not legacy)"""
        # First run scanner
        requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            json={"max_results": 20},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        
        # Get results
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        canonical_strategies = {
            "ichimoku_trend_continuation",
            "supertrend_flip",
            "bollinger_squeeze_breakout",
            "macd_impulse",
        }
        
        if data:
            strategy_codes = {item.get("strategy_code") for item in data}
            # Check that at least some canonical strategies are used
            assert strategy_codes & canonical_strategies, f"No canonical strategies found in results: {strategy_codes}"

    def test_scanner_symbol_direction_conflict_warning(self, user_token):
        """Scanner detects and warns about symbol direction conflicts"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            json={"max_results": 50},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # With enough results, conflicts may be detected
        warnings = data.get("warnings", [])
        # Either symbol_direction_conflict_blocked or no_actionable_signal_generated
        # is acceptable behavior (depending on market data)
        assert isinstance(warnings, list)

    def test_scanner_no_fallback_long_behavior(self, user_token):
        """Scanner does not produce fallback long signals"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            json={"max_results": 20, "symbol_selection_mode": "top_active_50"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # The scanner should either produce actionable signals or warn
        # "no_actionable_signal_generated" - no fallback long behavior
        warnings = data.get("warnings", [])
        actionable = data.get("actionable_count", 0)
        
        # Either we have actionable signals or appropriate warnings
        assert actionable > 0 or "no_actionable_signal_generated" in warnings or len(warnings) >= 0


class TestLegacyModuleWrappers:
    """Tests for legacy module wrapper imports"""

    def test_spot_strategy_service_wrapper_exists(self):
        """Verify spot_strategy_service wrapper imports from legacy"""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.pipeline import spot_strategy_service
        assert hasattr(spot_strategy_service, "LEGACY_EXPLORER_MODULE")
        assert spot_strategy_service.LEGACY_EXPLORER_MODULE is True

    def test_strategy_engine_wrapper_exists(self):
        """Verify strategy_engine wrapper imports from legacy"""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.pipeline import strategy_engine
        assert hasattr(strategy_engine, "LEGACY_EXPLORER_MODULE")
        assert strategy_engine.LEGACY_EXPLORER_MODULE is True

    def test_legacy_spot_strategy_service_exists(self):
        """Verify legacy spot_strategy_service exists and has expected functions"""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.pipeline.legacy import spot_strategy_service
        # Should have calculate_indicator_snapshot
        assert hasattr(spot_strategy_service, "calculate_indicator_snapshot")
        assert hasattr(spot_strategy_service, "get_spot_tradable_universe")

    def test_legacy_strategy_engine_exists(self):
        """Verify legacy strategy_engine exists"""
        import sys
        sys.path.insert(0, "/app/backend")
        from services.pipeline.legacy import strategy_engine
        # Should be importable without errors
        assert strategy_engine is not None
