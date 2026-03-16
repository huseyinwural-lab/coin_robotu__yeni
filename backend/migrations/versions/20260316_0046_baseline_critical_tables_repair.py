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


def downgrade() -> None:
    # Repair migration intentionally non-destructive on downgrade.
    pass
