"""
Iteration 95 - Sprint-3 Explainability + Sprint-4 Learning + Scanner Symbol Persistence

Features to test:
1. Decision Cards: symbol, decision, confidence, long/short score, dominant family, top contributors, 
   entry zone, stop, tp1/tp2, invalidation, blocked reason, cooldown, risk state, updated_at
2. DecisionCard -> Explainability Drawer: source strategies, family gate score/threshold/status/reason, blocked timeline reason_detail
3. Dashboard decision card section with 10s refresh label
4. DecisionCard Symbol Detail button -> /user/symbol/:symbol route
5. Scanner symbol persistence: GET/PUT /api/user/scanner/symbol-selection
6. Admin Learning Panel: strategy memory (rolling_quality_score, decay_adjusted_score, quality_degradation_flag, recommendation),
   guardrails panel, events table
7. GET /api/admin/learning/events endpoint
8. GET /api/admin/learning/overview: guardrails + events fields
9. POST /api/admin/learning/recommendations/{id}/apply: new recommendation types
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def admin_token():
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": os.environ.get("TEST_ADMIN_EMAIL", ""),
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "")
    })
    if resp.status_code == 200:
        return resp.json().get("access_token")
    pytest.skip("Admin auth failed")

@pytest.fixture(scope="module")
def user_token():
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "TEST_phase4iter2_pipeline@example.com",
        "password": "TestPassword123!"
    })
    if resp.status_code == 200:
        return resp.json().get("access_token")
    pytest.skip("User auth failed")


class TestUserScannerSymbolSelection:
    """Scanner symbol persistence: /api/user/scanner/symbol-selection GET/PUT"""

    def test_get_symbol_selection_returns_defaults(self, user_token):
        """GET /api/user/scanner/symbol-selection returns persisted or default selection"""
        resp = requests.get(
            f"{BASE_URL}/api/user/scanner/symbol-selection",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"scanner_id": "default"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "user_id" in data
        assert "scanner_id" in data
        assert "symbol_source" in data
        assert "symbol_selection_mode" in data
        assert "selected_symbols" in data
        assert "saved_at" in data
        print(f"GET symbol-selection OK: source={data['symbol_source']}, mode={data['symbol_selection_mode']}")

    def test_put_symbol_selection_persists(self, user_token):
        """PUT /api/user/scanner/symbol-selection persists and returns updated selection"""
        payload = {
            "scanner_id": "default",
            "symbol_source": "crypto",
            "symbol_selection_mode": "watchlist",
            "selected_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        }
        resp = requests.put(
            f"{BASE_URL}/api/user/scanner/symbol-selection",
            headers={"Authorization": f"Bearer {user_token}"},
            json=payload
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol_source"] == "crypto"
        assert data["symbol_selection_mode"] == "watchlist"
        assert "BTCUSDT" in data["selected_symbols"]
        assert "ETHUSDT" in data["selected_symbols"]
        assert "SOLUSDT" in data["selected_symbols"]
        assert data["saved_at"] is not None
        print(f"PUT symbol-selection OK: saved_at={data['saved_at']}")

    def test_get_symbol_selection_after_persist(self, user_token):
        """GET returns previously persisted selection"""
        resp = requests.get(
            f"{BASE_URL}/api/user/scanner/symbol-selection",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"scanner_id": "default"}
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should reflect persisted values from previous test
        assert data["symbol_selection_mode"] == "watchlist"
        assert "BTCUSDT" in data["selected_symbols"]
        print("GET after persist OK: selection matches persisted values")


class TestUserDecisionCards:
    """Decision Cards: /api/user/decision-cards"""

    def test_get_decision_cards_list(self, user_token):
        """GET /api/user/decision-cards returns list with expected fields"""
        resp = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 20}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "schema_version" in data
        assert "engine_version" in data
        assert "generated_at" in data
        assert "items" in data
        print(f"GET decision-cards OK: {len(data['items'])} items")
        
        # If items exist, verify card fields
        if data["items"]:
            card = data["items"][0]
            required_fields = ["symbol", "decision", "confidence", "long_score", "short_score", 
                              "dominant_family", "top_contributors", "entry_zone", "stop_loss",
                              "take_profit_1", "take_profit_2", "invalidation", "blocked_reason",
                              "cooldown_remaining", "risk_block", "risk_state", "updated_at"]
            for field in required_fields:
                assert field in card, f"Missing field: {field}"
            print(f"Card fields verified: symbol={card['symbol']}, decision={card['decision']}")

    def test_get_decision_card_by_symbol(self, user_token):
        """GET /api/user/decision-cards/{symbol} returns single card or 404"""
        # First get a symbol from list
        resp = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 1}
        )
        if resp.status_code == 200 and resp.json().get("items"):
            symbol = resp.json()["items"][0]["symbol"]
            detail_resp = requests.get(
                f"{BASE_URL}/api/user/decision-cards/{symbol}",
                headers={"Authorization": f"Bearer {user_token}"}
            )
            assert detail_resp.status_code == 200
            card = detail_resp.json()
            assert card["symbol"] == symbol
            print(f"GET decision-cards/{symbol} OK")
        else:
            # No cards, verify 404 for non-existent
            resp_404 = requests.get(
                f"{BASE_URL}/api/user/decision-cards/NONEXISTENT999",
                headers={"Authorization": f"Bearer {user_token}"}
            )
            assert resp_404.status_code == 404
            print("GET decision-cards/NONEXISTENT returns 404 OK")


class TestUserExplainability:
    """Explainability endpoint: /api/user/explainability/{symbol}"""

    def test_get_explainability_structure(self, user_token):
        """GET /api/user/explainability/{symbol} returns full explainability data"""
        # Get a symbol first
        cards_resp = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 1}
        )
        if cards_resp.status_code == 200 and cards_resp.json().get("items"):
            symbol = cards_resp.json()["items"][0]["symbol"]
            resp = requests.get(
                f"{BASE_URL}/api/user/explainability/{symbol}",
                headers={"Authorization": f"Bearer {user_token}"}
            )
            assert resp.status_code == 200
            data = resp.json()
            # Verify explainability structure
            assert "schema_version" in data
            assert "final_decision" in data
            assert "long_score" in data
            assert "short_score" in data
            assert "winning_side" in data
            assert "decision_confidence" in data
            assert "source_strategies" in data
            assert "family_scores" in data
            assert "blocked_reason_timeline" in data
            assert "explanation_templates" in data
            print(f"Explainability for {symbol}: decision={data['final_decision']}")
            
            # Verify source_strategies structure if present
            if data["source_strategies"]:
                strat = data["source_strategies"][0]
                assert "strategy_id" in strat
                assert "family" in strat
                assert "contribution_score" in strat
                assert "status" in strat
                print(f"Source strategy verified: {strat['strategy_id']}")
            
            # Verify family_scores structure if present
            if data["family_scores"]:
                family_key = list(data["family_scores"].keys())[0]
                gate = data["family_scores"][family_key]
                assert "gate_status" in gate
                assert "gate_reason" in gate
                print(f"Family gate verified: {family_key} -> {gate['gate_status']}")
        else:
            pytest.skip("No decision cards available to test explainability")


class TestAdminLearningOverview:
    """Admin Learning Panel: /api/admin/learning/overview"""

    def test_get_learning_overview_structure(self, admin_token):
        """GET /api/admin/learning/overview returns guardrails and events"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/learning/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Required top-level fields
        assert "schema_version" in data
        assert "engine_version" in data
        assert "generated_at" in data
        assert "guardrails" in data
        assert "strategy_memory" in data
        assert "family_memory" in data
        assert "recommendations" in data
        assert "events" in data
        
        print(f"Learning overview OK: {len(data['strategy_memory'])} strategies, {len(data['events'])} events")

    def test_learning_overview_guardrails(self, admin_token):
        """Guardrails panel contains required flags"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/learning/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        guardrails = resp.json().get("guardrails", {})
        
        assert "auto_change_forbidden" in guardrails
        assert "admin_approval_required" in guardrails
        assert "audit_log_enabled" in guardrails
        
        print(f"Guardrails verified: auto_change_forbidden={guardrails['auto_change_forbidden']}")

    def test_learning_overview_strategy_memory_fields(self, admin_token):
        """Strategy memory contains rolling_quality_score, decay_adjusted_score, quality_degradation_flag, recommendation"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/learning/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        strategy_memory = resp.json().get("strategy_memory", [])
        
        if strategy_memory:
            strat = strategy_memory[0]
            # Verify new Sprint-4 fields
            assert "rolling_quality_score" in strat or "recent_rolling_score" in strat
            assert "decay_adjusted_score" in strat or "decay_adjusted_quality_score" in strat
            assert "quality_degradation_flag" in strat
            # recommendation can be None
            print(f"Strategy memory fields verified: strategy={strat.get('strategy_id')}, degradation={strat.get('quality_degradation_flag')}")
        else:
            print("No strategy memory data yet (expected if no signals processed)")

    def test_learning_overview_events_structure(self, admin_token):
        """Events list contains expected fields"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/learning/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        events = resp.json().get("events", [])
        
        if events:
            event = events[0]
            required_event_fields = ["event_id", "symbol", "decision", "outcome_label", "pnl_normalized",
                                     "max_favorable_excursion", "max_adverse_excursion", "hold_duration", "created_at"]
            for field in required_event_fields:
                assert field in event, f"Missing event field: {field}"
            print(f"Event fields verified: event_id={event['event_id']}, symbol={event['symbol']}")
        else:
            print("No learning events yet (expected if no signals processed)")


class TestAdminLearningEvents:
    """GET /api/admin/learning/events endpoint"""

    def test_get_learning_events_endpoint(self, admin_token):
        """GET /api/admin/learning/events returns list of events"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/learning/events",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"limit": 50}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "schema_version" in data
        assert "engine_version" in data
        assert "generated_at" in data
        assert "items" in data
        
        print(f"GET /api/admin/learning/events OK: {len(data['items'])} events")


class TestAdminLearningRefresh:
    """POST /api/admin/learning/refresh endpoint"""

    def test_post_learning_refresh(self, admin_token):
        """POST /api/admin/learning/refresh refreshes learning memory"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/learning/refresh",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"days": 30}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "schema_version" in data
        assert "engine_version" in data
        assert "generated_at" in data
        assert "events_count" in data
        
        print(f"Learning refresh OK: {data['events_count']} events processed")


class TestAdminLearningRecommendations:
    """POST /api/admin/learning/recommendations/{id}/apply endpoint"""

    def test_apply_recommendation_not_found(self, admin_token):
        """POST recommendations apply returns 404 for non-existent recommendation"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/learning/recommendations/nonexistent-id-12345/apply",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 404
        print("Apply non-existent recommendation returns 404 OK")

    def test_apply_recommendation_if_available(self, admin_token):
        """POST recommendations apply works for existing recommendation"""
        # First get overview to find a recommendation
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/learning/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if overview_resp.status_code != 200:
            pytest.skip("Cannot get learning overview")
        
        recommendations = overview_resp.json().get("recommendations", [])
        unapplied = [r for r in recommendations if not r.get("is_applied")]
        
        if unapplied:
            rec_id = unapplied[0]["id"]
            resp = requests.post(
                f"{BASE_URL}/api/admin/learning/recommendations/{rec_id}/apply",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            # Should succeed or fail based on strategy existence
            assert resp.status_code in [200, 404]
            if resp.status_code == 200:
                data = resp.json()
                assert data.get("applied") == True
                print(f"Applied recommendation {rec_id} OK")
            else:
                print(f"Recommendation {rec_id} strategy not found (expected if no matching strategy)")
        else:
            print("No unapplied recommendations to test (expected if none generated)")


class TestDashboardDecisionCards:
    """Dashboard includes decision cards section"""

    def test_user_dashboard_endpoint(self, user_token):
        """GET /api/user/dashboard returns dashboard data"""
        resp = requests.get(
            f"{BASE_URL}/api/user/dashboard",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "bot_count" in data
        assert "running_bot_count" in data
        print(f"Dashboard OK: {data['bot_count']} bots")


class TestUserScannerOverview:
    """Scanner overview with mode and results"""

    def test_scanner_overview_endpoint(self, user_token):
        """GET /api/user/scanner returns overview"""
        resp = requests.get(
            f"{BASE_URL}/api/user/scanner",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "mode" in data
        assert "total_results" in data
        print(f"Scanner overview OK: mode={data['mode']}")
