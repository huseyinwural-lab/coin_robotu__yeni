"""add strategy template lifecycle fields

Revision ID: 20260330_2100_strategy_template_lifecycle
Revises: 20260330_2000_risk_policy_lifecycle
Create Date: 2026-03-30 21:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260330_2100_strategy_template_lifecycle"
down_revision = "20260330_2000_risk_policy_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategy_templates", sa.Column("template_code", sa.String(length=120), nullable=False, server_default="legacy_template"))
    op.add_column("strategy_templates", sa.Column("version_group_id", sa.String(length=120), nullable=False, server_default="legacy_group"))
    op.add_column("strategy_templates", sa.Column("version_num", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("strategy_templates", sa.Column("lifecycle_state", sa.String(length=30), nullable=False, server_default="DRAFT"))
    op.add_column("strategy_templates", sa.Column("parent_template_id", sa.String(length=120), nullable=True))
    op.add_column("strategy_templates", sa.Column("rollback_from_template_id", sa.String(length=120), nullable=True))
    op.add_column("strategy_templates", sa.Column("param_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("strategy_templates", sa.Column("logic_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("strategy_templates", sa.Column("indicator_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("strategy_templates", sa.Column("backtest_result_ref", sa.String(length=120), nullable=True))
    op.add_column("strategy_templates", sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_strategy_templates_template_code", "strategy_templates", ["template_code"], unique=False)
    op.create_index("ix_strategy_templates_version_group_id", "strategy_templates", ["version_group_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_strategy_templates_version_group_id", table_name="strategy_templates")
    op.drop_index("ix_strategy_templates_template_code", table_name="strategy_templates")
    op.drop_column("strategy_templates", "last_validated_at")
    op.drop_column("strategy_templates", "backtest_result_ref")
    op.drop_column("strategy_templates", "indicator_schema")
    op.drop_column("strategy_templates", "logic_schema")
    op.drop_column("strategy_templates", "param_schema")
    op.drop_column("strategy_templates", "rollback_from_template_id")
    op.drop_column("strategy_templates", "parent_template_id")
    op.drop_column("strategy_templates", "lifecycle_state")
    op.drop_column("strategy_templates", "version_num")
    op.drop_column("strategy_templates", "version_group_id")
    op.drop_column("strategy_templates", "template_code")
