"""
FAZ-0 Phase 0 DB Determinism Tests
Tests for zero-tolerance embedded DB policy and PostgreSQL-only enforcement.
"""
import os
import subprocess
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestT01RepoScanCleanup:
    """T-0.1: repo scan cleanup - sqlite marker referansı allowlist dışında kalmamalı"""

    def test_allowlist_filter_working(self):
        """Filtered scan log should be empty (no sqlite refs outside allowlist)"""
        filtered_log = Path("/app/artifacts/faz0_embeddeddb_scan_filtered.log")
        if filtered_log.exists():
            content = filtered_log.read_text().strip()
            assert content == "", f"Found sqlite references outside allowlist:\n{content}"
        else:
            # If file doesn't exist, run verify script first
            result = subprocess.run(
                ["bash", "/app/scripts/verify_phase0_db_determinism.sh"],
                capture_output=True,
                text=True,
                cwd="/app",
            )
            assert result.returncode == 0, f"Verify script failed: {result.stderr}"
            content = filtered_log.read_text().strip()
            assert content == "", f"Found sqlite references outside allowlist:\n{content}"

    def test_allowed_locations_have_marker(self):
        """Allowlist locations (README, docs/11) should have the marker for documentation"""
        raw_scan_log = Path("/app/artifacts/faz0_embeddeddb_scan_post_cleanup.log")
        if raw_scan_log.exists():
            content = raw_scan_log.read_text()
            # Verify marker exists only in allowed locations
            allowed_paths = ["/app/README.md:", "/app/docs/11_alembic_drift_report.md:"]
            for line in content.strip().splitlines():
                if line.strip():
                    assert any(line.startswith(p) for p in allowed_paths), f"Unexpected sqlite reference: {line}"


class TestT01ForbiddenFilePatterns:
    """T-0.1: forbidden file patterns (*.db, *.sqlite, *.sqlite3, *.bak) should be zero"""

    def test_no_forbidden_files(self):
        """No forbidden DB artifact files should exist"""
        pattern_log = Path("/app/artifacts/faz0_forbidden_file_patterns.log")
        if pattern_log.exists():
            content = pattern_log.read_text().strip()
            assert content == "", f"Found forbidden DB artifact files:\n{content}"
        else:
            # Run find command directly
            result = subprocess.run(
                [
                    "find",
                    "/app",
                    "-type",
                    "f",
                    "(",
                    "-iname",
                    "*.db",
                    "-o",
                    "-iname",
                    "*.sqlite",
                    "-o",
                    "-iname",
                    "*.sqlite3",
                    "-o",
                    "-iname",
                    "*.bak",
                    ")",
                    "!",
                    "-path",
                    "*/.git/*",
                    "!",
                    "-path",
                    "*/node_modules/*",
                ],
                capture_output=True,
                text=True,
            )
            assert result.stdout.strip() == "", f"Found forbidden files:\n{result.stdout}"


class TestT02RuntimeHardGuard:
    """T-0.2: runtime hard guard active in startup, migration, and test bootstrap guard"""

    def test_db_determinism_module_exists(self):
        """db_determinism.py module exists with enforce_postgresql_only"""
        module_path = Path("/app/backend/core/db_determinism.py")
        assert module_path.exists(), "db_determinism.py not found"
        content = module_path.read_text()
        assert "enforce_postgresql_only" in content
        assert "postgresql" in content.lower() or "post" + "gresql" in content

    def test_startup_guard_present(self):
        """server.py has startup guard calling enforce_postgresql_only"""
        server_path = Path("/app/backend/server.py")
        content = server_path.read_text()
        assert "enforce_postgresql_only" in content
        assert 'enforce_postgresql_only(db_url, "startup")' in content

    def test_migration_service_guard_present(self):
        """migration_service.py has guard for alembic URL"""
        migration_path = Path("/app/backend/services/migration_service.py")
        content = migration_path.read_text()
        assert "enforce_postgresql_only" in content
        assert "alembic_database_url" in content

    def test_alembic_env_guard_present(self):
        """migrations/env.py has guard for get_url"""
        env_path = Path("/app/backend/migrations/env.py")
        content = env_path.read_text()
        assert "enforce_postgresql_only" in content
        assert "get_url" in content

    def test_bootstrap_guard_rejects_embedded_db(self):
        """Bootstrap guard correctly rejects sqlite URLs"""
        guard_log = Path("/app/artifacts/faz0_test_bootstrap_guard.log")
        if guard_log.exists():
            content = guard_log.read_text()
            assert "PASS bootstrap guard rejects embedded db URL" in content
        else:
            # Run the guard test directly
            import sys
            sys.path.insert(0, "/app/backend")
            from core.db_determinism import enforce_postgresql_only

            # Should pass for PostgreSQL
            result = enforce_postgresql_only(
                "postgresql+psycopg2://u:p@localhost:5432/app", "test_ok"
            )
            assert "postgresql" in result.lower()

            # Should fail for sqlite
            with pytest.raises(AssertionError):
                enforce_postgresql_only("sqlite:///tmp/dev.db", "test_fail")


class TestT03AlembicCurrentHead:
    """T-0.3: alembic current == head"""

    def test_alembic_current_equals_head(self):
        """Alembic current revision matches head revision"""
        current_log = Path("/app/artifacts/faz0_alembic_current.log")
        heads_log = Path("/app/artifacts/faz0_alembic_heads.log")

        if current_log.exists() and heads_log.exists():
            current_content = current_log.read_text()
            heads_content = heads_log.read_text()

            # Extract revision from logs
            import re

            current_matches = re.findall(r"([0-9]{8}_[0-9]{4})", current_content)
            heads_matches = re.findall(r"([0-9]{8}_[0-9]{4})", heads_content)

            assert current_matches, "Could not parse current revision"
            assert heads_matches, "Could not parse head revision"

            current_rev = current_matches[-1]
            head_rev = heads_matches[-1]
            assert current_rev == head_rev, f"Alembic drift: current={current_rev}, head={head_rev}"
        else:
            # Run alembic check directly
            result = subprocess.run(
                ["alembic", "current"],
                capture_output=True,
                text=True,
                cwd="/app/backend",
            )
            assert "(head)" in result.stdout, f"Alembic not at head: {result.stdout}"


class TestT04RestartPersistence:
    """T-0.4: restart persistence log PASS (brand settings value persists after backend restart)"""

    def test_persistence_log_pass(self):
        """Persistence restart test shows PASS"""
        persistence_log = Path("/app/artifacts/faz0_persistence_restart.log")
        assert persistence_log.exists(), "Persistence restart log not found"
        content = persistence_log.read_text()
        assert "PERSISTENCE_RESULT PASS" in content, f"Persistence test did not pass:\n{content}"

    def test_persistence_log_has_all_stages(self):
        """Persistence log shows all stages: INSERT, PRE_RESTART, RESTART, POST_RESTART"""
        persistence_log = Path("/app/artifacts/faz0_persistence_restart.log")
        content = persistence_log.read_text()
        assert "INSERT_OK" in content, "Missing INSERT_OK"
        assert "PRE_RESTART_READ_OK" in content, "Missing PRE_RESTART_READ_OK"
        assert "RESTART_OK" in content, "Missing RESTART_OK"
        assert "POST_RESTART_READ_OK" in content, "Missing POST_RESTART_READ_OK"


class TestT05VerifyPhase0Script:
    """T-0.5: scripts/verify_phase0_db_determinism.sh runs PASS and produces summary artifact"""

    def test_verify_script_exists(self):
        """verify_phase0_db_determinism.sh script exists"""
        script_path = Path("/app/scripts/verify_phase0_db_determinism.sh")
        assert script_path.exists(), "Verify script not found"
        assert script_path.stat().st_mode & 0o111, "Script is not executable"

    def test_summary_artifact_shows_pass(self):
        """Summary artifact shows SUMMARY: PASS"""
        summary_log = Path("/app/artifacts/faz0_verify_phase0_db_determinism.log")
        assert summary_log.exists(), "Summary artifact not found"
        content = summary_log.read_text()
        assert "SUMMARY: PASS" in content, f"Summary does not show PASS:\n{content}"


class TestCIDeployGate:
    """CI: deploy-gate.yml has mandatory phase0-db-determinism-gate job"""

    def test_deploy_gate_has_phase0_job(self):
        """deploy-gate.yml contains phase0-db-determinism-gate job"""
        deploy_gate_path = Path("/app/.github/workflows/deploy-gate.yml")
        assert deploy_gate_path.exists(), "deploy-gate.yml not found"
        content = deploy_gate_path.read_text()
        assert "phase0-db-determinism-gate" in content, "Missing phase0-db-determinism-gate job"

    def test_phase0_job_runs_verify_script(self):
        """phase0-db-determinism-gate job runs the verify script"""
        deploy_gate_path = Path("/app/.github/workflows/deploy-gate.yml")
        content = deploy_gate_path.read_text()
        assert "verify_phase0_db_determinism.sh" in content, "Job doesn't run verify script"

    def test_phase0_job_uploads_artifacts(self):
        """phase0-db-determinism-gate job uploads verification artifacts"""
        deploy_gate_path = Path("/app/.github/workflows/deploy-gate.yml")
        content = deploy_gate_path.read_text()
        assert "phase0-db-determinism-artifacts" in content, "Job doesn't upload artifacts"


class TestBackendHealthWithPostgres:
    """Integration: Backend health endpoint works with PostgreSQL"""

    def test_health_endpoint_database_connected(self):
        """Health endpoint returns database connected status"""
        if not BASE_URL:
            pytest.skip("REACT_APP_BACKEND_URL not set")
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("database") == "connected"


class TestEnvConfigValidation:
    """Environment config validation for PostgreSQL-only"""

    def test_backend_env_has_postgresql_url(self):
        """Backend .env has PostgreSQL DATABASE_URL"""
        env_path = Path("/app/backend/.env")
        assert env_path.exists(), "Backend .env not found"
        content = env_path.read_text()
        assert "DATABASE_URL" in content
        assert "postgresql" in content.lower()
        assert "sqlite" not in content.lower()

    def test_env_validation_log_pass(self):
        """Env validation log shows PASS"""
        validation_log = Path("/app/artifacts/faz0_env_config_validation.log")
        assert validation_log.exists(), "Env validation log not found"
        content = validation_log.read_text()
        assert "PASS /app/backend/.env" in content
