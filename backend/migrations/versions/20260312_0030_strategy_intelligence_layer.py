"""strategy intelligence layer schema

Revision ID: 20260312_0030
Revises: 20260312_0029
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa

revision = "20260312_0030"
down_revision = "20260312_0029"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "user_decision_traces"):
        if not _column_exists(bind, "user_decision_traces", "hedge_recommendation"):
            op.add_column("user_decision_traces", sa.Column("hedge_recommendation", sa.String(length=160), nullable=True))
        if not _column_exists(bind, "user_decision_traces", "risk_reduction_score"):
            op.add_column("user_decision_traces", sa.Column("risk_reduction_score", sa.Float(), nullable=True))
        if not _column_exists(bind, "user_decision_traces", "correlation_basis"):
            op.add_column("user_decision_traces", sa.Column("correlation_basis", sa.String(length=160), nullable=True))

    if not _table_exists(bind, "manual_override_log"):
        op.create_table(
            "manual_override_log",
            sa.Column("override_id", sa.String(length=120), nullable=False),
            sa.Column("admin_id", sa.String(), nullable=False),
            sa.Column("action_type", sa.String(length=80), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["admin_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("override_id"),
        )
        op.create_index("ix_manual_override_log_admin_id", "manual_override_log", ["admin_id"])
        op.create_index("ix_manual_override_log_action_type", "manual_override_log", ["action_type"])
        op.create_index("ix_manual_override_log_timestamp", "manual_override_log", ["timestamp"])


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "manual_override_log"):
        op.drop_index("ix_manual_override_log_timestamp", table_name="manual_override_log")
        op.drop_index("ix_manual_override_log_action_type", table_name="manual_override_log")
        op.drop_index("ix_manual_override_log_admin_id", table_name="manual_override_log")
        op.drop_table("manual_override_log")

    if _table_exists(bind, "user_decision_traces"):
        if _column_exists(bind, "user_decision_traces", "correlation_basis"):
            op.drop_column("user_decision_traces", "correlation_basis")
        if _column_exists(bind, "user_decision_traces", "risk_reduction_score"):
            op.drop_column("user_decision_traces", "risk_reduction_score")
        if _column_exists(bind, "user_decision_traces", "hedge_recommendation"):
            op.drop_column("user_decision_traces", "hedge_recommendation")
