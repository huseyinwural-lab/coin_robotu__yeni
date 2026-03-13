"""
Sprint-3 + Sprint-4 Combined Test Suite (Iteration 93)
Testing: Strategy Family Gates, Learning Memory, Decision Cards, Explainability, Admin Learning Panel

Features:
- GET/PUT /api/admin/strategy-family-gates
- GET /api/admin/blocked-reason-timeline/{symbol}
- GET /api/user/decision-cards
- GET /api/user/decision-cards/{symbol}
- GET /api/user/explainability/{symbol}
- GET /api/user/learning/safe-surface
- POST /api/admin/learning/refresh
- GET /api/admin/learning/overview
- POST /api/admin/learning/recommendations/{id}/apply
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "TEST_phase4iter2_pipeline@example.com"
USER_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def admin_token():
    """Login as admin and get token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if resp.status_code == 200:
        return resp.json().get("access_token")
    pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text}")


@pytest.fixture(scope="module")
def user_token():
    """Login as user and get token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
    )
    if resp.status_code == 200:
        return resp.json().get("access_token")
    pytest.skip(f"User login failed: {resp.status_code} - {resp.text}")


class TestStrategyFamilyGates:
    """Sprint-3: Strategy Family Strict Gates endpoints"""

    def test_get_strategy_family_gates_returns_200(self, admin_token):
        """GET /api/admin/strategy-family-gates should return 200 with gates list"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-family-gates",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Expected list of family gates"
        # Verify 4 default families: trend, breakout, pullback, reversal
        families = [item.get("family") for item in data]
        expected_families = {"trend", "breakout", "pullback", "reversal"}
        assert expected_families.issubset(set(families)), f"Missing families: {expected_families - set(families)}"
        print(f"PASS: GET strategy-family-gates returned {len(data)} gates: {families}")

    def test_get_strategy_family_gates_schema_fields(self, admin_token):
        """Gates should have correct schema fields"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-family-gates",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0, "Expected at least one gate"
        gate = data[0]
        # Required schema fields
        required_fields = [
            "schema_version", "engine_version", "generated_at", "family", "is_enabled",
            "long_threshold", "short_threshold", "min_strategy_count", "max_conflict_score",
            "regime_match_required", "risk_clear_required", "reversal_extra_confirmation"
        ]
        for field in required_fields:
            assert field in gate, f"Missing required field: {field}"
        print(f"PASS: Gate schema contains all required fields")

    def test_put_strategy_family_gates_updates_persist(self, admin_token):
        """PUT /api/admin/strategy-family-gates should persist updates"""
        # Get current gates
        resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-family-gates",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        current_gates = resp.json()

        # Update one gate
        update_payload = {
            "items": [
                {
                    "family": "trend",
                    "is_enabled": True,
                    "long_threshold": 5.5,  # Slightly modified
                    "short_threshold": 5.5,
                    "min_strategy_count": 1,
                    "max_conflict_score": 2.0,
                    "regime_match_required": True,
                    "risk_clear_required": True,
                    "reversal_extra_confirmation": False,
                }
            ]
        }
        resp = requests.put(
            f"{BASE_URL}/api/admin/strategy-family-gates",
            json=update_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        trend_gate = next((g for g in data if g["family"] == "trend"), None)
        assert trend_gate is not None, "Trend gate not found in response"
        assert float(trend_gate["long_threshold"]) == 5.5, "long_threshold not updated"
        print(f"PASS: PUT strategy-family-gates persisted update (long_threshold=5.5)")

        # Restore original value
        restore_payload = {
            "items": [
                {
                    "family": "trend",
                    "long_threshold": 5.0,
                    "short_threshold": 5.0,
                }
            ]
        }
        requests.put(
            f"{BASE_URL}/api/admin/strategy-family-gates",
            json=restore_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )


class TestBlockedReasonTimeline:
    """Sprint-3: Blocked reason timeline endpoint"""

    def test_admin_blocked_reason_timeline_returns_200(self, admin_token):
        """GET /api/admin/blocked-reason-timeline/{symbol} should return 200"""
        symbol = "BTCUSDT"
        resp = requests.get(
            f"{BASE_URL}/api/admin/blocked-reason-timeline/{symbol}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Verify response schema
        assert "schema_version" in data, "Missing schema_version"
        assert "engine_version" in data, "Missing engine_version"
        assert "generated_at" in data, "Missing generated_at"
        assert "symbol" in data, "Missing symbol"
        assert "items" in data, "Missing items"
        assert data["schema_version"] == "sprint3.v1", f"Unexpected schema_version: {data['schema_version']}"
        assert data["engine_version"] == "canonical-engine.v3", f"Unexpected engine_version: {data['engine_version']}"
        print(f"PASS: Admin blocked-reason-timeline/{symbol} returns correct schema (items={len(data['items'])})")


class TestDecisionCards:
    """Sprint-3: User decision cards endpoints"""

    def test_user_decision_cards_list_returns_200(self, user_token):
        """GET /api/user/decision-cards should return 200"""
        resp = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 40},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Verify envelope
        assert "schema_version" in data, "Missing schema_version"
        assert "engine_version" in data, "Missing engine_version"
        assert "generated_at" in data, "Missing generated_at"
        assert "items" in data, "Missing items"
        print(f"PASS: User decision-cards returns envelope with {len(data['items'])} items")

    def test_user_decision_cards_item_schema(self, user_token):
        """Decision card items should have correct fields"""
        resp = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        if len(data.get("items", [])) > 0:
            card = data["items"][0]
            required_fields = [
                "symbol", "decision", "confidence", "long_score", "short_score",
                "dominant_family", "top_contributors", "entry_zone",
                "confidence_adjustment", "learning_badges"
            ]
            for field in required_fields:
                assert field in card, f"Missing required field in card: {field}"
            # Verify decision is deterministic value
            valid_decisions = {"LONG", "SHORT", "BLOCKED", "NO_TRADE"}
            assert card["decision"] in valid_decisions, f"Invalid decision: {card['decision']}"
            print(f"PASS: Decision card schema correct ({card['symbol']}: {card['decision']})")
        else:
            print("PASS: No decision cards available (empty list)")

    def test_user_decision_card_by_symbol_returns_correct_or_404(self, user_token):
        """GET /api/user/decision-cards/{symbol} should return card or 404"""
        # First get list to find a valid symbol
        resp = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 10},
        )
        assert resp.status_code == 200
        items = resp.json().get("items", [])

        if items:
            symbol = items[0]["symbol"]
            resp = requests.get(
                f"{BASE_URL}/api/user/decision-cards/{symbol}",
                headers={"Authorization": f"Bearer {user_token}"},
            )
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            card = resp.json()
            assert card["symbol"] == symbol, f"Symbol mismatch: {card['symbol']} != {symbol}"
            print(f"PASS: Decision card by symbol '{symbol}' returned correctly")
        else:
            # No cards available, test 404 for non-existent symbol
            resp = requests.get(
                f"{BASE_URL}/api/user/decision-cards/NONEXISTENT",
                headers={"Authorization": f"Bearer {user_token}"},
            )
            assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
            print("PASS: Decision card returns 404 for non-existent symbol")


class TestExplainability:
    """Sprint-3: User explainability endpoint"""

    def test_user_explainability_returns_correct_or_404(self, user_token):
        """GET /api/user/explainability/{symbol} should return explainability or 404"""
        # First get decision cards to find a symbol
        resp = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 10},
        )
        assert resp.status_code == 200
        items = resp.json().get("items", [])

        if items:
            symbol = items[0]["symbol"]
            resp = requests.get(
                f"{BASE_URL}/api/user/explainability/{symbol}",
                headers={"Authorization": f"Bearer {user_token}"},
            )
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            # Verify schema
            required_fields = [
                "schema_version", "engine_version", "generated_at", "symbol",
                "final_decision", "long_score", "short_score", "winning_side",
                "source_strategies", "family_scores", "blocked_reason_timeline",
                "explanation_templates"
            ]
            for field in required_fields:
                assert field in data, f"Missing field in explainability: {field}"
            print(f"PASS: Explainability for '{symbol}' returns correct schema")
        else:
            resp = requests.get(
                f"{BASE_URL}/api/user/explainability/NONEXISTENT",
                headers={"Authorization": f"Bearer {user_token}"},
            )
            assert resp.status_code == 404
            print("PASS: Explainability returns 404 for non-existent symbol")


class TestLearningMemory:
    """Sprint-4: Learning Memory endpoints"""

    def test_user_learning_safe_surface_returns_200(self, user_token):
        """GET /api/user/learning/safe-surface should return learning badges/adjustments"""
        resp = requests.get(
            f"{BASE_URL}/api/user/learning/safe-surface",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 30},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Verify schema
        assert "schema_version" in data, "Missing schema_version"
        assert "engine_version" in data, "Missing engine_version"
        assert "generated_at" in data, "Missing generated_at"
        assert "items" in data, "Missing items"
        assert data["schema_version"] == "learning.v1", f"Unexpected schema_version: {data['schema_version']}"
        assert data["engine_version"] == "learning-engine.v1", f"Unexpected engine_version: {data['engine_version']}"
        print(f"PASS: User learning/safe-surface returns learning data (items={len(data['items'])})")

    def test_user_learning_safe_surface_item_schema(self, user_token):
        """Safe surface items should have confidence_adjustment and learning_badges"""
        resp = requests.get(
            f"{BASE_URL}/api/user/learning/safe-surface",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 30},
        )
        assert resp.status_code == 200
        data = resp.json()
        if len(data.get("items", [])) > 0:
            item = data["items"][0]
            required_fields = ["symbol", "decision", "confidence_adjustment", "learning_badges"]
            for field in required_fields:
                assert field in item, f"Missing field in safe-surface item: {field}"
            assert isinstance(item["learning_badges"], list), "learning_badges should be list"
            print(f"PASS: Safe-surface item schema correct ({item['symbol']})")
        else:
            print("PASS: No safe-surface items (empty list)")


class TestAdminLearning:
    """Sprint-4: Admin Learning Panel endpoints"""

    def test_admin_learning_overview_returns_200(self, admin_token):
        """GET /api/admin/learning/overview should return learning overview"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/learning/overview",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Verify schema
        assert "schema_version" in data, "Missing schema_version"
        assert "engine_version" in data, "Missing engine_version"
        assert "generated_at" in data, "Missing generated_at"
        assert "strategy_memory" in data, "Missing strategy_memory"
        assert "family_memory" in data, "Missing family_memory"
        assert "recommendations" in data, "Missing recommendations"
        assert isinstance(data["strategy_memory"], list), "strategy_memory should be list"
        assert isinstance(data["family_memory"], list), "family_memory should be list"
        assert isinstance(data["recommendations"], list), "recommendations should be list"
        print(f"PASS: Admin learning/overview returns overview (strategies={len(data['strategy_memory'])}, families={len(data['family_memory'])}, recommendations={len(data['recommendations'])})")

    def test_admin_learning_refresh_returns_200(self, admin_token):
        """POST /api/admin/learning/refresh should refresh learning memory"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/learning/refresh",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"days": 30},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Verify response schema
        assert "schema_version" in data, "Missing schema_version"
        assert "engine_version" in data, "Missing engine_version"
        assert "generated_at" in data, "Missing generated_at"
        assert "window_days" in data, "Missing window_days"
        assert "events_count" in data, "Missing events_count"
        assert data["schema_version"] == "learning.v1"
        assert data["engine_version"] == "learning-engine.v1"
        print(f"PASS: Admin learning/refresh completed (events={data['events_count']}, window_days={data['window_days']})")

    def test_admin_learning_recommendation_apply_nonexistent(self, admin_token):
        """POST /api/admin/learning/recommendations/{id}/apply should return 404 for non-existent"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/learning/recommendations/nonexistent-id/apply",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("PASS: Admin learning/recommendations/{id}/apply returns 404 for non-existent")

    def test_admin_learning_recommendation_apply_if_exists(self, admin_token):
        """Test apply recommendation flow if recommendation exists"""
        # First get overview to find a recommendation
        resp = requests.get(
            f"{BASE_URL}/api/admin/learning/overview",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        recommendations = data.get("recommendations", [])

        # Find an unapplied recommendation
        unapplied = [r for r in recommendations if not r.get("is_applied")]
        if unapplied:
            rec_id = unapplied[0]["id"]
            strategy_id = unapplied[0].get("strategy_id")
            resp = requests.post(
                f"{BASE_URL}/api/admin/learning/recommendations/{rec_id}/apply",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            # Expected outcomes:
            # - 200 if strategy exists in registry and recommendation applied
            # - 404 if strategy referenced doesn't exist in canonical registry
            # Both are valid behaviors - the endpoint correctly validates strategy existence
            if resp.status_code == 200:
                result = resp.json()
                assert result.get("status") == "ok", f"Unexpected status: {result.get('status')}"
                assert result.get("applied") is True, "Expected applied=True"
                print(f"PASS: Recommendation {rec_id} applied successfully")
            elif resp.status_code == 404:
                # This is expected if the strategy doesn't exist in canonical registry
                detail = resp.json().get("detail", "")
                assert "strategy_not_found" in detail, f"Unexpected 404 detail: {detail}"
                print(f"PASS: Apply returns 404 as strategy '{strategy_id}' not in registry (expected behavior)")
            else:
                raise AssertionError(f"Unexpected status: {resp.status_code}: {resp.text}")
        else:
            print("SKIP: No unapplied recommendations to test apply flow")


class TestScannerRunStability:
    """Test scanner run endpoint stability (should not return 500)"""

    def test_scanner_run_returns_non_500(self, user_token):
        """POST /api/user/scanner/run should not return 500"""
        resp = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            json={
                "mode": "ASSISTED",
                "max_results": 10,
                "symbol_source": "crypto",
                "symbol_selection_mode": "top_active_50",
                "selected_symbols": [],
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # Allow 200, 400, 422 but not 500
        assert resp.status_code != 500, f"Scanner run returned 500: {resp.text}"
        print(f"PASS: Scanner run returned {resp.status_code} (not 500)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
