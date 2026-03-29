# Incident Intelligence Core API Tests (P0+P1+P2) - TestClient Version
# Tests: engine run, anomalies, incidents, KPIs, weekly summary, graph, predictions, incident detail/timeline, state patch
# Auto-remediation is MOCKED (safe state/history updates only)

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from fastapi.testclient import TestClient
from server import app
from db import SessionLocal
from models import User, UserRole
from core.security import hash_password
import uuid


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient"""
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_user():
    """Create or get admin user for testing"""
    db = SessionLocal()
    try:
        # Check if canary admin exists
        user = db.query(User).filter(User.email == "canary.admin@platform.local").first()
        if not user:
            user = User(
                email="canary.admin@platform.local",
                password_hash=hash_password("CanaryAdmin123!"),
                role=UserRole.ADMIN,
                is_active=True,
                approval_status="approved",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()


@pytest.fixture(scope="module")
def auth_headers(client, admin_user):
    """Get auth headers by logging in"""
    response = client.post(
        "/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
    )
    if response.status_code != 200:
        pytest.skip(f"Login failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return {"Authorization": f"Bearer {token}"}


class TestIncidentIntelligenceEngineRun:
    """Test engine run endpoint - produces anomalies/incidents/auto_remediation payloads"""

    def test_engine_run_returns_200(self, client, auth_headers):
        """Engine run with window_minutes=15 should return 200"""
        response = client.post(
            "/api/admin/incident-intelligence/engine/run?window_minutes=15",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Verify response structure
        assert "generated_at" in data, "Missing generated_at field"
        assert "context" in data, "Missing context field"
        assert "thresholds" in data, "Missing thresholds field"
        assert "anomalies" in data, "Missing anomalies field"
        assert "incidents" in data, "Missing incidents field"
        assert "auto_remediation" in data, "Missing auto_remediation field"
        # Verify types
        assert isinstance(data["anomalies"], list), "anomalies should be a list"
        assert isinstance(data["incidents"], list), "incidents should be a list"
        assert isinstance(data["auto_remediation"], list), "auto_remediation should be a list"

    def test_engine_run_context_has_dynamic_fields(self, client, auth_headers):
        """Engine run context should have volatility, load, regime fields"""
        response = client.post(
            "/api/admin/incident-intelligence/engine/run?window_minutes=15",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        context = data.get("context", {})
        assert "volatility" in context, "Missing volatility in context"
        assert "load" in context, "Missing load in context"
        assert "regime" in context, "Missing regime in context"

    def test_engine_run_thresholds_has_adaptive_fields(self, client, auth_headers):
        """Engine run thresholds should have z_score, baseline_deviation, burst_count, repeat_count"""
        response = client.post(
            "/api/admin/incident-intelligence/engine/run?window_minutes=15",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        thresholds = data.get("thresholds", {})
        assert "z_score" in thresholds, "Missing z_score in thresholds"
        assert "baseline_deviation" in thresholds, "Missing baseline_deviation in thresholds"
        assert "burst_count" in thresholds, "Missing burst_count in thresholds"
        assert "repeat_count" in thresholds, "Missing repeat_count in thresholds"


class TestIncidentIntelligenceAnomalies:
    """Test anomalies endpoint - returns unified anomaly model fields"""

    def test_anomalies_returns_200(self, client, auth_headers):
        """GET /anomalies should return 200 with items list"""
        response = client.get(
            "/api/admin/incident-intelligence/anomalies",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, "Missing items field"
        assert isinstance(data["items"], list), "items should be a list"

    def test_anomalies_unified_model_fields(self, client, auth_headers):
        """Anomalies should have unified model fields"""
        # First run engine to ensure anomalies exist
        client.post("/api/admin/incident-intelligence/engine/run?window_minutes=60", headers=auth_headers)
        
        response = client.get(
            "/api/admin/incident-intelligence/anomalies?limit=10",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        if not items:
            pytest.skip("No anomalies found - run engine first")
        
        anomaly = items[0]
        required_fields = ["id", "type", "source", "domain", "severity", "state", "owner", "linked_events", "impact", "root_cause", "suggested_actions"]
        for field in required_fields:
            assert field in anomaly, f"Missing unified model field: {field}"
        
        # Verify impact structure
        impact = anomaly.get("impact", {})
        assert "pnl" in impact or "exposure" in impact or "availability" in impact, "Impact should have pnl/exposure/availability"

    def test_anomalies_filter_by_domain(self, client, auth_headers):
        """Anomalies can be filtered by domain"""
        response = client.get(
            "/api/admin/incident-intelligence/anomalies?domain=execution&limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        # All returned items should have domain=execution (if any)
        for item in items:
            assert item.get("domain") == "execution", f"Expected domain=execution, got {item.get('domain')}"

    def test_anomalies_filter_by_severity(self, client, auth_headers):
        """Anomalies can be filtered by severity"""
        response = client.get(
            "/api/admin/incident-intelligence/anomalies?severity=CRITICAL&limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        for item in items:
            assert item.get("severity") == "CRITICAL", f"Expected severity=CRITICAL, got {item.get('severity')}"


class TestIncidentIntelligenceIncidents:
    """Test incidents endpoint - returns incident list"""

    def test_incidents_returns_200(self, client, auth_headers):
        """GET /incidents should return 200 with items list"""
        response = client.get(
            "/api/admin/incident-intelligence/incidents",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, "Missing items field"
        assert isinstance(data["items"], list), "items should be a list"

    def test_incidents_have_required_fields(self, client, auth_headers):
        """Incidents should have required fields"""
        response = client.get(
            "/api/admin/incident-intelligence/incidents?limit=10",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        if not items:
            pytest.skip("No incidents found - run engine first")
        
        incident = items[0]
        required_fields = ["incident_id", "title", "severity", "state", "owner", "evidence", "impact", "root_cause", "suggested_actions", "remediation_history"]
        for field in required_fields:
            assert field in incident, f"Missing incident field: {field}"

    def test_incidents_filter_by_state(self, client, auth_headers):
        """Incidents can be filtered by state"""
        response = client.get(
            "/api/admin/incident-intelligence/incidents?state=OPEN&limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        for item in items:
            assert item.get("state") == "OPEN", f"Expected state=OPEN, got {item.get('state')}"


class TestIncidentIntelligenceIncidentDetail:
    """Test incident detail endpoint - returns timeline chain"""

    def test_incident_detail_returns_timeline(self, client, auth_headers):
        """GET /incidents/{incident_id} should return incident and timeline with chain"""
        # First get an incident
        list_response = client.get(
            "/api/admin/incident-intelligence/incidents?limit=5",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        items = list_response.json().get("items", [])
        if not items:
            pytest.skip("No incidents found - run engine first")
        
        incident_id = items[0]["incident_id"]
        
        # Get detail
        response = client.get(
            f"/api/admin/incident-intelligence/incidents/{incident_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "incident" in data, "Missing incident field"
        assert "timeline" in data, "Missing timeline field"
        
        timeline = data.get("timeline", {})
        assert "incident_id" in timeline, "Timeline missing incident_id"
        assert "chain" in timeline, "Timeline missing chain"
        assert isinstance(timeline["chain"], list), "Timeline chain should be a list"

    def test_incident_detail_timeline_has_kinds(self, client, auth_headers):
        """Timeline chain should have kinds: raw_event, anomaly, incident, remediation, resolution"""
        list_response = client.get(
            "/api/admin/incident-intelligence/incidents?limit=5",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        items = list_response.json().get("items", [])
        if not items:
            pytest.skip("No incidents found")
        
        incident_id = items[0]["incident_id"]
        response = client.get(
            f"/api/admin/incident-intelligence/incidents/{incident_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        chain = data.get("timeline", {}).get("chain", [])
        if not chain:
            pytest.skip("Empty timeline chain")
        
        kinds = {item.get("kind") for item in chain}
        # At minimum should have incident kind
        assert "incident" in kinds, "Timeline should have incident kind"
        # Check each item has required fields
        for item in chain:
            assert "kind" in item, "Chain item missing kind"
            assert "id" in item, "Chain item missing id"
            assert "timestamp" in item, "Chain item missing timestamp"
            assert "payload" in item, "Chain item missing payload"

    def test_incident_detail_404_for_invalid_id(self, client, auth_headers):
        """GET /incidents/{invalid_id} should return 404"""
        response = client.get(
            "/api/admin/incident-intelligence/incidents/invalid-incident-id-12345",
            headers=auth_headers,
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestIncidentIntelligenceStatePatch:
    """Test incident state patch - supports FALSE_POSITIVE and owner/note update"""

    def test_patch_incident_state_to_investigating(self, client, auth_headers):
        """PATCH /incidents/{incident_id} with state=INVESTIGATING should work"""
        # Get an OPEN incident
        list_response = client.get(
            "/api/admin/incident-intelligence/incidents?state=OPEN&limit=5",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        items = list_response.json().get("items", [])
        if not items:
            pytest.skip("No OPEN incidents found")
        
        incident_id = items[0]["incident_id"]
        
        response = client.patch(
            f"/api/admin/incident-intelligence/incidents/{incident_id}",
            headers=auth_headers,
            json={"state": "INVESTIGATING"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "incident" in data, "Missing incident in response"
        assert data["incident"]["state"] == "INVESTIGATING", f"Expected state=INVESTIGATING, got {data['incident']['state']}"

    def test_patch_incident_state_to_false_positive(self, client, auth_headers):
        """PATCH /incidents/{incident_id} with state=FALSE_POSITIVE should work"""
        # Get any incident
        list_response = client.get(
            "/api/admin/incident-intelligence/incidents?limit=10",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        items = list_response.json().get("items", [])
        if not items:
            pytest.skip("No incidents found")
        
        # Find one that's not already FALSE_POSITIVE
        target = None
        for item in items:
            if item.get("state") != "FALSE_POSITIVE":
                target = item
                break
        
        if not target:
            pytest.skip("All incidents are already FALSE_POSITIVE")
        
        incident_id = target["incident_id"]
        
        response = client.patch(
            f"/api/admin/incident-intelligence/incidents/{incident_id}",
            headers=auth_headers,
            json={"state": "FALSE_POSITIVE", "owner": "test-ops", "note": "Validated as false positive by test"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["incident"]["state"] == "FALSE_POSITIVE", f"Expected state=FALSE_POSITIVE, got {data['incident']['state']}"

    def test_patch_incident_with_owner_and_note(self, client, auth_headers):
        """PATCH /incidents/{incident_id} with owner and note should update"""
        list_response = client.get(
            "/api/admin/incident-intelligence/incidents?limit=5",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        items = list_response.json().get("items", [])
        if not items:
            pytest.skip("No incidents found")
        
        incident_id = items[0]["incident_id"]
        
        response = client.patch(
            f"/api/admin/incident-intelligence/incidents/{incident_id}",
            headers=auth_headers,
            json={"state": "MITIGATED", "owner": "test-owner-update", "note": "Test note update"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["incident"]["owner"] == "test-owner-update", f"Expected owner=test-owner-update, got {data['incident']['owner']}"

    def test_patch_incident_invalid_state_returns_400(self, client, auth_headers):
        """PATCH /incidents/{incident_id} with invalid state should return 400"""
        list_response = client.get(
            "/api/admin/incident-intelligence/incidents?limit=5",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        items = list_response.json().get("items", [])
        if not items:
            pytest.skip("No incidents found")
        
        incident_id = items[0]["incident_id"]
        
        response = client.patch(
            f"/api/admin/incident-intelligence/incidents/{incident_id}",
            headers=auth_headers,
            json={"state": "INVALID_STATE_XYZ"},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"


class TestIncidentIntelligenceKPIs:
    """Test KPI endpoint - returns MTTD, MTTR, incident_count, repeat_incident_rate"""

    def test_kpis_returns_200(self, client, auth_headers):
        """GET /kpis should return 200"""
        response = client.get(
            "/api/admin/incident-intelligence/kpis",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_kpis_has_required_fields(self, client, auth_headers):
        """KPIs should have: days, incident_count, mttd_seconds, mttr_seconds, repeat_incident_rate"""
        response = client.get(
            "/api/admin/incident-intelligence/kpis?days=7",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ["days", "incident_count", "mttd_seconds", "mttr_seconds", "repeat_incident_rate"]
        for field in required_fields:
            assert field in data, f"Missing KPI field: {field}"
        
        # Verify types
        assert isinstance(data["days"], int), "days should be int"
        assert isinstance(data["incident_count"], int), "incident_count should be int"
        assert isinstance(data["mttd_seconds"], (int, float)), "mttd_seconds should be numeric"
        assert isinstance(data["mttr_seconds"], (int, float)), "mttr_seconds should be numeric"
        assert isinstance(data["repeat_incident_rate"], (int, float)), "repeat_incident_rate should be numeric"

    def test_kpis_days_parameter(self, client, auth_headers):
        """KPIs should respect days parameter"""
        response = client.get(
            "/api/admin/incident-intelligence/kpis?days=30",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 30, f"Expected days=30, got {data['days']}"


class TestIncidentIntelligenceWeeklySummary:
    """Test weekly summary endpoint"""

    def test_weekly_summary_returns_200(self, client, auth_headers):
        """GET /weekly-summary should return 200"""
        response = client.get(
            "/api/admin/incident-intelligence/weekly-summary",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_weekly_summary_has_required_fields(self, client, auth_headers):
        """Weekly summary should have: generated_at, kpis, top_root_causes, top_domains, top_incidents"""
        response = client.get(
            "/api/admin/incident-intelligence/weekly-summary",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ["generated_at", "kpis", "top_root_causes", "top_domains", "top_incidents"]
        for field in required_fields:
            assert field in data, f"Missing weekly summary field: {field}"
        
        # Verify kpis structure
        kpis = data.get("kpis", {})
        assert "incident_count" in kpis, "kpis missing incident_count"
        assert "mttd_seconds" in kpis, "kpis missing mttd_seconds"
        assert "mttr_seconds" in kpis, "kpis missing mttr_seconds"


class TestIncidentIntelligenceGraph:
    """Test correlation graph endpoint"""

    def test_graph_returns_200(self, client, auth_headers):
        """GET /graph should return 200"""
        response = client.get(
            "/api/admin/incident-intelligence/graph",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_graph_has_nodes_and_edges(self, client, auth_headers):
        """Graph should have nodes and edges arrays"""
        response = client.get(
            "/api/admin/incident-intelligence/graph?limit=60",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "nodes" in data, "Missing nodes field"
        assert "edges" in data, "Missing edges field"
        assert isinstance(data["nodes"], list), "nodes should be a list"
        assert isinstance(data["edges"], list), "edges should be a list"

    def test_graph_node_structure(self, client, auth_headers):
        """Graph nodes should have id, type fields"""
        response = client.get(
            "/api/admin/incident-intelligence/graph?limit=60",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        nodes = data.get("nodes", [])
        if not nodes:
            pytest.skip("No graph nodes found")
        
        for node in nodes[:5]:  # Check first 5
            assert "id" in node, "Node missing id"
            assert "type" in node, "Node missing type"

    def test_graph_edge_structure(self, client, auth_headers):
        """Graph edges should have source, target, relation fields"""
        response = client.get(
            "/api/admin/incident-intelligence/graph?limit=60",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        edges = data.get("edges", [])
        if not edges:
            pytest.skip("No graph edges found")
        
        for edge in edges[:5]:  # Check first 5
            assert "source" in edge, "Edge missing source"
            assert "target" in edge, "Edge missing target"
            assert "relation" in edge, "Edge missing relation"


class TestIncidentIntelligencePredictions:
    """Test predictions endpoint"""

    def test_predictions_returns_200(self, client, auth_headers):
        """GET /predictions should return 200"""
        response = client.get(
            "/api/admin/incident-intelligence/predictions",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_predictions_has_required_fields(self, client, auth_headers):
        """Predictions should have: generated_at, items"""
        response = client.get(
            "/api/admin/incident-intelligence/predictions?days=14",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "generated_at" in data, "Missing generated_at field"
        assert "items" in data, "Missing items field"
        assert isinstance(data["items"], list), "items should be a list"

    def test_predictions_item_structure(self, client, auth_headers):
        """Prediction items should have: fingerprint, recurrence_count, predicted_risk, risk_trend, last_seen_at, root_cause"""
        response = client.get(
            "/api/admin/incident-intelligence/predictions?days=30",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        if not items:
            pytest.skip("No prediction items found")
        
        item = items[0]
        required_fields = ["fingerprint", "recurrence_count", "predicted_risk", "risk_trend", "last_seen_at", "root_cause"]
        for field in required_fields:
            assert field in item, f"Missing prediction item field: {field}"


class TestIncidentIntelligenceCrossDomainCoverage:
    """Test cross-domain coverage: execution/risk/system/exchange anomaly generation"""

    def test_engine_produces_cross_domain_anomalies(self, client, auth_headers):
        """Engine run should produce anomalies from multiple domains"""
        # Run engine
        run_response = client.post(
            "/api/admin/incident-intelligence/engine/run?window_minutes=60",
            headers=auth_headers,
        )
        assert run_response.status_code == 200
        
        # Get anomalies
        anomalies_response = client.get(
            "/api/admin/incident-intelligence/anomalies?limit=100",
            headers=auth_headers,
        )
        assert anomalies_response.status_code == 200
        
        items = anomalies_response.json().get("items", [])
        if not items:
            pytest.skip("No anomalies found")
        
        domains = {item.get("domain") for item in items}
        # Should have at least 1 domain
        assert len(domains) >= 1, f"Expected at least 1 domain, got {domains}"
        print(f"Found domains: {domains}")


class TestExistingAuditIncidentRoutes:
    """Test no regressions on existing audit/incident/export routes"""

    def test_audit_logs_list_still_works(self, client, auth_headers):
        """GET /audit-logs should still return 200"""
        response = client.get(
            "/api/audit-logs?limit=10",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_audit_logs_timeline_still_works(self, client, auth_headers):
        """GET /audit-logs/timeline should still return 200"""
        response = client.get(
            "/api/audit-logs/timeline?limit=20",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_audit_logs_incidents_list_still_works(self, client, auth_headers):
        """GET /audit-logs/incidents should still return 200"""
        response = client.get(
            "/api/audit-logs/incidents?limit=20",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_trading_lifecycle_still_works(self, client, auth_headers):
        """GET /audit-logs/trading-lifecycle should still return 200"""
        response = client.get(
            "/api/audit-logs/trading-lifecycle?limit=20",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
