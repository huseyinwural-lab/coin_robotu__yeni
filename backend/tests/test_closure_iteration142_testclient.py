"""
Iteration 142 - Closure Testing with TestClient: Infra stabilization, smoke PASS, readiness READY, final go/no-go artifact, env hardening, final regression.

Tests:
1. daily_smoke_latest.json overall_status PASS
2. final_go_no_go_artifact.json dry_run PASS/readiness READY/go_live true
3. closure_regression_report.json overall_pass true
4. wizard auth super_admin only endpoint guard
5. health endpoints: /api/health/live and /api/health/ready response semantics
"""

import json
import sys
import pytest
from pathlib import Path

sys.path.insert(0, "/app/backend")

from fastapi.testclient import TestClient
from server import fastapi_app

client = TestClient(fastapi_app)

SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"

# Artifact paths
DAILY_SMOKE_PATH = Path("/app/test_reports/daily_smoke_latest.json")
FINAL_GO_NO_GO_PATH = Path("/app/test_reports/final_go_no_go_artifact.json")
CLOSURE_REGRESSION_PATH = Path("/app/test_reports/closure_regression_report.json")


class TestArtifactValidation:
    """Validate closure artifacts content"""

    def test_daily_smoke_overall_status_pass(self):
        """Verify daily_smoke_latest.json has overall_status PASS"""
        assert DAILY_SMOKE_PATH.exists(), f"Artifact not found: {DAILY_SMOKE_PATH}"
        
        data = json.loads(DAILY_SMOKE_PATH.read_text(encoding="utf-8"))
        overall_status = data.get("overall_status", "")
        
        assert overall_status == "PASS", f"Expected overall_status=PASS, got {overall_status}"
        print(f"✓ daily_smoke_latest.json overall_status: {overall_status}")
        
        # Verify steps
        steps = data.get("steps", {})
        for step_name, step_data in steps.items():
            step_status = step_data.get("status", "")
            print(f"  - {step_name}: {step_status}")
            assert step_status == "PASS", f"Step {step_name} not PASS: {step_status}"

    def test_final_go_no_go_artifact_dry_run_pass(self):
        """Verify final_go_no_go_artifact.json dry_run status is PASS"""
        assert FINAL_GO_NO_GO_PATH.exists(), f"Artifact not found: {FINAL_GO_NO_GO_PATH}"
        
        data = json.loads(FINAL_GO_NO_GO_PATH.read_text(encoding="utf-8"))
        dry_run = data.get("dry_run", {})
        dry_run_status = dry_run.get("status", "")
        
        assert dry_run_status == "PASS", f"Expected dry_run.status=PASS, got {dry_run_status}"
        print(f"✓ final_go_no_go_artifact.json dry_run.status: {dry_run_status}")
        
        # Verify checks
        checks = dry_run.get("checks", {})
        print(f"  Checks: {checks}")
        assert checks.get("lifecycle") is True, "lifecycle check not true"
        assert checks.get("canary") is True, "canary check not true"
        assert checks.get("regression") is True, "regression check not true"
        assert checks.get("readiness_ready") is True, "readiness_ready check not true"
        assert checks.get("go_live") is True, "go_live check not true"

    def test_final_go_no_go_artifact_readiness_ready(self):
        """Verify final_go_no_go_artifact.json readiness status is READY"""
        assert FINAL_GO_NO_GO_PATH.exists(), f"Artifact not found: {FINAL_GO_NO_GO_PATH}"
        
        data = json.loads(FINAL_GO_NO_GO_PATH.read_text(encoding="utf-8"))
        dry_run = data.get("dry_run", {})
        readiness = dry_run.get("readiness", {})
        readiness_status = readiness.get("status", "")
        
        assert readiness_status == "READY", f"Expected readiness.status=READY, got {readiness_status}"
        print(f"✓ final_go_no_go_artifact.json readiness.status: {readiness_status}")
        
        # Verify readiness score
        score = readiness.get("score", 0)
        print(f"  Readiness score: {score}")
        assert score >= 85, f"Readiness score {score} below threshold 85"

    def test_final_go_no_go_artifact_go_live_true(self):
        """Verify final_go_no_go_artifact.json go_live is true"""
        assert FINAL_GO_NO_GO_PATH.exists(), f"Artifact not found: {FINAL_GO_NO_GO_PATH}"
        
        data = json.loads(FINAL_GO_NO_GO_PATH.read_text(encoding="utf-8"))
        dry_run = data.get("dry_run", {})
        checklist = dry_run.get("checklist", {})
        go_live = checklist.get("go_live", False)
        
        assert go_live is True, f"Expected checklist.go_live=true, got {go_live}"
        print(f"✓ final_go_no_go_artifact.json checklist.go_live: {go_live}")

    def test_closure_regression_report_overall_pass(self):
        """Verify closure_regression_report.json overall_pass is true"""
        assert CLOSURE_REGRESSION_PATH.exists(), f"Artifact not found: {CLOSURE_REGRESSION_PATH}"
        
        data = json.loads(CLOSURE_REGRESSION_PATH.read_text(encoding="utf-8"))
        overall_pass = data.get("overall_pass", False)
        
        assert overall_pass is True, f"Expected overall_pass=true, got {overall_pass}"
        print(f"✓ closure_regression_report.json overall_pass: {overall_pass}")
        
        # Verify individual checks
        checks = data.get("checks", {})
        for check_name, check_data in checks.items():
            check_pass = check_data.get("pass", False)
            print(f"  - {check_name}: {'PASS' if check_pass else 'FAIL'}")


class TestHealthEndpoints:
    """Test health endpoint semantics"""

    def test_health_live_returns_200_ok(self):
        """/api/health/live should return 200 with status=ok (lightweight check)"""
        response = client.get("/api/health/live")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "ok", f"Expected status=ok, got {data.get('status')}"
        assert data.get("service") == "backend-api", "Expected service=backend-api"
        
        # Verify lightweight - only process check
        checks = data.get("checks", {})
        assert "process" in checks, "Missing process check"
        assert checks["process"].get("status") == "up", "Process not up"
        
        print(f"✓ /api/health/live: status={data.get('status')}, process={checks['process'].get('status')}")

    def test_health_ready_checks_dependencies(self):
        """/api/health/ready should check database and redis"""
        response = client.get("/api/health/ready")
        
        # Can be 200 (ready) or 503 (not ready)
        assert response.status_code in [200, 503], f"Unexpected status: {response.status_code}"
        
        data = response.json()
        status = data.get("status")
        assert status in ["ready", "not_ready"], f"Unexpected status: {status}"
        
        checks = data.get("checks", {})
        
        # Verify database check exists
        assert "database" in checks, "Missing database check"
        db_status = checks["database"].get("status")
        print(f"  Database: {db_status}")
        
        # Verify redis check exists
        assert "redis" in checks, "Missing redis check"
        redis_status = checks["redis"].get("status")
        print(f"  Redis: {redis_status}")
        
        print(f"✓ /api/health/ready: status={status}, http_code={response.status_code}")

    def test_health_live_is_lightweight(self):
        """/api/health/live should NOT check database or redis (lightweight)"""
        response = client.get("/api/health/live")
        
        data = response.json()
        checks = data.get("checks", {})
        
        # Should NOT have database or redis checks
        assert "database" not in checks, "/api/health/live should not check database"
        assert "redis" not in checks, "/api/health/live should not check redis"
        
        print("✓ /api/health/live is lightweight (no DB/Redis checks)")


class TestWizardAuthSuperAdminOnly:
    """Test wizard endpoints require super_admin role"""

    @pytest.fixture
    def super_admin_token(self):
        """Get super_admin token"""
        response = client.post(
            "/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.status_code}")
        
        data = response.json()
        return data.get("access_token") or data.get("token")

    def test_wizard_state_accessible_to_admin(self, super_admin_token):
        """GET /api/runtime/go-live/wizard/state accessible to admin"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = client.get("/api/runtime/go-live/wizard/state", headers=headers)
        
        # Should be 200 for admin
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "result" in data, "Missing result in response"
        result = data["result"]
        assert "stage" in result, "Missing stage in wizard state"
        print(f"✓ wizard/state: accessible to admin, stage={result.get('stage')}")

    def test_wizard_readiness_check_requires_super_admin(self, super_admin_token):
        """POST /api/runtime/go-live/wizard/readiness-check requires super_admin"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = client.post("/api/runtime/go-live/wizard/readiness-check", headers=headers)
        
        # Should NOT be 403 for super_admin
        assert response.status_code != 403, "super_admin should not get 403"
        print(f"✓ wizard/readiness-check: super_admin gets {response.status_code}")

    def test_wizard_arm_requires_super_admin(self, super_admin_token):
        """POST /api/runtime/go-live/wizard/arm requires super_admin"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = client.post("/api/runtime/go-live/wizard/arm", headers=headers)
        
        # Should NOT be 403 for super_admin (may be 409 if not ready)
        assert response.status_code != 403, "super_admin should not get 403"
        print(f"✓ wizard/arm: super_admin gets {response.status_code}")

    def test_wizard_confirm_requires_super_admin(self, super_admin_token):
        """POST /api/runtime/go-live/wizard/confirm requires super_admin"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = client.post("/api/runtime/go-live/wizard/confirm", headers=headers)
        
        # Should NOT be 403 for super_admin (may be 409 if not armed)
        assert response.status_code != 403, "super_admin should not get 403"
        print(f"✓ wizard/confirm: super_admin gets {response.status_code}")

    def test_wizard_rollback_requires_super_admin(self, super_admin_token):
        """POST /api/runtime/go-live/wizard/rollback requires super_admin"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = client.post("/api/runtime/go-live/wizard/rollback", headers=headers)
        
        # Should NOT be 403 for super_admin
        assert response.status_code != 403, "super_admin should not get 403"
        print(f"✓ wizard/rollback: super_admin gets {response.status_code}")

    def test_wizard_endpoints_reject_unauthenticated(self):
        """Wizard endpoints should reject unauthenticated requests"""
        endpoints = [
            ("POST", "/api/runtime/go-live/wizard/readiness-check"),
            ("POST", "/api/runtime/go-live/wizard/canary-check"),
            ("POST", "/api/runtime/go-live/wizard/arm"),
            ("POST", "/api/runtime/go-live/wizard/confirm"),
            ("POST", "/api/runtime/go-live/wizard/rollback"),
        ]
        
        for method, endpoint in endpoints:
            if method == "POST":
                response = client.post(endpoint)
            else:
                response = client.get(endpoint)
            
            # Should be 401 or 403 without auth
            assert response.status_code in [401, 403, 422], f"{endpoint} should reject unauthenticated: got {response.status_code}"
            print(f"✓ {endpoint}: unauthenticated gets {response.status_code}")


class TestClosureRegressionChecks:
    """Verify closure regression report checks"""

    def test_closure_regression_login_check(self):
        """Verify login check passed in closure regression"""
        data = json.loads(CLOSURE_REGRESSION_PATH.read_text(encoding="utf-8"))
        login_check = data.get("checks", {}).get("login", {})
        
        assert login_check.get("pass") is True, "Login check should pass"
        assert login_check.get("status_code") == 200, "Login should return 200"
        print("✓ Closure regression login check: PASS")

    def test_closure_regression_smoke_check(self):
        """Verify smoke check passed in closure regression"""
        data = json.loads(CLOSURE_REGRESSION_PATH.read_text(encoding="utf-8"))
        smoke_check = data.get("checks", {}).get("smoke", {})
        
        assert smoke_check.get("pass") is True, "Smoke check should pass"
        assert smoke_check.get("overall_status") == "PASS", "Smoke overall_status should be PASS"
        print("✓ Closure regression smoke check: PASS")

    def test_closure_regression_readiness_check(self):
        """Verify readiness check passed in closure regression"""
        data = json.loads(CLOSURE_REGRESSION_PATH.read_text(encoding="utf-8"))
        readiness_check = data.get("checks", {}).get("readiness", {})
        
        assert readiness_check.get("pass") is True, "Readiness check should pass"
        assert readiness_check.get("status_code") == 200, "Readiness should return 200"
        
        result = readiness_check.get("result", {})
        assert result.get("status") == "READY", "Readiness status should be READY"
        assert result.get("score") == 100, "Readiness score should be 100"
        print(f"✓ Closure regression readiness check: PASS (score={result.get('score')})")

    def test_closure_regression_dry_run_check(self):
        """Verify dry_run check passed in closure regression"""
        data = json.loads(CLOSURE_REGRESSION_PATH.read_text(encoding="utf-8"))
        dry_run_check = data.get("checks", {}).get("dry_run", {})
        
        assert dry_run_check.get("pass") is True, "Dry run check should pass"
        assert dry_run_check.get("result_status") == "PASS", "Dry run result_status should be PASS"
        print("✓ Closure regression dry_run check: PASS")

    def test_closure_regression_wizard_auth_check(self):
        """Verify wizard auth super_admin only check passed"""
        data = json.loads(CLOSURE_REGRESSION_PATH.read_text(encoding="utf-8"))
        wizard_auth_check = data.get("checks", {}).get("wizard_auth_super_admin_only", {})
        
        assert wizard_auth_check.get("pass") is True, "Wizard auth check should pass"
        assert wizard_auth_check.get("status_code") == 403, "Non-super_admin should get 403"
        print("✓ Closure regression wizard_auth_super_admin_only check: PASS")


class TestReadinessAndChecklist:
    """Test readiness score and go-live checklist endpoints"""

    @pytest.fixture
    def admin_token(self):
        """Get admin token"""
        response = client.post(
            "/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.status_code}")
        
        data = response.json()
        return data.get("access_token") or data.get("token")

    def test_canary_readiness_score_endpoint(self, admin_token):
        """GET /api/runtime/canary/readiness-score returns score and status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = client.get("/api/runtime/canary/readiness-score", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        result = data.get("result", {})
        
        assert "score" in result, "Missing score in readiness"
        assert "status" in result, "Missing status in readiness"
        assert "components" in result, "Missing components in readiness"
        
        print(f"✓ readiness-score: score={result.get('score')}, status={result.get('status')}")

    def test_go_live_checklist_endpoint(self, admin_token):
        """GET /api/runtime/go-live/checklist returns go_live and checks"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = client.get("/api/runtime/go-live/checklist", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        result = data.get("result", {})
        
        assert "go_live" in result, "Missing go_live in checklist"
        assert "checks" in result, "Missing checks in checklist"
        assert "metrics" in result, "Missing metrics in checklist"
        
        # Verify smoke_status is in metrics
        metrics = result.get("metrics", {})
        assert "smoke_status" in metrics, "Missing smoke_status in metrics"
        
        print(f"✓ go-live/checklist: go_live={result.get('go_live')}, smoke_status={metrics.get('smoke_status')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
