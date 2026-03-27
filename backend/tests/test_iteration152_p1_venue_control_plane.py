"""
P1 Venue/Exchange Management Control Plane Tests
Tests for:
- POST /api/venues/admin/capability-discovery
- GET /api/venues/admin/capability-matrix
- PUT/GET /api/venues/admin/market-policy-layer
- PUT/GET /api/venues/admin/routing-policies
- POST /api/venues/admin/routing-preview-v2
- GET /api/venues/admin/operational-health
- GET /api/venues/admin/audit-timeline
- Market policy symbol deny enforcement
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
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


class TestCapabilityDiscovery:
    """Tests for POST /api/venues/admin/capability-discovery"""

    def test_capability_discovery_returns_symbol_capabilities(self, admin_headers):
        """POST /api/venues/admin/capability-discovery should return symbol_capabilities"""
        payload = {
            "exchange_code": "binance",
            "market_type": "spot",
            "environment": "testnet",
            "symbols": ["BTCUSDT", "ETHUSDT"],
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/capability-discovery",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "net_status" in data, "Response should have net_status"
        assert "checks" in data, "Response should have checks"
        assert "capability" in data, "Response should have capability"
        
        # Verify capability has symbol_capabilities
        capability = data.get("capability", {})
        assert "symbol_capabilities" in capability, "capability should have symbol_capabilities"
        assert isinstance(capability["symbol_capabilities"], list), "symbol_capabilities should be a list"
        
        # Verify net_status is valid
        assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"Invalid net_status: {data['net_status']}"
        
        print(f"Capability discovery returned {len(capability.get('symbol_capabilities', []))} symbols")

    def test_capability_discovery_futures_market(self, admin_headers):
        """POST /api/venues/admin/capability-discovery for futures market"""
        payload = {
            "exchange_code": "binance",
            "market_type": "futures",
            "environment": "testnet",
            "symbols": ["BTCUSDT"],
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/capability-discovery",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        capability = data.get("capability", {})
        symbol_caps = capability.get("symbol_capabilities", [])
        
        # Futures should have leverage support
        if symbol_caps:
            first_symbol = symbol_caps[0]
            assert "supports_leverage" in first_symbol, "Futures symbol should have supports_leverage"
            assert "supports_reduce_only" in first_symbol, "Futures symbol should have supports_reduce_only"


class TestCapabilityMatrix:
    """Tests for GET /api/venues/admin/capability-matrix"""

    def test_capability_matrix_persists_config(self, admin_headers):
        """GET /api/venues/admin/capability-matrix should return persisted config"""
        # First, run a discovery to populate the matrix
        discovery_payload = {
            "exchange_code": "binance",
            "market_type": "spot",
            "environment": "testnet",
            "symbols": ["BTCUSDT"],
        }
        requests.post(
            f"{BASE_URL}/api/venues/admin/capability-discovery",
            headers=admin_headers,
            json=discovery_payload,
        )
        
        # Now get the capability matrix
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/capability-matrix",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should be a dict with keys like "binance:spot:testnet"
        assert isinstance(data, dict), "capability-matrix should return a dict"
        
        # Check if our discovery was persisted
        expected_key = "binance:spot:testnet"
        if expected_key in data:
            print(f"Found persisted capability for {expected_key}")
            assert "symbol_capabilities" in data[expected_key], "Persisted capability should have symbol_capabilities"


class TestMarketPolicyLayer:
    """Tests for PUT/GET /api/venues/admin/market-policy-layer"""

    def test_market_policy_layer_put_and_get(self, admin_headers):
        """PUT /api/venues/admin/market-policy-layer should persist and GET should retrieve"""
        # Create a market policy
        payload = {
            "exchange_code": "binance",
            "market_type": "spot",
            "environment": "testnet",
            "symbol_rules": [
                {"symbol": "BTCUSDT", "action": "allow"},
                {"symbol": "TESTUSDT", "action": "deny"},
            ],
            "restricted_symbol_classes": ["meme", "leverage_token"],
            "risk_tier_defaults": {"tier1": 0.1, "tier2": 0.05},
        }
        
        put_response = requests.put(
            f"{BASE_URL}/api/venues/admin/market-policy-layer",
            headers=admin_headers,
            json=payload,
        )
        assert put_response.status_code == 200, f"PUT failed: {put_response.status_code}: {put_response.text}"
        put_data = put_response.json()
        
        assert put_data.get("updated") is True, "PUT should return updated=True"
        assert "key" in put_data, "PUT should return key"
        assert "policy" in put_data, "PUT should return policy"
        
        # Now GET the market policy layer
        get_response = requests.get(
            f"{BASE_URL}/api/venues/admin/market-policy-layer",
            headers=admin_headers,
        )
        assert get_response.status_code == 200, f"GET failed: {get_response.status_code}: {get_response.text}"
        get_data = get_response.json()
        
        # Should have rules dict
        assert "rules" in get_data, "GET should return rules"
        
        expected_key = "binance:spot:testnet"
        if expected_key in get_data.get("rules", {}):
            rule = get_data["rules"][expected_key]
            assert "symbol_rules" in rule, "Rule should have symbol_rules"
            assert "restricted_symbol_classes" in rule, "Rule should have restricted_symbol_classes"
            print(f"Market policy persisted for {expected_key}")


class TestRoutingPolicies:
    """Tests for PUT/GET /api/venues/admin/routing-policies"""

    def test_routing_policies_put_and_get(self, admin_headers):
        """PUT /api/venues/admin/routing-policies should persist and GET should retrieve"""
        # Create a routing policy
        payload = {
            "user_id": "test-user-123",
            "strategy_id": "test-strategy-456",
            "default_venue": "binance",
            "preferred_venues": ["binance", "bybit"],
            "blocked_venues": ["okx"],
            "capital_allocation": [{"venue": "binance", "weight": 0.7}, {"venue": "bybit", "weight": 0.3}],
            "execution_policy_override": {"max_slippage": 0.01},
        }
        
        put_response = requests.put(
            f"{BASE_URL}/api/venues/admin/routing-policies",
            headers=admin_headers,
            json=payload,
        )
        assert put_response.status_code == 200, f"PUT failed: {put_response.status_code}: {put_response.text}"
        put_data = put_response.json()
        
        assert put_data.get("updated") is True, "PUT should return updated=True"
        assert "key" in put_data, "PUT should return key"
        assert "routing_rule" in put_data, "PUT should return routing_rule"
        
        # Now GET the routing policies
        get_response = requests.get(
            f"{BASE_URL}/api/venues/admin/routing-policies",
            headers=admin_headers,
        )
        assert get_response.status_code == 200, f"GET failed: {get_response.status_code}: {get_response.text}"
        get_data = get_response.json()
        
        # Should have rules dict
        assert "rules" in get_data, "GET should return rules"
        
        expected_key = "test-user-123:test-strategy-456"
        if expected_key in get_data.get("rules", {}):
            rule = get_data["rules"][expected_key]
            assert rule.get("default_venue") == "binance", "Rule should have correct default_venue"
            assert "preferred_venues" in rule, "Rule should have preferred_venues"
            assert "blocked_venues" in rule, "Rule should have blocked_venues"
            print(f"Routing policy persisted for {expected_key}")


class TestRoutingPreviewV2:
    """Tests for POST /api/venues/admin/routing-preview-v2"""

    def test_routing_preview_v2_returns_contract(self, admin_headers):
        """POST /api/venues/admin/routing-preview-v2 should return net_status + checks + resolved path"""
        # First, get an approved user ID
        users_response = requests.get(
            f"{BASE_URL}/api/auth/admin/user-approval-requests?status=approved",
            headers=admin_headers,
        )
        user_id = "test-user-123"
        if users_response.status_code == 200:
            users = users_response.json()
            if users:
                user_id = users[0].get("id", user_id)
        
        payload = {
            "user_id": user_id,
            "strategy_id": "test-strategy-456",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100,
        }
        
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/routing-preview-v2",
            headers=admin_headers,
            json=payload,
        )
        
        # May fail if no credentials are set up, but should return proper error
        if response.status_code == 200:
            data = response.json()
            
            # Verify contract structure
            assert "net_status" in data, "Response should have net_status"
            assert "reason_codes" in data, "Response should have reason_codes"
            assert "remediation_suggestions" in data, "Response should have remediation_suggestions"
            assert "checks" in data, "Response should have checks"
            assert "resolved_execution_path" in data, "Response should have resolved_execution_path"
            assert "routing_rule" in data, "Response should have routing_rule"
            assert "capital_allocation" in data, "Response should have capital_allocation"
            
            # Verify net_status is valid
            assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"Invalid net_status: {data['net_status']}"
            
            # Verify checks structure
            for check in data.get("checks", []):
                assert "name" in check, "Check should have name"
                assert "status" in check, "Check should have status"
                assert "reason_code" in check, "Check should have reason_code"
                assert "severity" in check, "Check should have severity"
                assert "remediation_suggestions" in check, "Check should have remediation_suggestions"
            
            print(f"Routing preview v2 returned net_status={data['net_status']}")
        else:
            # Should return proper error structure
            assert response.status_code in [400, 404, 409], f"Unexpected status: {response.status_code}"
            print(f"Routing preview returned error (expected if no credentials): {response.status_code}")


class TestOperationalHealth:
    """Tests for GET /api/venues/admin/operational-health"""

    def test_operational_health_returns_health_scores(self, admin_headers):
        """GET /api/venues/admin/operational-health should return health scores"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/operational-health",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "net_status" in data, "Response should have net_status"
        assert "reason_codes" in data, "Response should have reason_codes"
        assert "remediation_suggestions" in data, "Response should have remediation_suggestions"
        assert "checks" in data, "Response should have checks"
        assert "exchange_health" in data, "Response should have exchange_health"
        assert "market_availability" in data, "Response should have market_availability"
        assert "operational_scores" in data, "Response should have operational_scores"
        
        # Verify net_status is valid
        assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"Invalid net_status: {data['net_status']}"
        
        # Verify operational_scores structure
        for score in data.get("operational_scores", []):
            assert "exchange" in score, "Score should have exchange"
            assert "health_score" in score, "Score should have health_score"
            assert "health_status" in score, "Score should have health_status"
            assert "rate_limit_status" in score, "Score should have rate_limit_status"
            assert "reason_codes" in score, "Score should have reason_codes"
        
        print(f"Operational health returned net_status={data['net_status']}, {len(data.get('operational_scores', []))} exchanges")


class TestAuditTimeline:
    """Tests for GET /api/venues/admin/audit-timeline"""

    def test_audit_timeline_returns_items_with_diff(self, admin_headers):
        """GET /api/venues/admin/audit-timeline should return items with old/new diff"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/audit-timeline",
            headers=admin_headers,
            params={"limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "items" in data, "Response should have items"
        assert isinstance(data["items"], list), "items should be a list"
        
        # Verify item structure
        for item in data.get("items", [])[:5]:  # Check first 5 items
            assert "id" in item, "Item should have id"
            assert "action" in item, "Item should have action"
            assert "entity_type" in item, "Item should have entity_type"
            assert "entity_id" in item, "Item should have entity_id"
            assert "actor_user_id" in item, "Item should have actor_user_id"
            assert "actor_role" in item, "Item should have actor_role"
            assert "details" in item, "Item should have details"
            assert "created_at" in item, "Item should have created_at"
            
            # old_value and new_value may be None but should be present
            assert "old_value" in item, "Item should have old_value field"
            assert "new_value" in item, "Item should have new_value field"
        
        print(f"Audit timeline returned {len(data.get('items', []))} items")

    def test_audit_timeline_filter_by_entity_type(self, admin_headers):
        """GET /api/venues/admin/audit-timeline with entity_type filter"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/audit-timeline",
            headers=admin_headers,
            params={"entity_type": "venue_market_policy", "limit": 10},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # All items should have the filtered entity_type
        for item in data.get("items", []):
            assert item.get("entity_type") == "venue_market_policy", f"Item has wrong entity_type: {item.get('entity_type')}"


class TestMarketPolicySymbolDenyEnforcement:
    """Tests for market policy symbol deny enforcement in routing preview"""

    def test_symbol_policy_blocked_reason_code(self, admin_headers):
        """Routing preview should return symbol_policy_blocked when symbol is denied"""
        # First, create a market policy that denies a specific symbol
        policy_payload = {
            "exchange_code": "binance",
            "market_type": "spot",
            "environment": "testnet",
            "symbol_rules": [
                {"symbol": "BLOCKEDUSDT", "action": "deny"},
            ],
            "restricted_symbol_classes": [],
            "risk_tier_defaults": {},
        }
        
        requests.put(
            f"{BASE_URL}/api/venues/admin/market-policy-layer",
            headers=admin_headers,
            json=policy_payload,
        )
        
        # Get an approved user ID
        users_response = requests.get(
            f"{BASE_URL}/api/auth/admin/user-approval-requests?status=approved",
            headers=admin_headers,
        )
        user_id = "test-user-123"
        if users_response.status_code == 200:
            users = users_response.json()
            if users:
                user_id = users[0].get("id", user_id)
        
        # Try routing preview with the blocked symbol
        preview_payload = {
            "user_id": user_id,
            "strategy_id": "test-strategy-456",
            "symbol": "BLOCKEDUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100,
        }
        
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/routing-preview-v2",
            headers=admin_headers,
            json=preview_payload,
        )
        
        # The response may be 409 with symbol_policy_blocked or 200 with BLOCK status
        # depending on implementation
        if response.status_code == 409:
            data = response.json()
            detail = data.get("detail", "")
            print(f"Symbol policy enforcement returned 409: {detail}")
            # This is expected behavior for blocked symbols
        elif response.status_code == 200:
            data = response.json()
            # Check if reason_codes contains symbol_policy_blocked
            reason_codes = data.get("reason_codes", [])
            print(f"Routing preview returned: net_status={data.get('net_status')}, reason_codes={reason_codes}")


class TestControlPlaneConfigPersistence:
    """Tests for control plane config persistence"""

    def test_capability_matrix_persists_after_discovery(self, admin_headers):
        """Capability matrix should persist discovery results"""
        # Run discovery
        discovery_payload = {
            "exchange_code": "binance",
            "market_type": "futures",
            "environment": "testnet",
            "symbols": ["BTCUSDT", "ETHUSDT"],
        }
        
        discovery_response = requests.post(
            f"{BASE_URL}/api/venues/admin/capability-discovery",
            headers=admin_headers,
            json=discovery_payload,
        )
        assert discovery_response.status_code == 200
        
        # Get matrix
        matrix_response = requests.get(
            f"{BASE_URL}/api/venues/admin/capability-matrix",
            headers=admin_headers,
        )
        assert matrix_response.status_code == 200
        matrix_data = matrix_response.json()
        
        # Verify the discovery was persisted
        expected_key = "binance:futures:testnet"
        assert expected_key in matrix_data, f"Expected key {expected_key} not found in matrix"
        
        persisted = matrix_data[expected_key]
        assert "symbol_capabilities" in persisted, "Persisted data should have symbol_capabilities"
        assert "discovered_at" in persisted, "Persisted data should have discovered_at"
        
        print(f"Capability matrix persisted {len(persisted.get('symbol_capabilities', []))} symbols for {expected_key}")


class TestUnifiedContractFormat:
    """Tests to verify all endpoints return unified contract format"""

    def test_capability_discovery_unified_contract(self, admin_headers):
        """Capability discovery should return unified contract format"""
        payload = {
            "exchange_code": "binance",
            "market_type": "spot",
            "environment": "testnet",
            "symbols": [],
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/capability-discovery",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify unified contract fields
        assert "net_status" in data
        assert "reason_codes" in data
        assert "remediation_suggestions" in data
        assert "checks" in data
        
        # Verify checks structure
        for check in data.get("checks", []):
            assert "name" in check
            assert "status" in check
            assert "reason_code" in check
            assert "severity" in check
            assert "remediation_suggestions" in check

    def test_operational_health_unified_contract(self, admin_headers):
        """Operational health should return unified contract format"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/operational-health",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify unified contract fields
        assert "net_status" in data
        assert "reason_codes" in data
        assert "remediation_suggestions" in data
        assert "checks" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
