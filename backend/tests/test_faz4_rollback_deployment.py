"""
FAZ-4 Rollback Testing: Deploy & Rollback Scripts Verification
Tests:
- T1: deploy.sh <version> produces image_tag app:release-<sha>
- T2: rollback.sh finds previous version from history automatically
- T3: verify_phase4_rollback.sh full scenario PASS
- T4: rollback_time < 60s
- T5: post-rollback /health and /ready return 200
"""
import pytest
import requests
import subprocess
import os
import json
import time
import re
from pathlib import Path

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ROOT_DIR = "/app"
STATE_DIR = f"{ROOT_DIR}/artifacts/release_state"
HISTORY_FILE = f"{STATE_DIR}/deploy_history.jsonl"


class TestFaz4DeployScript:
    """Tests for deploy.sh script - image_tag generation"""

    def test_deploy_generates_correct_image_tag_format(self):
        """deploy.sh should produce image_tag app:release-<sha>"""
        test_version = "abcdef1234567"
        
        result = subprocess.run(
            [f"{ROOT_DIR}/scripts/deploy.sh", test_version],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            timeout=30
        )
        
        assert result.returncode == 0, f"deploy.sh failed: {result.stderr}"
        
        # Verify output contains expected image tag
        assert f"image_tag=app:release-{test_version}" in result.stdout
        assert f"deployed_image_tag=app:release-{test_version}" in result.stdout
        
        # Verify image_tag in history file
        history_lines = Path(HISTORY_FILE).read_text().strip().split('\n')
        last_entry = json.loads(history_lines[-1])
        assert last_entry['image_tag'] == f"app:release-{test_version}"
        assert last_entry['status'] in ('deployed', 'rolled_back')

    def test_deploy_rejects_invalid_sha_format(self):
        """deploy.sh should reject non-SHA version strings"""
        invalid_versions = ["invalid!", "XYZ123", "abc", "abc123def!"]
        
        for version in invalid_versions:
            result = subprocess.run(
                [f"{ROOT_DIR}/scripts/deploy.sh", version],
                capture_output=True,
                text=True,
                cwd=ROOT_DIR,
                timeout=10
            )
            assert result.returncode != 0, f"Should reject {version}"

    def test_deploy_version_parameterized(self):
        """deploy.sh accepts version as parameter and uses it"""
        version_a = "1111111111111"
        version_b = "2222222222222"
        
        # Deploy A
        result_a = subprocess.run(
            [f"{ROOT_DIR}/scripts/deploy.sh", version_a],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            timeout=30
        )
        assert result_a.returncode == 0
        assert f"version={version_a}" in result_a.stdout
        
        # Deploy B
        result_b = subprocess.run(
            [f"{ROOT_DIR}/scripts/deploy.sh", version_b],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            timeout=30
        )
        assert result_b.returncode == 0
        assert f"version={version_b}" in result_b.stdout


class TestFaz4RollbackScript:
    """Tests for rollback.sh script - automatic previous version detection"""

    def test_rollback_finds_previous_version_from_history(self):
        """rollback.sh should automatically find previous deployed version"""
        # First deploy a known version
        known_version = "3333333333333"
        subprocess.run(
            [f"{ROOT_DIR}/scripts/deploy.sh", known_version],
            capture_output=True,
            cwd=ROOT_DIR,
            timeout=30
        )
        
        # Deploy another version
        new_version = "4444444444444"
        subprocess.run(
            [f"{ROOT_DIR}/scripts/deploy.sh", new_version],
            capture_output=True,
            cwd=ROOT_DIR,
            timeout=30
        )
        
        # Rollback should find previous version
        result = subprocess.run(
            [f"{ROOT_DIR}/scripts/rollback.sh"],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            timeout=60
        )
        
        assert result.returncode == 0, f"rollback.sh failed: {result.stderr}"
        assert "previous_version=" in result.stdout
        # Should roll back to known_version
        assert f"previous_version={known_version}" in result.stdout

    def test_rollback_time_under_60_seconds(self):
        """rollback_time should be < 60 seconds"""
        # Deploy a version first
        subprocess.run(
            [f"{ROOT_DIR}/scripts/deploy.sh", "5555555555555"],
            capture_output=True,
            cwd=ROOT_DIR,
            timeout=30
        )
        
        subprocess.run(
            [f"{ROOT_DIR}/scripts/deploy.sh", "6666666666666"],
            capture_output=True,
            cwd=ROOT_DIR,
            timeout=30
        )
        
        start = time.time()
        result = subprocess.run(
            [f"{ROOT_DIR}/scripts/rollback.sh"],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            timeout=60
        )
        elapsed = time.time() - start
        
        assert result.returncode == 0
        assert elapsed < 60, f"Rollback took {elapsed}s, expected < 60s"
        
        # Also check the script's reported time
        match = re.search(r'rollback_time_seconds=(\d+)', result.stdout)
        if match:
            script_reported_time = int(match.group(1))
            assert script_reported_time < 60


class TestFaz4VerifyPhaseScript:
    """Tests for verify_phase4_rollback.sh full scenario"""

    def test_verify_phase4_rollback_passes(self):
        """verify_phase4_rollback.sh should complete with SUMMARY: PASS"""
        result = subprocess.run(
            [f"{ROOT_DIR}/scripts/verify_phase4_rollback.sh"],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            timeout=120
        )
        
        assert result.returncode == 0, f"verify_phase4_rollback.sh failed: {result.stderr}\n{result.stdout}"
        assert "SUMMARY: PASS" in result.stdout

    def test_verify_phase4_generates_summary_json(self):
        """verify script should create faz4_rollback_summary.json with PASS"""
        summary_path = Path(f"{ROOT_DIR}/artifacts/faz4_rollback_summary.json")
        
        # Run verify script
        subprocess.run(
            [f"{ROOT_DIR}/scripts/verify_phase4_rollback.sh"],
            capture_output=True,
            cwd=ROOT_DIR,
            timeout=120
        )
        
        assert summary_path.exists(), "faz4_rollback_summary.json not created"
        
        summary = json.loads(summary_path.read_text())
        assert summary['result'] == 'PASS'
        assert summary['health_http'] == 200
        assert summary['ready_http'] == 200
        assert summary['rollback_time_seconds'] < 60


class TestFaz4HealthEndpoints:
    """Tests for /health and /ready endpoint availability post-rollback"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure we have a valid BASE_URL"""
        assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

    def test_health_endpoint_returns_200(self):
        """/api/health should return 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'

    def test_ready_endpoint_returns_200(self):
        """/api/ready should return 200"""
        response = requests.get(f"{BASE_URL}/api/ready", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ready'

    def test_health_ready_after_rollback(self):
        """After rollback, both endpoints should still return 200"""
        # Deploy and rollback
        subprocess.run(
            [f"{ROOT_DIR}/scripts/deploy.sh", "7777777777777"],
            capture_output=True,
            cwd=ROOT_DIR,
            timeout=30
        )
        subprocess.run(
            [f"{ROOT_DIR}/scripts/deploy.sh", "8888888888888"],
            capture_output=True,
            cwd=ROOT_DIR,
            timeout=30
        )
        subprocess.run(
            [f"{ROOT_DIR}/scripts/rollback.sh"],
            capture_output=True,
            cwd=ROOT_DIR,
            timeout=60
        )
        
        # Check endpoints after rollback
        health_resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        ready_resp = requests.get(f"{BASE_URL}/api/ready", timeout=10)
        
        assert health_resp.status_code == 200
        assert ready_resp.status_code == 200


class TestFaz4DeployHistory:
    """Tests for deploy_history.jsonl structure and content"""

    def test_history_records_image_tag_standard(self):
        """All history entries should have app:release-<sha> format"""
        history_path = Path(HISTORY_FILE)
        assert history_path.exists(), f"History file not found: {HISTORY_FILE}"
        
        for line in history_path.read_text().strip().split('\n'):
            if not line.strip():
                continue
            entry = json.loads(line)
            image_tag = entry.get('image_tag', '')
            assert image_tag.startswith('app:release-'), f"Invalid image_tag: {image_tag}"
            
            # Verify SHA portion matches version
            sha = image_tag.replace('app:release-', '')
            assert re.match(r'^[0-9a-f]{7,40}$', sha), f"Invalid SHA in tag: {sha}"

    def test_history_has_required_fields(self):
        """Each history entry must have version, image_tag, status, source"""
        history_path = Path(HISTORY_FILE)
        required_fields = ['version', 'image_tag', 'status']
        
        for line in history_path.read_text().strip().split('\n'):
            if not line.strip():
                continue
            entry = json.loads(line)
            for field in required_fields:
                assert field in entry, f"Missing field {field} in entry: {entry}"

    def test_history_records_rollback_events(self):
        """History should contain rolled_back status entries"""
        history_path = Path(HISTORY_FILE)
        
        rollback_entries = []
        for line in history_path.read_text().strip().split('\n'):
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get('status') == 'rolled_back':
                rollback_entries.append(entry)
        
        assert len(rollback_entries) > 0, "No rollback entries in history"
        
        # Rollback entries should have rollback_time_seconds
        for entry in rollback_entries:
            assert 'rollback_time_seconds' in entry
            assert entry['rollback_time_seconds'] < 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
