"""canonical strategy registry

Revision ID: 20260313_0037
Revises: 20260313_0036
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

revision = "20260313_0037"
down_revision = "20260313_0036"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "canonical_strategy_registry"):
        return

    op.create_table(
        "canonical_strategy_registry",
        sa.Column("strategy_id", sa.String(length=120), nullable=False),
        sa.Column("strategy_family", sa.String(length=60), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False, server_default="both"),
        sa.Column("market_regime", sa.String(length=40), nullable=False, server_default="any"),
        sa.Column("entry_logic_version", sa.String(length=40), nullable=False, server_default="v1"),
        sa.Column("exit_logic_version", sa.String(length=40), nullable=False, server_default="v1"),
        sa.Column("risk_profile", sa.String(length=40), nullable=False, server_default="balanced"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("cooldown_policy", sa.String(length=80), nullable=False, server_default="symbol:180s"),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("entry_long", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("entry_short", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("exit_long", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("exit_short", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("invalid_state_rules", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("cooldown_rules", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("risk_rules", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_legacy_candidate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("in_production_path", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_50_signal_quality", sa.Float(), nullable=False, server_default="0"),
        sa.Column("false_allow_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("false_reject_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cooldown_state", sa.String(length=20), nullable=False, server_default="ready"),
        sa.Column("risk_block_reason", sa.String(length=120), nullable=True),
        sa.Column("forced_disable_reason", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("strategy_id"),
    )
    op.create_index("ix_canonical_strategy_registry_family", "canonical_strategy_registry", ["strategy_family"])
    op.create_index("ix_canonical_strategy_registry_enabled", "canonical_strategy_registry", ["is_enabled"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "canonical_strategy_registry"):
        return

    try:
        op.drop_index("ix_canonical_strategy_registry_enabled", table_name="canonical_strategy_registry")
    except Exception:
        pass
    try:
        op.drop_index("ix_canonical_strategy_registry_family", table_name="canonical_strategy_registry")
    except Exception:
        pass
    op.drop_table("canonical_strategy_registry")
