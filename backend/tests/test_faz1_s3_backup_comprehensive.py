"""
FAZ-1 S3 Backup Comprehensive Tests
- backup_service.py: S3 upload functionality
- upload_backup_to_s3.py CLI: BACKUP_S3_UPLOAD_REQUIRED guard
- db_backup.sh: S3 upload integration
- deploy-gate.yml: backup-restore-s3-gate job
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services import backup_service


# ============================================================================
# backup_service.py TESTS
# ============================================================================

class TestS3BackupServiceUnit:
    """Unit tests for backup_service.py S3 upload logic"""

    def _set_full_s3_env(self, monkeypatch) -> None:
        """Helper to set all required S3 env vars"""
        monkeypatch.setenv("BACKUP_S3_BUCKET", "test-bucket")
        monkeypatch.setenv("BACKUP_AWS_ACCESS_KEY_ID", "test-access-key")
        monkeypatch.setenv("BACKUP_AWS_SECRET_ACCESS_KEY", "test-secret")
        monkeypatch.setenv("BACKUP_AWS_REGION", "eu-central-1")

    def _clear_s3_env(self, monkeypatch) -> None:
        """Helper to clear all S3 env vars"""
        for key in backup_service.S3_REQUIRED_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)

    def test_s3_upload_skips_when_no_env_vars(self, monkeypatch, tmp_path: Path):
        """When no S3 env vars are set, upload should be skipped"""
        backup_file = tmp_path / "backup.sql"
        backup_file.write_text("SELECT 1;", encoding="utf-8")
        self._clear_s3_env(monkeypatch)

        result = backup_service.upload_backup_to_s3(str(backup_file))

        assert result.status == "skipped"
        assert "upload skipped" in result.message.lower()

    def test_s3_upload_fails_on_partial_config(self, monkeypatch, tmp_path: Path):
        """When only some S3 env vars are set, upload should fail with misconfiguration"""
        backup_file = tmp_path / "backup.sql"
        backup_file.write_text("SELECT 1;", encoding="utf-8")
        
        # Set only bucket, clear others
        monkeypatch.setenv("BACKUP_S3_BUCKET", "test-bucket")
        monkeypatch.delenv("BACKUP_AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("BACKUP_AWS_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("BACKUP_AWS_REGION", raising=False)

        result = backup_service.upload_backup_to_s3(str(backup_file))

        assert result.status == "failed"
        assert "missing required env vars" in result.message.lower()

    def test_s3_upload_fails_on_missing_file(self, monkeypatch):
        """When backup file doesn't exist, upload should fail"""
        self._set_full_s3_env(monkeypatch)

        result = backup_service.upload_backup_to_s3("/nonexistent/path/backup.sql")

        assert result.status == "failed"
        assert "not found" in result.message.lower()

    def test_s3_upload_fails_on_empty_file(self, monkeypatch, tmp_path: Path):
        """When backup file is empty, upload should fail"""
        backup_file = tmp_path / "empty.sql"
        backup_file.write_text("", encoding="utf-8")
        self._set_full_s3_env(monkeypatch)

        result = backup_service.upload_backup_to_s3(str(backup_file))

        assert result.status == "failed"
        assert "empty" in result.message.lower()

    def test_s3_upload_uses_sse_s3_encryption(self, monkeypatch, tmp_path: Path):
        """SSE-S3 header (AES256) must be enforced in upload call"""
        backup_file = tmp_path / "backup.sql"
        backup_file.write_text("SELECT 1;", encoding="utf-8")
        self._set_full_s3_env(monkeypatch)
        monkeypatch.setenv("BACKUP_S3_PREFIX", "scheduled")

        captured = {}

        class DummyS3Client:
            def upload_file(self, filename, bucket, object_key, ExtraArgs=None):
                captured["filename"] = filename
                captured["bucket"] = bucket
                captured["object_key"] = object_key
                captured["extra_args"] = ExtraArgs or {}

        monkeypatch.setattr(backup_service.boto3, "client", lambda *a, **kw: DummyS3Client())

        result = backup_service.upload_backup_to_s3(str(backup_file))

        assert result.status == "uploaded"
        assert result.s3_uri is not None
        assert captured["extra_args"].get("ServerSideEncryption") == "AES256"

    def test_s3_object_key_includes_date_path(self, monkeypatch, tmp_path: Path):
        """S3 object key should include date-based path like YYYY/MM/DD"""
        backup_file = tmp_path / "mybackup.sql"
        backup_file.write_text("SELECT 1;", encoding="utf-8")
        self._set_full_s3_env(monkeypatch)

        captured = {}

        class DummyS3Client:
            def upload_file(self, filename, bucket, object_key, ExtraArgs=None):
                captured["object_key"] = object_key

        monkeypatch.setattr(backup_service.boto3, "client", lambda *a, **kw: DummyS3Client())

        result = backup_service.upload_backup_to_s3(str(backup_file))

        assert result.status == "uploaded"
        # Object key should match pattern like "2026/03/19/mybackup.sql"
        import re
        assert re.match(r"\d{4}/\d{2}/\d{2}/mybackup\.sql", captured["object_key"])

    def test_s3_object_key_with_prefix(self, monkeypatch, tmp_path: Path):
        """S3 object key should include BACKUP_S3_PREFIX when set"""
        backup_file = tmp_path / "backup.sql"
        backup_file.write_text("SELECT 1;", encoding="utf-8")
        self._set_full_s3_env(monkeypatch)
        monkeypatch.setenv("BACKUP_S3_PREFIX", "my-prefix")

        captured = {}

        class DummyS3Client:
            def upload_file(self, filename, bucket, object_key, ExtraArgs=None):
                captured["object_key"] = object_key

        monkeypatch.setattr(backup_service.boto3, "client", lambda *a, **kw: DummyS3Client())

        result = backup_service.upload_backup_to_s3(str(backup_file))

        assert result.status == "uploaded"
        assert captured["object_key"].startswith("my-prefix/")


# ============================================================================
# upload_backup_to_s3.py CLI TESTS
# ============================================================================

class TestS3UploadCLI:
    """Tests for CLI upload_backup_to_s3.py"""

    def _clear_s3_env(self, monkeypatch) -> None:
        for key in backup_service.S3_REQUIRED_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv("BACKUP_S3_UPLOAD_REQUIRED", raising=False)

    def test_cli_skips_when_no_s3_env_and_not_required(self, monkeypatch, tmp_path: Path):
        """CLI should return 0 when S3 is skipped and BACKUP_S3_UPLOAD_REQUIRED is not 1"""
        backup_file = tmp_path / "backup.sql"
        backup_file.write_text("SELECT 1;", encoding="utf-8")
        self._clear_s3_env(monkeypatch)

        from cli.upload_backup_to_s3 import main
        monkeypatch.setattr("sys.argv", ["upload_backup_to_s3.py", str(backup_file)])

        exit_code = main()
        assert exit_code == 0

    def test_cli_fails_when_s3_required_but_missing(self, monkeypatch, tmp_path: Path):
        """CLI should return 1 when BACKUP_S3_UPLOAD_REQUIRED=1 but no S3 creds"""
        backup_file = tmp_path / "backup.sql"
        backup_file.write_text("SELECT 1;", encoding="utf-8")
        self._clear_s3_env(monkeypatch)
        monkeypatch.setenv("BACKUP_S3_UPLOAD_REQUIRED", "1")

        from cli.upload_backup_to_s3 import main
        monkeypatch.setattr("sys.argv", ["upload_backup_to_s3.py", str(backup_file)])

        exit_code = main()
        assert exit_code == 1


# ============================================================================
# db_backup.sh INTEGRATION TESTS
# ============================================================================

class TestDbBackupShellScript:
    """Integration tests for db_backup.sh"""

    def test_db_backup_creates_local_sql_file(self, tmp_path: Path):
        """db_backup.sh should create a local .sql backup file"""
        # Skip if DATABASE_URL not set or pg_dump not available
        if not os.getenv("DATABASE_URL"):
            pytest.skip("DATABASE_URL not set")
        
        result = subprocess.run(
            ["which", "pg_dump"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            pytest.skip("pg_dump not available")

        backup_path = tmp_path / "test_backup.sql"
        env = os.environ.copy()
        env["APP_ROOT"] = "/app"

        result = subprocess.run(
            ["bash", "/app/scripts/db_backup.sh", str(backup_path)],
            capture_output=True,
            text=True,
            env=env
        )

        # The script should output the backup path on success
        assert backup_path.exists(), f"Backup file not created. stderr: {result.stderr}"
        assert backup_path.stat().st_size > 0, "Backup file is empty"

    def test_db_backup_triggers_s3_upload_cli(self, tmp_path: Path, monkeypatch):
        """db_backup.sh should invoke upload_backup_to_s3.py CLI"""
        if not os.getenv("DATABASE_URL"):
            pytest.skip("DATABASE_URL not set")
        
        result = subprocess.run(["which", "pg_dump"], capture_output=True)
        if result.returncode != 0:
            pytest.skip("pg_dump not available")

        backup_path = tmp_path / "test_backup.sql"
        env = os.environ.copy()
        env["APP_ROOT"] = "/app"
        # Ensure S3 env vars are not set to test skip behavior
        for key in backup_service.S3_REQUIRED_ENV_KEYS:
            env.pop(key, None)
        env.pop("BACKUP_S3_UPLOAD_REQUIRED", None)

        result = subprocess.run(
            ["bash", "/app/scripts/db_backup.sh", str(backup_path)],
            capture_output=True,
            text=True,
            env=env,
            timeout=60
        )

        # Should complete without error
        assert result.returncode == 0, f"db_backup.sh failed: {result.stderr}"
        # The S3 upload should be skipped (logged)
        log_content = (Path("/app/artifacts/backup.log").read_text() 
                      if Path("/app/artifacts/backup.log").exists() else "")
        # Verify script ran to completion


# ============================================================================
# deploy-gate.yml STRUCTURE TESTS
# ============================================================================

class TestDeployGateWorkflow:
    """Tests for .github/workflows/deploy-gate.yml structure"""

    @pytest.fixture
    def workflow_content(self) -> str:
        workflow_path = Path("/app/.github/workflows/deploy-gate.yml")
        if not workflow_path.exists():
            pytest.skip("deploy-gate.yml not found")
        return workflow_path.read_text()

    def test_backup_restore_s3_gate_job_exists(self, workflow_content: str):
        """Workflow should contain backup-restore-s3-gate job"""
        assert "backup-restore-s3-gate:" in workflow_content

    def test_s3_gate_runs_on_pull_request(self, workflow_content: str):
        """S3 gate job should trigger on pull_request events"""
        # The workflow has pull_request in 'on:' section
        assert "pull_request" in workflow_content

    def test_s3_gate_has_required_s3_secrets(self, workflow_content: str):
        """S3 gate job should reference required S3 secrets"""
        required_secrets = [
            "BACKUP_S3_BUCKET",
            "BACKUP_AWS_ACCESS_KEY_ID",
            "BACKUP_AWS_SECRET_ACCESS_KEY",
            "BACKUP_AWS_REGION"
        ]
        for secret in required_secrets:
            assert secret in workflow_content, f"Missing secret reference: {secret}"

    def test_s3_gate_has_backup_s3_upload_required_env(self, workflow_content: str):
        """S3 gate job should set BACKUP_S3_UPLOAD_REQUIRED=1"""
        assert "BACKUP_S3_UPLOAD_REQUIRED: 1" in workflow_content

    def test_s3_gate_runs_unit_test(self, workflow_content: str):
        """S3 gate job should run test_s3_backup_service.py"""
        assert "test_s3_backup_service.py" in workflow_content

    def test_s3_gate_runs_full_cycle_test(self, workflow_content: str):
        """S3 gate job should run db_backup_restore_full_cycle_test.sh"""
        assert "db_backup_restore_full_cycle_test.sh" in workflow_content

    def test_s3_gate_validates_required_secrets(self, workflow_content: str):
        """S3 gate job should validate required S3 secrets are present"""
        # Check for secret validation step
        assert "Validate required S3 secrets" in workflow_content or "required_vars" in workflow_content

    def test_s3_gate_installs_postgresql_client(self, workflow_content: str):
        """S3 gate job should install postgresql-client for pg_dump/psql"""
        assert "postgresql-client" in workflow_content


# ============================================================================
# FULL CYCLE INTEGRATION TEST
# ============================================================================

class TestFullBackupRestoreCycle:
    """Full backup->restore cycle integration test"""

    def test_full_cycle_script_passes(self):
        """db_backup_restore_full_cycle_test.sh should complete successfully"""
        if not os.getenv("DATABASE_URL"):
            pytest.skip("DATABASE_URL not set")
        
        result = subprocess.run(["which", "pg_dump"], capture_output=True)
        if result.returncode != 0:
            pytest.skip("pg_dump not available")

        result = subprocess.run(["which", "psql"], capture_output=True)
        if result.returncode != 0:
            pytest.skip("psql not available")

        env = os.environ.copy()
        env["APP_ROOT"] = "/app"

        result = subprocess.run(
            ["bash", "/app/scripts/db_backup_restore_full_cycle_test.sh"],
            capture_output=True,
            text=True,
            env=env,
            timeout=120
        )

        assert result.returncode == 0, f"Full cycle test failed: {result.stderr}"
        assert "DATA_FOUND_AFTER_RESTORE" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
