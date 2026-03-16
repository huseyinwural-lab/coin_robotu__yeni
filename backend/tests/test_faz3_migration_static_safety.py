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
    path_0041 = MIGRATIONS_DIR / "20260315_0041_non_destructive_drift_alignment.py"
    path_0044 = MIGRATIONS_DIR / "20260315_0044_nullable_alignment.py"

    assert "recreate=\"always\"" not in path_0041.read_text(encoding="utf-8")
    assert "with op.batch_alter_table(" not in path_0044.read_text(encoding="utf-8")


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
