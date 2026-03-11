"""execution state transition table

Revision ID: 20260311_0002
Revises: 20260311_0001
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0002"
down_revision = "20260311_0001"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "execution_state_transitions"):
        op.create_table(
            "execution_state_transitions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("execution_event_id", sa.String(), nullable=False),
            sa.Column("state", sa.String(length=30), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["execution_event_id"], ["execution_events.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_execution_state_transitions_execution_event_id", "execution_state_transitions", ["execution_event_id"])
        op.create_index("ix_execution_state_transitions_state", "execution_state_transitions", ["state"])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "execution_state_transitions"):
        op.drop_index("ix_execution_state_transitions_state", table_name="execution_state_transitions")
        op.drop_index("ix_execution_state_transitions_execution_event_id", table_name="execution_state_transitions")
        op.drop_table("execution_state_transitions")