"""
P1 Chain Timeline & Playbook Preflight Tests
Tests for:
- GET /api/admin/strategy/timeline/{chain_id}: chain summary + causal ordering + relation_status + broken link detection
- Broken parent-child scenario: summary.is_chain_valid=false and broken_links_count>0
- 500+ node chain: summary.virtualization_recommended=true, lazy_load_recommended=true
- Impact labels: Risk/Exposure/Signals/Alert labels instead of raw JSON
- Role parity: admin and super_admin can read same chain detail
- Drill-down consistency: action-impact-timeline chain count matches detail count
- Playbook preflight endpoint: GET /api/admin-phase3/incident-snapshots/playbook/preflight contract
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

# Seed data chain IDs
HEAVY_CHAIN_ID = "p1-heavy-chain-600"
BROKEN_CHAIN_ID = "p1-broken-chain-001"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip("Super admin authentication failed")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip("Admin authentication failed")
    return response.json().get("access_token")


class TestChainTimelineEndpoint:
    """Tests for GET /api/admin/strategy/timeline/{chain_id}"""

    def test_heavy_chain_returns_success(self, super_admin_token):
        """Test heavy chain (500+ nodes) returns success with correct summary"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert data.get("status") == "success"
        assert data.get("chain_id") == HEAVY_CHAIN_ID
        assert "summary" in data
        assert "nodes" in data
        assert "count" in data

    def test_heavy_chain_virtualization_recommended(self, super_admin_token):
        """Test 500+ node chain has virtualization_recommended=true"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        
        # Verify 500+ node recommendations
        assert summary.get("total_nodes", 0) > 500, "Heavy chain should have 500+ nodes"
        assert summary.get("virtualization_recommended") is True, "virtualization_recommended should be true for 500+ nodes"
        assert summary.get("lazy_load_recommended") is True, "lazy_load_recommended should be true for 500+ nodes"

    def test_heavy_chain_is_valid(self, super_admin_token):
        """Test heavy chain is valid (no broken links)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        
        assert summary.get("is_chain_valid") is True
        assert summary.get("broken_links_count", 0) == 0
        assert len(summary.get("invalid_reasons", [])) == 0

    def test_broken_chain_returns_success(self, super_admin_token):
        """Test broken chain returns success with correct summary"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{BROKEN_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "success"
        assert data.get("chain_id") == BROKEN_CHAIN_ID

    def test_broken_chain_is_invalid(self, super_admin_token):
        """Test broken chain has is_chain_valid=false and broken_links_count>0"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{BROKEN_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        
        assert summary.get("is_chain_valid") is False, "Broken chain should have is_chain_valid=false"
        assert summary.get("broken_links_count", 0) > 0, "Broken chain should have broken_links_count>0"
        assert "parent_not_found" in summary.get("invalid_reasons", []), "Should have parent_not_found reason"

    def test_broken_chain_nodes_have_broken_link_flag(self, super_admin_token):
        """Test broken chain nodes have is_broken_link and broken_reason fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{BROKEN_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        nodes = data.get("nodes", [])
        
        # Find broken node
        broken_nodes = [n for n in nodes if n.get("is_broken_link")]
        assert len(broken_nodes) > 0, "Should have at least one broken node"
        
        broken_node = broken_nodes[0]
        assert broken_node.get("relation_status") == "broken_link"
        assert broken_node.get("broken_reason") == "parent_not_found"


class TestImpactLabels:
    """Tests for impact labels formatting (Risk/Exposure/Signals/Alert instead of raw JSON)"""

    def test_impact_labels_are_formatted_strings(self, super_admin_token):
        """Test impact_labels are human-readable strings, not raw JSON"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        nodes = data.get("nodes", [])
        
        assert len(nodes) > 0, "Should have nodes"
        
        # Check first few nodes have impact_labels
        for node in nodes[:5]:
            impact_labels = node.get("impact_labels", [])
            assert isinstance(impact_labels, list), "impact_labels should be a list"
            
            for label in impact_labels:
                assert isinstance(label, str), "Each impact label should be a string"
                # Labels should contain readable text, not raw JSON
                assert not label.startswith("{"), "Label should not be raw JSON"
                assert not label.startswith("["), "Label should not be raw JSON array"

    def test_impact_labels_contain_expected_keywords(self, super_admin_token):
        """Test impact_labels contain expected keywords (Risk, Exposure, Signals, Alert)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        nodes = data.get("nodes", [])
        
        # Collect all labels
        all_labels = []
        for node in nodes[:20]:
            all_labels.extend(node.get("impact_labels", []))
        
        all_labels_text = " ".join(all_labels)
        
        # At least some expected keywords should appear
        expected_keywords = ["Risk", "Exposure", "Signals", "Alert"]
        found_keywords = [kw for kw in expected_keywords if kw in all_labels_text]
        assert len(found_keywords) >= 2, f"Should find at least 2 expected keywords, found: {found_keywords}"


class TestRoleParity:
    """Tests for role parity - admin and super_admin should read same chain data"""

    def test_super_admin_can_read_chain(self, super_admin_token):
        """Test super_admin can read chain detail"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{BROKEN_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"
        return data.get("count")

    def test_admin_can_read_chain(self, admin_token):
        """Test admin can read chain detail"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{BROKEN_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"
        return data.get("count")

    def test_role_parity_same_data(self, super_admin_token, admin_token):
        """Test both roles get same chain data"""
        # Super admin request
        super_admin_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{BROKEN_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        
        # Admin request
        admin_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{BROKEN_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        
        assert super_admin_response.status_code == 200
        assert admin_response.status_code == 200
        
        super_admin_data = super_admin_response.json()
        admin_data = admin_response.json()
        
        # Both should have same count and summary
        assert super_admin_data.get("count") == admin_data.get("count")
        assert super_admin_data.get("summary", {}).get("total_nodes") == admin_data.get("summary", {}).get("total_nodes")


class TestDrillDownConsistency:
    """Tests for drill-down consistency between action-impact-timeline and chain detail"""

    def test_action_impact_timeline_returns_chains(self, super_admin_token):
        """Test action-impact-timeline returns chain data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            params={"window": "30d", "limit": 2000},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "success"
        assert "items" in data
        assert "summary" in data

    def test_chain_detail_count_matches_timeline(self, super_admin_token):
        """Test chain detail count matches what's in action-impact-timeline"""
        # Get action-impact-timeline
        timeline_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            params={"window": "30d", "limit": 2000},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert timeline_response.status_code == 200
        timeline_data = timeline_response.json()
        
        # Count items for heavy chain
        heavy_chain_items = [
            item for item in timeline_data.get("items", [])
            if item.get("chain_id") == HEAVY_CHAIN_ID
        ]
        
        # Get chain detail
        detail_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert detail_response.status_code == 200
        detail_data = detail_response.json()
        
        # Counts should match
        assert len(heavy_chain_items) == detail_data.get("count"), \
            f"Timeline items ({len(heavy_chain_items)}) should match detail count ({detail_data.get('count')})"


class TestPlaybookPreflightEndpoint:
    """Tests for GET /api/admin-phase3/incident-snapshots/playbook/preflight"""

    def test_preflight_returns_success(self, super_admin_token):
        """Test preflight endpoint returns success"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"

    def test_preflight_has_overall_state(self, super_admin_token):
        """Test preflight has overall_state field"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "overall_state" in data
        assert data.get("overall_state") in ["ready", "blocked"]

    def test_preflight_has_checks_list(self, super_admin_token):
        """Test preflight has checks list with required items"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        checks = data.get("checks", [])
        assert isinstance(checks, list)
        assert len(checks) >= 4, "Should have at least 4 checks"
        
        # Verify check structure
        for check in checks:
            assert "key" in check
            assert "label" in check
            assert "status" in check
            assert "detail" in check

    def test_preflight_has_required_check_keys(self, super_admin_token):
        """Test preflight has all required check keys"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        checks = data.get("checks", [])
        check_keys = [c.get("key") for c in checks]
        
        required_keys = [
            "db_readiness",
            "migration_compatibility",
            "table_access",
            "integration_readiness",
            "playbook_flow_gate",
        ]
        
        for key in required_keys:
            assert key in check_keys, f"Missing required check key: {key}"

    def test_preflight_has_migration_info(self, super_admin_token):
        """Test preflight has migration info"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        migration = data.get("migration", {})
        assert "current" in migration
        assert "required" in migration
        assert "compatible" in migration

    def test_preflight_has_integration_modes(self, super_admin_token):
        """Test preflight has integration_modes info"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        integration_modes = data.get("integration_modes", {})
        assert "slack" in integration_modes
        assert "binance" in integration_modes
        assert "execution_mode" in integration_modes

    def test_preflight_has_role_gate(self, super_admin_token):
        """Test preflight has role_gate info"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        role_gate = data.get("role_gate", {})
        assert "current_role" in role_gate
        assert "approve_allowed" in role_gate

    def test_preflight_admin_role_gate(self, admin_token):
        """Test preflight shows correct role_gate for admin"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        role_gate = data.get("role_gate", {})
        assert role_gate.get("current_role") == "admin"
        assert role_gate.get("approve_allowed") is False


class TestChainSummaryFields:
    """Tests for chain summary fields"""

    def test_summary_has_all_required_fields(self, super_admin_token):
        """Test chain summary has all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        
        required_fields = [
            "total_nodes",
            "manual_action_count",
            "system_reaction_count",
            "broken_links_count",
            "root_nodes_count",
            "is_chain_valid",
            "invalid_reasons",
            "max_depth",
            "default_view",
            "lazy_load_recommended",
            "virtualization_recommended",
        ]
        
        for field in required_fields:
            assert field in summary, f"Missing required summary field: {field}"

    def test_node_has_relation_status(self, super_admin_token):
        """Test nodes have relation_status field"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        nodes = data.get("nodes", [])
        
        for node in nodes[:10]:
            assert "relation_status" in node
            assert node.get("relation_status") in ["root", "linked", "broken_link"]

    def test_node_has_causal_ordering_fields(self, super_admin_token):
        """Test nodes have causal ordering fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN_ID}",
            params={"window": "30d"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        nodes = data.get("nodes", [])
        
        for node in nodes[:10]:
            assert "causal_index" in node
            assert "causal_depth" in node
            assert "flow_stage" in node
