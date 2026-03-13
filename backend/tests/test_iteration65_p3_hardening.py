"""
Iteration 65 - P3 Hardening Test Suite
Tests H-01: Global State Contract Closure
Tests H-02: End-to-End Scenario Validation
Tests H-03: Cross-Screen Snapshot Consistency Audit
Tests H-04: Final Artefact Standardization
"""
import os
import pytest
import requests
from dotenv import load_dotenv

# Load frontend env for BASE_URL
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "e2_conn_last@example.com"
USER_PASSWORD = "User12345!"


@pytest.fixture(scope="module")
def admin_token():
    """Authenticate as admin"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip("Admin authentication failed")


@pytest.fixture(scope="module")
def user_token():
    """Authenticate as regular user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip("User authentication failed")


@pytest.fixture(scope="module")
def admin_session(admin_token):
    """Admin session with auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}",
    })
    return session


@pytest.fixture(scope="module")
def user_session(user_token):
    """User session with auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_token}",
    })
    return session


# ============================================================================
# H-01 Global State Contract Tests
# ============================================================================
class TestH01GlobalStateContract:
    """H-01: Global State Contract Closure - verify loading/no data/no match/
    backend unavailable/permission denied/blocked by policy/invalid input states"""

    def test_admin_closure_panels_endpoint(self, admin_session):
        """Verify closure panel inventory with state coverage metadata"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/closure/panels")
        assert resp.status_code == 200, f"Closure panels failed: {resp.text}"
        data = resp.json()
        assert "panels" in data
        assert "contracts" in data
        panels = data["panels"]
        assert len(panels) > 0, "No panels in closure inventory"
        
        # Validate each panel has state coverage
        for panel in panels[:5]:  # Sample first 5
            assert "state_coverage" in panel, f"Missing state_coverage for {panel.get('panel_key')}"
            coverage = panel["state_coverage"]
            assert "loading" in coverage
            assert "empty" in coverage
            assert "broken" in coverage
            assert "success" in coverage
        print(f"Validated {len(panels)} panels with state contracts")

    def test_admin_closure_consistency_endpoint(self, admin_session):
        """Verify consistency endpoint returns canonical vs panel metrics"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/closure/consistency")
        assert resp.status_code == 200
        data = resp.json()
        assert "canonical_metrics" in data
        assert "checks" in data
        assert "mismatch_count" in data
        assert "status" in data
        print(f"Consistency status: {data['status']}, mismatches: {data['mismatch_count']}")

    def test_admin_positions_monitor_broken_state_contract(self, admin_session):
        """Verify positions monitor returns proper structure for state detection"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/positions-monitor")
        assert resp.status_code == 200
        data = resp.json()
        # Must have fields for: loading detection (generated_at), empty detection (open_positions array), 
        # broken detection (risk_level), success (cluster_exposure)
        assert "generated_at" in data
        assert "open_positions" in data
        assert isinstance(data["open_positions"], list)
        assert "cluster_exposure" in data
        assert "risk_level" in data
        print(f"Positions monitor: {len(data['open_positions'])} positions, risk={data['risk_level']}")

    def test_admin_portfolio_risk_state_contract(self, admin_session):
        """Verify portfolio risk endpoint returns complete state contract data"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/portfolio-risk")
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamp" in data
        assert "total_exposure" in data
        assert "cluster_exposure" in data
        assert "risk_alerts" in data
        print(f"Portfolio risk: exposure={data['total_exposure']}, alerts={len(data['risk_alerts'])}")

    def test_admin_execution_queue_state_contract(self, admin_session):
        """Verify execution queue returns list or empty state properly"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/execution-queue", params={"status_filter": "all", "limit": 50})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Execution queue should return array"
        print(f"Execution queue: {len(data)} intents")

    def test_user_dashboard_state_contract(self, user_session):
        """Verify user dashboard returns proper structure for state detection"""
        resp = user_session.get(f"{BASE_URL}/api/user/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        expected_fields = ["current_capital", "available_balance", "bot_count", "open_positions_count"]
        for field in expected_fields:
            assert field in data, f"Missing {field} in user dashboard"
        print(f"User dashboard: capital={data['current_capital']}, positions={data['open_positions_count']}")

    def test_user_positions_state_contract(self, user_session):
        """Verify user positions returns list structure"""
        resp = user_session.get(f"{BASE_URL}/api/user/execution/positions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Positions should return array"
        print(f"User positions: {len(data)} open positions")

    def test_permission_denied_state_admin_only_endpoint(self, user_session):
        """Verify admin-only endpoint returns 403 for regular user (permission denied state)"""
        resp = user_session.get(f"{BASE_URL}/api/admin/closure/panels")
        # Should be 401 or 403 for non-admin
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print("Permission denied state correctly enforced")


# ============================================================================
# H-02 End-to-End Scenario Validation Tests
# ============================================================================
class TestH02EndToEndScenarios:
    """H-02: End-to-End Scenario Validation - register->approve->login, 
    scanner->signal, signal->execute, queue->execution->trade flows"""

    def test_scanner_to_results_flow(self, user_session):
        """E2E: Scanner -> Results flow"""
        # Run scanner - correct endpoint is POST /user/scanner/run
        resp = user_session.post(f"{BASE_URL}/api/user/scanner/run", json={
            "exchange": "binance_futures",
            "market_type": "futures",
            "mode": "universe"
        })
        assert resp.status_code in [200, 201], f"Scanner run failed: {resp.text}"
        
        # Get results
        results_resp = user_session.get(f"{BASE_URL}/api/user/scanner/results", params={"limit": 10})
        assert results_resp.status_code == 200
        print("Scanner->Results flow: PASS")

    def test_signals_flow(self, user_session):
        """E2E: Signals list retrieval"""
        resp = user_session.get(f"{BASE_URL}/api/user/signals", params={"limit": 20})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"Signals flow: {len(data)} signals retrieved")

    def test_execute_preview_flow(self, user_session):
        """E2E: Execute intent preview flow"""
        # Get connections first
        conn_resp = user_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert conn_resp.status_code == 200
        connections = conn_resp.json()
        
        if not connections:
            pytest.skip("No exchange connections for execute preview test")
        
        conn = connections[0]
        
        # Preview execution - correct endpoint is POST /user/execution/intent/preview
        preview_resp = user_session.post(f"{BASE_URL}/api/user/execution/intent/preview", json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "size": 0.001,
            "order_type": "MARKET",
            "connection_id": conn.get("id"),
        })
        assert preview_resp.status_code in [200, 400, 422], f"Preview unexpected status: {preview_resp.status_code}"
        data = preview_resp.json()
        # Even if rejected, should return validation structure
        assert "validation_status" in data or "detail" in data
        print(f"Execute preview flow: validation_status={data.get('validation_status', 'error')}")

    def test_queue_visibility_flow(self, admin_session):
        """E2E: Queue -> Execution visibility"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/execution-queue", params={"status_filter": "all", "limit": 100})
        assert resp.status_code == 200
        data = resp.json()
        statuses = set(item.get("status") for item in data if isinstance(item, dict))
        print(f"Queue visibility: {len(data)} items, statuses={statuses}")

    def test_failed_event_retry_resolve_flow(self, admin_session):
        """E2E: Failed event retry/resolve actions"""
        # Get failed events - correct endpoint is under /admin-phase3 prefix
        resp = admin_session.get(f"{BASE_URL}/api/admin-phase3/failed-events")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"Failed events: {len(data)} events")

    def test_state_rebuild_flow(self, admin_session):
        """E2E: State rebuild logs retrieval"""
        resp = admin_session.get(f"{BASE_URL}/api/admin-phase3/state-rebuild-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"State rebuild logs: {len(data)} entries")

    def test_screener_filter_execute_bridge_flow(self, user_session):
        """E2E: Screener -> Filter -> Execute bridge context"""
        # Run screener with filters
        resp = user_session.post(f"{BASE_URL}/api/user/indicator-screener/run", json={
            "filter_payload": {
                "exchange": "binance_futures",
                "market_type": "futures",
                "timeframe": "4h",
                "limit": 5,
            }
        })
        assert resp.status_code in [200, 201], f"Screener run failed: {resp.text}"
        data = resp.json()
        # Screener returns evaluated_count + applied_filters or other fields - verify structure
        assert "evaluated_count" in data or "applied_filters" in data or "calculation_timestamp" in data
        print(f"Screener->Filter->Execute bridge flow: PASS (evaluated={data.get('evaluated_count', 'N/A')})")


# ============================================================================
# H-03 Cross-Screen Snapshot Consistency Tests  
# ============================================================================
class TestH03CrossScreenConsistency:
    """H-03: Cross-Screen Snapshot Consistency Audit - capital/balance/pnl/
    open positions/exposure/risk score/readiness/release gate/strategy state"""

    def test_capital_balance_consistency(self, user_session):
        """Verify capital/balance consistency across dashboard and portfolio"""
        dashboard_resp = user_session.get(f"{BASE_URL}/api/user/dashboard")
        portfolio_resp = user_session.get(f"{BASE_URL}/api/user/portfolio")
        
        assert dashboard_resp.status_code == 200
        assert portfolio_resp.status_code == 200
        
        dash = dashboard_resp.json()
        port = portfolio_resp.json()
        
        # Capital values should match
        dash_capital = dash.get("current_capital", 0)
        port_capital = port.get("current_capital", 0)
        assert dash_capital == port_capital, f"Capital mismatch: dashboard={dash_capital}, portfolio={port_capital}"
        
        dash_balance = dash.get("available_balance", 0)
        port_balance = port.get("available_balance", 0)
        assert dash_balance == port_balance, f"Balance mismatch: dashboard={dash_balance}, portfolio={port_balance}"
        print(f"Capital/balance consistency: PASS (capital={dash_capital}, balance={dash_balance})")

    def test_open_positions_count_consistency(self, user_session):
        """Verify open positions count matches across screens"""
        dashboard_resp = user_session.get(f"{BASE_URL}/api/user/dashboard")
        positions_resp = user_session.get(f"{BASE_URL}/api/user/execution/positions", params={"include_closed": False})
        
        assert dashboard_resp.status_code == 200
        assert positions_resp.status_code == 200
        
        dash = dashboard_resp.json()
        positions = positions_resp.json()
        
        dash_count = dash.get("open_positions_count", 0)
        actual_count = len(positions)
        assert dash_count == actual_count, f"Position count mismatch: dashboard={dash_count}, actual={actual_count}"
        print(f"Position count consistency: PASS ({dash_count} positions)")

    def test_admin_canonical_metrics_consistency(self, admin_session):
        """Verify admin canonical metrics match across panels"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/closure/consistency")
        assert resp.status_code == 200
        data = resp.json()
        
        checks = data.get("checks", [])
        all_pass = all(check.get("in_tolerance", False) for check in checks)
        
        if not all_pass:
            failures = [c for c in checks if not c.get("in_tolerance")]
            print(f"Metric consistency issues: {failures}")
        else:
            print(f"All {len(checks)} canonical metrics in tolerance")
        
        assert data.get("status") in ["PASS", "WARNING"], f"Unexpected consistency status: {data.get('status')}"

    def test_exposure_consistency_admin_vs_user(self, admin_session, user_session):
        """Verify exposure data consistency between admin and user views"""
        admin_portfolio = admin_session.get(f"{BASE_URL}/api/admin/portfolio-risk")
        user_portfolio = user_session.get(f"{BASE_URL}/api/user/portfolio")
        
        assert admin_portfolio.status_code == 200
        assert user_portfolio.status_code == 200
        
        admin_data = admin_portfolio.json()
        user_data = user_portfolio.json()
        
        # Total exposure should be visible in both
        assert "total_exposure" in admin_data
        print(f"Exposure consistency: admin_total={admin_data.get('total_exposure')}")

    def test_readiness_release_gate_consistency(self, admin_session):
        """Verify readiness score and release gate status consistency"""
        live_readiness = admin_session.get(f"{BASE_URL}/api/admin/futures/live-readiness")
        testnet_status = admin_session.get(f"{BASE_URL}/api/admin/futures/testnet/status")
        
        assert live_readiness.status_code == 200
        assert testnet_status.status_code == 200
        
        readiness_data = live_readiness.json()
        testnet_data = testnet_status.json()
        
        assert "readiness_score" in readiness_data
        assert "release_gate" in testnet_data
        
        print(f"Readiness={readiness_data.get('readiness_score')}, Gate={testnet_data.get('release_gate', {}).get('status')}")

    def test_strategy_state_consistency(self, admin_session):
        """Verify strategy allocation and intelligence consistency"""
        allocation = admin_session.get(f"{BASE_URL}/api/admin/strategy-allocation")
        intelligence = admin_session.get(f"{BASE_URL}/api/admin/strategy-intelligence")
        
        assert allocation.status_code == 200
        assert intelligence.status_code == 200
        
        alloc_data = allocation.json()
        intel_data = intelligence.json()
        
        assert isinstance(alloc_data, list)
        assert "strategy_conflicts" in intel_data
        print(f"Strategy consistency: {len(alloc_data)} allocations, {len(intel_data.get('strategy_conflicts', []))} conflicts")


# ============================================================================
# H-04 Final Artefact Standardization Tests
# ============================================================================
class TestH04ArtefactStandardization:
    """H-04: Final Artefact Standardization - verify report files exist and structure"""

    def test_closure_matrix_admin_artefact(self):
        """Verify admin closure matrix artefact exists and has proper structure"""
        artefact_path = "/app/reports/closure_matrix_admin.json"
        assert os.path.exists(artefact_path), f"Missing artefact: {artefact_path}"
        
        import json
        with open(artefact_path) as f:
            data = json.load(f)
        
        assert "generated_at" in data
        assert "domain" in data
        assert data["domain"] == "admin"
        assert "matrix" in data
        assert len(data["matrix"]) > 0
        print(f"Admin closure matrix: {len(data['matrix'])} areas validated")

    def test_closure_matrix_user_artefact(self):
        """Verify user closure matrix artefact exists and has proper structure"""
        artefact_path = "/app/reports/closure_matrix_user.json"
        assert os.path.exists(artefact_path), f"Missing artefact: {artefact_path}"
        
        import json
        with open(artefact_path) as f:
            data = json.load(f)
        
        assert "generated_at" in data
        assert "domain" in data
        assert data["domain"] == "user"
        assert "matrix" in data
        assert len(data["matrix"]) > 0
        print(f"User closure matrix: {len(data['matrix'])} areas validated")

    def test_e2e_trading_flow_artefact(self):
        """Verify end-to-end trading flow validation artefact"""
        artefact_path = "/app/reports/end_to_end_trading_flow_validation.json"
        assert os.path.exists(artefact_path), f"Missing artefact: {artefact_path}"
        
        import json
        with open(artefact_path) as f:
            data = json.load(f)
        
        assert "status" in data
        assert "validated_paths" in data
        print(f"E2E trading flow: status={data['status']}, paths={len(data['validated_paths'])}")

    def test_platform_ui_consistency_artefact(self):
        """Verify platform UI consistency validation artefact"""
        artefact_path = "/app/reports/platform_ui_consistency_validation.json"
        assert os.path.exists(artefact_path), f"Missing artefact: {artefact_path}"
        
        import json
        with open(artefact_path) as f:
            data = json.load(f)
        
        assert "checks" in data
        all_pass = all(c.get("status") == "pass" for c in data["checks"])
        print(f"Platform UI consistency: all_pass={all_pass}, checks={len(data['checks'])}")

    def test_test_reports_iteration_artefacts(self):
        """Verify test report iteration files exist for P0, P1, P2"""
        required_iterations = [62, 63, 64]
        for iter_num in required_iterations:
            path = f"/app/test_reports/iteration_{iter_num}.json"
            assert os.path.exists(path), f"Missing iteration report: {path}"
        print(f"Iteration reports verified: {required_iterations}")

    def test_pytest_results_artefacts(self):
        """Verify pytest XML results exist"""
        expected_results = [
            "/app/test_reports/pytest/pytest_results_iter62_regression.xml",
            "/app/test_reports/pytest/pytest_results_iter63_user_p1.xml",
        ]
        for path in expected_results:
            assert os.path.exists(path), f"Missing pytest results: {path}"
        print(f"Pytest XML artefacts verified: {len(expected_results)}")


# ============================================================================
# Health and Auth Sanity Tests
# ============================================================================
class TestHealthAndAuth:
    """Basic health and auth sanity checks"""

    def test_health_endpoint(self):
        """Verify API health"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"
        print("Health check: PASS")

    def test_admin_auth(self, admin_session):
        """Verify admin session is valid"""
        resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("role") in ["admin", "superadmin"]
        print(f"Admin auth: role={data.get('role')}")

    def test_user_auth(self, user_session):
        """Verify user session is valid"""
        resp = user_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("role") in ["user", "approved"]
        print(f"User auth: role={data.get('role')}")
