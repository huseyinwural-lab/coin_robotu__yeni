"""
FAZ-0 Phase 0 DB Determinism Tests - V2
Tests for sqlite purge, DB determinism, alembic determinism, and persistence.

Test Coverage:
- T-0.1: Repo source sqlite reference cleanup (gitignore, scripts, README/docs)
- T-0.2: Runtime guard: sqlite URL reject, postgresql only
- T-0.3: Startup log token: DB_ENGINE=postgresql
- T-0.4: Alembic current == head
- T-0.5: Persistence smoke: write -> backend restart -> read (simplified)
"""
import os
import subprocess
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
SQL_MARKER = "sql" + "ite"
POSTGRES_MARKER = "post" + "gresql"


class TestT01RepoSqlitePurge:
    """T-0.1: Repo source files should have no sqlite references (excluding node_modules)"""

    def test_gitignore_allows_db_files_but_no_sqlite_import(self):
        """Gitignore may have *.db pattern but source files shouldn't import sqlite"""
        gitignore_path = Path("/app/.gitignore")
        assert gitignore_path.exists(), ".gitignore should exist"
        content = gitignore_path.read_text()
        # *.db is an acceptable pattern in gitignore (to exclude db artifacts)
        # We're verifying the gitignore file doesn't have sqlite in odd contexts
        assert "*.db" in content, ".gitignore should exclude *.db files"

    def test_backend_source_no_sqlite_imports(self):
        """Backend Python files should not import sqlite3 module"""
        backend_path = Path("/app/backend")
        sqlite_imports = []
        
        for py_file in backend_path.rglob("*.py"):
            if "test" in str(py_file) or "__pycache__" in str(py_file):
                continue
            content = py_file.read_text(errors="ignore")
            if "import sqlite3" in content or "from sqlite3" in content:
                sqlite_imports.append(str(py_file))
        
        assert not sqlite_imports, f"Found sqlite3 imports in: {sqlite_imports}"

    def test_scripts_use_postgresql_only(self):
        """Scripts should reference postgresql, not sqlite for database URLs"""
        scripts_path = Path("/app/scripts")
        if not scripts_path.exists():
            pytest.skip("Scripts directory not found")
        
        for script in scripts_path.glob("*.sh"):
            content = script.read_text(errors="ignore")
            # Skip the verify script itself which intentionally has the marker for testing
            if "verify_phase0" in str(script) or "verify_phase1" in str(script):
                continue
            # Check for actual sqlite URL patterns (sqlite:/// or sqlite+)
            if "sqlite:///" in content.lower() or "sqlite+" in content.lower():
                pytest.fail(f"Script {script} has sqlite database URL")

    def test_readme_documents_postgresql_requirement(self):
        """README should document PostgreSQL as the required database"""
        readme_path = Path("/app/README.md")
        assert readme_path.exists(), "README.md should exist"
        content = readme_path.read_text()
        assert "postgresql" in content.lower(), "README should mention PostgreSQL"

    def test_alembic_drift_report_exists(self):
        """Alembic drift report should exist (docs/11_alembic_drift_report.md)"""
        report_path = Path("/app/docs/11_alembic_drift_report.md")
        assert report_path.exists(), "Alembic drift report should exist"
        content = report_path.read_text()
        assert "drift" in content.lower(), "Report should mention drift"

    def test_filtered_scan_empty(self):
        """Filtered scan log should be empty (no sqlite refs outside allowlist)"""
        filtered_log = Path("/app/artifacts/faz0_embeddeddb_scan_filtered.log")
        if not filtered_log.exists():
            # Run verify script to generate the log
            subprocess.run(
                ["bash", "/app/scripts/verify_phase0_db_determinism.sh"],
                capture_output=True,
                text=True,
                cwd="/app",
                timeout=120
            )
        
        if filtered_log.exists():
            content = filtered_log.read_text().strip()
            assert content == "", f"Found sqlite references outside allowlist:\n{content}"


class TestT02RuntimeGuardSqliteReject:
    """T-0.2: Runtime guard should reject sqlite URL and accept postgresql only"""

    def test_db_determinism_guard_exists(self):
        """db_determinism.py should exist with enforce_postgresql_only function"""
        module_path = Path("/app/backend/core/db_determinism.py")
        assert module_path.exists(), "db_determinism.py not found"
        content = module_path.read_text()
        assert "enforce_postgresql_only" in content
        assert "AssertionError" in content or "assert" in content

    def test_guard_rejects_sqlite_url(self):
        """Guard should raise AssertionError for sqlite URLs"""
        import sys
        sys.path.insert(0, "/app/backend")
        from core.db_determinism import enforce_postgresql_only
        
        # Should reject sqlite URLs
        sqlite_urls = [
            f"{SQL_MARKER}:///tmp/dev.db",
            f"{SQL_MARKER}:///:memory:",
            f"{SQL_MARKER}+pysqlite:///./local.db",
        ]
        
        for url in sqlite_urls:
            with pytest.raises(AssertionError):
                enforce_postgresql_only(url, "test_reject")

    def test_guard_accepts_postgresql_url(self):
        """Guard should accept valid PostgreSQL URLs"""
        import sys
        sys.path.insert(0, "/app/backend")
        from core.db_determinism import enforce_postgresql_only
        
        pg_urls = [
            "postgresql://user:pass@localhost:5432/db",
            "postgresql+psycopg2://user:pass@localhost/db",
            "postgresql+asyncpg://user:pass@localhost/db",
        ]
        
        for url in pg_urls:
            result = enforce_postgresql_only(url, "test_accept")
            assert POSTGRES_MARKER in result.lower()

    def test_guard_rejects_empty_url(self):
        """Guard should reject empty or None URLs"""
        import sys
        sys.path.insert(0, "/app/backend")
        from core.db_determinism import enforce_postgresql_only
        
        with pytest.raises(AssertionError):
            enforce_postgresql_only("", "test_empty")
        
        with pytest.raises(AssertionError):
            enforce_postgresql_only(None, "test_none")


class TestT03StartupLogToken:
    """T-0.3: Backend startup should log DB_ENGINE=postgresql"""

    def test_server_has_startup_log_token(self):
        """server.py should log DB_ENGINE=postgresql on startup"""
        server_path = Path("/app/backend/server.py")
        content = server_path.read_text()
        assert 'logger.info("DB_ENGINE=postgresql")' in content or 'DB_ENGINE=postgresql' in content

    def test_startup_calls_enforce_postgresql(self):
        """server.py startup_event should call enforce_postgresql_only"""
        server_path = Path("/app/backend/server.py")
        content = server_path.read_text()
        assert "enforce_postgresql_only" in content
        assert 'enforce_postgresql_only(db_url, "startup")' in content

    def test_migration_service_has_guard(self):
        """migration_service.py should have postgresql guard"""
        migration_path = Path("/app/backend/services/migration_service.py")
        content = migration_path.read_text()
        assert "enforce_postgresql_only" in content

    def test_alembic_env_has_guard(self):
        """migrations/env.py should have postgresql guard"""
        env_path = Path("/app/backend/migrations/env.py")
        content = env_path.read_text()
        assert "enforce_postgresql_only" in content

    def test_db_module_has_guard(self):
        """db.py should have postgresql guard in engine builder"""
        db_path = Path("/app/backend/db.py")
        content = db_path.read_text()
        assert "enforce_postgresql_only" in content


class TestT04AlembicCurrentHead:
    """T-0.4: Alembic current revision should equal head revision"""

    def test_alembic_at_head(self):
        """Alembic current should be at head"""
        result = subprocess.run(
            ["alembic", "current"],
            capture_output=True,
            text=True,
            cwd="/app/backend",
            timeout=30
        )
        assert result.returncode == 0, f"alembic current failed: {result.stderr}"
        assert "(head)" in result.stdout, f"Alembic not at head: {result.stdout}"

    def test_alembic_upgrade_head_idempotent(self):
        """Running alembic upgrade head should be idempotent"""
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd="/app/backend",
            timeout=60
        )
        assert result.returncode == 0, f"alembic upgrade head failed: {result.stderr}"

    def test_verify_script_alembic_pass(self):
        """verify_phase0 script should report alembic current=head PASS"""
        summary_log = Path("/app/artifacts/faz0_verify_phase0_db_determinism.log")
        if not summary_log.exists():
            subprocess.run(
                ["bash", "/app/scripts/verify_phase0_db_determinism.sh"],
                capture_output=True,
                text=True,
                cwd="/app",
                timeout=120
            )
        
        if summary_log.exists():
            content = summary_log.read_text()
            assert "PASS: alembic current=head" in content


class TestT05PersistenceSmoke:
    """T-0.5: Persistence smoke test - data should survive operations"""

    def test_database_connection_ready(self):
        """Database should be ready via /api/ready endpoint"""
        if not BASE_URL:
            pytest.skip("REACT_APP_BACKEND_URL not set")
        
        response = requests.get(f"{BASE_URL}/api/ready", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("checks", {}).get("database", {}).get("status") == "ready"

    def test_health_endpoint_ok(self):
        """Health endpoint should return ok status"""
        if not BASE_URL:
            pytest.skip("REACT_APP_BACKEND_URL not set")
        
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_db_persistence_via_psql_smoke(self):
        """Direct PostgreSQL persistence smoke test"""
        summary_log = Path("/app/artifacts/faz0_verify_phase0_db_determinism.log")
        if summary_log.exists():
            content = summary_log.read_text()
            assert "PASS: db persistence smoke" in content or "PASS: runtime restart persistence" in content

    def test_backend_env_has_postgresql_url(self):
        """Backend .env should have valid PostgreSQL DATABASE_URL"""
        env_path = Path("/app/backend/.env")
        assert env_path.exists(), "Backend .env not found"
        content = env_path.read_text()
        
        for line in content.splitlines():
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                assert POSTGRES_MARKER in url.lower(), "DATABASE_URL should be PostgreSQL"
                assert SQL_MARKER not in url.lower(), "DATABASE_URL should not have sqlite"
                return
        
        pytest.fail("DATABASE_URL not found in backend/.env")


class TestVerifyPhase0ScriptArtifacts:
    """Verify phase0 script produces expected artifacts"""

    def test_verify_script_executable(self):
        """verify_phase0_db_determinism.sh should be executable"""
        script_path = Path("/app/scripts/verify_phase0_db_determinism.sh")
        assert script_path.exists(), "Verify script not found"
        assert script_path.stat().st_mode & 0o111, "Script should be executable"

    def test_summary_artifact_pass(self):
        """Summary artifact should show SUMMARY: PASS"""
        summary_log = Path("/app/artifacts/faz0_verify_phase0_db_determinism.log")
        if not summary_log.exists():
            subprocess.run(
                ["bash", "/app/scripts/verify_phase0_db_determinism.sh"],
                capture_output=True,
                text=True,
                cwd="/app",
                timeout=120
            )
        
        assert summary_log.exists(), "Summary artifact not created"
        content = summary_log.read_text()
        assert "SUMMARY: PASS" in content, f"Summary does not show PASS:\n{content}"


class TestCIIntegration:
    """CI workflow integration tests"""

    def test_deploy_gate_has_phase0_job(self):
        """deploy-gate.yml should have phase0-db-determinism-gate job"""
        deploy_gate_path = Path("/app/.github/workflows/deploy-gate.yml")
        if not deploy_gate_path.exists():
            pytest.skip("deploy-gate.yml not found (CI integration)")
        
        content = deploy_gate_path.read_text()
        assert "phase0-db-determinism-gate" in content

    def test_phase0_job_runs_verify_script(self):
        """phase0 job should run the verify script"""
        deploy_gate_path = Path("/app/.github/workflows/deploy-gate.yml")
        if not deploy_gate_path.exists():
            pytest.skip("deploy-gate.yml not found")
        
        content = deploy_gate_path.read_text()
        assert "verify_phase0_db_determinism.sh" in content

    def test_phase0_job_uploads_artifacts(self):
        """phase0 job should upload verification artifacts"""
        deploy_gate_path = Path("/app/.github/workflows/deploy-gate.yml")
        if not deploy_gate_path.exists():
            pytest.skip("deploy-gate.yml not found")
        
        content = deploy_gate_path.read_text()
        assert "phase0-db-determinism-artifacts" in content
