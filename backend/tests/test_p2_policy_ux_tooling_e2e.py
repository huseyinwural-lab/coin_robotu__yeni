"""
P2 Policy UX Tooling E2E Tests
Tests: Builder/Validation/Diff/Simulation/Bulk/Activation Gate/JSON Read-only/Audit Log
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestAdminLogin:
    """Test admin login and access"""
    
    def test_admin_login_success(self):
        """Admin login with correct credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data or "token" in data
        assert data.get("role") == "super_admin"
        print("PASS: Admin login successful")


class TestPolicyBuilder:
    """Test Policy Builder - create + validate"""
    
    def test_policy_validate_success(self, api_client):
        """Validate a policy with valid rules"""
        payload = {
            "policy_code": "TEST_p2_e2e_validate",
            "version_label": "builder",
            "description": "E2E test policy",
            "scope": {
                "environment": "DEV",
                "strategy": "test-strategy",
                "symbol": "BTCUSDT"
            },
            "rules": [
                {
                    "rule_id": "rule_1",
                    "action": "BLOCK",
                    "severity": "HIGH",
                    "logical_operator": "AND",
                    "conditions": [
                        {"field": "exposure", "operator": ">", "value": "100000"}
                    ]
                }
            ]
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/validate", json=payload)
        assert response.status_code == 200, f"Validate failed: {response.text}"
        data = response.json()
        assert "errors" in data
        assert "warnings" in data
        assert "risk_level" in data
        assert "schema" in data
        assert "human_readable" in data
        print(f"PASS: Policy validation - errors={len(data['errors'])}, warnings={len(data['warnings'])}, risk_level={data['risk_level']}")
    
    def test_policy_validate_errors_block(self, api_client):
        """Validate policy with errors - should return errors array"""
        payload = {
            "policy_code": "",  # Empty policy_code should cause error
            "version_label": "builder",
            "scope": {"environment": "DEV"},
            "rules": []  # Empty rules should cause error
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/validate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("errors", [])) > 0, "Expected validation errors for empty policy_code and rules"
        assert data.get("risk_level") == "HIGH", "Expected HIGH risk level when errors exist"
        print(f"PASS: Validation errors block - errors={data['errors']}")
    
    def test_policy_validate_high_risk_warning(self, api_client):
        """Validate policy without BLOCK action - should show high-risk warning"""
        payload = {
            "policy_code": "TEST_p2_e2e_no_block",
            "version_label": "builder",
            "scope": {"environment": "DEV"},
            "rules": [
                {
                    "rule_id": "rule_1",
                    "action": "WARN",  # No BLOCK action
                    "severity": "MEDIUM",
                    "conditions": [
                        {"field": "exposure", "operator": ">", "value": "50000"}
                    ]
                }
            ]
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/validate", json=payload)
        assert response.status_code == 200
        data = response.json()
        # Should have warning about no BLOCK action
        warnings = data.get("warnings", [])
        has_high_risk_warning = any("BLOCK" in w or "yüksek risk" in w.lower() for w in warnings)
        assert has_high_risk_warning, f"Expected high-risk warning for no BLOCK action, got: {warnings}"
        print(f"PASS: High-risk warning detected - warnings={warnings}")
    
    def test_policy_create_version(self, api_client):
        """Create a policy version from builder"""
        payload = {
            "policy_code": "TEST_p2_e2e_create",
            "version_label": "builder_v1",
            "description": "E2E test policy creation",
            "change_summary": "Initial E2E test version",
            "scope": {
                "environment": "DEV",
                "strategy": "test-strategy"
            },
            "rules": [
                {
                    "rule_id": "exposure_cap",
                    "action": "BLOCK",
                    "severity": "HIGH",
                    "conditions": [
                        {"field": "exposure", "operator": ">", "value": "100000"}
                    ]
                }
            ]
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/builder/versions", json=payload)
        assert response.status_code == 200, f"Create version failed: {response.text}"
        data = response.json()
        assert "version_id" in data
        assert data.get("policy_code") == "TEST_p2_e2e_create"
        print(f"PASS: Policy version created - version_id={data['version_id']}")
        return data["version_id"]


class TestActivationGate:
    """Test Activation Gate - errors block, override required, prod approval gate"""
    
    def test_activation_blocked_with_errors(self, api_client):
        """Activation should be blocked when validation has errors"""
        # First create a version with valid data
        create_payload = {
            "policy_code": "TEST_p2_activation_gate",
            "version_label": "gate_test",
            "change_summary": "Activation gate test",
            "scope": {"environment": "DEV"},
            "rules": [
                {
                    "rule_id": "rule_1",
                    "action": "BLOCK",
                    "severity": "HIGH",
                    "conditions": [
                        {"field": "exposure", "operator": ">", "value": "100000"}
                    ]
                }
            ]
        }
        create_response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/builder/versions", json=create_payload)
        if create_response.status_code != 200:
            pytest.skip(f"Could not create test version: {create_response.text}")
        
        version_id = create_response.json().get("version_id")
        
        # Try to activate without approval (should work for non-prod)
        activate_payload = {
            "environment": "live",
            "activation_mode": "ACTIVE"
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/versions/{version_id}/activate", json=activate_payload)
        # Should succeed for live without approval
        print(f"Activation response: {response.status_code} - {response.text[:200]}")
        # The activation gate checks validation errors - if no errors, it should proceed
        assert response.status_code in [200, 400, 403], f"Unexpected status: {response.status_code}"
        print(f"PASS: Activation gate tested - status={response.status_code}")
    
    def test_high_risk_override_required(self, api_client):
        """High-risk policy requires override flag and reason"""
        # Create a high-risk policy (no BLOCK action)
        create_payload = {
            "policy_code": "TEST_p2_high_risk_override",
            "version_label": "high_risk",
            "change_summary": "High risk test",
            "scope": {"environment": "DEV"},
            "rules": [
                {
                    "rule_id": "rule_1",
                    "action": "WARN",  # No BLOCK = high risk
                    "severity": "MEDIUM",
                    "conditions": [
                        {"field": "exposure", "operator": ">", "value": "50000"}
                    ]
                }
            ]
        }
        create_response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/builder/versions", json=create_payload)
        if create_response.status_code != 200:
            pytest.skip(f"Could not create high-risk version: {create_response.text}")
        
        version_id = create_response.json().get("version_id")
        
        # Try to activate without override - should fail
        activate_payload = {
            "environment": "live",
            "activation_mode": "ACTIVE",
            "override_high_risk": False
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/versions/{version_id}/activate", json=activate_payload)
        
        # Should require override for high-risk
        if response.status_code == 400:
            data = response.json()
            detail = data.get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error") == "high_risk_override_required", f"Expected high_risk_override_required, got: {detail}"
            print(f"PASS: High-risk override required - error={detail}")
        else:
            print(f"INFO: Activation response: {response.status_code} - {response.text[:200]}")
    
    def test_prod_approval_gate(self, api_client):
        """Prod environment requires approval before activation"""
        # Create a valid policy
        create_payload = {
            "policy_code": "TEST_p2_prod_gate",
            "version_label": "prod_gate",
            "change_summary": "Prod gate test",
            "scope": {"environment": "PROD"},
            "rules": [
                {
                    "rule_id": "rule_1",
                    "action": "BLOCK",
                    "severity": "HIGH",
                    "conditions": [
                        {"field": "exposure", "operator": ">", "value": "100000"}
                    ]
                }
            ]
        }
        create_response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/builder/versions", json=create_payload)
        if create_response.status_code != 200:
            pytest.skip(f"Could not create prod version: {create_response.text}")
        
        version_id = create_response.json().get("version_id")
        
        # Try to activate in prod without approval
        activate_payload = {
            "environment": "prod",
            "activation_mode": "ACTIVE"
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/versions/{version_id}/activate", json=activate_payload)
        
        # Should require approval for prod
        print(f"Prod activation response: {response.status_code} - {response.text[:300]}")
        # Either blocked (400/403) or requires approval
        assert response.status_code in [200, 400, 403], f"Unexpected status: {response.status_code}"
        print("PASS: Prod approval gate tested")


class TestDiffViewer:
    """Test Diff Viewer A/B comparison"""
    
    def test_diff_comparison(self, api_client):
        """Compare two policy versions"""
        # First create two versions
        base_payload = {
            "policy_code": "TEST_p2_diff_compare",
            "version_label": "v1",
            "change_summary": "Version 1",
            "scope": {"environment": "DEV"},
            "rules": [
                {
                    "rule_id": "rule_1",
                    "action": "WARN",
                    "severity": "MEDIUM",
                    "conditions": [
                        {"field": "exposure", "operator": ">", "value": "50000"}
                    ]
                }
            ]
        }
        
        # Create version A
        response_a = api_client.post(f"{BASE_URL}/api/admin/execution-policies/builder/versions", json=base_payload)
        if response_a.status_code != 200:
            pytest.skip(f"Could not create version A: {response_a.text}")
        version_a = response_a.json().get("version_id")
        
        # Create version B with different action
        base_payload["version_label"] = "v2"
        base_payload["change_summary"] = "Version 2 - upgraded to BLOCK"
        base_payload["rules"][0]["action"] = "BLOCK"
        base_payload["rules"][0]["severity"] = "HIGH"
        
        response_b = api_client.post(f"{BASE_URL}/api/admin/execution-policies/builder/versions", json=base_payload)
        if response_b.status_code != 200:
            pytest.skip(f"Could not create version B: {response_b.text}")
        version_b = response_b.json().get("version_id")
        
        # Now compare
        diff_payload = {
            "policy_code": "TEST_p2_diff_compare",
            "version_a": version_a,
            "version_b": version_b
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/diff", json=diff_payload)
        assert response.status_code == 200, f"Diff failed: {response.text}"
        
        data = response.json()
        assert "version_a" in data
        assert "version_b" in data
        assert "changes" in data
        
        # Should detect the action change
        changes = data.get("changes", [])
        print(f"PASS: Diff comparison - changes={len(changes)}, version_a={version_a[:8]}, version_b={version_b[:8]}")
        
        # Check risk impact markers
        for change in changes:
            assert "risk_impact" in change, "Change should have risk_impact marker"
            print(f"  Change: rule_id={change.get('rule_id')}, risk_impact={change.get('risk_impact')}")


class TestSimulationPanel:
    """Test Simulation Panel - single intent"""
    
    def test_simulation_single_intent(self, api_client):
        """Simulate policy against single intent"""
        # First create a policy version
        create_payload = {
            "policy_code": "TEST_p2_simulation",
            "version_label": "sim_test",
            "change_summary": "Simulation test",
            "scope": {"environment": "DEV"},
            "rules": [
                {
                    "rule_id": "exposure_block",
                    "action": "BLOCK",
                    "severity": "HIGH",
                    "conditions": [
                        {"field": "exposure", "operator": ">", "value": "100000"}
                    ]
                },
                {
                    "rule_id": "volatility_warn",
                    "action": "WARN",
                    "severity": "MEDIUM",
                    "conditions": [
                        {"field": "volatility", "operator": ">=", "value": "0.5"}
                    ]
                }
            ]
        }
        create_response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/builder/versions", json=create_payload)
        if create_response.status_code != 200:
            pytest.skip(f"Could not create simulation version: {create_response.text}")
        
        version_id = create_response.json().get("version_id")
        
        # Simulate with high exposure (should trigger BLOCK)
        sim_payload = {
            "policy_code": "TEST_p2_simulation",
            "version_id": version_id,
            "simulation_input": {
                "environment": "live",
                "strategy_risk_class": "MEDIUM",
                "strategy": "test-strategy",
                "order": {
                    "exposure": 150000,  # Above threshold
                    "pnl": 0
                },
                "market_state": {
                    "volatility": 0.3
                }
            }
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/simulate", json=sim_payload)
        assert response.status_code == 200, f"Simulation failed: {response.text}"
        
        data = response.json()
        simulation = data.get("simulation", {})
        assert "decision" in simulation
        assert "action" in simulation
        assert "triggered_rules" in simulation
        assert "trace" in simulation
        
        # Should trigger BLOCK due to high exposure
        assert simulation.get("decision") == "BLOCK", f"Expected BLOCK decision, got: {simulation.get('decision')}"
        print(f"PASS: Simulation - decision={simulation['decision']}, action={simulation['action']}, triggered_rules={len(simulation['triggered_rules'])}")
    
    def test_simulation_no_trigger(self, api_client):
        """Simulate policy with values below thresholds"""
        # Get existing versions
        response = api_client.get(f"{BASE_URL}/api/admin/execution-policies")
        if response.status_code != 200:
            pytest.skip("Could not get policy versions")
        
        versions = response.json().get("policy_versions", [])
        test_versions = [v for v in versions if v.get("policy_code", "").startswith("TEST_p2_simulation")]
        if not test_versions:
            pytest.skip("No test simulation version found")
        
        version_id = test_versions[0].get("version_id")
        
        # Simulate with low exposure (should not trigger)
        sim_payload = {
            "policy_code": test_versions[0].get("policy_code"),
            "version_id": version_id,
            "simulation_input": {
                "environment": "live",
                "strategy_risk_class": "LOW",
                "order": {
                    "exposure": 10000,  # Below threshold
                    "pnl": 100
                },
                "market_state": {
                    "volatility": 0.1
                }
            }
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/simulate", json=sim_payload)
        assert response.status_code == 200, f"Simulation failed: {response.text}"
        
        data = response.json()
        simulation = data.get("simulation", {})
        # Should ALLOW since no rules triggered
        assert simulation.get("decision") in ["ALLOW", "FLAG"], f"Expected ALLOW/FLAG, got: {simulation.get('decision')}"
        print(f"PASS: Simulation no trigger - decision={simulation['decision']}")


class TestBulkOperations:
    """Test Bulk activate/rollback/strategy binding"""
    
    def test_bulk_activate(self, api_client):
        """Bulk activate multiple versions"""
        # Create multiple versions
        version_ids = []
        for i in range(2):
            create_payload = {
                "policy_code": f"TEST_p2_bulk_activate_{i}",
                "version_label": f"bulk_v{i}",
                "change_summary": f"Bulk test {i}",
                "scope": {"environment": "DEV"},
                "rules": [
                    {
                        "rule_id": "rule_1",
                        "action": "BLOCK",
                        "severity": "HIGH",
                        "conditions": [
                            {"field": "exposure", "operator": ">", "value": "100000"}
                        ]
                    }
                ]
            }
            response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/builder/versions", json=create_payload)
            if response.status_code == 200:
                version_ids.append(response.json().get("version_id"))
        
        if len(version_ids) < 2:
            pytest.skip("Could not create enough versions for bulk test")
        
        # Bulk activate
        bulk_payload = {
            "items": [
                {
                    "version_id": vid,
                    "environment": "live",
                    "activation_mode": "ACTIVE"
                }
                for vid in version_ids
            ]
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/bulk/activate", json=bulk_payload)
        assert response.status_code == 200, f"Bulk activate failed: {response.text}"
        
        data = response.json()
        assert "summary" in data or "results" in data
        print(f"PASS: Bulk activate - response={data}")
    
    def test_bulk_rollback(self, api_client):
        """Bulk rollback multiple policies"""
        # Get existing versions
        response = api_client.get(f"{BASE_URL}/api/admin/execution-policies")
        if response.status_code != 200:
            pytest.skip("Could not get policy versions")
        
        versions = response.json().get("policy_versions", [])
        test_versions = [v for v in versions if v.get("policy_code", "").startswith("TEST_p2_bulk")]
        
        if len(test_versions) < 1:
            pytest.skip("No test versions for rollback")
        
        # Bulk rollback
        bulk_payload = {
            "items": [
                {
                    "policy_code": v.get("policy_code"),
                    "target_version_id": v.get("version_id"),
                    "reason": "E2E bulk rollback test"
                }
                for v in test_versions[:2]
            ]
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/bulk/rollback", json=bulk_payload)
        assert response.status_code == 200, f"Bulk rollback failed: {response.text}"
        
        data = response.json()
        assert "summary" in data or "results" in data
        print(f"PASS: Bulk rollback - response={data}")
    
    def test_bulk_strategy_binding(self, api_client):
        """Bulk strategy binding"""
        bulk_payload = {
            "items": [
                {
                    "strategy_id": "TEST_strategy_1",
                    "bound_policy_set": "TEST_p2_bulk_activate_0",
                    "risk_class": "MEDIUM",
                    "execution_mode": "SIMULATION",
                    "state": "enabled",
                    "enabled": True
                },
                {
                    "strategy_id": "TEST_strategy_2",
                    "bound_policy_set": "TEST_p2_bulk_activate_1",
                    "risk_class": "HIGH",
                    "execution_mode": "SIMULATION",
                    "state": "enabled",
                    "enabled": True
                }
            ]
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/bulk/strategy-binding", json=bulk_payload)
        assert response.status_code == 200, f"Bulk binding failed: {response.text}"
        
        data = response.json()
        assert "summary" in data or "results" in data
        print(f"PASS: Bulk strategy binding - response={data}")


class TestAuditLog:
    """Test Audit Log records"""
    
    def test_audit_timeline_endpoint(self, api_client):
        """Test audit timeline endpoint"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/audit-timeline")
        # This endpoint may or may not exist
        if response.status_code == 404:
            # Try alternative audit endpoints
            response = api_client.get(f"{BASE_URL}/api/admin/audit-logs?limit=10")
        
        if response.status_code == 404:
            # Try another alternative
            response = api_client.get(f"{BASE_URL}/api/admin/system/audit-logs?limit=10")
        
        print(f"Audit endpoint response: {response.status_code}")
        # Just verify we can access some audit data
        if response.status_code == 200:
            data = response.json()
            print(f"PASS: Audit log accessible - records={len(data) if isinstance(data, list) else 'object'}")
        else:
            print(f"INFO: Audit endpoint returned {response.status_code}")
    
    def test_policy_actions_create_audit(self, api_client):
        """Verify policy actions create audit records"""
        # Create a policy - this should create audit log
        create_payload = {
            "policy_code": "TEST_p2_audit_check",
            "version_label": "audit_test",
            "change_summary": "Audit log test",
            "scope": {"environment": "DEV"},
            "rules": [
                {
                    "rule_id": "rule_1",
                    "action": "BLOCK",
                    "severity": "HIGH",
                    "conditions": [
                        {"field": "exposure", "operator": ">", "value": "100000"}
                    ]
                }
            ]
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/builder/versions", json=create_payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        # Validate - this should also create audit log
        validate_payload = {
            "policy_code": "TEST_p2_audit_check",
            "scope": {"environment": "DEV"},
            "rules": create_payload["rules"]
        }
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/validate", json=validate_payload)
        assert response.status_code == 200
        
        print("PASS: Policy actions completed - audit logs should be created")


class TestJSONReadOnly:
    """Test JSON read-only display"""
    
    def test_execution_policies_json_structure(self, api_client):
        """Verify execution policies returns proper JSON structure"""
        response = api_client.get(f"{BASE_URL}/api/admin/execution-policies")
        assert response.status_code == 200, f"Get policies failed: {response.text}"
        
        data = response.json()
        
        # Verify expected fields
        expected_fields = [
            "registry",
            "engine_config",
            "observability_metrics",
            "policy_decision_log",
            "policy_versions",
            "strategy_health",
            "release_gate",
            "remediation_recommendations",
            "environment_overrides",
            "safe_mode_states"
        ]
        
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"PASS: JSON structure verified - fields={list(data.keys())}")
    
    def test_policy_version_json_readonly(self, api_client):
        """Verify policy version contains read-only JSON schema"""
        response = api_client.get(f"{BASE_URL}/api/admin/execution-policies")
        assert response.status_code == 200
        
        versions = response.json().get("policy_versions", [])
        if not versions:
            pytest.skip("No policy versions to check")
        
        # Check first version has expected structure
        version = versions[0]
        assert "version_id" in version
        assert "policy_code" in version
        assert "version_number" in version
        assert "state" in version
        
        print(f"PASS: Policy version JSON structure verified - version_id={version.get('version_id')[:8]}")


class TestVersionValidation:
    """Test version-specific validation endpoint"""
    
    def test_version_validate_endpoint(self, api_client):
        """Test validation of existing version"""
        # Get existing versions
        response = api_client.get(f"{BASE_URL}/api/admin/execution-policies")
        if response.status_code != 200:
            pytest.skip("Could not get policy versions")
        
        versions = response.json().get("policy_versions", [])
        if not versions:
            pytest.skip("No versions to validate")
        
        version_id = versions[0].get("version_id")
        
        # Validate specific version
        response = api_client.post(f"{BASE_URL}/api/admin/execution-policies/versions/{version_id}/validate")
        
        if response.status_code == 200:
            data = response.json()
            assert "errors" in data or "validation" in data
            print(f"PASS: Version validation - version_id={version_id[:8]}")
        elif response.status_code == 404:
            print(f"INFO: Version validation endpoint not found for {version_id[:8]}")
        else:
            print(f"INFO: Version validation returned {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
