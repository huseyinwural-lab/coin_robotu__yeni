"""execution environment overrides and safe mode

Revision ID: 20260327_0093
Revises: 20260327_0092
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260327_0093"
down_revision = "20260327_0092"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "execution_environment_overrides"):
        op.create_table(
            "execution_environment_overrides",
            sa.Column("override_id", sa.String(length=120), primary_key=True),
            sa.Column("environment", sa.String(length=20), nullable=False),
            sa.Column("scope_type", sa.String(length=20), nullable=False, server_default="GLOBAL"),
            sa.Column("scope_value", sa.String(length=120), nullable=False, server_default="*"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("override_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("change_summary", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_execution_environment_overrides_environment", "execution_environment_overrides", ["environment"], unique=False)
        op.create_index("ix_execution_environment_overrides_scope_type", "execution_environment_overrides", ["scope_type"], unique=False)
        op.create_index("ix_execution_environment_overrides_scope_value", "execution_environment_overrides", ["scope_value"], unique=False)
        op.create_index("ix_execution_environment_overrides_priority", "execution_environment_overrides", ["priority"], unique=False)
        op.create_index("ix_execution_environment_overrides_is_active", "execution_environment_overrides", ["is_active"], unique=False)

    if not _has_table(bind, "execution_safe_mode_states"):
        op.create_table(
            "execution_safe_mode_states",
            sa.Column("safe_mode_id", sa.String(length=120), primary_key=True),
            sa.Column("environment", sa.String(length=20), nullable=False),
            sa.Column("scope_type", sa.String(length=20), nullable=False, server_default="GLOBAL"),
            sa.Column("scope_value", sa.String(length=120), nullable=False, server_default="*"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("trigger_reason", sa.String(length=160), nullable=False),
            sa.Column("trigger_source", sa.String(length=80), nullable=False, server_default="AUTO"),
            sa.Column("activated_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("deactivated_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("override_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_execution_safe_mode_states_environment", "execution_safe_mode_states", ["environment"], unique=False)
        op.create_index("ix_execution_safe_mode_states_scope_type", "execution_safe_mode_states", ["scope_type"], unique=False)
        op.create_index("ix_execution_safe_mode_states_scope_value", "execution_safe_mode_states", ["scope_value"], unique=False)
        op.create_index("ix_execution_safe_mode_states_is_active", "execution_safe_mode_states", ["is_active"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "execution_safe_mode_states"):
        op.drop_table("execution_safe_mode_states")
    if _has_table(bind, "execution_environment_overrides"):
        op.drop_table("execution_environment_overrides")
