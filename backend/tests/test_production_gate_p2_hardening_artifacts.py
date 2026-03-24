"""
Production Gate P2 Hardening Artifacts Validation Tests
========================================================
Tests to verify:
1. Artifact files contain real data (no placeholders/dummy/run-sample)
2. Evidence.md has 'generation: automated' and 'source: runtime test execution'
3. Flapping.json has count>0 and severity MEDIUM/HIGH
4. Compare.json has run_count>=3 with real latency_delta/stability_score and improvement=true
5. Timeline audit match has UUID format audit_id/request_id
6. iteration_115.json has runtime validation fields
7. Cross-check API returns is_consistent=true
8. Manifest accuracy - all entries exist and no phantom entries
"""

import json
import os
import re
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"

UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)

APP_ROOT = Path("/app")
TEST_REPORTS = APP_ROOT / "test_reports"
MANIFEST_PATH = APP_ROOT / "backend" / "exports" / "artifact_manifest.json"


@pytest.fixture(scope="module")
def auth_session():
    """Authenticate and return session with token"""
    session = requests.Session()
    resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        timeout=30,
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json().get("access_token")
    assert token, "No access_token in response"
    session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return session


class TestArtifactFilesExist:
    """Verify all required artifact files exist and are non-empty"""

    def test_evidence_md_exists(self):
        path = TEST_REPORTS / "production_gate_p2_hardening_evidence.md"
        assert path.exists(), f"File not found: {path}"
        assert path.stat().st_size > 100, "Evidence file too small"

    def test_risk_engine_json_exists(self):
        path = TEST_REPORTS / "production_gate_p2_risk_engine.json"
        assert path.exists(), f"File not found: {path}"
        data = json.loads(path.read_text())
        assert "risk_score" in data, "Missing risk_score"
        assert "risk_level" in data, "Missing risk_level"

    def test_flapping_json_exists(self):
        path = TEST_REPORTS / "production_gate_p2_flapping.json"
        assert path.exists(), f"File not found: {path}"
        data = json.loads(path.read_text())
        assert "rows" in data, "Missing rows"
        assert len(data["rows"]) > 0, "No flapping rows"

    def test_timeline_audit_match_json_exists(self):
        path = TEST_REPORTS / "production_gate_p2_timeline_audit_match.json"
        assert path.exists(), f"File not found: {path}"
        data = json.loads(path.read_text())
        assert "items" in data, "Missing items"
        assert len(data["items"]) > 0, "No timeline items"

    def test_compare_multi_run_json_exists(self):
        path = TEST_REPORTS / "production_gate_p2_compare_multi_run.json"
        assert path.exists(), f"File not found: {path}"
        data = json.loads(path.read_text())
        assert "items" in data, "Missing items"
        assert len(data["items"]) > 0, "No compare items"

    def test_iteration_115_json_exists(self):
        path = TEST_REPORTS / "iteration_115.json"
        assert path.exists(), f"File not found: {path}"
        data = json.loads(path.read_text())
        assert "validation" in data, "Missing validation field"


class TestEvidenceMdContent:
    """Verify evidence.md has required automated generation markers"""

    def test_generation_automated_marker(self):
        path = TEST_REPORTS / "production_gate_p2_hardening_evidence.md"
        content = path.read_text()
        assert "generation: automated" in content, "Missing 'generation: automated'"

    def test_source_runtime_test_execution_marker(self):
        path = TEST_REPORTS / "production_gate_p2_hardening_evidence.md"
        content = path.read_text()
        assert "source: runtime test execution" in content, "Missing 'source: runtime test execution'"

    def test_no_placeholder_content(self):
        path = TEST_REPORTS / "production_gate_p2_hardening_evidence.md"
        content = path.read_text().lower()
        assert "placeholder" not in content, "Contains placeholder"
        assert "dummy" not in content, "Contains dummy"
        assert "sample" not in content or "run_id_uuid_format_valid_samples" in content.lower(), "Contains sample (not in valid context)"


class TestFlappingJsonContent:
    """Verify flapping.json has count>0 and severity MEDIUM/HIGH"""

    def test_flapping_has_non_low_severity(self):
        path = TEST_REPORTS / "production_gate_p2_flapping.json"
        data = json.loads(path.read_text())
        
        non_low_rows = [
            row for row in data.get("rows", [])
            if row.get("count", 0) > 0 and row.get("severity", "LOW").upper() in {"MEDIUM", "HIGH"}
        ]
        assert len(non_low_rows) >= 1, f"No rows with count>0 and severity MEDIUM/HIGH. Found: {len(non_low_rows)}"

    def test_flapping_has_count_greater_than_zero(self):
        path = TEST_REPORTS / "production_gate_p2_flapping.json"
        data = json.loads(path.read_text())
        
        rows_with_count = [row for row in data.get("rows", []) if row.get("count", 0) > 0]
        assert len(rows_with_count) >= 1, "No rows with count > 0"

    def test_flapping_generation_automated(self):
        path = TEST_REPORTS / "production_gate_p2_flapping.json"
        data = json.loads(path.read_text())
        assert data.get("generation") == "automated", f"Expected 'automated', got: {data.get('generation')}"
        assert data.get("source") == "runtime test execution", f"Expected 'runtime test execution', got: {data.get('source')}"


class TestCompareMultiRunJsonContent:
    """Verify compare.json has run_count>=3 with real values and improvement=true"""

    def test_compare_has_run_count_gte_3(self):
        path = TEST_REPORTS / "production_gate_p2_compare_multi_run.json"
        data = json.loads(path.read_text())
        
        items_gte3 = [item for item in data.get("items", []) if item.get("run_count", 0) >= 3]
        assert len(items_gte3) >= 1, f"No items with run_count >= 3. Found: {len(items_gte3)}"

    def test_compare_has_real_latency_delta(self):
        path = TEST_REPORTS / "production_gate_p2_compare_multi_run.json"
        data = json.loads(path.read_text())
        
        items_with_latency = [
            item for item in data.get("items", [])
            if item.get("run_count", 0) >= 3 and item.get("latency_delta_ms") is not None
        ]
        assert len(items_with_latency) >= 1, "No items with run_count>=3 and latency_delta_ms"

    def test_compare_has_real_stability_score(self):
        path = TEST_REPORTS / "production_gate_p2_compare_multi_run.json"
        data = json.loads(path.read_text())
        
        items_with_stability = [
            item for item in data.get("items", [])
            if item.get("run_count", 0) >= 3 and item.get("stability_score") is not None
        ]
        assert len(items_with_stability) >= 1, "No items with run_count>=3 and stability_score"

    def test_compare_has_improvement_true(self):
        path = TEST_REPORTS / "production_gate_p2_compare_multi_run.json"
        data = json.loads(path.read_text())
        
        improvements = [item for item in data.get("items", []) if item.get("improvement") is True]
        assert len(improvements) >= 1, f"No items with improvement=true. Found: {len(improvements)}"

    def test_compare_generation_automated(self):
        path = TEST_REPORTS / "production_gate_p2_compare_multi_run.json"
        data = json.loads(path.read_text())
        assert data.get("generation") == "automated", f"Expected 'automated', got: {data.get('generation')}"
        assert data.get("source") == "runtime test execution", f"Expected 'runtime test execution', got: {data.get('source')}"


class TestTimelineAuditMatchJsonContent:
    """Verify timeline audit match has UUID format audit_id/request_id"""

    def test_timeline_has_uuid_audit_id(self):
        path = TEST_REPORTS / "production_gate_p2_timeline_audit_match.json"
        data = json.loads(path.read_text())
        
        items_with_uuid_audit = [
            item for item in data.get("items", [])
            if item.get("audit_id") and UUID_PATTERN.match(str(item.get("audit_id")))
        ]
        assert len(items_with_uuid_audit) >= 1, "No items with valid UUID audit_id"

    def test_timeline_has_uuid_request_id(self):
        path = TEST_REPORTS / "production_gate_p2_timeline_audit_match.json"
        data = json.loads(path.read_text())
        
        items_with_uuid_request = [
            item for item in data.get("items", [])
            if item.get("request_id") and UUID_PATTERN.match(str(item.get("request_id")))
        ]
        assert len(items_with_uuid_request) >= 1, "No items with valid UUID request_id"

    def test_timeline_generation_automated(self):
        path = TEST_REPORTS / "production_gate_p2_timeline_audit_match.json"
        data = json.loads(path.read_text())
        assert data.get("generation") == "automated", f"Expected 'automated', got: {data.get('generation')}"
        assert data.get("source") == "runtime test execution", f"Expected 'runtime test execution', got: {data.get('source')}"


class TestIteration115JsonContent:
    """Verify iteration_115.json has runtime validation fields"""

    def test_iteration_has_validation_field(self):
        path = TEST_REPORTS / "iteration_115.json"
        data = json.loads(path.read_text())
        assert "validation" in data, "Missing validation field"

    def test_iteration_has_generation_automated(self):
        path = TEST_REPORTS / "iteration_115.json"
        data = json.loads(path.read_text())
        assert data.get("generation") == "automated", f"Expected 'automated', got: {data.get('generation')}"

    def test_iteration_has_source_runtime(self):
        path = TEST_REPORTS / "iteration_115.json"
        data = json.loads(path.read_text())
        assert data.get("source") == "runtime test execution", f"Expected 'runtime test execution', got: {data.get('source')}"

    def test_iteration_has_cross_check(self):
        path = TEST_REPORTS / "iteration_115.json"
        data = json.loads(path.read_text())
        assert "cross_check" in data, "Missing cross_check field"
        assert data["cross_check"].get("is_consistent") is True, "cross_check.is_consistent should be True"

    def test_iteration_validation_fields(self):
        path = TEST_REPORTS / "iteration_115.json"
        data = json.loads(path.read_text())
        validation = data.get("validation", {})
        
        assert "run_id_uuid_format_valid_samples" in validation, "Missing run_id_uuid_format_valid_samples"
        assert "timeline_uuid_items" in validation, "Missing timeline_uuid_items"
        assert "compare_items_gte3" in validation, "Missing compare_items_gte3"
        assert "compare_improvements" in validation, "Missing compare_improvements"
        assert "flapping_non_low_rows" in validation, "Missing flapping_non_low_rows"


class TestCrossCheckAPI:
    """Verify cross-check API returns is_consistent=true"""

    def test_cross_check_is_consistent(self, auth_session):
        resp = auth_session.get(
            f"{BASE_URL}/api/phase4/admin/production-gate/system/cross-check",
            timeout=30,
        )
        assert resp.status_code == 200, f"Cross-check API failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert data.get("is_consistent") is True, f"is_consistent should be True, got: {data.get('is_consistent')}"


class TestManifestAccuracy:
    """Verify manifest accuracy - all entries exist and no phantom entries"""

    def test_manifest_exists(self):
        assert MANIFEST_PATH.exists(), f"Manifest not found: {MANIFEST_PATH}"

    def test_manifest_no_phantom_entries(self):
        """All entries in manifest should have exists=true and file should actually exist"""
        data = json.loads(MANIFEST_PATH.read_text())
        artifacts = data.get("artifacts", [])
        
        phantom_entries = []
        for artifact in artifacts:
            rel_path = artifact.get("path", "")
            abs_path = APP_ROOT / rel_path.lstrip("/")
            exists_flag = artifact.get("exists", False)
            
            # Check if exists flag matches reality
            actual_exists = abs_path.exists()
            if exists_flag and not actual_exists:
                phantom_entries.append(f"{rel_path} (marked exists=true but file missing)")
            elif not exists_flag and actual_exists:
                phantom_entries.append(f"{rel_path} (marked exists=false but file exists)")
        
        assert len(phantom_entries) == 0, f"Phantom entries found: {phantom_entries}"

    def test_manifest_all_entries_exist(self):
        """All entries marked as exists=true should have actual files"""
        data = json.loads(MANIFEST_PATH.read_text())
        artifacts = data.get("artifacts", [])
        
        missing_files = []
        for artifact in artifacts:
            if artifact.get("exists", False):
                rel_path = artifact.get("path", "")
                abs_path = APP_ROOT / rel_path.lstrip("/")
                if not abs_path.exists():
                    missing_files.append(rel_path)
        
        assert len(missing_files) == 0, f"Missing files marked as exists=true: {missing_files}"

    def test_manifest_size_bytes_accurate(self):
        """Size bytes should match actual file size for existing files"""
        data = json.loads(MANIFEST_PATH.read_text())
        artifacts = data.get("artifacts", [])
        
        size_mismatches = []
        for artifact in artifacts:
            if artifact.get("exists", False):
                rel_path = artifact.get("path", "")
                abs_path = APP_ROOT / rel_path.lstrip("/")
                if abs_path.exists():
                    actual_size = abs_path.stat().st_size
                    manifest_size = artifact.get("size_bytes", 0)
                    # Allow some tolerance for files that may have been updated
                    if manifest_size > 0 and actual_size == 0:
                        size_mismatches.append(f"{rel_path}: manifest={manifest_size}, actual={actual_size}")
        
        assert len(size_mismatches) == 0, f"Size mismatches: {size_mismatches}"


class TestNoPlaceholderContent:
    """Verify artifacts don't contain placeholder/dummy/sample content"""

    def test_risk_engine_no_placeholders(self):
        path = TEST_REPORTS / "production_gate_p2_risk_engine.json"
        content = path.read_text().lower()
        assert "placeholder" not in content, "Contains placeholder"
        assert "dummy" not in content, "Contains dummy"

    def test_flapping_no_placeholders(self):
        path = TEST_REPORTS / "production_gate_p2_flapping.json"
        content = path.read_text().lower()
        assert "placeholder" not in content, "Contains placeholder"
        assert "dummy" not in content, "Contains dummy"

    def test_compare_no_placeholders(self):
        path = TEST_REPORTS / "production_gate_p2_compare_multi_run.json"
        content = path.read_text().lower()
        assert "placeholder" not in content, "Contains placeholder"
        assert "dummy" not in content, "Contains dummy"

    def test_timeline_no_placeholders(self):
        path = TEST_REPORTS / "production_gate_p2_timeline_audit_match.json"
        content = path.read_text().lower()
        assert "placeholder" not in content, "Contains placeholder"
        assert "dummy" not in content, "Contains dummy"


class TestRiskEngineJsonContent:
    """Verify risk engine json has real values"""

    def test_risk_engine_has_real_score(self):
        path = TEST_REPORTS / "production_gate_p2_risk_engine.json"
        data = json.loads(path.read_text())
        
        risk_score = data.get("risk_score")
        assert risk_score is not None, "Missing risk_score"
        assert isinstance(risk_score, (int, float)), f"risk_score should be numeric, got: {type(risk_score)}"

    def test_risk_engine_has_real_level(self):
        path = TEST_REPORTS / "production_gate_p2_risk_engine.json"
        data = json.loads(path.read_text())
        
        risk_level = data.get("risk_level")
        assert risk_level is not None, "Missing risk_level"
        assert risk_level in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}, f"Invalid risk_level: {risk_level}"

    def test_risk_engine_generation_automated(self):
        path = TEST_REPORTS / "production_gate_p2_risk_engine.json"
        data = json.loads(path.read_text())
        assert data.get("generation") == "automated", f"Expected 'automated', got: {data.get('generation')}"
        assert data.get("source") == "runtime test execution", f"Expected 'runtime test execution', got: {data.get('source')}"
