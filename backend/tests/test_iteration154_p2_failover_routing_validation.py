"""
P2 Iteration Testing: Failover+Redundancy, Deterministic Multi-venue Routing Engine, Validation Engine

Tests cover:
- PUT /api/venues/admin/failover-policies: primary/secondary/fallback_chain kaydediliyor mu
- POST /api/venues/admin/failover/manual-override: force route ve force disable çalışıyor mu
- GET /api/venues/admin/failover-policies ve /api/venues/admin/failover-state: runtime_state + transition_logs + routing_decision_logs dönüyor mu
- POST /api/venues/admin/routing-preview-v2 deterministic route output veriyor mu (aynı input aynı selected_venue)
- routing-preview-v2 output alanları: selected_venue, fallback_chain, decision_factors, reject_reason, failover_transition_logs, routing_decision_log, validation_report
- routing skor girdileri (health/capability/policy/latency/rate-limit/allocation) karar faktörlerinde görünür mü
- validation sonucu BLOCK ise routing net_status BLOCK oluyor mu (consistency check)
- POST /api/venues/admin/execution-validation standardized report döndürüyor mu: checks, net_status, reason_codes, validation_report
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"

TEST_EMAIL = "canary.admin@platform.local"
TEST_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in auth response")
    return token


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


@pytest.fixture(scope="module")
def test_user_id(api_client):
    """Get a test user ID from approved users"""
    response = api_client.get(f"{BASE_URL}/api/auth/admin/user-approval-requests?status=approved", timeout=30)
    if response.status_code != 200:
        pytest.skip("Could not fetch approved users")
    users = response.json()
    if not users:
        pytest.skip("No approved users found")
    return users[0].get("id")


class TestFailoverPoliciesPUT:
    """PUT /api/venues/admin/failover-policies: primary/secondary/fallback_chain kaydediliyor mu"""

    def test_failover_policy_upsert_returns_200(self, api_client, test_user_id):
        """Test that failover policy upsert returns 200"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_strategy_p2",
            "market_type": "spot",
            "environment": "testnet",
            "primary_venue": "binance",
            "secondary_venue": "bybit",
            "fallback_chain": ["okx", "kucoin"],
            "auto_reroute_enabled": True,
            "auto_trigger_thresholds": {
                "latency_ms": 1200,
                "error_rate_pct": 20,
                "validation_failure_pct": 25
            },
            "manual_override": {
                "force_route": None,
                "force_disable": [],
                "reason": None
            }
        }
        response = api_client.put(f"{BASE_URL}/api/venues/admin/failover-policies", json=payload, timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_failover_policy_returns_updated_true(self, api_client, test_user_id):
        """Test that failover policy response contains updated=True"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_strategy_p2",
            "market_type": "spot",
            "environment": "testnet",
            "primary_venue": "binance",
            "secondary_venue": "bybit",
            "fallback_chain": ["okx"],
            "auto_reroute_enabled": True,
            "auto_trigger_thresholds": {
                "latency_ms": 1200,
                "error_rate_pct": 20,
                "validation_failure_pct": 25
            }
        }
        response = api_client.put(f"{BASE_URL}/api/venues/admin/failover-policies", json=payload, timeout=30)
        data = response.json()
        assert data.get("updated") is True, "Expected updated=True in response"

    def test_failover_policy_returns_failover_rule(self, api_client, test_user_id):
        """Test that failover policy response contains failover_rule with primary/secondary/fallback_chain"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_strategy_p2_rule",
            "market_type": "futures",
            "environment": "testnet",
            "primary_venue": "binance",
            "secondary_venue": "bybit",
            "fallback_chain": ["okx", "kucoin"],
            "auto_reroute_enabled": True,
            "auto_trigger_thresholds": {
                "latency_ms": 1000,
                "error_rate_pct": 15,
                "validation_failure_pct": 20
            }
        }
        response = api_client.put(f"{BASE_URL}/api/venues/admin/failover-policies", json=payload, timeout=30)
        data = response.json()
        
        failover_rule = data.get("failover_rule")
        assert failover_rule is not None, "Expected failover_rule in response"
        assert failover_rule.get("primary_venue") == "binance", "Expected primary_venue=binance"
        assert failover_rule.get("secondary_venue") == "bybit", "Expected secondary_venue=bybit"
        assert "okx" in failover_rule.get("fallback_chain", []), "Expected okx in fallback_chain"

    def test_failover_policy_returns_failover_state(self, api_client, test_user_id):
        """Test that failover policy response contains failover_state"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_strategy_p2_state",
            "market_type": "spot",
            "environment": "testnet",
            "primary_venue": "binance",
            "secondary_venue": "bybit",
            "fallback_chain": [],
            "auto_reroute_enabled": True,
            "auto_trigger_thresholds": {
                "latency_ms": 1200,
                "error_rate_pct": 20,
                "validation_failure_pct": 25
            }
        }
        response = api_client.put(f"{BASE_URL}/api/venues/admin/failover-policies", json=payload, timeout=30)
        data = response.json()
        
        failover_state = data.get("failover_state")
        assert failover_state is not None, "Expected failover_state in response"
        assert "active_venue" in failover_state, "Expected active_venue in failover_state"


class TestFailoverManualOverridePOST:
    """POST /api/venues/admin/failover/manual-override: force route ve force disable çalışıyor mu"""

    def test_manual_override_force_route_works(self, api_client, test_user_id):
        """Test that manual override force_route works"""
        # First create a failover policy
        setup_payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_manual_override",
            "market_type": "spot",
            "environment": "testnet",
            "primary_venue": "binance",
            "secondary_venue": "bybit",
            "fallback_chain": ["okx"],
            "auto_reroute_enabled": True,
            "auto_trigger_thresholds": {
                "latency_ms": 1200,
                "error_rate_pct": 20,
                "validation_failure_pct": 25
            }
        }
        api_client.put(f"{BASE_URL}/api/venues/admin/failover-policies", json=setup_payload, timeout=30)

        # Apply manual override with force_route
        override_payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_manual_override",
            "market_type": "spot",
            "environment": "testnet",
            "force_route": "bybit",
            "force_disable": [],
            "reason": "Testing force route",
            "clear_override": False
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/failover/manual-override", json=override_payload, timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("updated") is True, "Expected updated=True"
        manual_override = data.get("manual_override")
        assert manual_override is not None, "Expected manual_override in response"
        assert manual_override.get("force_route") == "bybit", "Expected force_route=bybit"

    def test_manual_override_force_disable_works(self, api_client, test_user_id):
        """Test that manual override force_disable works"""
        # First create a failover policy
        setup_payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_manual_disable",
            "market_type": "spot",
            "environment": "testnet",
            "primary_venue": "binance",
            "secondary_venue": "bybit",
            "fallback_chain": ["okx"],
            "auto_reroute_enabled": True,
            "auto_trigger_thresholds": {
                "latency_ms": 1200,
                "error_rate_pct": 20,
                "validation_failure_pct": 25
            }
        }
        api_client.put(f"{BASE_URL}/api/venues/admin/failover-policies", json=setup_payload, timeout=30)

        # Apply manual override with force_disable
        override_payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_manual_disable",
            "market_type": "spot",
            "environment": "testnet",
            "force_route": None,
            "force_disable": ["okx", "kucoin"],
            "reason": "Testing force disable",
            "clear_override": False
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/failover/manual-override", json=override_payload, timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        manual_override = data.get("manual_override")
        assert manual_override is not None, "Expected manual_override in response"
        assert "okx" in manual_override.get("force_disable", []), "Expected okx in force_disable"

    def test_manual_override_clear_works(self, api_client, test_user_id):
        """Test that manual override clear_override works"""
        # First create a failover policy with override
        setup_payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_manual_clear",
            "market_type": "spot",
            "environment": "testnet",
            "primary_venue": "binance",
            "secondary_venue": "bybit",
            "fallback_chain": [],
            "auto_reroute_enabled": True,
            "auto_trigger_thresholds": {
                "latency_ms": 1200,
                "error_rate_pct": 20,
                "validation_failure_pct": 25
            },
            "manual_override": {
                "force_route": "bybit",
                "force_disable": ["okx"],
                "reason": "Initial override"
            }
        }
        api_client.put(f"{BASE_URL}/api/venues/admin/failover-policies", json=setup_payload, timeout=30)

        # Clear the override
        clear_payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_manual_clear",
            "market_type": "spot",
            "environment": "testnet",
            "clear_override": True
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/failover/manual-override", json=clear_payload, timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        manual_override = data.get("manual_override")
        assert manual_override is not None, "Expected manual_override in response"
        assert manual_override.get("force_route") is None, "Expected force_route=None after clear"
        assert manual_override.get("force_disable") == [], "Expected force_disable=[] after clear"


class TestFailoverPoliciesGET:
    """GET /api/venues/admin/failover-policies ve /api/venues/admin/failover-state: runtime_state + transition_logs + routing_decision_logs dönüyor mu"""

    def test_failover_policies_get_returns_200(self, api_client):
        """Test that GET failover-policies returns 200"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/failover-policies", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_failover_policies_get_returns_rules(self, api_client):
        """Test that GET failover-policies returns rules dict"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/failover-policies", timeout=30)
        data = response.json()
        assert "rules" in data, "Expected rules in response"
        assert isinstance(data["rules"], dict), "Expected rules to be a dict"

    def test_failover_policies_get_returns_runtime_state(self, api_client):
        """Test that GET failover-policies returns runtime_state"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/failover-policies", timeout=30)
        data = response.json()
        assert "runtime_state" in data, "Expected runtime_state in response"

    def test_failover_policies_get_returns_transition_logs(self, api_client):
        """Test that GET failover-policies returns transition_logs"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/failover-policies", timeout=30)
        data = response.json()
        assert "transition_logs" in data, "Expected transition_logs in response"
        assert isinstance(data["transition_logs"], list), "Expected transition_logs to be a list"

    def test_failover_policies_get_returns_routing_decision_logs(self, api_client):
        """Test that GET failover-policies returns routing_decision_logs"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/failover-policies", timeout=30)
        data = response.json()
        assert "routing_decision_logs" in data, "Expected routing_decision_logs in response"
        assert isinstance(data["routing_decision_logs"], list), "Expected routing_decision_logs to be a list"

    def test_failover_state_get_returns_200(self, api_client, test_user_id):
        """Test that GET failover-state returns 200 for existing policy"""
        # First create a failover policy
        setup_payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_failover_state_get",
            "market_type": "spot",
            "environment": "testnet",
            "primary_venue": "binance",
            "secondary_venue": "bybit",
            "fallback_chain": [],
            "auto_reroute_enabled": True,
            "auto_trigger_thresholds": {
                "latency_ms": 1200,
                "error_rate_pct": 20,
                "validation_failure_pct": 25
            }
        }
        api_client.put(f"{BASE_URL}/api/venues/admin/failover-policies", json=setup_payload, timeout=30)

        # Get failover state
        params = {
            "user_id": test_user_id,
            "strategy_id": "TEST_failover_state_get",
            "market_type": "spot",
            "environment": "testnet"
        }
        response = api_client.get(f"{BASE_URL}/api/venues/admin/failover-state", params=params, timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_failover_state_get_returns_computed_state(self, api_client, test_user_id):
        """Test that GET failover-state returns computed_state"""
        params = {
            "user_id": test_user_id,
            "strategy_id": "TEST_failover_state_get",
            "market_type": "spot",
            "environment": "testnet"
        }
        response = api_client.get(f"{BASE_URL}/api/venues/admin/failover-state", params=params, timeout=30)
        if response.status_code == 404:
            pytest.skip("Failover policy not found")
        data = response.json()
        assert "computed_state" in data, "Expected computed_state in response"
        assert "active_venue" in data.get("computed_state", {}), "Expected active_venue in computed_state"


class TestRoutingPreviewV2:
    """POST /api/venues/admin/routing-preview-v2 deterministic route output veriyor mu"""

    def test_routing_preview_v2_returns_200(self, api_client, test_user_id):
        """Test that routing-preview-v2 returns 200"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_routing_preview",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_routing_preview_v2_returns_selected_venue(self, api_client, test_user_id):
        """Test that routing-preview-v2 returns selected_venue"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_routing_preview",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        assert "selected_venue" in data, "Expected selected_venue in response"
        assert data["selected_venue"] is not None, "Expected selected_venue to be non-null"

    def test_routing_preview_v2_returns_fallback_chain(self, api_client, test_user_id):
        """Test that routing-preview-v2 returns fallback_chain"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_routing_preview",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        assert "fallback_chain" in data, "Expected fallback_chain in response"
        assert isinstance(data["fallback_chain"], list), "Expected fallback_chain to be a list"

    def test_routing_preview_v2_returns_decision_factors(self, api_client, test_user_id):
        """Test that routing-preview-v2 returns decision_factors"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_routing_preview",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        assert "decision_factors" in data, "Expected decision_factors in response"
        assert isinstance(data["decision_factors"], list), "Expected decision_factors to be a list"

    def test_routing_preview_v2_returns_reject_reason(self, api_client, test_user_id):
        """Test that routing-preview-v2 returns reject_reason field"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_routing_preview",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        assert "reject_reason" in data, "Expected reject_reason in response"

    def test_routing_preview_v2_returns_failover_transition_logs(self, api_client, test_user_id):
        """Test that routing-preview-v2 returns failover_transition_logs"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_routing_preview",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        assert "failover_transition_logs" in data, "Expected failover_transition_logs in response"
        assert isinstance(data["failover_transition_logs"], list), "Expected failover_transition_logs to be a list"

    def test_routing_preview_v2_returns_routing_decision_log(self, api_client, test_user_id):
        """Test that routing-preview-v2 returns routing_decision_log"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_routing_preview",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        assert "routing_decision_log" in data, "Expected routing_decision_log in response"
        assert data["routing_decision_log"] is not None, "Expected routing_decision_log to be non-null"
        assert "id" in data["routing_decision_log"], "Expected id in routing_decision_log"
        assert "created_at" in data["routing_decision_log"], "Expected created_at in routing_decision_log"

    def test_routing_preview_v2_returns_validation_report(self, api_client, test_user_id):
        """Test that routing-preview-v2 returns validation_report"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_routing_preview",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        assert "validation_report" in data, "Expected validation_report in response"
        validation_report = data["validation_report"]
        assert "net_status" in validation_report, "Expected net_status in validation_report"
        assert "reason_codes" in validation_report, "Expected reason_codes in validation_report"

    def test_routing_preview_v2_deterministic_output(self, api_client, test_user_id):
        """Test that routing-preview-v2 returns deterministic output (same input = same selected_venue)"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_deterministic",
            "symbol": "ETHUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "SELL",
            "order_size_usd": 50
        }
        
        # Run preview twice
        response1 = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        response2 = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        
        data1 = response1.json()
        data2 = response2.json()
        
        assert data1.get("selected_venue") == data2.get("selected_venue"), \
            f"Expected deterministic output: {data1.get('selected_venue')} != {data2.get('selected_venue')}"


class TestRoutingDecisionFactors:
    """routing skor girdileri (health/capability/policy/latency/rate-limit/allocation) karar faktörlerinde görünür mü"""

    def test_decision_factors_include_health(self, api_client, test_user_id):
        """Test that decision_factors include operational_health factor"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_factors",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        
        decision_factors = data.get("decision_factors", [])
        factor_names = [f.get("name") for f in decision_factors]
        assert "operational_health" in factor_names, f"Expected operational_health in decision_factors: {factor_names}"

    def test_decision_factors_include_capability(self, api_client, test_user_id):
        """Test that decision_factors include capability factor"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_factors",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        
        decision_factors = data.get("decision_factors", [])
        factor_names = [f.get("name") for f in decision_factors]
        assert "capability" in factor_names, f"Expected capability in decision_factors: {factor_names}"

    def test_decision_factors_include_market_policy(self, api_client, test_user_id):
        """Test that decision_factors include market_policy factor"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_factors",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        
        decision_factors = data.get("decision_factors", [])
        factor_names = [f.get("name") for f in decision_factors]
        assert "market_policy" in factor_names, f"Expected market_policy in decision_factors: {factor_names}"

    def test_decision_factors_include_allocation_state(self, api_client, test_user_id):
        """Test that decision_factors include allocation_state factor"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_factors",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        
        decision_factors = data.get("decision_factors", [])
        factor_names = [f.get("name") for f in decision_factors]
        assert "allocation_state" in factor_names, f"Expected allocation_state in decision_factors: {factor_names}"

    def test_decision_factors_have_status_and_impact(self, api_client, test_user_id):
        """Test that decision_factors have status and impact fields"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_factors",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        
        decision_factors = data.get("decision_factors", [])
        for factor in decision_factors:
            assert "name" in factor, f"Expected name in factor: {factor}"
            assert "status" in factor, f"Expected status in factor: {factor}"
            assert "impact" in factor, f"Expected impact in factor: {factor}"
            assert "detail" in factor, f"Expected detail in factor: {factor}"


class TestValidationConsistency:
    """validation sonucu BLOCK ise routing net_status BLOCK oluyor mu (consistency check)"""

    def test_routing_preview_has_net_status(self, api_client, test_user_id):
        """Test that routing-preview-v2 returns net_status"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_consistency",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        
        assert "net_status" in data, "Expected net_status in response"
        assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"Expected valid net_status, got {data['net_status']}"

    def test_routing_preview_validation_report_consistency(self, api_client, test_user_id):
        """Test that validation_report net_status is consistent with routing net_status when BLOCK"""
        payload = {
            "user_id": test_user_id,
            "strategy_id": "TEST_consistency",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "environment": "testnet",
            "order_side": "BUY",
            "order_size_usd": 100
        }
        response = api_client.post(f"{BASE_URL}/api/venues/admin/routing-preview-v2", json=payload, timeout=30)
        data = response.json()
        
        validation_report = data.get("validation_report", {})
        validation_net_status = validation_report.get("net_status")
        routing_net_status = data.get("net_status")
        
        # If validation is BLOCK, routing should also be BLOCK
        if validation_net_status == "BLOCK":
            assert routing_net_status == "BLOCK", \
                f"Expected routing net_status=BLOCK when validation is BLOCK, got {routing_net_status}"


class TestExecutionValidation:
    """POST /api/venues/admin/execution-validation standardized report döndürüyor mu"""

    def test_execution_validation_returns_200(self, api_client):
        """Test that execution-validation returns 200"""
        response = api_client.post(f"{BASE_URL}/api/venues/admin/execution-validation", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_execution_validation_returns_net_status(self, api_client):
        """Test that execution-validation returns net_status"""
        response = api_client.post(f"{BASE_URL}/api/venues/admin/execution-validation", timeout=30)
        data = response.json()
        assert "net_status" in data, "Expected net_status in response"
        assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"Expected valid net_status, got {data['net_status']}"

    def test_execution_validation_returns_reason_codes(self, api_client):
        """Test that execution-validation returns reason_codes"""
        response = api_client.post(f"{BASE_URL}/api/venues/admin/execution-validation", timeout=30)
        data = response.json()
        assert "reason_codes" in data, "Expected reason_codes in response"
        assert isinstance(data["reason_codes"], list), "Expected reason_codes to be a list"

    def test_execution_validation_returns_checks(self, api_client):
        """Test that execution-validation returns checks array"""
        response = api_client.post(f"{BASE_URL}/api/venues/admin/execution-validation", timeout=30)
        data = response.json()
        assert "checks" in data, "Expected checks in response"
        assert isinstance(data["checks"], list), "Expected checks to be a list"
        
        # Verify check structure
        for check in data["checks"]:
            assert "name" in check, f"Expected name in check: {check}"
            assert "status" in check, f"Expected status in check: {check}"
            assert "reason_code" in check, f"Expected reason_code in check: {check}"

    def test_execution_validation_returns_validation_report(self, api_client):
        """Test that execution-validation returns validation_report"""
        response = api_client.post(f"{BASE_URL}/api/venues/admin/execution-validation", timeout=30)
        data = response.json()
        assert "validation_report" in data, "Expected validation_report in response"
        
        validation_report = data["validation_report"]
        assert "net_status" in validation_report, "Expected net_status in validation_report"
        assert "checks" in validation_report, "Expected checks in validation_report"

    def test_execution_validation_checks_have_required_fields(self, api_client):
        """Test that execution-validation checks have required fields"""
        response = api_client.post(f"{BASE_URL}/api/venues/admin/execution-validation", timeout=30)
        data = response.json()
        
        checks = data.get("checks", [])
        expected_check_names = [
            "real_balance_fetch",
            "permission_matrix_test",
            "venue_capability_runtime_test",
            "dry_run_execution_simulation",
            "test_order_cancel_retry",
            "rejection_classification"
        ]
        
        check_names = [c.get("name") for c in checks]
        for expected_name in expected_check_names:
            assert expected_name in check_names, f"Expected {expected_name} in checks: {check_names}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
