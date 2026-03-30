"""add risk policy lifecycle fields

Revision ID: 20260330_2000_risk_policy_lifecycle
Revises: 20260330_1900_bot_runtime_fields
Create Date: 2026-03-30 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260330_2000_risk_policy_lifecycle"
down_revision = "20260330_1900_bot_runtime_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("risk_policies", sa.Column("version_group_id", sa.String(length=120), nullable=False, server_default="legacy-group"))
    op.add_column("risk_policies", sa.Column("version_num", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("risk_policies", sa.Column("lifecycle_state", sa.String(length=30), nullable=False, server_default="draft"))
    op.add_column("risk_policies", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("risk_policies", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("risk_policies", sa.Column("activated_by", sa.String(), nullable=True))
    op.add_column("risk_policies", sa.Column("status_reason", sa.String(length=280), nullable=True))
    op.add_column("risk_policies", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.create_index("ix_risk_policies_version_group_id", "risk_policies", ["version_group_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_risk_policies_version_group_id", table_name="risk_policies")
    op.drop_column("risk_policies", "metadata_json")
    op.drop_column("risk_policies", "status_reason")
    op.drop_column("risk_policies", "activated_by")
    op.drop_column("risk_policies", "activated_at")
    op.drop_column("risk_policies", "is_active")
    op.drop_column("risk_policies", "lifecycle_state")
    op.drop_column("risk_policies", "version_num")
    op.drop_column("risk_policies", "version_group_id")
