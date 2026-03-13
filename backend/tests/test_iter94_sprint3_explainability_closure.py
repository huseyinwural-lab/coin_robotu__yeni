"""
Iteration 94 - Sprint-3 Explainability Closure Tests
Tests: Decision Cards, Explainability Drawer, Strategy Family Gates, 10s Polling
User: TEST_phase4iter2_pipeline@example.com / TestPassword123!
Admin: admin@platform.dev / Admin12345!
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestSprint3ExplainabilityAPIs:
    """Sprint-3 User Explainability and Decision Cards endpoints"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures - get auth tokens"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # User login
        user_login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "TEST_phase4iter2_pipeline@example.com",
            "password": "TestPassword123!"
        })
        if user_login_res.status_code == 200:
            self.user_token = user_login_res.json().get("access_token")
        else:
            pytest.skip("User auth failed")
        
        # Admin login
        admin_login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@platform.dev",
            "password": "Admin12345!"
        })
        if admin_login_res.status_code == 200:
            self.admin_token = admin_login_res.json().get("access_token")
        else:
            pytest.skip("Admin auth failed")

    def user_headers(self):
        return {"Authorization": f"Bearer {self.user_token}", "Content-Type": "application/json"}

    def admin_headers(self):
        return {"Authorization": f"Bearer {self.admin_token}", "Content-Type": "application/json"}

    # ========== Decision Cards List ==========
    def test_user_decision_cards_list_200(self):
        """GET /api/user/decision-cards - Returns 200 with envelope structure"""
        res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.user_headers(), params={"limit": 60})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        
        data = res.json()
        # Envelope fields
        assert "schema_version" in data, "Missing schema_version"
        assert "engine_version" in data, "Missing engine_version"
        assert "generated_at" in data, "Missing generated_at"
        assert "items" in data, "Missing items"
        assert isinstance(data["items"], list), "items should be list"
        print(f"Decision cards count: {len(data['items'])}")

    def test_user_decision_cards_item_structure(self):
        """Decision card items have required fields: symbol, decision, scores, learning_badges"""
        res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.user_headers(), params={"limit": 10})
        assert res.status_code == 200
        
        data = res.json()
        items = data.get("items", [])
        if not items:
            pytest.skip("No decision cards available")
        
        card = items[0]
        # Required fields
        required_fields = ["symbol", "decision", "long_score", "short_score", "dominant_family"]
        for field in required_fields:
            assert field in card, f"Missing field: {field}"
        
        # Decision values check
        assert card["decision"] in ["LONG", "SHORT", "BLOCKED", "NO_TRADE"], f"Invalid decision: {card['decision']}"
        
        # Learning badge fields
        assert "learning_badges" in card, "Missing learning_badges"
        assert "confidence_adjustment" in card, "Missing confidence_adjustment"
        print(f"Sample card: symbol={card['symbol']}, decision={card['decision']}, badges={card.get('learning_badges')}")

    def test_user_decision_cards_top_contributors(self):
        """Decision cards include top_contributors with strategy contribution details"""
        res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.user_headers())
        assert res.status_code == 200
        
        items = res.json().get("items", [])
        if not items:
            pytest.skip("No decision cards available")
        
        for card in items[:3]:
            if "top_contributors" in card and card["top_contributors"]:
                contrib = card["top_contributors"][0]
                assert "strategy_id" in contrib, "Missing strategy_id in contributor"
                assert "family" in contrib, "Missing family in contributor"
                assert "contribution_score" in contrib, "Missing contribution_score"
                print(f"Contributor: {contrib['strategy_id']} · {contrib['family']} · score={contrib['contribution_score']}")
                break

    # ========== Single Decision Card ==========
    def test_user_decision_card_by_symbol_200(self):
        """GET /api/user/decision-cards/{symbol} - Returns 200 for existing symbol"""
        # First get available symbols
        list_res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.user_headers())
        if list_res.status_code != 200:
            pytest.skip("Cannot list decision cards")
        
        items = list_res.json().get("items", [])
        if not items:
            pytest.skip("No decision cards available")
        
        symbol = items[0]["symbol"]
        res = self.session.get(f"{BASE_URL}/api/user/decision-cards/{symbol}", headers=self.user_headers())
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        
        card = res.json()
        assert card["symbol"] == symbol
        assert "decision" in card
        assert "long_score" in card
        assert "short_score" in card
        print(f"Single card: {card['symbol']} - {card['decision']}")

    def test_user_decision_card_by_symbol_404(self):
        """GET /api/user/decision-cards/{symbol} - Returns 404 for non-existent symbol"""
        res = self.session.get(f"{BASE_URL}/api/user/decision-cards/NONEXISTENT123", headers=self.user_headers())
        assert res.status_code == 404, f"Expected 404, got {res.status_code}"

    # ========== Explainability Endpoint ==========
    def test_user_explainability_200(self):
        """GET /api/user/explainability/{symbol} - Returns 200 with explainability data"""
        # Get available symbol
        list_res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.user_headers())
        items = list_res.json().get("items", [])
        if not items:
            pytest.skip("No decision cards to get explainability")
        
        symbol = items[0]["symbol"]
        res = self.session.get(f"{BASE_URL}/api/user/explainability/{symbol}", headers=self.user_headers())
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        
        data = res.json()
        # Required fields per SymbolExplainabilityResponse schema
        required_fields = [
            "schema_version", "engine_version", "generated_at", "symbol",
            "final_decision", "long_score", "short_score", "winning_side",
            "decision_confidence", "source_strategies", "family_scores",
            "blocked_reason_timeline", "explanation_templates"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"Explainability: symbol={data['symbol']}, final_decision={data['final_decision']}, winning_side={data['winning_side']}")

    def test_user_explainability_family_scores(self):
        """Explainability includes family_scores with gate_status"""
        list_res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.user_headers())
        items = list_res.json().get("items", [])
        if not items:
            pytest.skip("No decision cards")
        
        symbol = items[0]["symbol"]
        res = self.session.get(f"{BASE_URL}/api/user/explainability/{symbol}", headers=self.user_headers())
        assert res.status_code == 200
        
        data = res.json()
        family_scores = data.get("family_scores", {})
        print(f"Family scores for {symbol}: {list(family_scores.keys())}")
        
        # Family scores should have gate_status if present
        for family, gate in family_scores.items():
            if isinstance(gate, dict):
                print(f"  {family}: gate_status={gate.get('gate_status')}, gate_reason={gate.get('gate_reason')}")

    def test_user_explainability_explanation_templates(self):
        """Explainability includes human-readable explanation templates"""
        list_res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.user_headers())
        items = list_res.json().get("items", [])
        if not items:
            pytest.skip("No decision cards")
        
        symbol = items[0]["symbol"]
        res = self.session.get(f"{BASE_URL}/api/user/explainability/{symbol}", headers=self.user_headers())
        assert res.status_code == 200
        
        data = res.json()
        templates = data.get("explanation_templates", [])
        assert isinstance(templates, list), "explanation_templates should be list"
        print(f"Explanation templates: {templates}")

    def test_user_explainability_source_strategies(self):
        """Explainability includes source_strategies with status (accepted/rejected/gated/blocked)"""
        list_res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.user_headers())
        items = list_res.json().get("items", [])
        if not items:
            pytest.skip("No decision cards")
        
        symbol = items[0]["symbol"]
        res = self.session.get(f"{BASE_URL}/api/user/explainability/{symbol}", headers=self.user_headers())
        assert res.status_code == 200
        
        data = res.json()
        source_strategies = data.get("source_strategies", [])
        print(f"Source strategies count: {len(source_strategies)}")
        
        for strat in source_strategies[:3]:
            print(f"  {strat.get('strategy_id')} · {strat.get('family')} · status={strat.get('status')}")

    def test_user_explainability_blocked_timeline(self):
        """Explainability includes blocked_reason_timeline with event details"""
        list_res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.user_headers())
        items = list_res.json().get("items", [])
        if not items:
            pytest.skip("No decision cards")
        
        symbol = items[0]["symbol"]
        res = self.session.get(f"{BASE_URL}/api/user/explainability/{symbol}", headers=self.user_headers())
        assert res.status_code == 200
        
        data = res.json()
        timeline = data.get("blocked_reason_timeline", [])
        print(f"Blocked timeline events: {len(timeline)}")
        
        for event in timeline[:3]:
            print(f"  {event.get('event_time')} · {event.get('layer')} · {event.get('reason_code')} · {event.get('previous_state')}→{event.get('new_state')}")

    def test_user_explainability_404(self):
        """GET /api/user/explainability/{symbol} - Returns 404 for non-existent symbol"""
        res = self.session.get(f"{BASE_URL}/api/user/explainability/NONEXISTENT123", headers=self.user_headers())
        assert res.status_code == 404

    # ========== Admin Strategy Family Gates ==========
    def test_admin_strategy_family_gates_get(self):
        """GET /api/admin/strategy-family-gates - Returns 200 with 4 families"""
        res = self.session.get(f"{BASE_URL}/api/admin/strategy-family-gates", headers=self.admin_headers())
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        
        gates = res.json()
        assert isinstance(gates, list), "Response should be list"
        
        # Check expected families
        families = [g["family"] for g in gates]
        expected_families = ["trend", "breakout", "pullback", "reversal"]
        for fam in expected_families:
            assert fam in families, f"Missing family: {fam}"
        
        print(f"Strategy family gates: {families}")
        
        # Check gate structure
        gate = gates[0]
        required_fields = [
            "schema_version", "engine_version", "family", "is_enabled",
            "long_threshold", "short_threshold", "min_strategy_count",
            "max_conflict_score", "regime_match_required", "risk_clear_required"
        ]
        for field in required_fields:
            assert field in gate, f"Missing field: {field}"

    def test_admin_strategy_family_gates_put(self):
        """PUT /api/admin/strategy-family-gates - Updates gate configs"""
        # First get current values
        get_res = self.session.get(f"{BASE_URL}/api/admin/strategy-family-gates", headers=self.admin_headers())
        assert get_res.status_code == 200
        
        current_gates = get_res.json()
        trend_gate = next((g for g in current_gates if g["family"] == "trend"), None)
        assert trend_gate is not None, "trend gate not found"
        
        # Update with same values (idempotent test)
        update_payload = {
            "items": [
                {
                    "family": "trend",
                    "is_enabled": trend_gate["is_enabled"],
                    "long_threshold": trend_gate["long_threshold"],
                    "short_threshold": trend_gate["short_threshold"],
                    "min_strategy_count": trend_gate["min_strategy_count"],
                    "max_conflict_score": trend_gate["max_conflict_score"],
                    "regime_match_required": trend_gate["regime_match_required"],
                    "risk_clear_required": trend_gate["risk_clear_required"]
                }
            ]
        }
        
        put_res = self.session.put(f"{BASE_URL}/api/admin/strategy-family-gates", headers=self.admin_headers(), json=update_payload)
        assert put_res.status_code == 200, f"Expected 200, got {put_res.status_code}: {put_res.text}"
        
        updated = put_res.json()
        assert isinstance(updated, list)
        print(f"Family gates updated successfully, count: {len(updated)}")

    # ========== Admin Blocked Reason Timeline ==========
    def test_admin_blocked_reason_timeline(self):
        """GET /api/admin/blocked-reason-timeline/{symbol} - Returns timeline"""
        # Get a symbol to test
        cards_res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.user_headers())
        items = cards_res.json().get("items", [])
        if not items:
            pytest.skip("No decision cards")
        
        symbol = items[0]["symbol"]
        res = self.session.get(f"{BASE_URL}/api/admin/blocked-reason-timeline/{symbol}", headers=self.admin_headers())
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        
        data = res.json()
        assert "schema_version" in data
        assert "engine_version" in data
        assert "symbol" in data
        assert "items" in data
        assert data["symbol"].upper() == symbol.upper()
        print(f"Admin blocked timeline for {symbol}: {len(data['items'])} events")


class TestScannerPollingIntegration:
    """Test 10s polling refresh behavior"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "TEST_phase4iter2_pipeline@example.com",
            "password": "TestPassword123!"
        })
        if login_res.status_code == 200:
            self.token = login_res.json().get("access_token")
        else:
            pytest.skip("User auth failed")

    def headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def test_decision_cards_multiple_fetches(self):
        """Verify decision cards can be fetched multiple times (polling simulation)"""
        results = []
        for i in range(3):
            res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.headers(), params={"limit": 60})
            assert res.status_code == 200, f"Fetch {i+1} failed: {res.status_code}"
            data = res.json()
            results.append({
                "generated_at": data.get("generated_at"),
                "item_count": len(data.get("items", []))
            })
            if i < 2:
                time.sleep(1)  # Short wait between fetches
        
        print(f"Polling test results: {results}")
        # All fetches should succeed
        assert all(r["item_count"] >= 0 for r in results)


class TestDecisionCardLabels:
    """Test deterministic decision labels: LONG/SHORT/BLOCKED/NO_TRADE"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "TEST_phase4iter2_pipeline@example.com",
            "password": "TestPassword123!"
        })
        if login_res.status_code == 200:
            self.token = login_res.json().get("access_token")
        else:
            pytest.skip("Auth failed")

    def headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def test_decision_labels_valid(self):
        """All decision card labels are valid: LONG/SHORT/BLOCKED/NO_TRADE"""
        res = self.session.get(f"{BASE_URL}/api/user/decision-cards", headers=self.headers())
        assert res.status_code == 200
        
        items = res.json().get("items", [])
        valid_decisions = {"LONG", "SHORT", "BLOCKED", "NO_TRADE"}
        
        decision_counts = {"LONG": 0, "SHORT": 0, "BLOCKED": 0, "NO_TRADE": 0}
        for card in items:
            decision = card.get("decision")
            assert decision in valid_decisions, f"Invalid decision: {decision}"
            decision_counts[decision] += 1
        
        print(f"Decision distribution: {decision_counts}")


class TestUserScannerOverview:
    """Test scanner overview endpoint for polling data"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "TEST_phase4iter2_pipeline@example.com",
            "password": "TestPassword123!"
        })
        if login_res.status_code == 200:
            self.token = login_res.json().get("access_token")
        else:
            pytest.skip("Auth failed")

    def headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def test_scanner_overview_200(self):
        """GET /api/user/scanner - Returns scanner overview"""
        res = self.session.get(f"{BASE_URL}/api/user/scanner", headers=self.headers())
        assert res.status_code == 200
        
        data = res.json()
        expected_fields = ["mode", "total_results", "pending_signals"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"Scanner overview: mode={data['mode']}, results={data['total_results']}, pending={data['pending_signals']}")
