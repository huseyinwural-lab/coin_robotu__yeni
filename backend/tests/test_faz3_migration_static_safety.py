import re
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = BACKEND_ROOT / "migrations" / "versions"


def _migration_files() -> list[Path]:
    return sorted(path for path in MIGRATIONS_DIR.glob("*.py") if path.name != "__init__.py")


def test_boolean_defaults_have_no_numeric_text_literals():
    pattern = re.compile(r"server_default\s*=\s*sa\.text\(\s*\"[01]\"\s*\)")
    offenders: list[str] = []
    for file_path in _migration_files():
        content = file_path.read_text(encoding="utf-8")
        if pattern.search(content):
            offenders.append(file_path.name)
    assert offenders == []


def test_boolean_update_sql_has_no_numeric_assignment():
    pattern = re.compile(r"SET\s+is_running\s*=\s*[01]", re.IGNORECASE)
    offenders: list[str] = []
    for file_path in _migration_files():
        content = file_path.read_text(encoding="utf-8")
        if pattern.search(content):
            offenders.append(file_path.name)
    assert offenders == []


def test_0010_alert_policy_seed_uses_boolean_literals():
    path = MIGRATIONS_DIR / "20260311_0010_user_risk_and_alert_policy.py"
    content = path.read_text(encoding="utf-8")
    assert "'global', TRUE, '', TRUE" in content
    assert "'global', 1, '', 1" not in content


def test_fk_names_in_0041_are_short_and_deterministic():
    path = MIGRATIONS_DIR / "20260315_0041_non_destructive_drift_alignment.py"
    content = path.read_text(encoding="utf-8")
    assert "fk_ps_bot_profile" in content
    assert "fk_ps_exc_conn" in content
    assert "fk_ps_order_intent" in content
    assert "fk_ps_risk_policy" in content

    fk_names = ["fk_ps_bot_profile", "fk_ps_exc_conn", "fk_ps_order_intent", "fk_ps_risk_policy"]
    assert all(len(name) <= 63 for name in fk_names)


def test_batch_alter_removed_from_target_migrations():
    target_files = [
        "20260311_0005_user_approval_flow.py",
        "20260311_0007_execution_metrics_and_permission_drift.py",
        "20260311_0008_release_gate_override_and_validation_snapshot.py",
        "20260311_0009_execution_evidence_fields.py",
        "20260311_0012_execution_context_and_replay.py",
        "20260315_0041_non_destructive_drift_alignment.py",
        "20260315_0043_users_role_enum_alignment.py",
        "20260315_0044_nullable_alignment.py",
    ]
    for file_name in target_files:
        content = (MIGRATIONS_DIR / file_name).read_text(encoding="utf-8")
        assert "with op.batch_alter_table(" not in content
        assert "recreate=\"always\"" not in content


def test_migration_graph_single_head_and_no_orphans():
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)

    heads = scripts.get_heads()
    assert len(heads) == 1

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

    missing_down = sorted(item for item in down_ids if item not in all_ids)
    assert missing_down == []


def test_baseline_critical_tables_have_migration_creation_path():
    create_tables = set()
    create_pattern = re.compile(r"op\.create_table\(\s*\"([^\"]+)\"")
    for file_path in _migration_files():
        content = file_path.read_text(encoding="utf-8")
        create_tables.update(create_pattern.findall(content))

    critical = {
        "users",
        "bot_profiles",
        "risk_policies",
        "pending_signals",
        "admin_control",
        "signal_events",
        "paper_positions",
        "audit_logs",
    }

    covered = set(create_tables)
    repair_path = MIGRATIONS_DIR / "20260316_0046_baseline_critical_tables_repair.py"
    content = repair_path.read_text(encoding="utf-8")

    model_name_map = {
        "users": "User.__table__",
        "bot_profiles": "BotProfile.__table__",
        "risk_policies": "RiskPolicy.__table__",
        "pending_signals": "PendingSignal.__table__",
        "admin_control": "AdminControl.__table__",
        "signal_events": "SignalEvent.__table__",
        "paper_positions": "PaperPosition.__table__",
        "audit_logs": "AuditLog.__table__",
    }

    for table_name in critical:
        if (
            f'"{table_name}"' in content
            or f"'{table_name}'" in content
            or model_name_map[table_name] in content
        ):
            covered.add(table_name)

    missing = sorted(critical - covered)
    assert missing == []


def test_manifest_and_clean_install_script_exist():
    manifest_path = BACKEND_ROOT / "docs" / "migration_safety_manifest.md"
    script_path = BACKEND_ROOT / "scripts" / "verify_clean_install.sh"

    assert manifest_path.exists()
    assert script_path.exists()

    manifest = manifest_path.read_text(encoding="utf-8")
    assert "Current head" in manifest
    assert "CRITICAL" in manifest
    assert "OPTIONAL" in manifest
    assert "verify_clean_install.sh" in manifest


def test_0046_repair_contains_risk_policy_fk_repair_logic():
    path = MIGRATIONS_DIR / "20260316_0046_baseline_critical_tables_repair.py"
    content = path.read_text(encoding="utf-8")
    assert "op.create_foreign_key(" in content
    assert '"pending_signals"' in content
    assert '"risk_policies"' in content
    assert '"risk_policy_id"' in content


def test_0043_role_enum_alignment_handles_default_cast_safely():
    path = MIGRATIONS_DIR / "20260315_0043_users_role_enum_alignment.py"
    content = path.read_text(encoding="utf-8")
    assert "ALTER TABLE users ALTER COLUMN role DROP DEFAULT" in content
    assert "ELSE 'USER'::userrole" in content
    assert "SET DEFAULT 'USER'::userrole" in content
