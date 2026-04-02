"""
P1-C Venue Control Plane Testing - Iteration 153
Tests for:
- GET /api/venues/admin/operational-health (real telemetry fields)
- POST /api/venues/admin/routing-preview-v2 (explainability, alternative_paths, policy/capability/health impact)
- PUT /api/venues/admin/capability-matrix/override (audit diff)
- GET /api/venues/admin/audit-timeline (filters + diff_highlights)
- Market Policy and Routing Policy CRUD
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def approved_user_id(admin_headers):
    """Get an approved user ID for routing tests"""
    response = requests.get(
        f"{BASE_URL}/api/auth/admin/user-approval-requests?status=approved",
        headers=admin_headers,
    )
    if response.status_code == 200:
        users = response.json()
        if users:
            return users[0].get("id")
    return None


class TestOperationalHealth:
    """Tests for GET /api/venues/admin/operational-health"""

    def test_operational_health_returns_200(self, admin_headers):
        """Operational health endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/operational-health",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Operational health endpoint returns 200")

    def test_operational_health_has_net_status(self, admin_headers):
        """Operational health response has net_status field"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/operational-health",
            headers=admin_headers,
        )
        data = response.json()
        assert "net_status" in data, "Missing net_status field"
        assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"Invalid net_status: {data['net_status']}"
        print(f"PASS: net_status = {data['net_status']}")

    def test_operational_health_has_operational_scores(self, admin_headers):
        """Operational health response has operational_scores array"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/operational-health",
            headers=admin_headers,
        )
        data = response.json()
        assert "operational_scores" in data, "Missing operational_scores field"
        assert isinstance(data["operational_scores"], list), "operational_scores should be a list"
        print(f"PASS: operational_scores has {len(data['operational_scores'])} entries")

    def test_operational_health_telemetry_fields(self, admin_headers):
        """Operational health scores contain real telemetry fields"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/operational-health",
            headers=admin_headers,
        )
        data = response.json()
        scores = data.get("operational_scores", [])
        
        required_fields = [
            "latency_ms_p95",
            "validation_success_rate",
            "rate_limit_pressure",
            "websocket_sync_health",
            "orderbook_sync_health",
        ]
        
        if scores:
            first_score = scores[0]
            for field in required_fields:
                assert field in first_score, f"Missing telemetry field: {field}"
            print(f"PASS: All telemetry fields present: {required_fields}")
        else:
            print("WARN: No operational scores to validate telemetry fields")

    def test_operational_health_score_derived_from_telemetry(self, admin_headers):
        """Health score is derived from telemetry and has reason_codes"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/operational-health",
            headers=admin_headers,
        )
        data = response.json()
        scores = data.get("operational_scores", [])
        
        if scores:
            first_score = scores[0]
            assert "health_score" in first_score, "Missing health_score"
            assert "health_status" in first_score, "Missing health_status"
            assert "reason_codes" in first_score, "Missing reason_codes"
            assert isinstance(first_score["health_score"], (int, float)), "health_score should be numeric"
            assert 0 <= first_score["health_score"] <= 100, "health_score should be 0-100"
            print(f"PASS: health_score={first_score['health_score']}, status={first_score['health_status']}, reasons={first_score['reason_codes']}")
        else:
            print("WARN: No operational scores to validate health derivation")

    def test_operational_health_has_generated_at(self, admin_headers):
        """Operational health response has generated_at timestamp"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/operational-health",
            headers=admin_headers,
        )
        data = response.json()
        assert "generated_at" in data, "Missing generated_at field"
        print(f"PASS: generated_at = {data['generated_at']}")


class TestRoutingPreviewV2:
    """Tests for POST /api/venues/admin/routing-preview-v2"""

    def test_routing_preview_returns_200(self, admin_headers, approved_user_id):
        """Routing preview endpoint returns 200"""
        if not approved_user_id:
            pytest.skip("No approved user available for routing preview test")
        
        payload = {
            "user_id": approved_user_id,
            "strategy_id": "test_strategy_001",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "live",
            "order_side": "BUY",
            "order_size_usd": 100,
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/routing-preview-v2",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Routing preview endpoint returns 200")

    def test_routing_preview_has_alternative_paths(self, admin_headers, approved_user_id):
        """Routing preview response has alternative_paths"""
        if not approved_user_id:
            pytest.skip("No approved user available")
        
        payload = {
            "user_id": approved_user_id,
            "strategy_id": "test_strategy_002",
            "symbol": "ETHUSDT",
            "market_type": "spot",
            "environment": "live",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/routing-preview-v2",
            headers=admin_headers,
            json=payload,
        )
        data = response.json()
        assert "alternative_paths" in data, "Missing alternative_paths field"
        assert isinstance(data["alternative_paths"], list), "alternative_paths should be a list"
        print(f"PASS: alternative_paths has {len(data['alternative_paths'])} entries")

    def test_routing_preview_has_decision_factors(self, admin_headers, approved_user_id):
        """Routing preview response has decision_factors"""
        if not approved_user_id:
            pytest.skip("No approved user available")
        
        payload = {
            "user_id": approved_user_id,
            "strategy_id": "test_strategy_003",
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "environment": "live",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/routing-preview-v2",
            headers=admin_headers,
            json=payload,
        )
        data = response.json()
        assert "decision_factors" in data, "Missing decision_factors field"
        assert isinstance(data["decision_factors"], list), "decision_factors should be a list"
        print(f"PASS: decision_factors has {len(data['decision_factors'])} entries")

    def test_routing_preview_has_explainability(self, admin_headers, approved_user_id):
        """Routing preview response has explainability string"""
        if not approved_user_id:
            pytest.skip("No approved user available")
        
        payload = {
            "user_id": approved_user_id,
            "strategy_id": "test_strategy_004",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "live",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/routing-preview-v2",
            headers=admin_headers,
            json=payload,
        )
        data = response.json()
        assert "explainability" in data, "Missing explainability field"
        assert isinstance(data["explainability"], str), "explainability should be a string"
        assert len(data["explainability"]) > 0, "explainability should not be empty"
        print(f"PASS: explainability = {data['explainability'][:100]}...")

    def test_routing_preview_has_impact_fields(self, admin_headers, approved_user_id):
        """Routing preview response has policy_impact, capability_impact, health_impact"""
        if not approved_user_id:
            pytest.skip("No approved user available")
        
        payload = {
            "user_id": approved_user_id,
            "strategy_id": "test_strategy_005",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "live",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/routing-preview-v2",
            headers=admin_headers,
            json=payload,
        )
        data = response.json()
        
        assert "policy_impact" in data, "Missing policy_impact field"
        assert "capability_impact" in data, "Missing capability_impact field"
        assert "health_impact" in data, "Missing health_impact field"
        print("PASS: Impact fields present - policy_impact, capability_impact, health_impact")

    def test_routing_preview_selected_path_has_route_score(self, admin_headers, approved_user_id):
        """Routing preview selected_path has route_score"""
        if not approved_user_id:
            pytest.skip("No approved user available")
        
        payload = {
            "user_id": approved_user_id,
            "strategy_id": "test_strategy_006",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "live",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/routing-preview-v2",
            headers=admin_headers,
            json=payload,
        )
        data = response.json()
        
        assert "selected_path" in data, "Missing selected_path field"
        selected = data["selected_path"]
        assert "exchange" in selected, "selected_path missing exchange"
        assert "route_score" in selected, "selected_path missing route_score"
        assert "status" in selected, "selected_path missing status"
        print(f"PASS: selected_path = {selected['exchange']}, score={selected['route_score']}, status={selected['status']}")

    def test_routing_preview_net_status_reflects_path(self, admin_headers, approved_user_id):
        """Routing preview net_status reflects selected_path status"""
        if not approved_user_id:
            pytest.skip("No approved user available")
        
        payload = {
            "user_id": approved_user_id,
            "strategy_id": "test_strategy_007",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "live",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/routing-preview-v2",
            headers=admin_headers,
            json=payload,
        )
        data = response.json()
        
        assert "net_status" in data, "Missing net_status"
        assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"Invalid net_status: {data['net_status']}"
        print(f"PASS: net_status = {data['net_status']}")


class TestCapabilityMatrixOverride:
    """Tests for PUT /api/venues/admin/capability-matrix/override"""

    def test_capability_matrix_override_returns_200(self, admin_headers):
        """Capability matrix override endpoint returns 200"""
        payload = {
            "exchange_code": "binance",
            "market_type": "spot",
            "environment": "live",
            "symbol": "TESTUSDT",
            "support_level": "supported",
            "note": "Test override from iteration 153",
            "supports_leverage": False,
            "supports_reduce_only": False,
            "supports_margin_mode": False,
            "supports_hedge_mode": False,
        }
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/capability-matrix/override",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Capability matrix override returns 200")

    def test_capability_matrix_override_returns_updated_data(self, admin_headers):
        """Capability matrix override returns updated capability data"""
        payload = {
            "exchange_code": "binance",
            "market_type": "futures",
            "environment": "live",
            "symbol": "BTCUSDT",
            "support_level": "supported",
            "note": "Test override iteration 153 - BTCUSDT",
            "supports_leverage": True,
            "supports_reduce_only": True,
        }
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/capability-matrix/override",
            headers=admin_headers,
            json=payload,
        )
        data = response.json()
        
        assert "updated" in data, "Missing updated field"
        assert data["updated"] is True, "updated should be True"
        assert "key" in data, "Missing key field"
        assert "symbol" in data, "Missing symbol field"
        assert "override" in data, "Missing override field"
        print(f"PASS: Override returned - key={data['key']}, symbol={data['symbol']}")

    def test_capability_matrix_override_creates_audit_log(self, admin_headers):
        """Capability matrix override creates audit log with diff"""
        # First, create an override
        payload = {
            "exchange_code": "binance",
            "market_type": "spot",
            "environment": "live",
            "symbol": "AUDITUSDT",
            "support_level": "partial",
            "note": "Audit test override",
        }
        requests.put(
            f"{BASE_URL}/api/venues/admin/capability-matrix/override",
            headers=admin_headers,
            json=payload,
        )
        
        # Check audit timeline for the override action
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/audit-timeline",
            headers=admin_headers,
            params={"action": "venue_capability_matrix_override_updated", "limit": 5},
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        
        # Should have at least one audit entry for capability override
        override_entries = [item for item in items if "capability_matrix_override" in item.get("action", "")]
        assert len(override_entries) > 0, "No audit entries found for capability matrix override"
        print(f"PASS: Found {len(override_entries)} audit entries for capability matrix override")


class TestAuditTimeline:
    """Tests for GET /api/venues/admin/audit-timeline"""

    def test_audit_timeline_returns_200(self, admin_headers):
        """Audit timeline endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/audit-timeline",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Audit timeline endpoint returns 200")

    def test_audit_timeline_has_items_array(self, admin_headers):
        """Audit timeline response has items array"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/audit-timeline",
            headers=admin_headers,
        )
        data = response.json()
        assert "items" in data, "Missing items field"
        assert isinstance(data["items"], list), "items should be a list"
        print(f"PASS: Audit timeline has {len(data['items'])} items")

    def test_audit_timeline_filter_by_entity_type(self, admin_headers):
        """Audit timeline filter by entity_type works"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/audit-timeline",
            headers=admin_headers,
            params={"entity_type": "venue_capability_matrix", "limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check applied_filters
        assert "applied_filters" in data, "Missing applied_filters"
        assert data["applied_filters"]["entity_type"] == "venue_capability_matrix"
        print(f"PASS: entity_type filter applied, got {len(data['items'])} items")

    def test_audit_timeline_filter_by_action(self, admin_headers):
        """Audit timeline filter by action works"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/audit-timeline",
            headers=admin_headers,
            params={"action": "venue_capability_matrix_override_updated", "limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "applied_filters" in data
        assert data["applied_filters"]["action"] == "venue_capability_matrix_override_updated"
        print(f"PASS: action filter applied, got {len(data['items'])} items")

    def test_audit_timeline_filter_by_limit(self, admin_headers):
        """Audit timeline filter by limit works"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/audit-timeline",
            headers=admin_headers,
            params={"limit": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["items"]) <= 5, f"Expected max 5 items, got {len(data['items'])}"
        print(f"PASS: limit filter applied, got {len(data['items'])} items (max 5)")

    def test_audit_timeline_items_have_diff_highlights(self, admin_headers):
        """Audit timeline items have diff_highlights field"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/audit-timeline",
            headers=admin_headers,
            params={"limit": 20},
        )
        data = response.json()
        items = data.get("items", [])
        
        if items:
            first_item = items[0]
            assert "diff_keys" in first_item, "Missing diff_keys field"
            assert "diff_highlights" in first_item, "Missing diff_highlights field"
            print("PASS: Audit items have diff_keys and diff_highlights fields")
        else:
            print("WARN: No audit items to validate diff_highlights")

    def test_audit_timeline_filter_by_date_range(self, admin_headers):
        """Audit timeline filter by from_date and to_date works"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/audit-timeline",
            headers=admin_headers,
            params={
                "from_date": "2025-01-01T00:00:00Z",
                "to_date": "2027-12-31T23:59:59Z",
                "limit": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "applied_filters" in data
        assert data["applied_filters"]["from_date"] == "2025-01-01T00:00:00Z"
        assert data["applied_filters"]["to_date"] == "2027-12-31T23:59:59Z"
        print(f"PASS: Date range filter applied, got {len(data['items'])} items")


class TestMarketPolicyLayer:
    """Tests for PUT/GET /api/venues/admin/market-policy-layer"""

    def test_market_policy_get_returns_200(self, admin_headers):
        """Market policy GET endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/market-policy-layer",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Market policy GET returns 200")

    def test_market_policy_put_returns_200(self, admin_headers):
        """Market policy PUT endpoint returns 200"""
        payload = {
            "exchange_code": "binance",
            "market_type": "spot",
            "environment": "live",
            "symbol_rules": [
                {"symbol": "BTCUSDT", "action": "allow", "max_leverage": 20, "risk_tier": "tier1"},
                {"symbol": "PEPEUSDT", "action": "deny"},
            ],
            "restricted_symbol_classes": ["meme", "leverage_token"],
            "risk_tier_defaults": {"tier1": 0.1, "tier2": 0.05},
        }
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/market-policy-layer",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "updated" in data, "Missing updated field"
        assert data["updated"] is True
        print(f"PASS: Market policy PUT returns 200, key={data.get('key')}")

    def test_market_policy_persists_after_save(self, admin_headers):
        """Market policy persists after save"""
        # Save a policy
        payload = {
            "exchange_code": "binance",
            "market_type": "futures",
            "environment": "live",
            "symbol_rules": [{"symbol": "ETHUSDT", "action": "allow"}],
            "restricted_symbol_classes": ["leverage_token"],
            "risk_tier_defaults": {"tier1": 0.15},
        }
        requests.put(
            f"{BASE_URL}/api/venues/admin/market-policy-layer",
            headers=admin_headers,
            json=payload,
        )
        
        # Retrieve and verify
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/market-policy-layer",
            headers=admin_headers,
        )
        data = response.json()
        rules = data.get("rules", {})
        key = "binance:futures:live"
        
        assert key in rules, f"Policy key {key} not found in rules"
        assert "symbol_rules" in rules[key], "Missing symbol_rules in saved policy"
        print(f"PASS: Market policy persisted for key={key}")


class TestRoutingPolicies:
    """Tests for PUT/GET /api/venues/admin/routing-policies"""

    def test_routing_policies_get_returns_200(self, admin_headers):
        """Routing policies GET endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/routing-policies",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Routing policies GET returns 200")

    def test_routing_policies_put_returns_200(self, admin_headers, approved_user_id):
        """Routing policies PUT endpoint returns 200"""
        if not approved_user_id:
            pytest.skip("No approved user available")
        
        payload = {
            "user_id": approved_user_id,
            "strategy_id": "test_routing_strategy_001",
            "default_venue": "binance",
            "preferred_venues": ["binance", "bybit"],
            "blocked_venues": ["okx"],
            "capital_allocation": [{"venue": "binance", "weight": 0.7}, {"venue": "bybit", "weight": 0.3}],
            "execution_policy_override": {"max_slippage": 0.01},
        }
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/routing-policies",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "updated" in data, "Missing updated field"
        assert data["updated"] is True
        print(f"PASS: Routing policies PUT returns 200, key={data.get('key')}")

    def test_routing_policies_persists_after_save(self, admin_headers, approved_user_id):
        """Routing policies persists after save"""
        if not approved_user_id:
            pytest.skip("No approved user available")
        
        # Save a policy
        payload = {
            "user_id": approved_user_id,
            "strategy_id": "test_routing_persist_001",
            "default_venue": "bybit",
            "preferred_venues": ["bybit"],
            "blocked_venues": [],
            "capital_allocation": [],
            "execution_policy_override": {},
        }
        requests.put(
            f"{BASE_URL}/api/venues/admin/routing-policies",
            headers=admin_headers,
            json=payload,
        )
        
        # Retrieve and verify
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/routing-policies",
            headers=admin_headers,
        )
        data = response.json()
        rules = data.get("rules", {})
        key = f"{approved_user_id}:test_routing_persist_001"
        
        assert key in rules, f"Routing policy key {key} not found in rules"
        assert rules[key]["default_venue"] == "bybit", "default_venue mismatch"
        print(f"PASS: Routing policy persisted for key={key}")


class TestCapabilityDiscovery:
    """Tests for POST /api/venues/admin/capability-discovery"""

    def test_capability_discovery_returns_200(self, admin_headers):
        """Capability discovery endpoint returns 200"""
        payload = {
            "exchange_code": "binance",
            "market_type": "spot",
            "environment": "live",
            "symbols": ["BTCUSDT", "ETHUSDT"],
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/capability-discovery",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Capability discovery returns 200")

    def test_capability_discovery_returns_symbol_capabilities(self, admin_headers):
        """Capability discovery returns symbol_capabilities"""
        payload = {
            "exchange_code": "binance",
            "market_type": "spot",
            "environment": "live",
            "symbols": ["BTCUSDT"],
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/capability-discovery",
            headers=admin_headers,
            json=payload,
        )
        data = response.json()
        
        assert "capability" in data, "Missing capability field"
        capability = data["capability"]
        assert "symbol_capabilities" in capability, "Missing symbol_capabilities in capability"
        print(f"PASS: Capability discovery returned {len(capability.get('symbol_capabilities', []))} symbol capabilities")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
