"""phase4 exchange settings and testnet execution logs

Revision ID: 20260311_0006
Revises: 20260311_0005
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0006"
down_revision = "20260311_0005"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "user_exchange_settings"):
        op.create_table(
            "user_exchange_settings",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("exchange", sa.String(length=30), nullable=False),
            sa.Column("mode", sa.String(length=20), nullable=False),
            sa.Column("api_key_encrypted", sa.Text(), nullable=False),
            sa.Column("api_secret_encrypted", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
        op.create_index("ix_user_exchange_settings_user_id", "user_exchange_settings", ["user_id"], unique=True)

    if not _table_exists(bind, "testnet_execution_logs"):
        op.create_table(
            "testnet_execution_logs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("strategy_direction", sa.String(length=10), nullable=False),
            sa.Column("expected_price", sa.Float(), nullable=False),
            sa.Column("fill_price", sa.Float(), nullable=True),
            sa.Column("slippage", sa.Float(), nullable=True),
            sa.Column("execution_latency", sa.Float(), nullable=True),
            sa.Column("execution_quality_score", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("state_machine_path", sa.JSON(), nullable=False),
            sa.Column("permission_snapshot", sa.JSON(), nullable=False),
            sa.Column("release_gate_status", sa.String(length=20), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_testnet_execution_logs_user_id", "testnet_execution_logs", ["user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "testnet_execution_logs"):
        op.drop_index("ix_testnet_execution_logs_user_id", table_name="testnet_execution_logs")
        op.drop_table("testnet_execution_logs")

    if _table_exists(bind, "user_exchange_settings"):
        op.drop_index("ix_user_exchange_settings_user_id", table_name="user_exchange_settings")
        op.drop_table("user_exchange_settings")