"""FAZ-3 Closure Extended Tests
Additional static verification for FAZ-3 migration safety baseline closure criteria.
"""

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = BACKEND_ROOT / "migrations" / "versions"


def _read_migration(filename: str) -> str:
    """Read migration file content."""
    return (MIGRATIONS_DIR / filename).read_text(encoding="utf-8")


# --- Test: batch_alter_table removed from target migrations ---

class TestBatchAlterTableCleanup:
    """Verify batch_alter_table is removed from target migration files."""
    
    TARGET_FILES = [
        "20260311_0005_user_approval_flow.py",
        "20260311_0007_execution_metrics_and_permission_drift.py",
        "20260311_0008_release_gate_override_and_validation_snapshot.py",
        "20260311_0009_execution_evidence_fields.py",
        "20260311_0012_execution_context_and_replay.py",
        "20260315_0043_users_role_enum_alignment.py",
        "20260315_0044_nullable_alignment.py",
    ]
    
    def test_no_batch_alter_table_in_0005(self):
        content = _read_migration("20260311_0005_user_approval_flow.py")
        assert "with op.batch_alter_table(" not in content
        assert "recreate=" not in content
    
    def test_no_batch_alter_table_in_0007(self):
        content = _read_migration("20260311_0007_execution_metrics_and_permission_drift.py")
        assert "with op.batch_alter_table(" not in content
        assert "recreate=" not in content
    
    def test_no_batch_alter_table_in_0008(self):
        content = _read_migration("20260311_0008_release_gate_override_and_validation_snapshot.py")
        assert "with op.batch_alter_table(" not in content
        assert "recreate=" not in content
    
    def test_no_batch_alter_table_in_0009(self):
        content = _read_migration("20260311_0009_execution_evidence_fields.py")
        assert "with op.batch_alter_table(" not in content
        assert "recreate=" not in content
    
    def test_no_batch_alter_table_in_0012(self):
        content = _read_migration("20260311_0012_execution_context_and_replay.py")
        assert "with op.batch_alter_table(" not in content
        assert "recreate=" not in content
    
    def test_no_batch_alter_table_in_0043(self):
        content = _read_migration("20260315_0043_users_role_enum_alignment.py")
        assert "with op.batch_alter_table(" not in content
        assert "recreate=" not in content
    
    def test_no_batch_alter_table_in_0044(self):
        content = _read_migration("20260315_0044_nullable_alignment.py")
        assert "with op.batch_alter_table(" not in content
        # Comment is allowed, actual usage is not
        assert "recreate=" not in content


# --- Test: Migration behavior is postgres-focused and deterministic ---

class TestPostgresAndDeterministicMigrations:
    """Verify migrations 0041/0043/0044 are postgres-focused and deterministic."""
    
    def test_0041_uses_deterministic_fk_names(self):
        """Check 0041 uses short, deterministic FK names."""
        content = _read_migration("20260315_0041_non_destructive_drift_alignment.py")
        expected_fks = [
            "fk_ps_bot_profile",
            "fk_ps_exc_conn",
            "fk_ps_order_intent",
            "fk_ps_risk_policy",
        ]
        for fk in expected_fks:
            assert fk in content, f"Expected FK name {fk} not found in 0041"
            assert len(fk) <= 63, f"FK name {fk} exceeds 63 char limit"
    
    def test_0041_has_idempotent_checks(self):
        """Check 0041 has proper idempotency checks."""
        content = _read_migration("20260315_0041_non_destructive_drift_alignment.py")
        assert "_table_exists" in content
        assert "_column_exists" in content
        assert "_index_exists" in content
        assert "_fk_exists" in content
    
    def test_0043_uses_postgres_dialect_check(self):
        """Check 0043 properly checks dialect for postgres-specific code."""
        content = _read_migration("20260315_0043_users_role_enum_alignment.py")
        assert 'dialect == "postgresql"' in content
        assert "CREATE TYPE userrole" in content
    
    def test_0043_is_deterministic_with_uppercase_role(self):
        """Check 0043 normalizes role values deterministically."""
        content = _read_migration("20260315_0043_users_role_enum_alignment.py")
        assert "UPDATE users SET role = UPPER(role)" in content
        assert "UPDATE users SET role = 'USER' WHERE role IS NULL" in content
    
    def test_0044_uses_direct_alter_column(self):
        """Check 0044 uses direct op.alter_column, not batch."""
        content = _read_migration("20260315_0044_nullable_alignment.py")
        assert "op.alter_column" in content
        # Verify direct alter_column calls exist
        assert 'op.alter_column("bot_profiles", "is_running"' in content
        assert 'op.alter_column("strategy_observability_events", "created_at"' in content
        assert 'op.alter_column("users", "updated_at"' in content


# --- Test: Boolean numeric default/update risks ---

class TestBooleanSafety:
    """Verify no boolean numeric default/update risks."""
    
    def test_no_numeric_boolean_server_defaults(self):
        """Ensure no sa.text("0") or sa.text("1") patterns."""
        pattern = re.compile(r'server_default\s*=\s*sa\.text\(\s*["\'][01]["\']\s*\)')
        for path in MIGRATIONS_DIR.glob("*.py"):
            if path.name == "__init__.py":
                continue
            content = path.read_text(encoding="utf-8")
            assert not pattern.search(content), f"Numeric boolean default in {path.name}"
    
    def test_no_numeric_update_for_is_running(self):
        """Ensure UPDATE ... SET is_running = 0/1 is not used."""
        pattern = re.compile(r"SET\s+is_running\s*=\s*[01]", re.IGNORECASE)
        for path in MIGRATIONS_DIR.glob("*.py"):
            if path.name == "__init__.py":
                continue
            content = path.read_text(encoding="utf-8")
            assert not pattern.search(content), f"Numeric is_running update in {path.name}"
    
    def test_boolean_defaults_use_proper_sqlalchemy_functions(self):
        """Ensure booleans use sa.false()/sa.true() or sa.text("true"/"false")."""
        proper_patterns = [
            r"sa\.false\(\)",
            r"sa\.true\(\)",
            r'sa\.text\(["\']true["\']\)',
            r'sa\.text\(["\']false["\']\)',
            r'sa\.text\(["\']TRUE["\']\)',
            r'sa\.text\(["\']FALSE["\']\)',
        ]
        # Just verify we have some Boolean columns using proper patterns
        found_proper = False
        for path in MIGRATIONS_DIR.glob("*.py"):
            content = path.read_text(encoding="utf-8")
            for pat in proper_patterns:
                if re.search(pat, content):
                    found_proper = True
                    break
            if found_proper:
                break
        assert found_proper, "No proper Boolean defaults found in migrations"


# --- Test: Migration graph single head ---

class TestMigrationGraph:
    """Verify migration graph integrity."""
    
    def test_single_head_is_20260316_0046(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
        scripts = ScriptDirectory.from_config(config)
        
        heads = scripts.get_heads()
        assert len(heads) == 1, f"Expected single head, got {len(heads)}: {heads}"
        assert heads[0] == "20260316_0046", f"Expected head 20260316_0046, got {heads[0]}"
    
    def test_no_orphan_revisions(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
        scripts = ScriptDirectory.from_config(config)
        
        revisions = list(scripts.walk_revisions())
        all_ids = {rev.revision for rev in revisions}
        down_ids = set()
        for rev in revisions:
            if rev.down_revision is None:
                continue
            if isinstance(rev.down_revision, tuple):
                down_ids.update(item for item in rev.down_revision if item)
            else:
                down_ids.add(rev.down_revision)
        
        missing = sorted(item for item in down_ids if item not in all_ids)
        assert missing == [], f"Orphan/broken down_revisions: {missing}"


# --- Test: Critical baseline tables have creation path ---

class TestBaselineTableCreationPath:
    """Verify critical baseline tables have migration creation path."""
    
    CRITICAL_TABLES = [
        "users",
        "bot_profiles",
        "risk_policies",
        "pending_signals",
        "admin_control",
        "signal_events",
        "paper_positions",
        "audit_logs",
    ]
    
    def test_baseline_repair_migration_exists(self):
        path = MIGRATIONS_DIR / "20260316_0046_baseline_critical_tables_repair.py"
        assert path.exists(), "Baseline repair migration 0046 not found"
    
    def test_critical_tables_in_repair_migration(self):
        content = _read_migration("20260316_0046_baseline_critical_tables_repair.py")
        for table in self.CRITICAL_TABLES:
            assert f'"{table}"' in content, f"Critical table {table} not in 0046 repair migration"
    
    def test_repair_uses_checkfirst_pattern(self):
        content = _read_migration("20260316_0046_baseline_critical_tables_repair.py")
        assert "checkfirst=True" in content, "0046 should use checkfirst=True for create"


# --- Test: Manifest and script artifacts ---

class TestManifestAndScriptArtifacts:
    """Verify manifest and clean-install script exist with proper content."""
    
    def test_manifest_exists(self):
        path = BACKEND_ROOT / "docs" / "migration_safety_manifest.md"
        assert path.exists(), "Manifest not found at docs/migration_safety_manifest.md"
    
    def test_manifest_has_required_sections(self):
        content = (BACKEND_ROOT / "docs" / "migration_safety_manifest.md").read_text()
        required = [
            "Current head",
            "batch_alter_table",
            "Baseline Scope Matrix",
            "CRITICAL",
            "OPTIONAL",
            "verify_clean_install.sh",
        ]
        for section in required:
            assert section in content, f"Manifest missing section: {section}"
    
    def test_clean_install_script_exists(self):
        path = BACKEND_ROOT / "scripts" / "verify_clean_install.sh"
        assert path.exists(), "Clean install script not found"
    
    def test_clean_install_script_is_executable_syntax(self):
        """Verify script has valid bash syntax."""
        import subprocess
        path = BACKEND_ROOT / "scripts" / "verify_clean_install.sh"
        result = subprocess.run(
            ["bash", "-n", str(path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Script syntax error: {result.stderr}"
    
    def test_clean_install_script_checks_expected_head(self):
        content = (BACKEND_ROOT / "scripts" / "verify_clean_install.sh").read_text()
        assert "20260316_0046" in content, "Script should check for expected head 20260316_0046"
