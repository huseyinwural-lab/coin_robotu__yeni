"""non-destructive drift alignment (indexes + pending signal fks)

Revision ID: 20260315_0041
Revises: 20260313_0040
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_0041"
down_revision = "20260313_0040"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _fk_exists(bind, table_name: str, constrained_column: str, referred_table: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    for fk in inspector.get_foreign_keys(table_name):
        if fk.get("constrained_columns") == [constrained_column] and fk.get("referred_table") == referred_table:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "execution_intents") and _column_exists(bind, "execution_intents", "account_id"):
        if not _index_exists(bind, "execution_intents", "ix_execution_intents_account_id"):
            op.create_index("ix_execution_intents_account_id", "execution_intents", ["account_id"], unique=False)

    if _table_exists(bind, "user_execution_intents") and _column_exists(bind, "user_execution_intents", "intent_type"):
        if not _index_exists(bind, "user_execution_intents", "ix_user_execution_intents_intent_type"):
            op.create_index(
                "ix_user_execution_intents_intent_type",
                "user_execution_intents",
                ["intent_type"],
                unique=False,
            )

    if _table_exists(bind, "pending_signals"):
        fk_specs = [
            ("fk_ps_bot_profile", "bot_profile_id", "bot_profiles"),
            ("fk_ps_exc_conn", "exchange_connection_id", "user_exchange_connections"),
            ("fk_ps_order_intent", "created_order_intent_id", "user_execution_intents"),
            ("fk_ps_risk_policy", "risk_policy_id", "risk_policies"),
        ]

        missing_fk_specs: list[tuple[str, str, str]] = []
        for fk_name, column_name, referred_table in fk_specs:
            if not _column_exists(bind, "pending_signals", column_name):
                continue
            if not _table_exists(bind, referred_table):
                continue
            if _fk_exists(bind, "pending_signals", column_name, referred_table):
                continue
            missing_fk_specs.append((fk_name, column_name, referred_table))

        for fk_name, column_name, referred_table in missing_fk_specs:
            op.create_foreign_key(fk_name, "pending_signals", referred_table, [column_name], ["id"])


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "execution_intents") and _index_exists(bind, "execution_intents", "ix_execution_intents_account_id"):
        op.drop_index("ix_execution_intents_account_id", table_name="execution_intents")

    if _table_exists(bind, "user_execution_intents") and _index_exists(bind, "user_execution_intents", "ix_user_execution_intents_intent_type"):
        op.drop_index("ix_user_execution_intents_intent_type", table_name="user_execution_intents")

    if _table_exists(bind, "pending_signals"):
        inspector = sa.inspect(bind)
        existing_fk_names = {fk.get("name") for fk in inspector.get_foreign_keys("pending_signals") if fk.get("name")}
        removable = [
            "fk_ps_bot_profile",
            "fk_ps_exc_conn",
            "fk_ps_order_intent",
            "fk_ps_risk_policy",
            "fk_pending_signals_bot_profile_id_bot_profiles",
            "fk_pending_signals_exchange_connection_id_user_exchange_connections",
            "fk_pending_signals_created_order_intent_id_user_execution_intents",
            "fk_pending_signals_risk_policy_id_risk_policies",
        ]
        to_drop = [name for name in removable if name in existing_fk_names]
        for fk_name in to_drop:
            op.drop_constraint(fk_name, "pending_signals", type_="foreignkey")
