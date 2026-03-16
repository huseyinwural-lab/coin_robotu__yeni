"""baseline critical tables repair

Revision ID: 20260316_0046
Revises: 20260315_0045
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

revision = "20260316_0046"
down_revision = "20260315_0045"
branch_labels = None
depends_on = None

CRITICAL_TABLE_NAMES = [
    "users",
    "bot_profiles",
    "risk_policies",
    "audit_logs",
    "signal_events",
    "paper_positions",
    "admin_control",
    "pending_signals",
]


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def _fk_exists(bind, table_name: str, constrained_column: str, referred_table: str, referred_column: str = "id") -> bool:
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys(table_name):
        cols = fk.get("constrained_columns") or []
        ref_table = fk.get("referred_table")
        ref_cols = fk.get("referred_columns") or []
        if cols == [constrained_column] and ref_table == referred_table and ref_cols == [referred_column]:
            return True
    return False


def upgrade() -> None:
    from pathlib import Path
    import sys

    backend_root = Path(__file__).resolve().parents[2]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from models import AdminControl, AuditLog, BotProfile, PaperPosition, PendingSignal, RiskPolicy, SignalEvent, User

    bind = op.get_bind()
    critical_tables = {
        "users": User.__table__,
        "bot_profiles": BotProfile.__table__,
        "risk_policies": RiskPolicy.__table__,
        "audit_logs": AuditLog.__table__,
        "signal_events": SignalEvent.__table__,
        "paper_positions": PaperPosition.__table__,
        "admin_control": AdminControl.__table__,
        "pending_signals": PendingSignal.__table__,
    }

    for table_name in CRITICAL_TABLE_NAMES:
        table = critical_tables[table_name]
        if _table_exists(bind, table_name):
            continue
        table.create(bind=bind, checkfirst=True)

    # Ensure critical FK exists even when referenced table was introduced by this repair migration.
    if (
        _table_exists(bind, "pending_signals")
        and _table_exists(bind, "risk_policies")
        and _column_exists(bind, "pending_signals", "risk_policy_id")
        and not _fk_exists(bind, "pending_signals", "risk_policy_id", "risk_policies", "id")
    ):
        op.create_foreign_key(
            "fk_ps_risk_policy",
            "pending_signals",
            "risk_policies",
            ["risk_policy_id"],
            ["id"],
        )


def downgrade() -> None:
    # Repair migration intentionally non-destructive on downgrade.
    pass
