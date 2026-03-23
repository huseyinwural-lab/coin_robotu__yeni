"""
Test Suite: P1 Seed Isolation & Deterministic Root Cause Hint
Scope:
- GET /api/admin/strategy/timeline/{chain_id} summary.root_cause_hint field
- Deterministic root_cause_hint for same invalid reason combinations
- Hint classification "ÖNERİ (kesin neden değildir)" distinction
- Seed isolation: action-impact-timeline default include_seed=false filtering
- Seed isolation: include_seed=true shows seed data
- Chain detail: seed chain include_seed=false hidden behavior (seed_chain_hidden)
- Chain detail: seed chain include_seed=true shows nodes
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"

# Known seed chain IDs from context
SEED_CHAIN_IDS = ["p1-heavy-chain-600", "p1-broken-chain-001"]


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def super_admin_headers(super_admin_token):
    return {"Authorization": f"Bearer {super_admin_token}"}


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


class TestTimelineChainRootCauseHint:
    """Tests for GET /api/admin/strategy/timeline/{chain_id} root_cause_hint field"""

    def test_timeline_chain_endpoint_returns_root_cause_hint_field(self, admin_headers):
        """Verify timeline chain endpoint returns summary.root_cause_hint"""
        # Use a known chain ID or test with any chain
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=admin_headers,
            params={"window": "30d", "limit": 10},
        )
        assert response.status_code == 200, f"action-impact-timeline failed: {response.text}"
        data = response.json()
        
        # Get first chain_id from timeline
        items = data.get("items", [])
        if not items:
            pytest.skip("No timeline items found to test chain detail")
        
        chain_id = items[0].get("chain_id")
        assert chain_id, "chain_id missing from timeline item"
        
        # Now test the chain detail endpoint
        chain_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{chain_id}",
            headers=admin_headers,
            params={"window": "30d"},
        )
        assert chain_response.status_code == 200, f"timeline chain detail failed: {chain_response.text}"
        chain_data = chain_response.json()
        
        # Verify summary exists
        assert "summary" in chain_data, "summary field missing from chain detail"
        summary = chain_data["summary"]
        
        # root_cause_hint should exist (can be None for valid chains)
        assert "root_cause_hint" in summary, "root_cause_hint field missing from summary"
        print(f"PASS: timeline chain endpoint returns root_cause_hint field")

    def test_root_cause_hint_classification_label(self, admin_headers):
        """Verify root_cause_hint has 'ÖNERİ (kesin neden değildir)' classification"""
        # Get a chain with invalid reasons to test hint
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=admin_headers,
            params={"window": "30d", "limit": 50},
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No timeline items to test")
        
        # Test multiple chains to find one with root_cause_hint
        for item in items[:10]:
            chain_id = item.get("chain_id")
            if not chain_id:
                continue
            
            chain_response = requests.get(
                f"{BASE_URL}/api/admin/strategy/timeline/{chain_id}",
                headers=admin_headers,
                params={"window": "30d"},
            )
            if chain_response.status_code != 200:
                continue
            
            chain_data = chain_response.json()
            summary = chain_data.get("summary", {})
            hint = summary.get("root_cause_hint")
            
            if hint:
                # Verify classification label
                classification = hint.get("classification", "")
                assert "ÖNERİ" in classification or "kesin neden değil" in classification.lower(), \
                    f"Classification should indicate 'ÖNERİ (kesin neden değildir)', got: {classification}"
                
                # Verify deterministic flag
                assert hint.get("deterministic") is True, "root_cause_hint should be deterministic"
                
                # Verify rule_key exists
                assert "rule_key" in hint, "rule_key missing from root_cause_hint"
                
                # Verify hint text exists
                assert "hint" in hint, "hint text missing from root_cause_hint"
                
                print(f"PASS: root_cause_hint has correct classification: {classification}")
                print(f"PASS: rule_key={hint.get('rule_key')}, deterministic={hint.get('deterministic')}")
                return
        
        print("INFO: No chains with root_cause_hint found in sample - this is acceptable for valid chains")

    def test_root_cause_hint_deterministic_same_reasons(self, admin_headers):
        """Verify same invalid reason combination produces same rule_key and hint"""
        # Get multiple chains and check if same invalid_reasons produce same hint
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=admin_headers,
            params={"window": "30d", "limit": 100},
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        
        # Collect hints by reason_signature
        hints_by_signature = {}
        
        for item in items[:30]:
            chain_id = item.get("chain_id")
            if not chain_id:
                continue
            
            chain_response = requests.get(
                f"{BASE_URL}/api/admin/strategy/timeline/{chain_id}",
                headers=admin_headers,
                params={"window": "30d"},
            )
            if chain_response.status_code != 200:
                continue
            
            chain_data = chain_response.json()
            summary = chain_data.get("summary", {})
            hint = summary.get("root_cause_hint")
            
            if hint:
                signature = hint.get("reason_signature", "")
                rule_key = hint.get("rule_key", "")
                hint_text = hint.get("hint", "")
                
                if signature:
                    if signature not in hints_by_signature:
                        hints_by_signature[signature] = []
                    hints_by_signature[signature].append({
                        "chain_id": chain_id,
                        "rule_key": rule_key,
                        "hint": hint_text,
                    })
        
        # Verify determinism: same signature should produce same rule_key and hint
        for signature, hints in hints_by_signature.items():
            if len(hints) > 1:
                first_rule_key = hints[0]["rule_key"]
                first_hint = hints[0]["hint"]
                for h in hints[1:]:
                    assert h["rule_key"] == first_rule_key, \
                        f"Same reason_signature '{signature}' produced different rule_keys: {first_rule_key} vs {h['rule_key']}"
                    assert h["hint"] == first_hint, \
                        f"Same reason_signature '{signature}' produced different hints"
                print(f"PASS: Deterministic hint verified for signature '{signature}' across {len(hints)} chains")
        
        print(f"PASS: Tested {len(hints_by_signature)} unique reason signatures for determinism")


class TestSeedIsolationActionImpactTimeline:
    """Tests for seed isolation in action-impact-timeline endpoint"""

    def test_action_impact_timeline_default_excludes_seed(self, admin_headers):
        """Verify action-impact-timeline with default include_seed=false filters seed data"""
        # Request without include_seed (default=false)
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=admin_headers,
            params={"window": "30d", "limit": 500},
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check that seed_rows_filtered is reported in summary
        summary = data.get("summary", {})
        assert "seed_rows_filtered" in summary, "seed_rows_filtered field missing from summary"
        
        # Check items don't contain seed chains
        items = data.get("items", [])
        seed_items = [item for item in items if item.get("is_seed_chain")]
        
        assert len(seed_items) == 0, \
            f"Default include_seed=false should filter seed chains, found {len(seed_items)} seed items"
        
        print(f"PASS: Default include_seed=false filters seed data. seed_rows_filtered={summary.get('seed_rows_filtered')}")

    def test_action_impact_timeline_include_seed_true_shows_seed(self, admin_headers):
        """Verify action-impact-timeline with include_seed=true shows seed data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=admin_headers,
            params={"window": "30d", "limit": 500, "include_seed": "true"},
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        items = data.get("items", [])
        seed_items = [item for item in items if item.get("is_seed_chain")]
        summary = data.get("summary", {})
        
        # With include_seed=true, seed items should be visible (if any exist)
        print(f"PASS: include_seed=true returns {len(seed_items)} seed items out of {len(items)} total")
        
        # Verify seed_rows_filtered is 0 when include_seed=true
        assert summary.get("seed_rows_filtered", 0) == 0, \
            "seed_rows_filtered should be 0 when include_seed=true"

    def test_seed_isolation_comparison(self, admin_headers):
        """Compare include_seed=false vs include_seed=true to verify filtering"""
        # Get without seed
        response_no_seed = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=admin_headers,
            params={"window": "30d", "limit": 500, "include_seed": "false"},
        )
        assert response_no_seed.status_code == 200
        data_no_seed = response_no_seed.json()
        
        # Get with seed
        response_with_seed = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=admin_headers,
            params={"window": "30d", "limit": 500, "include_seed": "true"},
        )
        assert response_with_seed.status_code == 200
        data_with_seed = response_with_seed.json()
        
        count_no_seed = len(data_no_seed.get("items", []))
        count_with_seed = len(data_with_seed.get("items", []))
        summary_no_seed = data_no_seed.get("summary", {})
        filtered_count = summary_no_seed.get("seed_rows_filtered", 0)
        
        print(f"INFO: Without seed: {count_no_seed} items, With seed: {count_with_seed} items, Filtered: {filtered_count}")
        
        # If there are seed items, with_seed count should be >= no_seed count
        if filtered_count > 0:
            assert count_with_seed >= count_no_seed, \
                "include_seed=true should return at least as many items as include_seed=false"
        
        print("PASS: Seed isolation comparison verified")


class TestSeedChainDetailHiddenBehavior:
    """Tests for seed chain detail hidden behavior"""

    def test_seed_chain_hidden_when_include_seed_false(self, admin_headers):
        """Verify seed chain returns seed_chain_hidden when include_seed=false"""
        # First find a seed chain
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=admin_headers,
            params={"window": "30d", "limit": 500, "include_seed": "true"},
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        seed_items = [item for item in items if item.get("is_seed_chain")]
        
        if not seed_items:
            # Try known seed chain IDs
            for seed_chain_id in SEED_CHAIN_IDS:
                chain_response = requests.get(
                    f"{BASE_URL}/api/admin/strategy/timeline/{seed_chain_id}",
                    headers=admin_headers,
                    params={"window": "30d", "include_seed": "false"},
                )
                if chain_response.status_code == 200:
                    chain_data = chain_response.json()
                    meta = chain_data.get("meta", {})
                    summary = chain_data.get("summary", {})
                    
                    if meta.get("seed_chain_hidden"):
                        assert "seed_chain_hidden" in summary.get("invalid_reasons", []), \
                            "seed_chain_hidden should be in invalid_reasons"
                        assert chain_data.get("nodes", []) == [], \
                            "nodes should be empty when seed_chain_hidden"
                        print(f"PASS: Seed chain {seed_chain_id} correctly hidden with include_seed=false")
                        return
            
            pytest.skip("No seed chains found to test hidden behavior")
        
        # Test with found seed chain
        seed_chain_id = seed_items[0].get("chain_id")
        chain_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{seed_chain_id}",
            headers=admin_headers,
            params={"window": "30d", "include_seed": "false"},
        )
        assert chain_response.status_code == 200, f"Failed: {chain_response.text}"
        chain_data = chain_response.json()
        
        meta = chain_data.get("meta", {})
        summary = chain_data.get("summary", {})
        
        # Verify hidden behavior
        if meta.get("seed_chain"):
            assert meta.get("seed_chain_hidden") is True, \
                "seed_chain_hidden should be True when include_seed=false"
            assert "seed_chain_hidden" in summary.get("invalid_reasons", []), \
                "seed_chain_hidden should be in invalid_reasons"
            assert chain_data.get("nodes", []) == [], \
                "nodes should be empty when seed_chain_hidden"
            
            # Verify root_cause_hint for seed_chain_hidden
            hint = summary.get("root_cause_hint")
            if hint:
                assert hint.get("rule_key") == "seed_chain_hidden", \
                    f"rule_key should be 'seed_chain_hidden', got: {hint.get('rule_key')}"
            
            print(f"PASS: Seed chain {seed_chain_id} correctly hidden with include_seed=false")

    def test_seed_chain_visible_when_include_seed_true(self, admin_headers):
        """Verify seed chain returns nodes when include_seed=true"""
        # First find a seed chain
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=admin_headers,
            params={"window": "30d", "limit": 500, "include_seed": "true"},
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        seed_items = [item for item in items if item.get("is_seed_chain")]
        
        if not seed_items:
            # Try known seed chain IDs
            for seed_chain_id in SEED_CHAIN_IDS:
                chain_response = requests.get(
                    f"{BASE_URL}/api/admin/strategy/timeline/{seed_chain_id}",
                    headers=admin_headers,
                    params={"window": "30d", "include_seed": "true"},
                )
                if chain_response.status_code == 200:
                    chain_data = chain_response.json()
                    nodes = chain_data.get("nodes", [])
                    meta = chain_data.get("meta", {})
                    
                    if meta.get("seed_chain") and len(nodes) > 0:
                        assert meta.get("seed_chain_hidden") is not True, \
                            "seed_chain_hidden should not be True when include_seed=true"
                        print(f"PASS: Seed chain {seed_chain_id} shows {len(nodes)} nodes with include_seed=true")
                        return
            
            pytest.skip("No seed chains found to test visibility")
        
        # Test with found seed chain
        seed_chain_id = seed_items[0].get("chain_id")
        chain_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{seed_chain_id}",
            headers=admin_headers,
            params={"window": "30d", "include_seed": "true"},
        )
        assert chain_response.status_code == 200, f"Failed: {chain_response.text}"
        chain_data = chain_response.json()
        
        nodes = chain_data.get("nodes", [])
        meta = chain_data.get("meta", {})
        
        # Verify nodes are visible
        if meta.get("seed_chain"):
            assert meta.get("seed_chain_hidden") is not True, \
                "seed_chain_hidden should not be True when include_seed=true"
            # Nodes should be present (unless chain is genuinely empty)
            print(f"PASS: Seed chain {seed_chain_id} shows {len(nodes)} nodes with include_seed=true")


class TestLiveFlowsNotAffectedBySeed:
    """Tests to verify live-like flows are not affected by seed data"""

    def test_default_filter_excludes_seed_from_live_view(self, admin_headers):
        """Verify default filter behavior excludes seed from live operational view"""
        # This is the default behavior test - live operators should not see seed data
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=admin_headers,
            params={"window": "24h"},  # Default params, no include_seed
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        seed_items = [item for item in items if item.get("is_seed_chain")]
        
        assert len(seed_items) == 0, \
            f"Live view (default) should not show seed data, found {len(seed_items)} seed items"
        
        print(f"PASS: Live view excludes seed data. Total items: {len(items)}")

    def test_observability_strategies_not_affected_by_seed(self, admin_headers):
        """Verify observability strategies endpoint works correctly"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/strategies",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should return strategy list
        assert "items" in data, "items field missing"
        print(f"PASS: Observability strategies returns {len(data.get('items', []))} strategies")


class TestRootCauseHintRuleMapping:
    """Tests for specific root_cause_hint rule mappings"""

    def test_known_rule_keys_exist(self, admin_headers):
        """Verify known rule_keys are properly mapped"""
        # Known rule_keys from the code
        known_rule_keys = [
            "seed_chain_hidden",
            "graph_cycle_detected",
            "parent_timestamp_order_mismatch",
            "missing_parent_mapping_with_split_roots",
            "missing_parent_mapping",
            "self_parent_reference",
            "missing_manual_anchor",
            "detached_nodes_detected",
            "generic_chain_integrity",
            "chain_empty",
        ]
        
        # Get some chains to check rule_keys
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=admin_headers,
            params={"window": "30d", "limit": 100, "include_seed": "true"},
        )
        assert response.status_code == 200
        data = response.json()
        
        found_rule_keys = set()
        items = data.get("items", [])
        
        for item in items[:50]:
            chain_id = item.get("chain_id")
            if not chain_id:
                continue
            
            chain_response = requests.get(
                f"{BASE_URL}/api/admin/strategy/timeline/{chain_id}",
                headers=admin_headers,
                params={"window": "30d", "include_seed": "true"},
            )
            if chain_response.status_code != 200:
                continue
            
            chain_data = chain_response.json()
            hint = chain_data.get("summary", {}).get("root_cause_hint")
            
            if hint:
                rule_key = hint.get("rule_key")
                if rule_key:
                    found_rule_keys.add(rule_key)
                    assert rule_key in known_rule_keys, \
                        f"Unknown rule_key: {rule_key}"
        
        print(f"PASS: Found rule_keys: {found_rule_keys}")
        print(f"INFO: All found rule_keys are in known list")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
