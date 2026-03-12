"""user decision traces for explainability layer

Revision ID: 20260312_0027
Revises: 20260312_0026
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa

revision = "20260312_0027"
down_revision = "20260312_0026"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "user_decision_traces"):
        return

    op.create_table(
        "user_decision_traces",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("trace_scope", sa.String(length=20), nullable=False, server_default="signal"),
        sa.Column("trace_type", sa.String(length=40), nullable=False, server_default="decision"),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("strategy_code", sa.String(length=120), nullable=True),
        sa.Column("decision_status", sa.String(length=40), nullable=False, server_default="UNKNOWN"),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("reason_details", sa.JSON(), nullable=False),
        sa.Column("feature_snapshot", sa.JSON(), nullable=False),
        sa.Column("context_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_user_decision_traces_user_id", "user_decision_traces", ["user_id"])
    op.create_index("ix_user_decision_traces_scope", "user_decision_traces", ["trace_scope"])
    op.create_index("ix_user_decision_traces_entity_id", "user_decision_traces", ["entity_id"])
    op.create_index("ix_user_decision_traces_strategy", "user_decision_traces", ["strategy_code"])
    op.create_index("ix_user_decision_traces_decision", "user_decision_traces", ["decision_status"])
    op.create_index("ix_user_decision_traces_created_at", "user_decision_traces", ["created_at"])
    op.create_index("ix_user_decision_traces_expires_at", "user_decision_traces", ["expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "user_decision_traces"):
        return

    op.drop_index("ix_user_decision_traces_expires_at", table_name="user_decision_traces")
    op.drop_index("ix_user_decision_traces_created_at", table_name="user_decision_traces")
    op.drop_index("ix_user_decision_traces_decision", table_name="user_decision_traces")
    op.drop_index("ix_user_decision_traces_strategy", table_name="user_decision_traces")
    op.drop_index("ix_user_decision_traces_entity_id", table_name="user_decision_traces")
    op.drop_index("ix_user_decision_traces_scope", table_name="user_decision_traces")
    op.drop_index("ix_user_decision_traces_user_id", table_name="user_decision_traces")
    op.drop_table("user_decision_traces")
