"""
Iteration 92 - Sprint-3 User Explainability Panel + Strategy-family Strict Gating + Symbol-level Decision Cards

Tests Sprint-3 endpoints:
- GET /api/user/decision-cards 
- GET /api/user/decision-cards/{symbol}
- GET /api/user/explainability/{symbol}
- GET/PUT /api/admin/strategy-family-gates
- GET /api/admin/blocked-reason-timeline/{symbol}

Response Contract fields: schema_version, generated_at, engine_version
Decision Card fields: decision, long_score, short_score, dominant_family, top_contributors, entry/stop/tp/invalidation, blocked_reason
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
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Authenticate as admin and get token."""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin auth failed: {response.text}")


@pytest.fixture(scope="module")
def user_token(api_client):
    """Authenticate as user and get token."""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"User auth failed: {response.text}")


@pytest.fixture(scope="module")
def admin_client(api_client, admin_token):
    api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api_client


@pytest.fixture(scope="module")
def user_client(api_client, user_token):
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_token}"
    })
    return session


class TestAdminStrategyFamilyGates:
    """Tests for admin strategy family gates endpoints."""
    
    def test_get_strategy_family_gates_returns_200(self, admin_client):
        """GET /api/admin/strategy-family-gates returns 200."""
        response = admin_client.get(f"{BASE_URL}/api/admin/strategy-family-gates")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASS: GET /api/admin/strategy-family-gates returns 200 with {len(data)} gates")
    
    def test_strategy_family_gates_contract_fields(self, admin_client):
        """Response includes schema_version, engine_version, generated_at in each gate."""
        response = admin_client.get(f"{BASE_URL}/api/admin/strategy-family-gates")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0, "Should have at least one family gate"
        
        gate = data[0]
        assert "schema_version" in gate, "Gate should have schema_version"
        assert "engine_version" in gate, "Gate should have engine_version"
        assert "generated_at" in gate, "Gate should have generated_at"
        print(f"PASS: Family gate contract fields present: schema_version={gate['schema_version']}, engine_version={gate['engine_version']}")
    
    def test_expected_families_present(self, admin_client):
        """Expected families: trend, breakout, pullback, reversal."""
        response = admin_client.get(f"{BASE_URL}/api/admin/strategy-family-gates")
        assert response.status_code == 200
        data = response.json()
        
        families = {gate["family"] for gate in data}
        expected_families = {"trend", "breakout", "pullback", "reversal"}
        assert expected_families.issubset(families), f"Missing families. Expected {expected_families}, got {families}"
        print(f"PASS: All expected families present: {families}")
    
    def test_gate_fields_present(self, admin_client):
        """Each gate has required fields for strict gating."""
        response = admin_client.get(f"{BASE_URL}/api/admin/strategy-family-gates")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "family", "is_enabled", "long_threshold", "short_threshold",
            "min_strategy_count", "max_conflict_score", "regime_match_required",
            "risk_clear_required", "reversal_extra_confirmation"
        ]
        
        for gate in data:
            for field in required_fields:
                assert field in gate, f"Gate {gate.get('family')} missing field: {field}"
        print(f"PASS: All required gate fields present in {len(data)} gates")
    
    def test_put_strategy_family_gates_returns_200(self, admin_client):
        """PUT /api/admin/strategy-family-gates updates gates."""
        # First get current gates
        get_response = admin_client.get(f"{BASE_URL}/api/admin/strategy-family-gates")
        assert get_response.status_code == 200
        current_gates = get_response.json()
        
        # Prepare update payload with current values (no actual change to avoid side effects)
        items = []
        for gate in current_gates:
            items.append({
                "family": gate["family"],
                "is_enabled": gate["is_enabled"],
                "long_threshold": gate["long_threshold"],
                "short_threshold": gate["short_threshold"],
                "min_strategy_count": gate["min_strategy_count"],
                "max_conflict_score": gate["max_conflict_score"],
                "regime_match_required": gate["regime_match_required"],
                "risk_clear_required": gate["risk_clear_required"],
                "reversal_extra_confirmation": gate["reversal_extra_confirmation"]
            })
        
        put_response = admin_client.put(
            f"{BASE_URL}/api/admin/strategy-family-gates",
            json={"items": items}
        )
        assert put_response.status_code == 200, f"Expected 200, got {put_response.status_code}: {put_response.text}"
        updated_data = put_response.json()
        assert isinstance(updated_data, list)
        print(f"PASS: PUT /api/admin/strategy-family-gates returns 200 with {len(updated_data)} gates")


class TestAdminBlockedReasonTimeline:
    """Tests for admin blocked reason timeline endpoint."""
    
    def test_get_blocked_reason_timeline_returns_200(self, admin_client):
        """GET /api/admin/blocked-reason-timeline/{symbol} returns 200."""
        response = admin_client.get(f"{BASE_URL}/api/admin/blocked-reason-timeline/BTCUSDT")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "schema_version" in data, "Response should have schema_version"
        assert "engine_version" in data, "Response should have engine_version"
        assert "generated_at" in data, "Response should have generated_at"
        assert "symbol" in data, "Response should have symbol"
        assert "items" in data, "Response should have items list"
        print(f"PASS: GET /api/admin/blocked-reason-timeline/BTCUSDT returns 200 with {len(data['items'])} items")
    
    def test_blocked_timeline_contract_fields(self, admin_client):
        """Response includes schema_version, engine_version, generated_at."""
        response = admin_client.get(f"{BASE_URL}/api/admin/blocked-reason-timeline/ETHUSDT")
        assert response.status_code == 200
        data = response.json()
        
        assert data["schema_version"] == "sprint3.v1", f"Expected schema_version=sprint3.v1, got {data['schema_version']}"
        assert data["engine_version"] == "canonical-engine.v3", f"Expected engine_version=canonical-engine.v3, got {data['engine_version']}"
        assert data["symbol"] == "ETHUSDT", f"Expected symbol=ETHUSDT, got {data['symbol']}"
        print(f"PASS: Blocked timeline contract fields correct: schema_version={data['schema_version']}, engine_version={data['engine_version']}")


class TestUserDecisionCards:
    """Tests for user decision cards endpoints."""
    
    def test_get_user_decision_cards_returns_200(self, user_client):
        """GET /api/user/decision-cards returns 200."""
        response = user_client.get(f"{BASE_URL}/api/user/decision-cards")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "schema_version" in data, "Response should have schema_version"
        assert "engine_version" in data, "Response should have engine_version"
        assert "generated_at" in data, "Response should have generated_at"
        assert "items" in data, "Response should have items list"
        print(f"PASS: GET /api/user/decision-cards returns 200 with {len(data['items'])} items")
    
    def test_decision_cards_envelope_contract_fields(self, user_client):
        """Decision cards envelope includes schema_version, engine_version, generated_at."""
        response = user_client.get(f"{BASE_URL}/api/user/decision-cards")
        assert response.status_code == 200
        data = response.json()
        
        assert data["schema_version"] == "decision-card.v1", f"Expected schema_version=decision-card.v1, got {data['schema_version']}"
        assert data["engine_version"] == "canonical-engine.v3", f"Expected engine_version=canonical-engine.v3, got {data['engine_version']}"
        print(f"PASS: Decision cards envelope contract fields correct")
    
    def test_decision_card_item_fields(self, user_client):
        """Each decision card item has required fields."""
        response = user_client.get(f"{BASE_URL}/api/user/decision-cards")
        assert response.status_code == 200
        data = response.json()
        
        if len(data["items"]) == 0:
            pytest.skip("No decision cards available for field verification")
        
        card = data["items"][0]
        required_fields = [
            "schema_version", "engine_version", "generated_at", "symbol",
            "market_regime", "decision", "confidence", "long_score", "short_score",
            "dominant_family", "supporting_families", "top_contributors",
            "entry_zone", "stop_loss", "take_profit_1", "take_profit_2",
            "invalidation", "blocked_reason", "cooldown_remaining", "risk_block"
        ]
        
        for field in required_fields:
            assert field in card, f"Decision card missing field: {field}"
        
        # Verify decision is one of LONG/SHORT/BLOCKED/NO_TRADE
        valid_decisions = {"LONG", "SHORT", "BLOCKED", "NO_TRADE"}
        assert card["decision"] in valid_decisions, f"Invalid decision: {card['decision']}"
        print(f"PASS: Decision card has all required fields, decision={card['decision']}")


class TestUserDecisionCardBySymbol:
    """Tests for user decision card by symbol endpoint."""
    
    def test_get_decision_card_by_symbol_returns_200_or_404(self, user_client):
        """GET /api/user/decision-cards/{symbol} returns 200 or 404."""
        response = user_client.get(f"{BASE_URL}/api/user/decision-cards/BTCUSDT")
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "symbol" in data, "Response should have symbol"
            assert "decision" in data, "Response should have decision"
            print(f"PASS: GET /api/user/decision-cards/BTCUSDT returns 200 with decision={data['decision']}")
        else:
            print(f"PASS: GET /api/user/decision-cards/BTCUSDT returns 404 (no card available)")
    
    def test_decision_card_contract_fields(self, user_client):
        """Decision card has schema_version, engine_version, generated_at."""
        response = user_client.get(f"{BASE_URL}/api/user/decision-cards/BTCUSDT")
        
        if response.status_code == 404:
            pytest.skip("No decision card for BTCUSDT")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "schema_version" in data, "Response should have schema_version"
        assert "engine_version" in data, "Response should have engine_version"
        assert "generated_at" in data, "Response should have generated_at"
        print(f"PASS: Decision card contract fields present")


class TestUserExplainability:
    """Tests for user explainability endpoint."""
    
    def test_get_user_explainability_returns_200_or_404(self, user_client):
        """GET /api/user/explainability/{symbol} returns 200 or 404."""
        response = user_client.get(f"{BASE_URL}/api/user/explainability/BTCUSDT")
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "symbol" in data, "Response should have symbol"
            assert "final_decision" in data, "Response should have final_decision"
            print(f"PASS: GET /api/user/explainability/BTCUSDT returns 200 with final_decision={data['final_decision']}")
        else:
            print(f"PASS: GET /api/user/explainability/BTCUSDT returns 404 (no explainability data)")
    
    def test_explainability_contract_fields(self, user_client):
        """Explainability response has schema_version, engine_version, generated_at."""
        response = user_client.get(f"{BASE_URL}/api/user/explainability/BTCUSDT")
        
        if response.status_code == 404:
            pytest.skip("No explainability data for BTCUSDT")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "schema_version" in data, "Response should have schema_version"
        assert "engine_version" in data, "Response should have engine_version"
        assert "generated_at" in data, "Response should have generated_at"
        print(f"PASS: Explainability contract fields present: schema_version={data['schema_version']}")
    
    def test_explainability_payload_fields(self, user_client):
        """Explainability response has required payload fields."""
        response = user_client.get(f"{BASE_URL}/api/user/explainability/BTCUSDT")
        
        if response.status_code == 404:
            pytest.skip("No explainability data for BTCUSDT")
        
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "final_decision", "source_strategies", "family_scores",
            "blocked_reason_current", "blocked_reason_timeline",
            "risk_state", "cooldown_state", "regime_state"
        ]
        
        for field in required_fields:
            assert field in data, f"Explainability missing field: {field}"
        
        # Verify final_decision is deterministic
        valid_decisions = {"LONG", "SHORT", "BLOCKED", "NO_TRADE"}
        assert data["final_decision"] in valid_decisions, f"Invalid final_decision: {data['final_decision']}"
        print(f"PASS: Explainability payload has all required fields")
    
    def test_source_strategies_status_values(self, user_client):
        """Source strategies have status: accepted/rejected/gated/blocked."""
        response = user_client.get(f"{BASE_URL}/api/user/explainability/BTCUSDT")
        
        if response.status_code == 404:
            pytest.skip("No explainability data for BTCUSDT")
        
        assert response.status_code == 200
        data = response.json()
        
        valid_statuses = {"accepted", "rejected", "gated", "blocked"}
        strategies = data.get("source_strategies", [])
        
        if len(strategies) == 0:
            pytest.skip("No source strategies in explainability")
        
        for strategy in strategies:
            status = strategy.get("status", "")
            assert status in valid_statuses, f"Invalid strategy status: {status}"
        
        print(f"PASS: Source strategies have valid status values ({len(strategies)} strategies)")


class TestUserBlockedReasonTimeline:
    """Tests for user blocked reason timeline endpoint."""
    
    def test_get_user_blocked_reason_timeline_returns_200_or_404(self, user_client):
        """GET /api/user/blocked-reason-timeline/{symbol} returns 200 or 404."""
        response = user_client.get(f"{BASE_URL}/api/user/blocked-reason-timeline/BTCUSDT")
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "schema_version" in data, "Response should have schema_version"
            assert "engine_version" in data, "Response should have engine_version"
            assert "generated_at" in data, "Response should have generated_at"
            assert "symbol" in data, "Response should have symbol"
            assert "items" in data, "Response should have items"
            print(f"PASS: GET /api/user/blocked-reason-timeline/BTCUSDT returns 200 with {len(data['items'])} items")
        else:
            print(f"PASS: GET /api/user/blocked-reason-timeline/BTCUSDT returns 404 (no data)")


class TestScannerRunStability:
    """Tests for scanner run endpoint stability after Sprint-3."""
    
    def test_scanner_run_returns_200_not_500(self, user_client):
        """POST /api/user/scanner/run returns 200 (not 500) after Sprint-3."""
        response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 10,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_50",
            "selected_symbols": []
        })
        
        assert response.status_code != 500, f"Scanner run returned 500 error: {response.text}"
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "run_id" in data, "Response should have run_id"
        assert "mode" in data, "Response should have mode"
        print(f"PASS: POST /api/user/scanner/run returns 200, run_id={data['run_id']}")
    
    def test_scanner_run_with_auto_mode(self, user_client):
        """POST /api/user/scanner/run with AUTO mode works."""
        response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "AUTO",
            "max_results": 10,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_50"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Mode may be enforced to AUTO if bot is running
        assert data["mode"] in ["AUTO", "MANUAL", "ASSISTED"], f"Invalid mode: {data['mode']}"
        print(f"PASS: Scanner run with AUTO mode returns 200, result_count={data['result_count']}")


class TestFamilyGatingReasons:
    """Tests for family strict gating reasons in decision flow."""
    
    def test_strategy_family_gates_have_regime_match(self, admin_client):
        """Family gates have regime_match_required field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/strategy-family-gates")
        assert response.status_code == 200
        data = response.json()
        
        for gate in data:
            assert "regime_match_required" in gate, f"Gate {gate['family']} missing regime_match_required"
            assert isinstance(gate["regime_match_required"], bool)
        
        print(f"PASS: All {len(data)} family gates have regime_match_required field")
    
    def test_strategy_family_gates_have_threshold_fields(self, admin_client):
        """Family gates have long_threshold and short_threshold fields."""
        response = admin_client.get(f"{BASE_URL}/api/admin/strategy-family-gates")
        assert response.status_code == 200
        data = response.json()
        
        for gate in data:
            assert "long_threshold" in gate, f"Gate {gate['family']} missing long_threshold"
            assert "short_threshold" in gate, f"Gate {gate['family']} missing short_threshold"
            assert isinstance(gate["long_threshold"], (int, float))
            assert isinstance(gate["short_threshold"], (int, float))
        
        print(f"PASS: All family gates have threshold fields")
    
    def test_reversal_family_has_extra_confirmation(self, admin_client):
        """Reversal family gate has reversal_extra_confirmation field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/strategy-family-gates")
        assert response.status_code == 200
        data = response.json()
        
        reversal_gate = next((g for g in data if g["family"] == "reversal"), None)
        assert reversal_gate is not None, "Reversal family gate not found"
        assert "reversal_extra_confirmation" in reversal_gate, "Reversal gate missing reversal_extra_confirmation"
        print(f"PASS: Reversal family gate has reversal_extra_confirmation={reversal_gate['reversal_extra_confirmation']}")
